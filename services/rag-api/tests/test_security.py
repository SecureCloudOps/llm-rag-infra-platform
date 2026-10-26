"""Real signed JWTs/JWKS; no authentication bypass in these tests."""

import io
import json
import logging
from time import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import main
from app.embeddings import MockEmbeddingProvider
from app.security import (
    JWTVerifier,
    Principal,
    audit_logger,
    can_read,
    get_token_verifier,
)
from app.vector_store import VectorSearchResult, VectorStoreStats

pytestmark = pytest.mark.security


class StubStore:
    def __init__(self):
        self.chunks = []
        self.results = []
        self.calls = []

    def ensure_collection(self, vector_size):
        pass

    def add_chunks(self, chunks):
        self.chunks.extend(chunks)

    def get_stats(self, *, access):
        self.calls.append(access)
        return VectorStoreStats(0, 0)

    def search(self, query_embedding, top_k, *, access):
        self.calls.append(access)
        return self.results


@pytest.fixture
def authenticated_api(identity_provider):
    store = StubStore()
    main.app.dependency_overrides[get_token_verifier] = lambda: identity_provider.verifier
    main.app.dependency_overrides[main.get_embedding_provider] = MockEmbeddingProvider
    main.app.dependency_overrides[main.get_vector_store] = lambda: store
    with TestClient(main.app, raise_server_exceptions=True) as client:
        yield client, store


def headers(token):
    return {"Authorization": "Bearer " + token}


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/documents", "get", None),
        ("/search", "post", {"query": "private content"}),
        ("/ask", "post", {"question": "private content"}),
        ("/metrics", "get", None),
    ],
)
def test_missing_bearer_is_401(authenticated_api, path, method, body):
    client, _ = authenticated_api
    response = client.request(method, path, **({"json": body} if body else {}))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"iss": "https://attacker.invalid"},
        {"aud": "another-api"},
        {"nbf": int(time()) + 1000},
        {"iat": int(time()) + 1000},
        {"typ": "ID"},
        {"tenant_id": ""},
        {"tenant_id": ["tenant-a", "tenant-b"]},
        {"sub": ""},
        {"realm_access": {"roles": "tenant_admin"}},
        {"exp": "not-a-number"},
        {"iat": True},
    ],
)
def test_invalid_claims_rejected(authenticated_api, identity_provider, changes):
    client, store = authenticated_api
    response = client.get("/documents", headers=headers(identity_provider.token(**changes)))
    assert response.status_code == 401
    assert store.calls == []


@pytest.mark.parametrize("claim", ["exp", "iat", "iss", "aud", "sub", "tenant_id", "typ"])
def test_required_claims(authenticated_api, identity_provider, claim):
    token = identity_provider.token()
    payload = jwt.decode(token, options={"verify_signature": False})
    del payload[claim]
    token = jwt.encode(
        payload, identity_provider.key, algorithm="RS256", headers={"kid": "test-key"}
    )
    assert authenticated_api[0].get("/documents", headers=headers(token)).status_code == 401


def test_bad_signatures_algorithms_and_headers(authenticated_api, identity_provider):
    client, store = authenticated_api
    payload = jwt.decode(identity_provider.token(), options={"verify_signature": False})
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tokens = [
        "not.a.jwt",
        jwt.encode(payload, other, algorithm="RS256", headers={"kid": "test-key"}),
        jwt.encode(payload, "attacker-secret", algorithm="HS256", headers={"kid": "test-key"}),
        jwt.encode(payload, "", algorithm="none", headers={"kid": "test-key"}),
        jwt.encode(payload, identity_provider.key, algorithm="RS256"),
        jwt.encode(payload, identity_provider.key, algorithm="RS256", headers={"kid": "unknown"}),
        jwt.encode(
            payload,
            identity_provider.key,
            algorithm="RS256",
            headers={"kid": "test-key", "crit": ["unexpected"]},
        ),
        "x" * 17000,
    ]
    for token in tokens:
        assert client.get("/documents", headers=headers(token)).status_code == 401
    assert store.calls == []


