import sys
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import get_settings
from app.document_service import process_text_upload
from app.embeddings import SentenceTransformerEmbeddingProvider, validate_vector


class Encoder:
    calls = []

    def __init__(self, *args, **kwargs):
        self.calls.append(kwargs)

    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, texts, **kwargs):
        return np.array([[1.0] + [0.0] * 383 for _ in texts])


@pytest.fixture
def encoder(monkeypatch, tmp_path):
    Encoder.calls.clear()
    from app.embeddings import DEFAULT_REVISION

    snapshot = tmp_path / DEFAULT_REVISION
    snapshot.mkdir()
    (snapshot / "modules.json").write_text("[]")
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda **kwargs: str(snapshot)),
    )
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Encoder)
    )
    return Encoder


def test_dimension_determinism_batch_and_one_initialization(encoder):
    provider = SentenceTransformerEmbeddingProvider()
    assert len(provider.embed("test")) == 384
    assert provider.embed("test") == provider.embed("test")
    assert provider.embed_batch(["first", "second"]) == [
        provider.embed("first"),
        provider.embed("second"),
    ]
    assert len(encoder.calls) == 1
    assert encoder.calls[0]["device"] == "cpu"
    assert len(encoder.calls[0]["revision"]) == 40
    assert encoder.calls[0]["trust_remote_code"] is False
    assert provider.embed_batch([]) == []
    with pytest.raises(ValueError, match="non-whitespace"):
        provider.embed("   ")


@pytest.mark.parametrize(
    "changes",
    [
        {"embedding_provider": "unknown"},
        {"embedding_dimensions": 8},
        {"embedding_device": "cuda"},
        {"embedding_model_revision": "main"},
        {"embedding_batch_size": 0},
    ],
)
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        replace(get_settings(), **changes)


def test_mock_configuration():
    assert (
        replace(
            get_settings(), embedding_provider="mock", embedding_dimensions=8
        ).embedding_dimensions
        == 8
    )


def test_model_initialization_failure(monkeypatch, encoder):
    def broken(*args, **kwargs):
        raise OSError("download failed")

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=broken)
    )
    with pytest.raises(RuntimeError, match="No mock fallback"):
        SentenceTransformerEmbeddingProvider()


def test_model_dimension_mismatch(encoder):
    with pytest.raises(RuntimeError, match="Model produces 384"):
        SentenceTransformerEmbeddingProvider(dimensions=8)


@pytest.mark.parametrize("vector", [[0.0], [float("nan")] * 384, [float("inf")] * 384])
def test_vector_validation(vector):
    with pytest.raises(ValueError):
        validate_vector(vector, 384)


def test_embedding_failure_does_not_write():
    class Store:
        def add_chunks(self, chunks):
            pytest.fail("incomplete document written")

    class BrokenBatch:
        dimensions = 384

        def embed_batch(self, texts):
            return [[0.0] * 384]  # fewer than the two chunks

    with pytest.raises(ValueError, match="count"):
        process_text_upload("test.txt", b"a" * 600, BrokenBatch(), Store())


def test_missing_model_modules_fails_without_generic_pooling_fallback(
    encoder, monkeypatch, tmp_path
):
    from app.embeddings import DEFAULT_REVISION

    incomplete = tmp_path / "incomplete" / DEFAULT_REVISION
    incomplete.mkdir(parents=True)
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda **kwargs: str(incomplete)),
    )
    with pytest.raises(RuntimeError, match="modules.json"):
        SentenceTransformerEmbeddingProvider()
    assert not encoder.calls
