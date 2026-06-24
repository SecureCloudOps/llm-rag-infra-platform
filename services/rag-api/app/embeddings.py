from hashlib import sha256
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Interface for text embedding providers."""

    def embed(self, text: str) -> list[float]:
        """Create an embedding vector for text."""
        raise NotImplementedError


class MockEmbeddingProvider:
    """Deterministic local embedding provider for tests and development."""

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
