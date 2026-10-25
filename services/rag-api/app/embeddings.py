"""Pluggable embeddings: hash vectors for test fixtures, real ONNX vectors for RAG."""
from functools import lru_cache
from hashlib import sha256
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        """Create an embedding vector for text."""
        raise NotImplementedError


class MockEmbeddingProvider:
    """Deterministic fixtures only. These vectors do NOT perform semantic retrieval."""

    def __init__(self, dimensions: int = 8) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        digest = sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        for index in range(self.dimensions):
            offset = (index * 4) % len(digest)
            value = int.from_bytes(digest[offset : offset + 4], byteorder="big")
            vector.append(value / 0xFFFFFFFF)
        return vector


class FastEmbedProvider:
    """Real semantic embeddings using an ONNX model; install the 'semantic' extra.

    Default BAAI/bge-small-en-v1.5 produces 384-dimensional vectors. Requires
    model weights downloaded to a writable cache; pre-cache for offline clusters.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: str | None = None,
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError("Install 'rag-api[semantic]' for semantic embeddings") from exc
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed(self, text: str) -> list[float]:
        return self._model.embed([text]).__next__().astype(float).tolist()


@lru_cache(maxsize=4)
def semantic_provider(model_name: str, cache_dir: str | None) -> FastEmbedProvider:
    return FastEmbedProvider(model_name=model_name, cache_dir=cache_dir)