def test_jwks_cache_rotation_and_untrusted_jku(authenticated_api, identity_provider):
    client, _ = authenticated_api
    original = identity_provider.token()
    payload = jwt.decode(original, options={"verify_signature": False})
    token = jwt.encode(
        payload,
        identity_provider.key,
        algorithm="RS256",
        headers={"kid": "test-key", "jku": "https://attacker.invalid/keys"},
    )
    assert client.get("/documents", headers=headers(token)).status_code == 200
    requests_before = identity_provider.state["requests"]
    assert client.get("/documents", headers=headers(token)).status_code == 200
    assert identity_provider.state["requests"] == requests_before
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="rotated", use="sig", alg="RS256")
    identity_provider.state["keys"].append(jwk)
    rotated = jwt.encode(payload, key, algorithm="RS256", headers={"kid": "rotated"})
    assert client.get("/documents", headers=headers(rotated)).status_code == 200
    assert identity_provider.state["requests"] > requests_before


@pytest.mark.parametrize(
    "roles,status", [(("reader",), 403), ((), 403), (("uploader",), 200), (("tenant_admin",), 200)]
)
def test_upload_roles_and_trusted_metadata(authenticated_api, identity_provider, roles, status):
    client, store = authenticated_api
    response = client.post(
        "/documents/upload",
        headers=headers(identity_provider.token(roles=roles)),
        files={"file": ("secret.txt", "sensitive document body")},
        data={"tenant_id": "tenant-b", "owner_id": "mallory", "visibility": "tenant"},
    )
    assert response.status_code == status
    if status == 200:
        payload = store.chunks[0].metadata
        assert payload["tenant_id"] == "tenant-a"
        assert payload["owner_id"] == "alice"
        assert payload["visibility"] == "private"
        assert payload["allowed_subjects"] == []
        assert payload["document_id"] == response.json()["document_id"]
    else:
        assert store.chunks == []


@pytest.mark.parametrize(
    "roles,status",
    [
        ((), 403),
        (("unrelated",), 403),
        (("reader",), 200),
        (("uploader",), 200),
        (("tenant_admin",), 200),
    ],
)
def test_read_roles(authenticated_api, identity_provider, roles, status):
    assert (
        authenticated_api[0]
        .get("/documents", headers=headers(identity_provider.token(roles=roles)))
        .status_code
        == status
    )


def test_context_boundary_prevents_llm_leak_even_if_adapter_is_faulty(
    authenticated_api, identity_provider
):
    client, store = authenticated_api
    safe = dict(
        acl_version=1,
        tenant_id="tenant-a",
        owner_id="alice",
        visibility="private",
        allowed_subjects=[],
    )
    payloads = [
        safe,
        {**safe, "tenant_id": "tenant-b"},
        {**safe, "owner_id": "bob"},
        {},
        {**safe, "tenant_id": ["tenant-a"]},
    ]
    store.results = [
        VectorSearchResult(
            "SAFE" if i == 0 else "FORBIDDEN-CONTENT",
            "safe.txt" if i == 0 else "forbidden.txt",
            0,
            1.0,
            authorization=p,
        )
        for i, p in enumerate(payloads)
    ]
    observed = []

    class SpyLLM:
        provider_name = model_name = "spy"

        def generate_answer(self, question, retrieved_context, prompt):
            assert "FORBIDDEN" not in prompt
            assert [r.chunk_text for r in retrieved_context] == ["SAFE"]
            observed.append(prompt)
            return "safe answer"

    main.app.dependency_overrides[main.get_llm_provider] = SpyLLM
    token = identity_provider.token()
    response = client.post("/ask", headers=headers(token), json={"question": "scheduling"})
    assert response.status_code == 200 and response.json()["retrieved_chunks"] == 1
    assert "forbidden" not in response.text.lower()
    assert len(observed) == 1
    response = client.post("/search", headers=headers(token), json={"query": "scheduling"})
    assert len(response.json()["results"]) == 1
    assert store.calls[0].tenant_id == "tenant-a"


