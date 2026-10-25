from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.embeddings import validate_vector


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
    document_id: str = ""


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
    def __init__(
        self,
        url: str,
        collection_name: str,
        client: Any | None = None,
        embedding_identity: dict[str, Any] | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_identity = embedding_identity
        self.vector_size: int | None = None
        self.manifest_name = collection_name + "__embedding_manifest"
        self.manifest_id = "00000000-0000-0000-0000-000000000001"
        if client is None:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=url)
        self.client = client

    def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if self.embedding_identity is None:
            raise ValueError("Explicit embedding model identity is required to initialize Qdrant")
        if vector_size <= 0:
            raise ValueError("Vector dimension must be positive")
        expected = {**self.embedding_identity, "dimensions": vector_size, "distance": "Cosine"}
        exists = self.client.collection_exists(collection_name=self.collection_name)
        manifest_exists = self.client.collection_exists(collection_name=self.manifest_name)
        message = (
            f"Incompatible Qdrant collection {self.collection_name!r}. "
            "Set COLLECTION_NAME to a new versioned name and reingest original .txt files; "
            "never convert old vectors or delete populated collections automatically."
        )
        if exists:
            params = self.client.get_collection(self.collection_name).config.params.vectors
            if not isinstance(params, VectorParams) or params.size != vector_size:
                raise ValueError(
                    f"{message} Expected unnamed vectors with dimension {vector_size}; got {params}."
                )
            if params.distance != Distance.COSINE:
                raise ValueError(f"{message} Expected cosine distance; got {params.distance}.")
            if not manifest_exists:
                raise ValueError(
                    f"{message} Missing embedding model identity manifest (legacy or incomplete initialization)."
                )
            records = self.client.retrieve(self.manifest_name, ids=[self.manifest_id])
            if len(records) != 1 or records[0].payload != expected:
                raise ValueError(
                    f"{message} Embedding model identity/revision mismatch; expected {expected}."
                )
        else:
            if manifest_exists:
                raise ValueError(
                    f"{message} Orphaned identity manifest; select a new collection name."
                )
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            self.client.create_collection(
                collection_name=self.manifest_name,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )
            self.client.upsert(
                self.manifest_name,
                points=[PointStruct(id=self.manifest_id, vector=[1.0], payload=expected)],
                wait=True,
            )
        self.vector_size = vector_size

    def add_chunks(self, chunks: list[VectorStoreChunk]) -> None:
        if not chunks:
            return

        if self.vector_size is None:
            raise RuntimeError("ensure_collection must succeed before writes")
        for chunk in chunks:
            validate_vector(chunk.embedding, self.vector_size)
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=str(uuid4()),
                vector=chunk.embedding,
                payload=chunk.metadata,
            )
            for chunk in chunks
        ]
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

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
        if self.vector_size is not None:
            validate_vector(query_embedding, self.vector_size)
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
                    document_id=str(payload.get("document_id", "")),
                )
            )

        return results
