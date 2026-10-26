# Development-only live Keycloak validation

This is an opt-in extension of the Phase 2 security suite. **Its live Keycloak path is
currently unverified:** the managed environment denied both official artifact download
routes before an instance could start. See [actual results](../evidence/keycloak-validation.md).
Existing synthetic-JWKS tests are not evidence of real Keycloak issuance.

## Prerequisites

- A private, disposable local test environment, Java 21, and the official **Keycloak 26.1.4**
  ZIP distribution extracted into a fresh writable directory outside the repository.
  This is a development validation pin, not a production-version recommendation.
- The installed Phase 1/2 CPU dependencies and previously verified MiniLM hub cache.
- The managed local Docker daemon with cached `qdrant/qdrant:v1.12.6`.
- Allow `github.com` and the release redirect host `release-assets.githubusercontent.com`
  for the official distribution route. The original GitHub URL is:
  `https://github.com/keycloak/keycloak/releases/download/26.1.4/keycloak-26.1.4.zip`.
  Keep HTTPS certificate verification and the configured proxy enabled. Verify the official
  release artifact/checksum before extraction; no artifact was downloaded or verified here.
  The container alternative is `quay.io/keycloak/keycloak:26.1.4`, but that registry was also denied.

Do not point `KEYCLOAK_HOME` at a production/shared installation. The test launches `start-dev`
with an in-memory database and loopback-only HTTP. It does not connect to an existing realm,
change the working application's authentication requirements, or deploy infrastructure.

## Run

From the repository root, in the installed validation environment:

```bash
export KEYCLOAK_HOME=/workspace/.cache/keycloak-validation/keycloak-26.1.4
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HOME=/workspace/.cache/phase1-embeddings
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests/test_keycloak_integration.py -q
```

The native Keycloak fixture creates a fresh random realm, a bearer resource client,
a confidential test client with an explicit API audience/tenant/realm-role mapper,
and five users across two tenants (`a-reader`, `a-owner`, `a-admin`, `b-owner`, `b-admin`).
The tenant profile attribute is administrator-editable only. All passwords, client secrets,
bootstrap credentials, and the Qdrant service key are generated at runtime and are never
committed or printed. A local temporary log is private and removed on teardown. Do not enable
HTTP/body debug logging or pytest `--showlocals` when running credential-bearing tests.

For test issuance only, this disposable confidential client enables direct password grants.
**Do not copy that grant configuration, HTTP transport, or `start-dev` mode to production.**
Use authorization code + PKCE for browser clients and appropriately scoped service accounts.
The application permits HTTP OIDC only through its existing explicit literal-loopback exception.

The test definition covers:

1. Actual discovery and token issuance through Keycloak's token endpoint.
2. Full existing FastAPI ASGI startup with production environment-based JWT configuration,
   the real pinned CPU model, and a disposable API-key-protected Qdrant service.
3. Reader upload denial, uploader/admin uploads, private/tenant sharing, owner/admin boundaries,
   tenant-scoped counts/search, and an LLM spy checking actual prompt/context authorization.
4. Keycloak RSA signing-provider rotation to a higher priority, recognition of the new `kid`,
   and overlap acceptance of the previous still-valid token. This does not test automatic
   retired-key rejection after the entire five-minute JWKS cache lifetime.
5. Rejection of missing credentials, a modified genuine signature, and an expired token
   issued by Keycloak itself. Existing regressions additionally cover issuer/audience,
   algorithm, malformed claims, JWKS outage, and synthetic key-rotation cases.

The live test does not override authentication, embeddings, or storage. Its only service
observation override is the LLM spy. Both the native Keycloak process and its disposable
Qdrant container are stopped on teardown. Existing containers/collections are untouched.

If `RUN_KEYCLOAK_INTEGRATION` is unset the test is skipped. If explicitly selected without
an installed distribution, it fails setup rather than substituting a fake issuer. Until
this test executes successfully against the official distribution, its provisioning and
rotation code must be treated as prepared test scaffolding, not validated Keycloak support.
