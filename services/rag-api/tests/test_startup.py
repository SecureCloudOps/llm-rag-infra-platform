from fastapi.testclient import TestClient

from app import main
from app.embeddings import MockEmbeddingProvider


class FakeStore:
    def ensure_collection(self, vector_size):
        self.vector_size = vector_size


def test_startup_initializes_once_and_readiness():
    store = FakeStore()
    provider = MockEmbeddingProvider()
    calls = []

    def factory():
        calls.append(1)
        return provider

    main.app.dependency_overrides[main.get_embedding_provider] = factory
    main.app.dependency_overrides[main.get_vector_store] = lambda: store
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 200
        assert main.app.state.embedding_provider is provider
        assert store.vector_size == 8
        assert len(calls) == 1
    assert not main.app.state.ready


def test_startup_supports_original_embed_only_override():
    class OriginalProvider:
        def embed(self, text):
            return [0.1, 0.2, 0.3]

    store = FakeStore()
    main.app.dependency_overrides[main.get_embedding_provider] = OriginalProvider
    main.app.dependency_overrides[main.get_vector_store] = lambda: store
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 200
        assert store.vector_size == 3
