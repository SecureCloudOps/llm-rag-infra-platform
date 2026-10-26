# Phase 2 real Keycloak validation evidence

**PASS for remaining development acceptance.** Validated 2026-10-26 on
`feature/tenant-authz`, following base `2305db8` (which contains `d2a2a59` and accepted Phase 1).
The earlier artifact-access blocker is resolved. Real Keycloak realms, clients, users,
tokens, JWKS and signing-key rotation all executed successfully.

## Artifact and runtime

Official Keycloak image, verified by Docker during pull:

```text
quay.io/keycloak/keycloak@sha256:044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761
```

Version command reported Keycloak **26.1.4**, bundled OpenJDK **21.0.6**. Local Linux amd64
image ID: `sha256:c9fd7ee1a8de8ebf03efe6d52a882a9de66646d2beb07fea03f9c1bd4aa4c96f`. Registry access and layer transfer succeeded through `quay.io` and
`cdn01.quay.io` after the user applied the allowlist updates. No new environment-policy change,
proxy bypass, disabled TLS verification, or GitHub archive download was needed in this run.
The fixture uses the immutable reference and `--pull=never`; CI now pulls that same reference.

Only disposable development containers were started. Keycloak published a random loopback
port and used `start-dev --db=dev-mem`; Qdrant v1.12.6 published its own loopback port with a
nonempty random API key. Missing/wrong keys returned **401**, and authenticated requests
succeeded. No disposable test containers remained after completion. Existing services and
vector data were preserved. No production deployment was performed.

## Observed issue and smallest fix

The first live run started Keycloak and issued actual tokens, but the reader request received
401 instead of the expected role denial 403. Redacted diagnostics identified
`MissingRequiredClaimError; missing claim=sub`. The prepared fixture disabled all default
client scopes. Keycloak 26 supplies the subject mapper through its standard **basic** scope.

Changed only the fixture's default scopes from `[]` to `["basic"]`. The same production
signature, expiration, issuer, audience, subject, tenant and access-token-type validation then
passed. No application authentication checks were weakened or replaced. JWT-bearing header
assertions now have redacted representations; compatibility failures report exception type
and missing claim names without rendering a token decode traceback.

## Actual results

| Check | Outcome |
| --- | --- |
| Focused live Keycloak/real CPU model/keyed Qdrant case | **1 passed**, 0 failed/skipped, 25.80 s, 2 warnings |
| Complete Phase 1/2 suite, all four integration opt-ins enabled | **96 passed**, 0 failed/skipped, 56.14 s, 6 warnings |
| Real discovery and token issuance | Passed for all five development users |
| Reader / uploader / tenant_admin permissions | Reader upload 403; uploader/admin upload 200 |
| Ownership / tenant boundaries | Non-owner and cross-tenant permission changes 404; counts/search/ask restricted to permitted documents |
| Unauthorized LLM content | Spy checked actual retrieved context and prompt for every actor; private/foreign content excluded |
| Missing, tampered and expired credentials | HTTP 401; expiry token issued by Keycloak after reducing its lifetime |
| Key rotation | Higher-priority RSA provider generated a new kid; refreshed JWKS accepted new token and overlapping old token |
| Qdrant authentication | Nonempty random key; missing/wrong key 401; actual application queries authenticated |
| Phase 1 regression | Genuine 384-dimensional CPU inference, stored-vector checks, offline restart, collection compatibility and endpoint tests passed |
| Ruff / Python compilation / dependency consistency / diff hygiene | Passed; pip: No broken requirements found |
| CI definition | YAML parsed; same pinned image and RUN_KEYCLOAK_INTEGRATION=1 configured |
| Application/model/Terraform/evaluation inputs | Unchanged |

Raw outputs: [live test](keycloak-live-tests.txt), [full keyed regressions](keycloak-keyed-regressions.txt).
Machine-readable outcomes: [results](keycloak-validation-results.json).

