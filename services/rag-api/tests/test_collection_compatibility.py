import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.embeddings import MockEmbeddingProvider
from app.vector_store import QdrantVectorStore, VectorStoreChunk


@pytest.fixture
def store():
    client = QdrantClient(":memory:")
    yield QdrantVectorStore("", "unit", client, MockEmbeddingProvider.identity)
    client.close()


@pytest.mark.parametrize("change", [{"revision": "different"}, {"model": "different"}])
def test_initialization_idempotence_and_identity(store, change):
    store.ensure_collection(8)
    store.add_chunks([VectorStoreChunk("hello", [0.1] * 8, {"document_id": "doc"})])
    store.ensure_collection(8)
    assert store.get_stats().total_chunks == 1
    store.embedding_identity = {**store.embedding_identity, **change}
    with pytest.raises(ValueError, match="identity/revision mismatch"):
        store.ensure_collection(8)
    assert store.get_stats().total_chunks == 1


@pytest.mark.parametrize(
    "size,distance,message",
    [
        (3, Distance.COSINE, "dimension"),
        (8, Distance.DOT, "cosine"),
    ],
)
def test_incompatible_collection(store, size, distance, message):
    store.client.create_collection(
        "unit", vectors_config=VectorParams(size=size, distance=distance)
    )
    with pytest.raises(ValueError, match=message):
        store.ensure_collection(8)


def test_legacy_untracked_collection_fails_closed(store):
    store.client.create_collection(
        "unit", vectors_config=VectorParams(size=8, distance=Distance.COSINE)
    )
    with pytest.raises(ValueError, match="Missing embedding model identity"):
        store.ensure_collection(8)


def test_invalid_write_batch_not_inserted(store):
    store.ensure_collection(8)
    with pytest.raises(ValueError):
        store.add_chunks(
            [
                VectorStoreChunk("valid", [0.0] * 8, {}),
                VectorStoreChunk("bad", [float("nan")] * 8, {}),
            ]
        )
    assert store.get_stats().total_chunks == 0


def test_identity_required():
    client = QdrantClient(":memory:")
    try:
        with pytest.raises(ValueError, match="Explicit embedding model identity"):
            QdrantVectorStore("", "untracked", client).ensure_collection(8)
        assert not client.collection_exists("untracked")
    finally:
        client.close()
