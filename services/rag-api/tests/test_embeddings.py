from app.embeddings import MockEmbeddingProvider


def test_mock_embeddings_are_deterministic() -> None:
    provider = MockEmbeddingProvider()

    assert provider.embed("same text") == provider.embed("same text")


def test_mock_embeddings_differ_for_different_text() -> None:
    provider = MockEmbeddingProvider()

    assert provider.embed("first text") != provider.embed("second text")
