from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.llm_provider import MockLLMProvider, build_rag_prompt
from app.main import app, get_embedding_provider, get_llm_provider, get_vector_store
from app.vector_store import VectorSearchResult


client = TestClient(app)


class SpyEmbeddingProvider:
    def __init__(self) -> None:
        self.embedded_texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.embedded_texts.append(text)
        return [0.7, 0.8, 0.9]


class SpyVectorStore:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.results = [
            VectorSearchResult(
                chunk_text="vLLM serves optimized large language model inference.",
                filename="vllm.txt",
                chunk_index=0,
                score=0.97,
            ),
            VectorSearchResult(
                chunk_text="It can run OpenAI-compatible model serving APIs.",
                filename="serving.txt",
                chunk_index=2,
                score=0.91,
            ),
            VectorSearchResult(
                chunk_text="Batching requests improves throughput for generation workloads.",
                filename="performance.txt",
                chunk_index=4,
                score=0.82,
            ),
        ]

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        self.search_calls.append({"query_embedding": query_embedding, "top_k": top_k})
        return self.results


class SpyLLMProvider:
    def __init__(self) -> None:
        self.question = ""
        self.retrieved_context: Sequence[VectorSearchResult] = []
        self.prompt = ""

    def generate_answer(
        self,
        question: str,
        retrieved_context: Sequence[VectorSearchResult],
        prompt: str,
    ) -> str:
        self.question = question
        self.retrieved_context = retrieved_context
        self.prompt = prompt
        return "mocked ask answer"


def test_ask_endpoint_returns_answer_sources_and_retrieved_count() -> None:
    embedding_provider = SpyEmbeddingProvider()
    vector_store = SpyVectorStore()
    llm_provider = SpyLLMProvider()
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_llm_provider] = lambda: llm_provider

    try:
        response = client.post("/ask", json={"question": "What is vLLM used for?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "question": "What is vLLM used for?",
        "answer": "mocked ask answer",
        "sources": [
            {"filename": "vllm.txt", "chunk_index": 0, "score": 0.97},
            {"filename": "serving.txt", "chunk_index": 2, "score": 0.91},
            {"filename": "performance.txt", "chunk_index": 4, "score": 0.82},
        ],
        "retrieved_chunks": 3,
    }

    assert embedding_provider.embedded_texts == ["What is vLLM used for?"]
    assert vector_store.search_calls == [
        {"query_embedding": [0.7, 0.8, 0.9], "top_k": 3}
    ]
    assert llm_provider.question == "What is vLLM used for?"
    assert llm_provider.retrieved_context == vector_store.results
    assert "Question:\nWhat is vLLM used for?" in llm_provider.prompt
    assert "vLLM serves optimized large language model inference." in llm_provider.prompt


def test_build_rag_prompt_includes_question_and_retrieved_chunks() -> None:
    retrieved_context = [
        VectorSearchResult(
            chunk_text="First chunk text.",
            filename="first.txt",
            chunk_index=1,
            score=0.8,
        ),
        VectorSearchResult(
            chunk_text="Second chunk text.",
            filename="second.txt",
            chunk_index=3,
            score=0.7,
        ),
    ]

    prompt = build_rag_prompt("What did we retrieve?", retrieved_context)

    assert prompt.startswith("Use the retrieved context to answer the question.")
    assert "Question:\nWhat did we retrieve?" in prompt
    assert "[1] Source: first.txt#chunk-1\nFirst chunk text." in prompt
    assert "[2] Source: second.txt#chunk-3\nSecond chunk text." in prompt
    assert prompt.endswith("Answer:")


def test_build_rag_prompt_handles_empty_context() -> None:
    prompt = build_rag_prompt("Missing context?", [])

    assert "Question:\nMissing context?" in prompt
    assert "Retrieved context:\nNo context retrieved." in prompt


def test_mock_llm_provider_generates_deterministic_answer() -> None:
    provider = MockLLMProvider()
    retrieved_context = [
        VectorSearchResult(
            chunk_text="A useful context chunk.",
            filename="guide.txt",
            chunk_index=5,
            score=0.99,
        )
    ]

    first_answer = provider.generate_answer(
        question="What is vLLM used for?",
        retrieved_context=retrieved_context,
        prompt="ignored prompt",
    )
    second_answer = provider.generate_answer(
        question="What is vLLM used for?",
        retrieved_context=retrieved_context,
        prompt="another ignored prompt",
    )

    assert first_answer == second_answer
    assert first_answer == (
        "Mock answer for 'What is vLLM used for?' using 1 retrieved "
        "chunk(s): guide.txt#chunk-5."
    )
