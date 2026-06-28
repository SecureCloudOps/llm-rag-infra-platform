from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.llm_provider import MockLLMProvider
from app.main import app, get_embedding_provider, get_llm_provider, get_vector_store
from app.vector_store import VectorSearchResult


client = TestClient(app)


class MetricsEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        del text
        return [0.1, 0.2, 0.3]


class MetricsVectorStore:
    def search(self, query_embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        del query_embedding, top_k
        return [
            VectorSearchResult(
                chunk_text="vLLM serves OpenAI-compatible inference.",
                filename="vllm.txt",
                chunk_index=0,
                score=0.95,
            )
        ]


class MetricsLLMProvider(MockLLMProvider):
    def generate_answer(
        self,
        question: str,
        retrieved_context: Sequence[VectorSearchResult],
        prompt: str,
    ) -> str:
        del question, retrieved_context, prompt
        return "instrumented answer"


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "rag_api_http_requests_total" in response.text


def test_ask_records_retrieval_and_llm_metrics() -> None:
    app.dependency_overrides[get_embedding_provider] = MetricsEmbeddingProvider
    app.dependency_overrides[get_vector_store] = MetricsVectorStore
    app.dependency_overrides[get_llm_provider] = MetricsLLMProvider

    try:
        ask_response = client.post("/ask", json={"question": "What serves inference?"})
        metrics_response = client.get("/metrics")
    finally:
        app.dependency_overrides.clear()

    assert ask_response.status_code == 200
    assert ask_response.json()["retrieved_chunks"] == 1
    assert 'rag_api_qdrant_retrieval_latency_seconds_count{endpoint="/ask"}' in (
        metrics_response.text
    )
    assert (
        'rag_api_llm_provider_latency_seconds_count{model_name="mock-local",provider="mock"}'
        in metrics_response.text
    )
    assert 'rag_api_retrieved_chunk_count_count{endpoint="/ask"}' in metrics_response.text
