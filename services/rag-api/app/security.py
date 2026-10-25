"""Conservative defense in depth for untrusted RAG document text.

Pattern checks are not a complete defense against adversarial prompt injection
or every secret type. Authorization is enforced separately in the vector store.
"""
import re
from collections.abc import Sequence

from app.vector_store import VectorSearchResult


_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|password|client[_-]?secret|access[_-]?token)\s*[:=]\s*[\"']?[^\s\"'<>]{8,}", re.IGNORECASE),
]

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"\b(?:system|developer)\s*:\s*(?:ignore|override|new instructions)", re.IGNORECASE),
    re.compile(r"<\|(?:im_start|im_end)\|>", re.IGNORECASE),
    re.compile(r"\[INST\]|<<SYS>>", re.IGNORECASE),
    re.compile(r"(?:send|exfiltrate|upload)\s+(?:the\s+)?(?:passwords?|secrets?|tokens?|credentials?)\s+to\b", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def is_suspicious_context(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def filter_untrusted_context(
    results: Sequence[VectorSearchResult],
) -> list[VectorSearchResult]:
    # Drop suspect chunks outright, not just the injected instruction substring.
    # This intentionally favors confidentiality over recall.
    return [
        VectorSearchResult(
            chunk_text=redact_secrets(result.chunk_text),
            filename=result.filename,
            chunk_index=result.chunk_index,
            score=result.score,
        )
        for result in results
        if not is_suspicious_context(result.chunk_text)
    ]
