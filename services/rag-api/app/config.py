from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    collection_name: str
    llm_provider: str
    vllm_base_url: str
    model_name: str


def get_settings() -> Settings:
    return Settings(
        qdrant_url=getenv("QDRANT_URL", "http://localhost:6333"),
        collection_name=getenv("COLLECTION_NAME", "documents"),
        llm_provider=getenv("LLM_PROVIDER", "mock").lower(),
        vllm_base_url=getenv("VLLM_BASE_URL", "http://localhost:8001"),
        model_name=getenv("MODEL_NAME", "mistral-7b-instruct"),
    )
