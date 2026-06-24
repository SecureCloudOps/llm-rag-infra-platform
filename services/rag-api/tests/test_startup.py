from dataclasses import dataclass

from fastapi.testclient import TestClient

from app import main


@dataclass(frozen=True)
class FakeSettings:
    qdrant_url: str = "http://qdrant:6333"
    collection_name: str = "documents"


class FakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        return [0.0, 0.1, 0.2]


class FakeQdrantVectorStore:
    instances: list["FakeQdrantVectorStore"] = []

    def __init__(self, url: str, collection_name: str) -> None:
        self.url = url
        self.collection_name = collection_name
        self.ensure_collection_calls: list[int] = []
        self.instances.append(self)

    def ensure_collection(self, vector_size: int) -> None:
        self.ensure_collection_calls.append(vector_size)


def test_startup_initializes_qdrant_collection(monkeypatch) -> None:
    FakeQdrantVectorStore.instances.clear()
    monkeypatch.setattr(main, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(main, "get_embedding_provider", lambda: FakeEmbeddingProvider())
    monkeypatch.setattr(main, "QdrantVectorStore", FakeQdrantVectorStore)

    with TestClient(main.app):
        pass

    vector_store = FakeQdrantVectorStore.instances[0]
    assert vector_store.url == "http://qdrant:6333"
    assert vector_store.collection_name == "documents"
    assert vector_store.ensure_collection_calls == [3]
    assert main.app.state.vector_store is vector_store
