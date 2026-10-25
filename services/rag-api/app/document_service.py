from dataclasses import dataclass
from pathlib import PurePath
from uuid import uuid4

from app.auth import Principal
from app.chunking import chunk_text
from app.embeddings import EmbeddingProvider
from app.security import redact_secrets
from app.vector_store import VectorStore, VectorStoreChunk


SUPPORTED_TEXT_SUFFIX = ".txt"
MAX_UPLOAD_BYTES = 1024 * 1024


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
    *,
    principal: Principal,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
) -> DocumentUploadResult:
    safe_filename = PurePath(filename.replace("\\", "/")).name
    if not safe_filename or PurePath(safe_filename).suffix.lower() != SUPPORTED_TEXT_SUFFIX:
        raise UnsupportedDocumentTypeError("Only .txt files are supported")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload exceeds 1 MiB limit")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentDecodeError("Uploaded file must be valid UTF-8 text") from exc

    # Secrets are removed before embedding and persistence, not just at response time.
    chunks = chunk_text(redact_secrets(text))
    embeddings = [embedding_provider.embed(chunk) for chunk in chunks]
    document_id = str(uuid4())
    vector_store.add_chunks(
        [
            VectorStoreChunk(
                text=chunk,
                embedding=embedding,
                metadata={
                    "tenant_id": principal.tenant_id,
                    "owner_id": principal.user_id,
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
