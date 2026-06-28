from collections.abc import Sequence
from typing import Protocol

import httpx

from app.vector_store import VectorSearchResult


class LLMProvider(Protocol):
    """Interface for answer generation providers."""

    provider_name: str
    model_name: str

    def generate_answer(
        self,
        question: str,
        retrieved_context: Sequence[VectorSearchResult],
        prompt: str,
    ) -> str:
        """Generate an answer from a question, retrieved context, and prompt."""
        raise NotImplementedError


def build_rag_prompt(question: str, retrieved_context: Sequence[VectorSearchResult]) -> str:
    context_blocks = [
        (
            f"[{index}] Source: {result.filename}#chunk-{result.chunk_index}\n"
            f"{result.chunk_text}"
        )
        for index, result in enumerate(retrieved_context, start=1)
    ]
    context_text = "\n\n".join(context_blocks) if context_blocks else "No context retrieved."

    return (
        "Use the retrieved context to answer the question.\n"
        "If the context is insufficient, say that the available context is insufficient.\n\n"
        f"Question:\n{question}\n\n"
        f"Retrieved context:\n{context_text}\n\n"
        "Answer:"
    )


class MockLLMProvider:
    """Deterministic local LLM provider for tests and development."""

    provider_name = "mock"
    model_name = "mock-local"

    def generate_answer(
        self,
        question: str,
        retrieved_context: Sequence[VectorSearchResult],
        prompt: str,
    ) -> str:
        del prompt

        if not retrieved_context:
            return (
                f"Mock answer: no retrieved context was available for question: {question}"
            )

        sources = ", ".join(
            f"{result.filename}#chunk-{result.chunk_index}" for result in retrieved_context
        )
        return (
            f"Mock answer for '{question}' using {len(retrieved_context)} retrieved "
            f"chunk(s): {sources}."
        )


class OpenAICompatibleLLMProvider:
    """LLM provider for vLLM's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.provider_name = "vllm"
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def generate_answer(
        self,
        question: str,
        retrieved_context: Sequence[VectorSearchResult],
        prompt: str,
    ) -> str:
        del question, retrieved_context

        response = self.client.post(
            self._chat_completions_url(),
            json={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You answer questions using only the supplied retrieved context.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            },
        )
        response.raise_for_status()

        data = response.json()
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                "OpenAI-compatible LLM response did not include an answer"
            ) from exc

        return str(answer).strip()