def test_audit_json_redacts_credentials_contents_and_filenames(
    authenticated_api, identity_provider, monkeypatch
):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    monkeypatch.setattr(audit_logger, "handlers", [handler])
    client, _ = authenticated_api
    token = identity_provider.token(roles=("uploader",))
    client.get("/documents", headers=headers("secret-invalid-token"))
    client.post(
        "/documents/upload",
        headers=headers(identity_provider.token()),
        files={"file": ("sensitive-filename.txt", "CLASSIFIED-CONTENTS")},
    )
    client.post(
        "/documents/upload",
        headers=headers(token),
        files={"file": ("sensitive-filename.txt", "CLASSIFIED-CONTENTS")},
    )
    client.get("/documents", headers=headers(token))
    raw = stream.getvalue()
    for secret in [token, "secret-invalid-token", "CLASSIFIED-CONTENTS", "sensitive-filename"]:
        assert secret not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    assert {"authentication_failure", "authorization_denial", "document_upload", "access"} <= {
        row["event"] for row in records
    }
    assert all("time" in row for row in records)


def test_auth_configuration_fails_closed():
    for issuer, jwks in [
        ("", ""),
        ("http://idp.invalid", "http://idp.invalid/jwks"),
        ("https://idp.invalid", "http://idp.invalid/jwks"),
        ("https://user:password@idp.invalid", "https://idp.invalid/jwks"),
    ]:
        with pytest.raises(ValueError):
            JWTVerifier(issuer, "rag-api", jwks)
    with pytest.raises(ValueError):
        JWTVerifier("https://idp.invalid", "", "https://idp.invalid/jwks")


def test_admin_cannot_cross_tenants_or_read_legacy_acl():
    admin = Principal("tenant-a", "admin", frozenset({"tenant_admin"}))
    assert not can_read(admin, {})
    assert not can_read(
        admin,
        dict(
            tenant_id="tenant-b",
            owner_id="bob",
            acl_version=1,
            visibility="tenant",
            allowed_subjects=[],
        ),
    )


def test_permissions_schema_rejects_owner_tenant_and_invalid_ids(
    authenticated_api, identity_provider
):
    client, _ = authenticated_api
    for body in [
        {"visibility": "public"},
        {"owner_id": "mallory"},
        {"tenant_id": "tenant-b"},
        {"allowed_subjects": [""]},
        {"allowed_subjects": ["alice"] * 101},
    ]:
        assert (
            client.patch(
                f"/documents/{uuid4()}/permissions",
                json=body,
                headers=headers(identity_provider.token(roles=("uploader",))),
            ).status_code
            == 422
        )


def test_identity_provider_outage_fails_closed(authenticated_api, identity_provider, monkeypatch):
    def unavailable(*args):
        raise jwt.PyJWKClientConnectionError("internal-provider-error")

    monkeypatch.setattr(identity_provider.verifier.jwks, "get_signing_key_from_jwt", unavailable)
    response = authenticated_api[0].get("/documents", headers=headers(identity_provider.token()))
    assert response.status_code == 503
    assert "internal-provider-error" not in response.text


def test_unconfigured_auth_prevents_startup(monkeypatch):
    for name in ["OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL"]:
        monkeypatch.delenv(name, raising=False)
    main.app.dependency_overrides.clear()
    with pytest.raises(ValueError, match="trusted HTTPS"):
        with TestClient(main.app):
            pass


def test_upload_and_management_require_bearer(authenticated_api):
    client, store = authenticated_api
    assert (
        client.post("/documents/upload", files={"file": ("secret.txt", "secret")}).status_code
        == 401
    )
    assert (
        client.patch(f"/documents/{uuid4()}/permissions", json={"visibility": "tenant"}).status_code
        == 401
    )
    assert store.chunks == []


def test_metrics_requires_admin(authenticated_api, identity_provider):
    client, _ = authenticated_api
    assert client.get("/metrics", headers=headers(identity_provider.token())).status_code == 403
    assert (
        client.get(
            "/metrics", headers=headers(identity_provider.token(roles=("tenant_admin",)))
        ).status_code
        == 200
    )


def test_unknown_key_refresh_is_bounded(authenticated_api, identity_provider):
    client, _ = authenticated_api
    # Populate the ordinary cached signing set first.
    assert client.get("/documents", headers=headers(identity_provider.token())).status_code == 200
    before = identity_provider.state["requests"]
    payload = jwt.decode(identity_provider.token(), options={"verify_signature": False})
    for kid in ["unknown-1", "unknown-2", "unknown-3"]:
        token = jwt.encode(payload, identity_provider.key, algorithm="RS256", headers={"kid": kid})
        assert client.get("/documents", headers=headers(token)).status_code == 401
    assert identity_provider.state["requests"] == before + 1
