"""Signed JWT -> genuine CPU encoder -> real Qdrant -> LLM boundary."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_security import headers

from app import main
from app.vector_store import VectorStoreChunk

pytestmark = [
    pytest.mark.security,
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_SECURITY_INTEGRATION") != "1",
        reason="set RUN_SECURITY_INTEGRATION=1 with real Qdrant and the pinned CPU model cache",
    ),
]


def test_two_tenants_real_semantic_api_and_llm_isolation(identity_provider, monkeypatch):
    monkeypatch.setenv("COLLECTION_NAME", "security-integration-" + uuid4().hex)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "384")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("OIDC_ISSUER", identity_provider.origin + "/realms/rag")
    monkeypatch.setenv("OIDC_AUDIENCE", "rag-api")
    monkeypatch.setenv("OIDC_JWKS_URL", identity_provider.origin + "/jwks")
    monkeypatch.setenv("OIDC_ALLOW_LOOPBACK_HTTP", "true")
    identities = {
        "alice": identity_provider.token("tenant-a", "alice", ("uploader",)),
        "bob": identity_provider.token("tenant-a", "bob", ("uploader",)),
        "reader": identity_provider.token("tenant-a", "carol", ("reader",)),
        "admin": identity_provider.token("tenant-a", "admin", ("tenant_admin",)),
        "b": identity_provider.token("tenant-b", "alice", ("tenant_admin",)),
    }
    documents = {}
    llm_calls = []
    expected_context = set()

    class SpyLLM:
        provider_name = model_name = "security-spy"

        def generate_answer(self, question, retrieved_context, prompt):
            filenames = {r.filename for r in retrieved_context}
            assert filenames <= expected_context
            for filename, item in documents.items():
                if filename not in expected_context:
                    assert item["text"] not in prompt
                    assert filename not in prompt
            llm_calls.append(filenames)
            return "Authorized context only"

    main.app.dependency_overrides[main.get_llm_provider] = SpyLLM
    with TestClient(main.app) as client:
        assert main.app.state.embedding_provider.identity["provider"] == "sentence_transformers"
        assert str(main.app.state.embedding_provider._model.device) == "cpu"

        def upload(actor, filename, marker):
            text = "Kubernetes workload scheduling assigns pods to suitable worker nodes. " + marker
            response = client.post(
                "/documents/upload",
                headers=headers(identities[actor]),
                files={"file": (filename, text)},
                data={
                    "tenant_id": "tenant-b" if actor != "b" else "tenant-a",
                    "owner_id": "attacker",
                },
            )
            assert response.status_code == 200, response.text
            documents[filename] = dict(id=response.json()["document_id"], text=text)

        upload("alice", "alice-private.txt", "ALICE-PRIVATE-SECRET")
        upload("bob", "bob-private.txt", "BOB-PRIVATE-SECRET")
        upload("bob", "shared-with-carol.txt", "CAROL-SHARED-SECRET")
        upload("b", "tenant-b.txt", "TENANT-B-SECRET")
        doc_id = documents["shared-with-carol.txt"]["id"]

        def change(actor, doc, **permissions):
            return client.patch(
                f"/documents/{doc}/permissions",
                headers=headers(identities[actor]),
                json=permissions,
            )

        assert change("bob", doc_id, allowed_subjects=["carol"]).status_code == 200
        assert (
            change(
                "b",
                documents["tenant-b.txt"]["id"],
                visibility="tenant",
                allowed_subjects=["alice", "carol", "admin"],
            ).status_code
            == 200
        )
        # Attempts to manage another owner's or tenant's document reveal no existence.
        assert (
            change("alice", documents["bob-private.txt"]["id"], visibility="tenant").status_code
            == 404
        )
        assert (
            change("admin", documents["tenant-b.txt"]["id"], visibility="tenant").status_code == 404
        )
        assert change("b", doc_id, visibility="tenant").status_code == 404
        assert change("reader", doc_id, visibility="tenant").status_code == 403
        assert change("alice", str(uuid4()), visibility="tenant").status_code == 404

        # Narrow top-k must still retrieve the only permitted document: filtering
        # happens inside Qdrant before ranking, not by dropping other tenants later.
        one = client.post(
            "/search",
            headers=headers(identities["reader"]),
            json={"query": "Kubernetes workload scheduling", "top_k": 1},
        )
        assert [r["filename"] for r in one.json()["results"]] == ["shared-with-carol.txt"]
        store = main.app.state.vector_store
        vector = main.app.state.embedding_provider.embed("Kubernetes workload scheduling")
        # Legacy content without ACLs and corrupt tenant metadata must never be surfaced.
        store.add_chunks(
            [
                VectorStoreChunk(
                    "LEGACY-SECRET",
                    vector,
                    {
                        "document_id": str(uuid4()),
                        "chunk_text": "LEGACY-SECRET",
                        "filename": "legacy.txt",
                    },
                ),
                VectorStoreChunk(
                    "CORRUPT-SECRET",
                    vector,
                    {
                        "document_id": str(uuid4()),
                        "chunk_text": "CORRUPT-SECRET",
                        "filename": "corrupt.txt",
                        "acl_version": 1,
                        "tenant_id": ["tenant-a", "tenant-b"],
                        "owner_id": "alice",
                        "visibility": "tenant",
                        "allowed_subjects": [],
                    },
                ),
            ]
        )
        expectations = {
            "alice": {"alice-private.txt"},
            "bob": {"bob-private.txt", "shared-with-carol.txt"},
            "reader": {"shared-with-carol.txt"},
            "admin": {"alice-private.txt", "bob-private.txt", "shared-with-carol.txt"},
            "b": {"tenant-b.txt"},
        }
        for actor, expected in expectations.items():
            expected_context.clear()
            expected_context.update(expected)
            auth = headers(identities[actor])
            assert client.get("/documents", headers=auth).json() == {
                "total_documents": len(expected),
                "total_chunks": len(expected),
            }
            search = client.post(
                "/search",
                headers=auth,
                json={"query": "Kubernetes workload scheduling", "top_k": 100},
            )
            assert search.status_code == 200
            assert {r["filename"] for r in search.json()["results"]} == expected
            response = client.post(
                "/ask", headers=auth, json={"question": "Kubernetes workload scheduling"}
            )
            assert response.status_code == 200
            assert {r["filename"] for r in response.json()["sources"]} <= expected
            assert "LEGACY-SECRET" not in response.text and "CORRUPT-SECRET" not in response.text
            assert len(main.app.state.embedding_provider.embed("validation")) == 384

        assert len(llm_calls) == len(expectations)
        # Revoke a grant, then check both retrieval and LLM context on the next request.
        assert change("bob", doc_id, allowed_subjects=[]).status_code == 200
        expected_context.clear()
        auth = headers(identities["reader"])
        assert client.get("/documents", headers=auth).json()["total_documents"] == 0
        assert (
            client.post("/search", headers=auth, json={"query": "Kubernetes"}).json()["results"]
            == []
        )
        assert (
            client.post("/ask", headers=auth, json={"question": "Kubernetes"}).json()["sources"]
            == []
        )
        assert llm_calls[-1] == set()
        # Tenant admin may grant same-tenant access without changing ownership/tenant.
        assert (
            change("admin", documents["alice-private.txt"]["id"], visibility="tenant").status_code
            == 200
        )
        expected_context.add("alice-private.txt")
        assert (
            client.post("/ask", headers=auth, json={"question": "Kubernetes"}).json()["sources"][0][
                "filename"
            ]
            == "alice-private.txt"
        )
        assert store.get_stats().total_chunks == 6  # no vector data was deleted
