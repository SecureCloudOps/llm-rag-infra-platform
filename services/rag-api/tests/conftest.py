import pytest

from app.embeddings import MockEmbeddingProvider
from app.main import app, get_embedding_provider


@pytest.fixture(autouse=True)
def isolated_embeddings(request):
    if request.node.get_closest_marker("integration"):
        yield
        return
    app.dependency_overrides[get_embedding_provider] = lambda: MockEmbeddingProvider()
    yield
    app.dependency_overrides.clear()
