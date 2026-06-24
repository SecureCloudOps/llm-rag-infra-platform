from fastapi.testclient import TestClient

from app.document_service import process_text_upload
from app.main import app, get_vector_store
from app.vector_store import VectorStoreChunk, VectorStoreStats


client = TestClient(app)


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: list[VectorStoreChunk] = []
        self.stats = VectorStoreStats(total_documents=0, total_chunks=0)

    def ensure_collection(self, vector_size: int) -> None:
        self.vector_size = vector_size

    def add_chunks(self, chunks: list[VectorStoreChunk]) -> None:
        self.chunks.extend(chunks)

    def get_stats(self) -> VectorStoreStats:
        return self.stats


class CountingEmbeddingProvider:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return [float(len(text))]


def test_upload_text_document_returns_chunk_metadata() -> None:
    content = ("a" * 500) + ("b" * 500) + ("c" * 25)
    vector_store = FakeVectorStore()
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    try:
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.txt", content, "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "filename": "notes.txt",
        "total_chunks": 3,
        "chunk_sizes": [500, 500, 25],
        "embedding_count": 3,
    }
    assert [chunk.metadata["filename"] for chunk in vector_store.chunks] == [
        "notes.txt",
        "notes.txt",
        "notes.txt",
    ]
    assert [chunk.metadata["chunk_index"] for chunk in vector_store.chunks] == [0, 1, 2]
    assert [chunk.metadata["chunk_text"] for chunk in vector_store.chunks] == [
        "a" * 500,
        "b" * 500,
        "c" * 25,
    ]


def test_upload_text_document_generates_embeddings() -> None:
    provider = CountingEmbeddingProvider()
    vector_store = FakeVectorStore()

    result = process_text_upload(
        "notes.txt",
        (("a" * 500) + ("b" * 25)).encode("utf-8"),
        embedding_provider=provider,
        vector_store=vector_store,
    )

    assert provider.texts == ["a" * 500, "b" * 25]
    assert result.embedding_count == 2
    assert [chunk.embedding for chunk in vector_store.chunks] == [[500.0], [25.0]]
    assert len({chunk.metadata["document_id"] for chunk in vector_store.chunks}) == 1


def test_upload_rejects_non_text_file_extension() -> None:
    app.dependency_overrides[get_vector_store] = lambda: FakeVectorStore()

    try:
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.pdf", b"%PDF-1.7", "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    assert response.json() == {"detail": "Only .txt files are supported"}


def test_get_documents_returns_vector_store_stats() -> None:
    vector_store = FakeVectorStore()
    vector_store.stats = VectorStoreStats(total_documents=2, total_chunks=5)
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    try:
        response = client.get("/documents")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"total_documents": 2, "total_chunks": 5}
