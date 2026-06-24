from types import SimpleNamespace

from app.vector_store import QdrantVectorStore, VectorSearchResult, VectorStoreStats


class FakeQdrantClient:
    def __init__(self, collection_exists: bool = True) -> None:
        self.collection_exists_result = collection_exists
        self.created_collections: list[dict[str, object]] = []
        self.count_result = SimpleNamespace(count=0)
        self.scroll_pages: list[tuple[list[SimpleNamespace], object | None]] = []
        self.query_points_result: list[SimpleNamespace] = []

    def collection_exists(self, collection_name: str) -> bool:
        self.collection_exists_name = collection_name
        return self.collection_exists_result

    def create_collection(self, collection_name: str, vectors_config: object) -> None:
        self.created_collections.append(
            {"collection_name": collection_name, "vectors_config": vectors_config}
        )

    def count(self, collection_name: str, exact: bool) -> SimpleNamespace:
        self.count_args = {"collection_name": collection_name, "exact": exact}
        return self.count_result

    def scroll(
        self,
        collection_name: str,
        limit: int,
        offset: object | None,
        with_payload: bool,
        with_vectors: bool,
    ) -> tuple[list[SimpleNamespace], object | None]:
        self.scroll_args = {
            "collection_name": collection_name,
            "limit": limit,
            "offset": offset,
            "with_payload": with_payload,
            "with_vectors": with_vectors,
        }
        return self.scroll_pages.pop(0)

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        limit: int,
        with_payload: bool,
    ) -> SimpleNamespace:
        self.query_points_args = {
            "collection_name": collection_name,
            "query": query,
            "limit": limit,
            "with_payload": with_payload,
        }
        return SimpleNamespace(points=self.query_points_result)


def test_qdrant_ensure_collection_skips_existing_collection() -> None:
    client = FakeQdrantClient(collection_exists=True)
    store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="documents",
        client=client,
    )

    store.ensure_collection(vector_size=8)

    assert client.collection_exists_name == "documents"
    assert client.created_collections == []


def test_qdrant_stats_counts_documents_and_chunks() -> None:
    client = FakeQdrantClient()
    client.count_result = SimpleNamespace(count=3)
    client.scroll_pages = [
        (
            [
                SimpleNamespace(payload={"document_id": "doc-1"}),
                SimpleNamespace(payload={"document_id": "doc-1"}),
                SimpleNamespace(payload={"document_id": "doc-2"}),
            ],
            None,
        )
    ]
    store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="documents",
        client=client,
    )

    stats = store.get_stats()

    assert stats == VectorStoreStats(total_documents=2, total_chunks=3)
    assert client.count_args == {"collection_name": "documents", "exact": True}
    assert client.scroll_args == {
        "collection_name": "documents",
        "limit": 256,
        "offset": None,
        "with_payload": True,
        "with_vectors": False,
    }


def test_qdrant_search_returns_chunk_results() -> None:
    client = FakeQdrantClient()
    client.query_points_result = [
        SimpleNamespace(
            payload={
                "chunk_text": "matching chunk",
                "filename": "notes.txt",
                "chunk_index": 2,
            },
            score=0.92,
        )
    ]
    store = QdrantVectorStore(
        url="http://qdrant:6333",
        collection_name="documents",
        client=client,
    )

    results = store.search(query_embedding=[0.1, 0.2], top_k=4)

    assert results == [
        VectorSearchResult(
            chunk_text="matching chunk",
            filename="notes.txt",
            chunk_index=2,
            score=0.92,
        )
    ]
    assert client.query_points_args == {
        "collection_name": "documents",
        "query": [0.1, 0.2],
        "limit": 4,
        "with_payload": True,
    }
