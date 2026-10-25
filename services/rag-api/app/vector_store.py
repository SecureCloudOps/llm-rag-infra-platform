from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.auth import Principal


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
    """Store and retrieve only data owned by an authenticated principal."""

    def ensure_collection(self, vector_size: int) -> None:
        raise NotImplementedError

    def add_chunks(self, chunks: list[VectorStoreChunk]) -> None:
        raise NotImplementedError

    def get_stats(self, principal: Principal) -> VectorStoreStats:
        raise NotImplementedError

    def search(
        self, query_embedding: list[float], top_k: int, principal: Principal
    ) -> list[VectorSearchResult]:
        raise NotImplementedError


def owner_filter(principal: Principal) -> Any:
    """Qdrant evaluates authorization *before* ranking or returning points."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(must=[
        FieldCondition(key="tenant_id", match=MatchValue(value=principal.tenant_id)),
        FieldCondition(key="owner_id", match=MatchValue(value=principal.user_id)),
    ])


class QdrantVectorStore:
    def __init__(self, url: str, collection_name: str, client: Any | None = None) -> None:
        self.collection_name = collection_name
        if client is None:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=url)
        self.client = client

    def ensure_collection(self, vector_size: int) -> None:
        if self.client.collection_exists(collection_name=self.collection_name):
            info = self.client.get_collection(collection_name=self.collection_name)
            configured_vectors = info.config.params.vectors
            actual_size = getattr(configured_vectors, "size", None)
            if actual_size != vector_size:
                raise ValueError(
                    f"Collection {self.collection_name!r} has vector size {actual_size}; "
                    f"expected {vector_size}. Use a new versioned collection and re-ingest."
                )
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
            PointStruct(id=str(uuid4()), vector=chunk.embedding, payload=chunk.metadata)
            for chunk in chunks
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def get_stats(self, principal: Principal) -> VectorStoreStats:
        scope = owner_filter(principal)
        total_chunks = self.client.count(
            collection_name=self.collection_name,
            count_filter=scope,
            exact=True,
        ).count

        document_ids: set[str] = set()
        offset: Any | None = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                scroll_filter=scope,
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

    def search(
        self, query_embedding: list[float], top_k: int, principal: Principal
    ) -> list[VectorSearchResult]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=owner_filter(principal),
            limit=top_k,
            with_payload=True,
        )

        results: list[VectorSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            # Reject malformed/unscoped legacy points even if query evaluation changes.
            if (
                payload.get("tenant_id") != principal.tenant_id
                or payload.get("owner_id") != principal.user_id
            ):
                continue
            results.append(
                VectorSearchResult(
                    chunk_text=str(payload.get("chunk_text", "")),
                    filename=str(payload.get("filename", "")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    score=float(point.score),
                )
            )

        return results
