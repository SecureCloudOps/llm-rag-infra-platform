from collections.abc import Callable, Sequence
from time import perf_counter
from typing import TypeVar

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.vector_store import VectorSearchResult

T = TypeVar("T")


HTTP_REQUESTS_TOTAL = Counter(
    "rag_api_http_requests_total",
    "Total HTTP requests handled by the RAG API.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "rag_api_http_request_latency_seconds",
    "HTTP request latency for the RAG API.",
    ["method", "path"],
)

ASK_LATENCY_SECONDS = Histogram(
    "rag_api_ask_latency_seconds",
    "End-to-end latency for POST /ask requests.",
)

QDRANT_RETRIEVAL_LATENCY_SECONDS = Histogram(
    "rag_api_qdrant_retrieval_latency_seconds",
    "Latency for vector retrieval calls to Qdrant.",
    ["endpoint"],
)

LLM_PROVIDER_LATENCY_SECONDS = Histogram(
    "rag_api_llm_provider_latency_seconds",
    "Latency for LLM provider answer generation.",
    ["provider", "model_name"],
)

RETRIEVED_CHUNK_COUNT = Histogram(
    "rag_api_retrieved_chunk_count",
    "Number of chunks retrieved for RAG requests.",
    ["endpoint"],
    buckets=(0, 1, 2, 3, 5, 8, 13, 21, float("inf")),
)

ERRORS_TOTAL = Counter(
    "rag_api_errors_total",
    "Errors raised while handling RAG API requests.",
    ["endpoint", "error_type"],
)


def metrics_response_body() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def observe_retrieval(
    endpoint: str,
    search_call: Callable[[], Sequence[VectorSearchResult]],
) -> Sequence[VectorSearchResult]:
    start = perf_counter()
    try:
        results = search_call()
    except Exception as exc:
        ERRORS_TOTAL.labels(endpoint=endpoint, error_type=type(exc).__name__).inc()
        raise
    finally:
        QDRANT_RETRIEVAL_LATENCY_SECONDS.labels(endpoint=endpoint).observe(
            perf_counter() - start
        )

    RETRIEVED_CHUNK_COUNT.labels(endpoint=endpoint).observe(len(results))
    return results


def observe_llm_generation(
    provider: object,
    generation_call: Callable[[], T],
) -> T:
    provider_name = str(getattr(provider, "provider_name", provider.__class__.__name__))
    model_name = str(getattr(provider, "model_name", "unknown"))

    start = perf_counter()
    try:
        return generation_call()
    except Exception as exc:
        ERRORS_TOTAL.labels(endpoint="/ask", error_type=type(exc).__name__).inc()
        raise
    finally:
        LLM_PROVIDER_LATENCY_SECONDS.labels(
            provider=provider_name,
            model_name=model_name,
        ).observe(perf_counter() - start)