The six full-suite warnings are one existing Starlette/AnyIO BlockingPortal deprecation and
five warnings about API keys over **loopback-only development HTTP**. They are not evidence of
production TLS validation. No credentials or complete bearer tokens appear in committed logs.

## Exact executed commands and environment

From the repository root, using the existing validated CPU environment:

```bash
# Successful acquisition and identity checks:
docker pull quay.io/keycloak/keycloak:26.1.4
docker run --rm --pull=never quay.io/keycloak/keycloak@sha256:044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761 --version
docker image inspect quay.io/keycloak/keycloak@sha256:044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761 --format '{{.Id}} {{.Os}}/{{.Architecture}}'

export HF_HOME=/workspace/.cache/phase1-embeddings
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests/test_keycloak_integration.py -q

/workspace/.cache/phase1-final/venv/bin/python \
  /workspace/.cache/keycloak-validation/run-quay-keyed-regressions.py
/workspace/.cache/phase1-final/venv/bin/python -m ruff check \
  services/rag-api benchmarks/semantic-retrieval scripts/semantic-container-smoke.py
/workspace/.cache/phase1-final/venv/bin/python -m compileall -q services/rag-api/app services/rag-api/tests
/workspace/.cache/phase1-final/venv/bin/python -m pip check
git diff --check
```

The local regression launcher started a separate cached Qdrant v1.12.6 container using a fresh
random key passed by environment name (no secret in argv), verified missing/wrong-key 401s,
and ran the complete pytest command below with that `QDRANT_URL` and `QDRANT_API_KEY` injected.
It then removed its own container. For reproduction with a separately provisioned keyed server:

```bash
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 RUN_SECURITY_INTEGRATION=1 \
  RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests -q
```

The Keycloak fixture itself provisions the realm/client/mappers/users through real admin REST,
uses environment-based application authentication without an authentication override, and
observes only answer generation with an LLM spy. That spy delegates to the existing mock LLM
after checking actual context/prompt. FastAPI is exercised through its complete ASGI lifecycle,
Keycloak and Qdrant through real HTTP services. The current official image replaces the native
Java/GitHub-archive fixture; no host Java installation is needed.

## Changed files and preserved behavior

- `tests/keycloak_fixtures.py`: digest-pinned official container lifecycle and required basic scope.
- `tests/test_keycloak_integration.py`: cached-image selection and token-redacted failure diagnostics.
- `pyproject.toml`: document the Docker/image requirement for the opt-in marker.
- `.github/workflows/rag-api-ci.yml`: enable live-provider integration with a pinned image pull.
- Keycloak setup/evidence documents and raw result files: replace the earlier blocker with measurements.

No application implementation, encoder, dependency pins, model assets, evaluation corpus/questions,
Terraform, or public API authorization behavior was changed. The previous fail-closed response
for missing claims was correct. The full suite confirms prior functionality with authenticated
request contexts and real model/vector-store behavior.

## Remaining production-readiness gaps

Development acceptance is complete. This isolated realm uses HTTP, an in-memory database,
`start-dev`, and password grants exclusively for automated tests. Production still needs a
reviewed/supported patched IdP image, HTTPS, durable database/backups/HA, managed secrets,
controlled tenant/role administration, hardened browser/service-account flows and ingress limits.
Image/dependency CVE scans and a production reverse-proxy/browser PKCE flow were not performed.

Live rotation verified new-key recognition and overlap. Automatic retired-key rejection after
the entire default 300-second JWKS cache TTL was not timed; maintain an overlap policy and
verify it in the deployment environment. Existing local-JWT validation/revocation limits and
in-flight ACL-change semantics remain documented. Secure external audit retention and authenticated
metrics scraping require operator provisioning.

The CI job is configured locally and was not run remotely. No push, merge, environment publication,
application deployment, Phase 3 work or existing-vector deletion was performed. All disposable
Keycloak and Qdrant test containers were removed after validation.
