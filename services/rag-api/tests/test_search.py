from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.main import app, get_embedding_provider, get_vector_store
from app.vector_store import VectorSearchResult


client = TestClient(app)


def test_search_embeds_query_and_returns_ranked_chunks() -> None:
    embedding_provider = Mock()
    embedding_provider.embed.return_value = [0.1, 0.2, 0.3]
    vector_store = Mock()
    vector_store.search.return_value = [
        VectorSearchResult(
            chunk_text="first matching chunk",
            filename="notes.txt",
            chunk_index=0,
            score=0.98,
        ),
        VectorSearchResult(
            chunk_text="second matching chunk",
            filename="guide.txt",
            chunk_index=3,
            score=0.87,
        ),
    ]
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    try:
        response = client.post("/search", json={"query": "what is rag?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "query": "what is rag?",
        "results": [
            {
                "chunk_text": "first matching chunk",
                "filename": "notes.txt",
                "chunk_index": 0,
                "score": 0.98,
            },
            {
                "chunk_text": "second matching chunk",
                "filename": "guide.txt",
                "chunk_index": 3,
                "score": 0.87,
            },
        ],
    }
    embedding_provider.embed.assert_called_once_with("what is rag?")
    vector_store.search.assert_called_once_with(
        query_embedding=[0.1, 0.2, 0.3],
        top_k=3,
    )


def test_search_uses_requested_top_k() -> None:
    embedding_provider = Mock()
    embedding_provider.embed.return_value = [0.4, 0.5]
    vector_store = Mock()
    vector_store.search.return_value = []
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    try:
        response = client.post("/search", json={"query": "install steps", "top_k": 5})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"query": "install steps", "results": []}
    vector_store.search.assert_called_once_with(
        query_embedding=[0.4, 0.5],
        top_k=5,
    )


def test_search_rejects_invalid_top_k() -> None:
    app.dependency_overrides[get_vector_store] = Mock()

    try:
        response = client.post("/search", json={"query": "invalid", "top_k": 0})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
