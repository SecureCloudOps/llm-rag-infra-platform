import pytest

from app.chunking import chunk_text


def test_chunk_text_splits_into_requested_size() -> None:
    chunks = chunk_text("a" * 1201, chunk_size=500)

    assert [len(chunk) for chunk in chunks] == [500, 500, 201]


def test_chunk_text_rejects_invalid_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("content", chunk_size=0)
