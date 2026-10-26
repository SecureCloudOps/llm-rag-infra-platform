# Development-only live Keycloak validation

Live-provider development acceptance passed on 2026-10-26: **96 tests passed, zero skipped**
with real Keycloak issuance, the existing FastAPI application, the actual pinned CPU model,
and API-key-protected Qdrant. See [actual evidence](../evidence/keycloak-validation.md).

## Official container and prerequisites

The test uses Keycloak 26.1.4 from the official Quay repository, pinned to its verified
multi-platform digest:

```text
quay.io/keycloak/keycloak@sha256:044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761
```

Docker selects Linux amd64 here. `--version` reported Keycloak 26.1.4 with bundled OpenJDK
21.0.6. Host Java and GitHub release archives are no longer needed. This is a reproducible
development pin, not a production image/version recommendation; review current support and
security updates before production use.

Required: a private local test environment, Docker, the installed Phase 1/2 Python CPU lock,
the verified MiniLM hub cache, and cached `qdrant/qdrant:v1.12.6`. The successful image pull
used allowed hosts `quay.io` and `cdn01.quay.io`. Keep the configured proxy, TLS verification,
and Docker registry configuration. If another registry delivery hostname is actually reported,
request that exact destination through the environment configuration workflow.

## Run the live-provider test

From the repository root, pull the pinned image once, then run:

```bash
docker pull quay.io/keycloak/keycloak@sha256:044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HOME=/workspace/.cache/phase1-embeddings
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests/test_keycloak_integration.py -q
```

Use the interpreter from your installed environment if its path differs. Model offline flags
apply to the encoder; Keycloak authentication uses the actual local discovery/token/JWKS HTTP
endpoints. The fixture uses `--pull=never` and fails explicitly if the pinned image is absent.
It never substitutes a synthetic issuer. Without `RUN_KEYCLOAK_INTEGRATION=1` this opt-in case
is skipped. The existing integration CI job now pulls the same image and enables the flag.

The fixture owns and removes two disposable containers. Keycloak uses `start-dev`, an in-memory
database, a random published port bound to **127.0.0.1**, and a UUID-named realm. Qdrant uses a
separate random loopback port and nonempty random API key. Missing/wrong keys must return 401
before the application is tested. Existing application containers, Qdrant collections/volumes,
and production/provider configurations are untouched.

Bootstrap passwords, user passwords, client secrets, and Qdrant keys are generated at runtime.
They are supplied by environment-variable names rather than secret command arguments, and are
never committed or printed by the fixture. Treat the Docker daemon and host as privileged: a
container environment is inspectable by its administrators. Containers and their in-memory
realm are removed during teardown. Do not enable HTTP/body debug logs or pytest `--showlocals`.
Credential-bearing assertion headers use a redacted representation.

## Realm, scopes and users

The development setup creates:

- Bearer resource client `rag-api` and confidential test client `rag-validation`.
- Explicit access-token audience, tenant attribute, and `realm_access.roles` mappers.
- Administrator-editable-only `tenant_id` profile attribute.
- Users `a-reader`, `a-owner`, `a-admin`, `b-owner`, `b-admin` across two tenants, with reader,
  uploader, and tenant_admin roles.

**Retain Keycloak 26's `basic` default client scope.** It supplies the required `sub` claim.
The initial empty-scope fixture issued tokens without `sub`, correctly rejected by the API
with 401. Restoring `basic` fixed the fixture without changing or relaxing JWT validation.

The confidential validation client enables password grants only to automate disposable test
issuance. Production should use authorization code + PKCE for browser clients and properly
scoped service accounts, with HTTPS, durable storage, secure administration and secret handling.
The application's existing explicit loopback HTTP exception is used only inside this dev test.

## Verified behavior and scope

Actual Keycloak tokens authenticate through the normal environment-configured JWT verifier.
The existing FastAPI ASGI lifecycle uses the real CPU model and real Qdrant; the only service
observation override is an LLM spy that delegates to the existing mock answer generator after
checking source and prompt authorization. The test verifies role-based upload restrictions,
private/tenant sharing, owner/admin boundaries, tenant-scoped counts/search/ask, rejection of
expired and signature-tampered tokens, and exclusion of unauthorized content from LLM input.

The test creates a higher-priority RSA signer through Keycloak's admin API. A new token has a
new `kid`; the API refreshes its JWKS and accepts it while retaining old-token overlap. It does
not wait through the default 300-second cache TTL to test retired-key removal. Existing unit
and security integration tests additionally verify issuer/audience, algorithms, malformed
claims, JWKS outage, negative-key refresh bounds, ACL revocation and corrupt/legacy metadata.

## Full regressions

With a separately configured local Qdrant server and its nonempty `QDRANT_API_KEY` supplied
through the trusted process environment, run:

```bash
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 RUN_SECURITY_INTEGRATION=1 \
  RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests -q
```

Set `QDRANT_URL` to that server and retain the model-cache/offline variables above. The live
Keycloak case provisions its own additional keyed Qdrant instance and restores the caller's
environment afterward. This execution ran all 96 tests against disposable keyed backends.
Six warnings were expected: one upstream Starlette/AnyIO deprecation and five warnings about
API keys over loopback development HTTP. Production transport/TLS, browser flows, IdP HA,
security scanning and remote CI execution remain outside this local acceptance run.
