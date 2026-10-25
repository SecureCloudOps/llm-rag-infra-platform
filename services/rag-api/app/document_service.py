from dataclasses import dataclass
from pathlib import PurePath
from uuid import uuid4

from app.chunking import chunk_text
from app.embeddings import EmbeddingProvider, validate_vector
from app.vector_store import VectorStore, VectorStoreChunk

SUPPORTED_TEXT_SUFFIX = ".txt"


class UnsupportedDocumentTypeError(ValueError):
    """Raised when a document type is not supported."""


class DocumentDecodeError(ValueError):
    """Raised when a document cannot be decoded as text."""


@dataclass(frozen=True)
class DocumentUploadResult:
    filename: str
    total_chunks: int
    chunk_sizes: list[int]
    embedding_count: int


def process_text_upload(
    filename: str,
    content: bytes,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> DocumentUploadResult:
    safe_filename = PurePath(filename).name
    if not safe_filename or PurePath(safe_filename).suffix.lower() != SUPPORTED_TEXT_SUFFIX:
        raise UnsupportedDocumentTypeError("Only .txt files are supported")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentDecodeError("Uploaded file must be valid UTF-8 text") from exc

    chunks = chunk_text(text)
    if embedding_provider is None:
        raise ValueError("An explicitly configured embedding provider is required")
    provider = embedding_provider
    batch = getattr(provider, "embed_batch", None)
    embeddings = batch(chunks) if batch else [provider.embed(chunk) for chunk in chunks]
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding count does not match chunk count; document not inserted")
    dimensions = getattr(provider, "dimensions", len(embeddings[0]) if embeddings else 0)
    for vector in embeddings:
        validate_vector(vector, dimensions)

    if vector_store is not None:
        document_id = str(uuid4())
        vector_store.add_chunks(
            [
                VectorStoreChunk(
                    text=chunk,
                    embedding=embedding,
                    metadata={
                        "document_id": document_id,
                        "filename": safe_filename,
                        "chunk_index": index,
                        "chunk_text": chunk,
                    },
                )
                for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
            ]
        )

    return DocumentUploadResult(
        filename=safe_filename,
        total_chunks=len(chunks),
        chunk_sizes=[len(chunk) for chunk in chunks],
        embedding_count=len(embeddings),
    )
