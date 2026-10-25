"""Real server compatibility tests independent of model download availability."""

import os
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.embeddings import MockEmbeddingProvider
from app.vector_store import QdrantVectorStore, VectorStoreChunk

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_QDRANT_INTEGRATION") != "1",
        reason="set RUN_QDRANT_INTEGRATION=1 for real Qdrant",
    ),
]


def test_real_qdrant_compatibility_and_restart():
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    name = "integration-compatibility-" + uuid4().hex
    store = QdrantVectorStore(url, name, embedding_identity=MockEmbeddingProvider.identity)
    store.ensure_collection(8)
    store.add_chunks(
        [VectorStoreChunk("test", [1.0] * 8, {"document_id": "test-doc", "chunk_text": "test"})]
    )
    store.client.close()
    store = QdrantVectorStore(url, name, embedding_identity=MockEmbeddingProvider.identity)
    store.ensure_collection(8)
    assert store.get_stats().total_chunks == 1
    assert store.search([1.0] * 8, 1)[0].document_id == "test-doc"
    with pytest.raises(ValueError, match="dimension"):
        store.ensure_collection(384)
    store.embedding_identity = {**MockEmbeddingProvider.identity, "model": "other"}
    with pytest.raises(ValueError, match="identity/revision"):
        store.ensure_collection(8)
    client = QdrantClient(url=url)
    dot_name = name + "-dot"
    client.create_collection(dot_name, vectors_config=VectorParams(size=8, distance=Distance.DOT))
    dot = QdrantVectorStore(url, dot_name, embedding_identity=MockEmbeddingProvider.identity)
    with pytest.raises(ValueError, match="cosine"):
        dot.ensure_collection(8)
    assert store.get_stats().total_chunks == 1
    dot.client.close()
    client.close()
    store.client.close()
