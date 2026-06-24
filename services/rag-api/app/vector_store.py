from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class VectorStoreChunk:
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VectorStoreStats:
    total_documents: int
    total_chunks: int


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_text: str
    filename: str
    chunk_index: int
    score: float


class VectorStore(Protocol):
    """Interface for vector database implementations."""

    def ensure_collection(self, vector_size: int) -> None:
        """Create backing collection/indexes when they do not exist."""
        raise NotImplementedError

    def add_chunks(self, chunks: list[VectorStoreChunk]) -> None:
        """Store embedded document chunks and metadata."""
        raise NotImplementedError

    def get_stats(self) -> VectorStoreStats:
        """Return document and chunk counts."""
        raise NotImplementedError

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        """Return the most similar chunks for an embedding."""
        raise NotImplementedError


class QdrantVectorStore:
    def __init__(self, url: str, collection_name: str, client: Any | None = None) -> None:
        self.collection_name = collection_name
        if client is None:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=url)
        self.client = client

    def ensure_collection(self, vector_size: int) -> None:
        if self.client.collection_exists(collection_name=self.collection_name):
            return

        from qdrant_client.models import Distance, VectorParams

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def add_chunks(self, chunks: list[VectorStoreChunk]) -> None:
        if not chunks:
            return

        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=str(uuid4()),
                vector=chunk.embedding,
                payload=chunk.metadata,
            )
            for chunk in chunks
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def get_stats(self) -> VectorStoreStats:
        total_chunks = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        ).count

        document_ids: set[str] = set()
        offset: Any | None = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                document_id = payload.get("document_id")
                if isinstance(document_id, str):
                    document_ids.add(document_id)

            if offset is None:
                break

        return VectorStoreStats(
            total_documents=len(document_ids),
            total_chunks=total_chunks,
        )

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k,
            with_payload=True,
        )

        results: list[VectorSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_text=str(payload.get("chunk_text", "")),
                    filename=str(payload.get("filename", "")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    score=float(point.score),
                )
            )

        return results
