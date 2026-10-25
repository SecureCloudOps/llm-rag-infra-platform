"""Opt-in: RUN_SEMANTIC_INTEGRATION=1 pytest -m integration -v."""

import os
import subprocess
import sys
from uuid import uuid4

import pytest
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
    texts = {
        "database.txt": "Place databases in private subnets without public IP addresses. Restrict access to the application security group.",
        "billing.txt": "Use cost allocation tags and review monthly cloud spending budgets.",
        "backup.txt": "Schedule encrypted backups and regularly test restoring data from separate regions.",
    }
    with TestClient(main.app) as client:
        provider = main.app.state.embedding_provider
        assert provider.identity["provider"] == "sentence_transformers"
        assert len(provider.embed("startup model test")) == 384
        assert provider.embed("same input") == provider.embed("same input")
        for filename, text in texts.items():
            assert (
                client.post("/documents/upload", files={"file": (filename, text)}).status_code
                == 200
            )
        assert client.get("/ready").status_code == 200
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
