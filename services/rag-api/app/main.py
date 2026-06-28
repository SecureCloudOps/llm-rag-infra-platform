from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from time import perf_counter

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.document_service import (
    DocumentDecodeError,
    DocumentUploadResult,
    UnsupportedDocumentTypeError,
    process_text_upload,
)
from app.embeddings import EmbeddingProvider, MockEmbeddingProvider
from app.llm_provider import (
    LLMProvider,
    MockLLMProvider,
    OpenAICompatibleLLMProvider,
    build_rag_prompt,
)
from app.metrics import (
    ASK_LATENCY_SECONDS,
    ERRORS_TOTAL,
    HTTP_REQUEST_LATENCY_SECONDS,
    HTTP_REQUESTS_TOTAL,
    metrics_content_type,
    metrics_response_body,
    observe_llm_generation,
    observe_retrieval,
)
from app.vector_store import QdrantVectorStore, VectorStore


class HealthResponse(BaseModel):
    status: str
    service: str


class DocumentUploadResponse(BaseModel):
    filename: str
    total_chunks: int
    chunk_sizes: list[int]
    embedding_count: int


class DocumentStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1)


class SearchResultResponse(BaseModel):
    chunk_text: str
    filename: str
    chunk_index: int
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class AskSourceResponse(BaseModel):
    filename: str
    chunk_index: int
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[AskSourceResponse]
    retrieved_chunks: int


def get_embedding_provider() -> EmbeddingProvider:
    return MockEmbeddingProvider()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "vllm":
        return OpenAICompatibleLLMProvider(
            base_url=settings.vllm_base_url,
            model_name=settings.model_name,
        )
    raise ValueError("LLM_PROVIDER must be 'mock' or 'vllm'")


def get_vector_store() -> VectorStore:
    vector_store = getattr(app.state, "vector_store", None)
    if vector_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store is not initialized",
        )
    return vector_store


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    embedding_provider = get_embedding_provider()
    vector_size = len(embedding_provider.embed(""))
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.collection_name,
    )
    vector_store.ensure_collection(vector_size=vector_size)
    app_instance.state.vector_store = vector_store
    yield


app = FastAPI(
    title="LLM RAG Infrastructure Platform API",
    description="FastAPI service for retrieval-augmented generation workflows.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def record_http_metrics(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    start = perf_counter()
    path = request.url.path
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        ERRORS_TOTAL.labels(endpoint=path, error_type=type(exc).__name__).inc()
        raise
    finally:
        elapsed = perf_counter() - start
        HTTP_REQUEST_LATENCY_SECONDS.labels(method=request.method, path=path).observe(
            elapsed
        )
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            path=path,
            status_code=str(status_code),
        ).inc()
        if status_code >= 500:
            ERRORS_TOTAL.labels(endpoint=path, error_type=f"HTTP_{status_code}").inc()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="rag-api")


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(
        content=metrics_response_body(),
        media_type=metrics_content_type(),
    )


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> DocumentUploadResponse:
    content = await file.read()

    try:
        result: DocumentUploadResult = process_text_upload(
            file.filename or "",
            content,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
    except UnsupportedDocumentTypeError as exc:
        ERRORS_TOTAL.labels(
            endpoint="/documents/upload",
            error_type=type(exc).__name__,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except DocumentDecodeError as exc:
        ERRORS_TOTAL.labels(
            endpoint="/documents/upload",
            error_type=type(exc).__name__,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return DocumentUploadResponse(
        filename=result.filename,
        total_chunks=result.total_chunks,
        chunk_sizes=result.chunk_sizes,
        embedding_count=result.embedding_count,
    )


@app.get("/documents", response_model=DocumentStatsResponse)
def get_documents(vector_store: VectorStore = Depends(get_vector_store)) -> DocumentStatsResponse:
    stats = vector_store.get_stats()
    return DocumentStatsResponse(
        total_documents=stats.total_documents,
        total_chunks=stats.total_chunks,
    )


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> SearchResponse:
    query_embedding = embedding_provider.embed(request.query)
    results = observe_retrieval(
        endpoint="/search",
        search_call=lambda: vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
        ),
    )

    return SearchResponse(
        query=request.query,
        results=[
            SearchResultResponse(
                chunk_text=result.chunk_text,
                filename=result.filename,
                chunk_index=result.chunk_index,
                score=result.score,
            )
            for result in results
        ],
    )


@app.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    ask_start = perf_counter()
    try:
        question_embedding = embedding_provider.embed(request.question)
        retrieved_context = observe_retrieval(
            endpoint="/ask",
            search_call=lambda: vector_store.search(
                query_embedding=question_embedding,
                top_k=3,
            ),
        )
        prompt = build_rag_prompt(
            question=request.question,
            retrieved_context=retrieved_context,
        )
        answer = observe_llm_generation(
            provider=llm_provider,
            generation_call=lambda: llm_provider.generate_answer(
                question=request.question,
                retrieved_context=retrieved_context,
                prompt=prompt,
            ),
        )
    finally:
        ASK_LATENCY_SECONDS.observe(perf_counter() - ask_start)

    return AskResponse(
        question=request.question,
        answer=answer,
        sources=[
            AskSourceResponse(
                filename=result.filename,
                chunk_index=result.chunk_index,
                score=result.score,
            )
            for result in retrieved_context
        ],
        retrieved_chunks=len(retrieved_context),
    )
