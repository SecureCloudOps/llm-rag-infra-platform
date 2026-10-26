from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.document_service import (
    DocumentDecodeError,
    DocumentUploadResult,
    UnsupportedDocumentTypeError,
    process_text_upload,
)
from app.embeddings import EmbeddingProvider, create_embedding_provider, validate_vector
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
from app.security import (
    JWTVerifier,
    Principal,
    audit,
    can_read,
    get_current_principal,
    get_token_verifier,
    require_permission,
)
from app.vector_store import QdrantVectorStore, VectorSearchResult, VectorStore


class HealthResponse(BaseModel):
    status: str
    service: str


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    total_chunks: int
    chunk_sizes: list[int]
    embedding_count: int


class DocumentStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=100)


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


class DocumentPermissions(BaseModel):
    model_config = {"extra": "forbid"}
    visibility: Literal["private", "tenant"] = "private"
    allowed_subjects: list[Annotated[str, Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,199}$"
    )]] = Field(default_factory=list, max_length=100)


def authorized_context(results: list[VectorSearchResult], principal: Principal):
    authorized = [result for result in results if can_read(principal, result.authorization)]
    if len(authorized) != len(results):
        audit("authorization_denial", principal=principal, operation="context_boundary")
    return authorized


def get_embedding_provider() -> EmbeddingProvider:
    provider = getattr(app.state, "embedding_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="Embedding provider is not initialized")
    return provider


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
    app_instance.state.ready = False
    settings = get_settings()
    verifier_factory = app_instance.dependency_overrides.get(get_token_verifier)
    verifier = verifier_factory() if verifier_factory else JWTVerifier.from_environment()
    factory = app_instance.dependency_overrides.get(get_embedding_provider)
    embedding_provider = await run_in_threadpool(
        factory or create_embedding_provider, *([] if factory else [settings])
    )
    vector_size = getattr(embedding_provider, "dimensions", None)
    if vector_size is None:
        # Preserve the original embed-only interface for injected test providers.
        probe = await run_in_threadpool(embedding_provider.embed, "startup validation")
        vector_size = len(probe)
        validate_vector(probe, vector_size)
    store_factory = app_instance.dependency_overrides.get(get_vector_store)
    vector_store = (
        store_factory()
        if store_factory
        else QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=settings.collection_name,
            embedding_identity=getattr(embedding_provider, "identity", None),
        )
    )
    try:
        await run_in_threadpool(vector_store.ensure_collection, vector_size=vector_size)
        if not store_factory:
            await run_in_threadpool(vector_store.ensure_acl_indexes)
        app_instance.state.token_verifier = verifier
        app_instance.state.embedding_provider = embedding_provider
        app_instance.state.vector_store = vector_store
        app_instance.state.ready = True
        yield
    finally:
        app_instance.state.ready = False
        app_instance.state.token_verifier = None
        app_instance.state.embedding_provider = None
        app_instance.state.vector_store = None
        if not store_factory:
            await run_in_threadpool(vector_store.client.close)


app = FastAPI(
    title="LLM RAG Infrastructure Platform API",
    description="FastAPI service for retrieval-augmented generation workflows.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def record_http_metrics(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    start = perf_counter()
    path = "unmatched"
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        ERRORS_TOTAL.labels(endpoint=path, error_type=type(exc).__name__).inc()
        raise
    finally:
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        elapsed = perf_counter() - start
        HTTP_REQUEST_LATENCY_SECONDS.labels(method=request.method, path=path).observe(elapsed)
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


@app.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Required dependencies are not initialized")
    return HealthResponse(status="ok", service="rag-api")


@app.get("/metrics", include_in_schema=False)
def metrics(principal: Principal = Depends(get_current_principal)) -> Response:
    require_permission(principal, "metrics")
    audit("access", principal=principal, operation="metrics")
    return Response(
        content=metrics_response_body(),
        media_type=metrics_content_type(),
    )


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    principal: Principal = Depends(get_current_principal),
) -> DocumentUploadResponse:
    require_permission(principal, "upload")
    content = await file.read()

    try:
        result: DocumentUploadResult = await run_in_threadpool(
            process_text_upload,
            file.filename or "",
            content,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            principal=principal,
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

    audit("document_upload", principal=principal, document_id=result.document_id,
          chunks=result.total_chunks)
    return DocumentUploadResponse(
        document_id=result.document_id,
        filename=result.filename,
        total_chunks=result.total_chunks,
        chunk_sizes=result.chunk_sizes,
        embedding_count=result.embedding_count,
    )


@app.get("/documents", response_model=DocumentStatsResponse)
def get_documents(
    vector_store: VectorStore = Depends(get_vector_store),
    principal: Principal = Depends(get_current_principal),
) -> DocumentStatsResponse:
    require_permission(principal, "read")
    stats = vector_store.get_stats(access=principal)
    audit("access", principal=principal, operation="document_stats")
    return DocumentStatsResponse(
        total_documents=stats.total_documents,
        total_chunks=stats.total_chunks,
    )


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    principal: Principal = Depends(get_current_principal),
) -> SearchResponse:
    require_permission(principal, "read")
    query_embedding = embedding_provider.embed(request.query)
    results = observe_retrieval(
        endpoint="/search",
        search_call=lambda: vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k,
            access=principal,
        ),
    )

    results = authorized_context(results, principal)
    audit("access", principal=principal, operation="search", returned_chunks=len(results))
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
    principal: Principal = Depends(get_current_principal),
) -> AskResponse:
    require_permission(principal, "read")
    ask_start = perf_counter()
    try:
        question_embedding = embedding_provider.embed(request.question)
        retrieved_context = observe_retrieval(
            endpoint="/ask",
            search_call=lambda: vector_store.search(
                query_embedding=question_embedding,
                top_k=3,
                access=principal,
            ),
        )
        retrieved_context = authorized_context(retrieved_context, principal)
        audit("access", principal=principal, operation="ask",
              returned_chunks=len(retrieved_context))
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


@app.patch("/documents/{document_id}/permissions")
def update_document_permissions(
    document_id: UUID,
    permissions: DocumentPermissions,
    principal: Principal = Depends(get_current_principal),
    vector_store: VectorStore = Depends(get_vector_store),
):
    require_permission(principal, "manage")
    updated = vector_store.update_permissions(
        str(document_id), principal, permissions.visibility, permissions.allowed_subjects
    )
    if not updated:
        audit("authorization_denial", principal=principal, operation="document_permissions")
        raise HTTPException(404, "Document not found")
    audit("document_permissions", principal=principal, document_id=str(document_id))
    return {"status": "updated"}
