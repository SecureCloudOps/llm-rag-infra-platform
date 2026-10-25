from hashlib import sha256
from math import isfinite
from pathlib import Path
from threading import Lock
from typing import Protocol

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"


def validate_vector(vector: list[float], dimensions: int) -> None:
    if len(vector) != dimensions or not all(isfinite(value) for value in vector):
        raise ValueError(f"Expected {dimensions} finite embedding values, got {len(vector)}")


class EmbeddingProvider(Protocol):
    """The original single-text interface; batch support is optional."""

    def embed(self, text: str) -> list[float]: ...


class MockEmbeddingProvider:
    """Deterministic SHA-256 baseline, never a semantic fallback."""

    identity = {"provider": "mock", "model": "sha256", "revision": "1"}

    def __init__(self, dimensions: int = 8) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        digest = sha256(text.encode("utf-8")).digest()
        return [
            int.from_bytes(digest[(i * 4) % 32 : (i * 4) % 32 + 4], "big") / 0xFFFFFFFF
            for i in range(self.dimensions)
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class SentenceTransformerEmbeddingProvider:
    """One CPU model per worker. Serialize inference to bound CPU contention."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        revision: str = DEFAULT_REVISION,
        dimensions: int = 384,
        device: str = "cpu",
        batch_size: int = 32,
        cache_folder: str | None = None,
    ) -> None:
        import re

        if device != "cpu":
            raise ValueError("EMBEDDING_DEVICE must be cpu")
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(
                "EMBEDDING_MODEL_REVISION must be an immutable 40-character commit SHA"
            )
        if dimensions <= 0 or batch_size <= 0:
            raise ValueError("Embedding dimensions and batch size must be positive")
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.identity = {
            "provider": "sentence_transformers",
            "model": model,
            "revision": revision,
            "normalized": True,
        }
        self._lock = Lock()
        try:
            from huggingface_hub import snapshot_download
            from sentence_transformers import SentenceTransformer

            # Resolve the complete pinned snapshot before loading. This prevents the
            # library from silently constructing a generic pooling model if modules.json
            # is missing. Hub caching reuses existing artifacts, including offline mode.
            snapshot = Path(
                snapshot_download(
                    repo_id=model,
                    revision=revision,
                    cache_dir=cache_folder,
                    allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model"],
                )
            )
            if snapshot.name != revision or not (snapshot / "modules.json").is_file():
                raise ValueError("Pinned snapshot must contain Sentence Transformers modules.json")
            self._model = SentenceTransformer(
                str(snapshot),
                revision=revision,
                device=device,
                cache_folder=cache_folder,
                trust_remote_code=False,
                model_kwargs={"use_safetensors": True},
            )
            actual = self._model.get_sentence_embedding_dimension()
            if actual != dimensions:
                raise ValueError(f"Model produces {actual} dimensions; configured {dimensions}")
            self.embed("startup validation")
        except Exception as exc:
            raise RuntimeError(
                f"Cannot initialize embedding model {model}@{revision}: {exc}. "
                "Install CPU dependencies, verify model/revision and Hugging Face network access, "
                "and ensure EMBEDDING_CACHE_DIR is writable or pre-populated. No mock fallback."
            ) from exc

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding input must contain non-whitespace text")
        with self._lock:
            vectors = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).tolist()
        if len(vectors) != len(texts):
            raise ValueError("Embedding batch returned an incorrect vector count")
        for vector in vectors:
            validate_vector(vector, self.dimensions)
        return vectors


def create_embedding_provider(settings):
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dimensions)
    return SentenceTransformerEmbeddingProvider(
        model=settings.embedding_model,
        revision=settings.embedding_model_revision,
        dimensions=settings.embedding_dimensions,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        cache_folder=settings.embedding_cache_dir,
    )
