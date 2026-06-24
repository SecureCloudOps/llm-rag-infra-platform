import json

import httpx
import pytest

from app.llm_provider import MockLLMProvider, OpenAICompatibleLLMProvider
from app.main import get_llm_provider
from app.vector_store import VectorSearchResult


def test_get_llm_provider_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    provider = get_llm_provider()

    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_builds_vllm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.local:8000")
    monkeypatch.setenv("MODEL_NAME", "example-model")

    provider = get_llm_provider()

    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.base_url == "http://vllm.local:8000"
    assert provider.model_name == "example-model"


def test_openai_compatible_provider_calls_chat_completions_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": " vLLM generated answer. ",
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLLMProvider(
        base_url="http://vllm.local:8000/",
        model_name="example-model",
        client=client,
    )
    context = [
        VectorSearchResult(
            chunk_text="vLLM exposes an OpenAI-compatible API.",
            filename="vllm.txt",
            chunk_index=0,
            score=0.99,
        )
    ]

    answer = provider.generate_answer(
        question="What API does vLLM expose?",
        retrieved_context=context,
        prompt="RAG prompt",
    )

    assert answer == "vLLM generated answer."
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "http://vllm.local:8000/v1/chat/completions"
    assert request.method == "POST"
    assert request.headers["content-type"] == "application/json"
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["model"] == "example-model"
    assert payload["messages"][1] == {"role": "user", "content": "RAG prompt"}
    assert payload["temperature"] == 0


def test_openai_compatible_provider_accepts_versioned_base_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "answer"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLLMProvider(
        base_url="http://vllm.local:8000/v1",
        model_name="example-model",
        client=client,
    )

    provider.generate_answer(
        question="Question?",
        retrieved_context=[],
        prompt="RAG prompt",
    )

    assert len(requests) == 1
    assert str(requests[0].url) == "http://vllm.local:8000/v1/chat/completions"


def test_openai_compatible_provider_rejects_missing_answer() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=200, json={"choices": []})
        )
    )
    provider = OpenAICompatibleLLMProvider(
        base_url="http://vllm.local:8000",
        model_name="example-model",
        client=client,
    )

    with pytest.raises(ValueError, match="did not include an answer"):
        provider.generate_answer(
            question="Question?",
            retrieved_context=[],
            prompt="RAG prompt",
        )
