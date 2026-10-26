"""Opt-in: RUN_SEMANTIC_INTEGRATION=1 pytest -m integration -v."""

import os
import subprocess
import sys
from uuid import uuid4

import numpy as np
import pytest
from conftest import override_test_auth
from fastapi.testclient import TestClient

from app import main
from app.embeddings import MockEmbeddingProvider
from app.vector_store import QdrantVectorStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_SEMANTIC_INTEGRATION") != "1",
        reason="set RUN_SEMANTIC_INTEGRATION=1; requires real model and Qdrant",
    ),
]


def test_real_ingestion_retrieval_ask_restart_cache_and_isolation(monkeypatch):
    name = "integration-semantic-" + uuid4().hex
    monkeypatch.setenv("COLLECTION_NAME", name)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "384")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    main.app.dependency_overrides.clear()
    override_test_auth()
    texts = {
        "database.txt": "Place databases in private subnets without public IP addresses. Restrict access to the application security group.",
        "billing.txt": "Use cost allocation tags and review monthly cloud spending budgets.",
        "backup.txt": "Schedule encrypted backups and regularly test restoring data from separate regions.",
    }
    with TestClient(main.app) as client:
        provider = main.app.state.embedding_provider
        assert provider.identity["provider"] == "sentence_transformers"
        assert str(provider._model.device) == "cpu"
        assert len(provider.embed("startup model test")) == 384
        assert provider.embed("same input") == provider.embed("same input")
        for filename, text in texts.items():
            assert (
                client.post("/documents/upload", files={"file": (filename, text)}).status_code
                == 200
            )
        assert client.get("/ready").status_code == 200
        store = main.app.state.vector_store
        params = store.client.get_collection(name).config.params.vectors
        assert params.size == 384
        assert params.distance.value == "Cosine"
        points, _ = store.client.scroll(name, with_vectors=True, with_payload=True)
        assert len(points) == len(texts)
        for point in points:
            # Check the API persisted the genuine encoder's output, rather than
            # relying only on its configured provider name or vector dimension.
            expected = provider.embed(point.payload["chunk_text"])
            np.testing.assert_allclose(point.vector, expected, atol=1e-6, rtol=1e-5)
        stats = client.get("/documents").json()
        result = client.post(
            "/search", json={"query": "How do I keep my data store off the public internet?"}
        ).json()
        assert result["results"][0]["filename"] == "database.txt"
        result = client.post(
            "/ask", json={"question": "How do I keep my data store off the public internet?"}
        ).json()
        assert result["sources"][0]["filename"] == "database.txt"
        assert result["retrieved_chunks"] == 3
        assert result["answer"]
        assert main.app.state.embedding_provider is provider
    # Offline restart proves cached artifacts suffice, rather than successful re-download.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from fastapi.testclient import TestClient\n"
                "from app.main import app\n"
                "from app.security import Principal, get_current_principal, get_token_verifier\n"
                "app.dependency_overrides[get_current_principal] = lambda: Principal('test-tenant', 'test-user', frozenset({'tenant_admin'}))\n"
                "app.dependency_overrides[get_token_verifier] = lambda: object()\n"
                "with TestClient(app) as client:\n"
                "    assert client.get('/ready').status_code == 200\n"
                "    assert client.get('/documents').json() == {'total_documents': 3, 'total_chunks': 3}\n"
                "    assert len(app.state.embedding_provider.embed('offline restart')) == 384\n"
            ),
        ],
        env=os.environ.copy(),
        check=True,
        timeout=120,
    )
    with TestClient(main.app) as client:
        assert main.app.state.embedding_provider is not provider
        assert client.get("/documents").json() == stats
        assert (
            client.post("/search", json={"query": "How can I recover lost data?"}).json()[
                "results"
            ][0]["filename"]
            == "backup.txt"
        )
    mock = QdrantVectorStore(
        os.getenv("QDRANT_URL", "http://localhost:6333"),
        name + "-mock",
        embedding_identity=MockEmbeddingProvider.identity,
    )
    mock.ensure_collection(8)
    assert mock.get_stats().total_chunks == 0
    incompatible = QdrantVectorStore(
        os.getenv("QDRANT_URL", "http://localhost:6333"),
        name,
        embedding_identity=MockEmbeddingProvider.identity,
    )
    with pytest.raises(ValueError, match="dimension"):
        incompatible.ensure_collection(8)
    mock.client.close()
    incompatible.client.close()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "8")
    with pytest.raises(ValueError, match="dimension"):
        with TestClient(main.app):
            pass
