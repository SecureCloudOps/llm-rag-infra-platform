import re
from dataclasses import dataclass
from os import getenv

from app.embeddings import DEFAULT_MODEL, DEFAULT_REVISION


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    collection_name: str
    llm_provider: str
    vllm_base_url: str
    model_name: str
    embedding_provider: str = "sentence_transformers"
    embedding_model: str = DEFAULT_MODEL
    embedding_model_revision: str = DEFAULT_REVISION
    embedding_dimensions: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    embedding_cache_dir: str | None = None

    def __post_init__(self) -> None:
        if self.embedding_provider not in {"sentence_transformers", "mock"}:
            raise ValueError("EMBEDDING_PROVIDER must be sentence_transformers or mock")
        if self.embedding_dimensions <= 0 or self.embedding_batch_size <= 0:
            raise ValueError("Embedding dimensions and batch size must be positive")
        if self.embedding_device != "cpu":
            raise ValueError("EMBEDDING_DEVICE must be cpu")
        if self.embedding_provider == "sentence_transformers":
            if not re.fullmatch(r"[0-9a-f]{40}", self.embedding_model_revision):
                raise ValueError("EMBEDDING_MODEL_REVISION must be an immutable commit SHA")
            if self.embedding_model == DEFAULT_MODEL and self.embedding_dimensions != 384:
                raise ValueError("all-MiniLM-L6-v2 requires EMBEDDING_DIMENSIONS=384")


def get_settings() -> Settings:
    return Settings(
        qdrant_url=getenv("QDRANT_URL", "http://localhost:6333"),
        collection_name=getenv("COLLECTION_NAME", "documents-minilm-v1"),
        llm_provider=getenv("LLM_PROVIDER", "mock").lower(),
        vllm_base_url=getenv("VLLM_BASE_URL", "http://localhost:8001"),
        embedding_provider=getenv("EMBEDDING_PROVIDER", "sentence_transformers").lower(),
        embedding_model=getenv("EMBEDDING_MODEL", DEFAULT_MODEL),
        embedding_model_revision=getenv("EMBEDDING_MODEL_REVISION", DEFAULT_REVISION),
        embedding_dimensions=int(getenv("EMBEDDING_DIMENSIONS", "384")),
        embedding_device=getenv("EMBEDDING_DEVICE", "cpu"),
        embedding_batch_size=int(getenv("EMBEDDING_BATCH_SIZE", "32")),
        embedding_cache_dir=getenv("EMBEDDING_CACHE_DIR"),
        model_name=getenv("MODEL_NAME", "mistral-7b-instruct"),
    )
