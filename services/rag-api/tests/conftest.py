import pytest
from keycloak_fixtures import dev_keycloak as dev_keycloak
from keycloak_fixtures import keyed_qdrant as keyed_qdrant
from oidc_fixtures import identity_provider as identity_provider

from app.embeddings import MockEmbeddingProvider
from app.main import app, get_embedding_provider
from app.security import Principal, get_current_principal, get_token_verifier

TEST_PRINCIPAL = Principal("test-tenant", "test-user", frozenset({"tenant_admin"}))
TEST_ACL = {"acl_version": 1, "tenant_id": "test-tenant", "owner_id": "test-user",
            "visibility": "private", "allowed_subjects": []}


def override_test_auth():
    # Explicit test-only dependency injection. Production has no auth-disable switch.
    app.dependency_overrides[get_current_principal] = lambda: TEST_PRINCIPAL
    app.dependency_overrides[get_token_verifier] = lambda: object()


@pytest.fixture(autouse=True)
def isolated_embeddings(request):
    if request.node.get_closest_marker("security"):
        yield
        app.dependency_overrides.clear()
        return
    override_test_auth()
    if not request.node.get_closest_marker("integration"):
        app.dependency_overrides[get_embedding_provider] = lambda: MockEmbeddingProvider()
    yield
    app.dependency_overrides.clear()
