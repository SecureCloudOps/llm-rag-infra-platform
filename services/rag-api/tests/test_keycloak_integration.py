"""Live Keycloak token issuance, real CPU model, and API-key protected Qdrant."""

import os
import time
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app import main
from app.llm_provider import MockLLMProvider

pytestmark = [
    pytest.mark.security,
    pytest.mark.integration,
    pytest.mark.keycloak,
    pytest.mark.skipif(
        os.getenv("RUN_KEYCLOAK_INTEGRATION") != "1",
        reason="set RUN_KEYCLOAK_INTEGRATION=1 and KEYCLOAK_HOME",
    ),
]


def test_live_keycloak_roles_tenants_rotation_and_invalid_tokens(
    dev_keycloak, keyed_qdrant, monkeypatch
):
    kc = dev_keycloak
    monkeypatch.setenv("COLLECTION_NAME", "live-keycloak-" + uuid4().hex)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "384")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OIDC_ISSUER", kc.issuer)
    monkeypatch.setenv("OIDC_AUDIENCE", "rag-api")
    monkeypatch.setenv("OIDC_JWKS_URL", kc.issuer + "/protocol/openid-connect/certs")
    monkeypatch.setenv("OIDC_ALLOW_LOOPBACK_HTTP", "true")
    discovery = kc.http.get(f"/realms/{kc.realm}/.well-known/openid-configuration")
    discovery.raise_for_status()
    assert discovery.json()["issuer"] == kc.issuer
    tokens = {name: kc.token(name) for name in kc.users}
    documents, allowed, observed = {}, set(), []

    class LLMSpy(MockLLMProvider):
        def generate_answer(self, question, retrieved_context, prompt):
            assert {row.filename for row in retrieved_context} <= allowed
            for filename, item in documents.items():
                if filename not in allowed:
                    assert filename not in prompt and item["text"] not in prompt
            observed.append({row.filename for row in retrieved_context})
            return super().generate_answer(question, retrieved_context, prompt)

    # Only answer generation is observed; token verification, encoder and Qdrant are real.
    main.app.dependency_overrides[main.get_llm_provider] = LLMSpy
    with TestClient(main.app) as api:
        assert main.app.state.vector_store.client.get_collections()
        assert str(main.app.state.embedding_provider._model.device) == "cpu"
        assert len(main.app.state.embedding_provider.embed("Kubernetes scheduling")) == 384

        def auth(name):
            return {"Authorization": "Bearer " + tokens[name]}

        def upload(name, filename, marker):
            text = "Kubernetes scheduling places pods onto suitable worker nodes. " + marker
            response = api.post(
                "/documents/upload",
                headers=auth(name),
                files={"file": (filename, text)},
                data={"tenant_id": "forged", "owner_id": "forged"},
            )
            assert response.status_code == 200
            documents[filename] = {"id": response.json()["document_id"], "text": text}

        assert api.get("/documents").status_code == 401
        assert (
            api.post(
                "/documents/upload",
                headers=auth("a-reader"),
                files={"file": ("denied.txt", "not uploaded")},
            ).status_code
            == 403
        )
        upload("a-owner", "a-private.txt", "TENANT-A-PRIVATE")
        upload("a-admin", "a-shared.txt", "TENANT-A-SHARED")
        upload("b-owner", "b-private.txt", "TENANT-B-PRIVATE")
        shared_id = documents["a-shared.txt"]["id"]
        assert (
            api.patch(
                f"/documents/{shared_id}/permissions",
                headers=auth("a-admin"),
                json={"visibility": "tenant"},
            ).status_code
            == 200
        )
        assert (
            api.patch(
                f"/documents/{shared_id}/permissions",
                headers=auth("a-owner"),
                json={"visibility": "private"},
            ).status_code
            == 404
        )
        assert (
            api.patch(
                f"/documents/{shared_id}/permissions",
                headers=auth("b-admin"),
                json={"visibility": "private"},
            ).status_code
            == 404
        )
        expected = {
            "a-reader": {"a-shared.txt"},
            "a-owner": {"a-private.txt", "a-shared.txt"},
            "a-admin": {"a-private.txt", "a-shared.txt"},
            "b-owner": {"b-private.txt"},
            "b-admin": {"b-private.txt"},
        }
        for name, filenames in expected.items():
            allowed.clear()
            allowed.update(filenames)
            assert api.get("/documents", headers=auth(name)).json() == {
                "total_documents": len(filenames),
                "total_chunks": len(filenames),
            }
            response = api.post(
                "/search", headers=auth(name), json={"query": "Kubernetes scheduling", "top_k": 10}
            )
            assert response.status_code == 200
            assert {row["filename"] for row in response.json()["results"]} == filenames
            response = api.post(
                "/ask", headers=auth(name), json={"question": "Kubernetes scheduling"}
            )
            assert response.status_code == 200
            assert {row["filename"] for row in response.json()["sources"]} == filenames
        assert len(observed) == len(expected)
        # Real Keycloak generates a higher-priority RSA signer; keep old keys for overlap.
        before = kc.token("a-reader")
        kc.rotate()
        after = kc.token("a-reader")
        assert jwt.get_unverified_header(before)["kid"] != jwt.get_unverified_header(after)["kid"]
        for token in (after, before):
            assert (
                api.get("/documents", headers={"Authorization": "Bearer " + token}).status_code
                == 200
            )
        # Tamper with a genuine signature, rather than issuing a local synthetic token.
        parts = after.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        assert (
            api.get(
                "/documents", headers={"Authorization": "Bearer " + ".".join(parts)}
            ).status_code
            == 401
        )
        # Keycloak itself issues the short-lived token; no locally signed substitute.
        kc.admin("PUT", f"/{kc.realm}", json={"accessTokenLifespan": 1})
        expired = kc.token("a-reader")
        time.sleep(2)
        assert (
            api.get("/documents", headers={"Authorization": "Bearer " + expired}).status_code == 401
        )
