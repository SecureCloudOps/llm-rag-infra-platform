from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    collection_name: str
    llm_provider: str
    vllm_base_url: str
    model_name: str
    embedding_provider: str = "mock"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str | None = None
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""


def get_settings() -> Settings:
    return Settings(
        qdrant_url=getenv("QDRANT_URL", "http://localhost:6333"),
        collection_name=getenv("COLLECTION_NAME", "documents"),
        llm_provider=getenv("LLM_PROVIDER", "mock").lower(),
        vllm_base_url=getenv("VLLM_BASE_URL", "http://localhost:8001"),
        model_name=getenv("MODEL_NAME", "mistral-7b-instruct"),
        embedding_provider=getenv("EMBEDDING_PROVIDER", "mock").lower(),
        embedding_model=getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        embedding_cache_dir=getenv("EMBEDDING_CACHE_DIR") or None,
        auth_issuer=getenv("AUTH_ISSUER", ""),
        auth_audience=getenv("AUTH_AUDIENCE", ""),
        auth_jwks_url=getenv("AUTH_JWKS_URL", ""),
    )
