# Remaining Phase 2 live Keycloak validation

**Status: BLOCKED.** Branch `feature/tenant-authz`, base commit `d2a2a59`.
No real Keycloak instance, realm, clients, or sample users could be created in this run.
Real Keycloak token issuance, provider-specific claim mapping, and live signing-key rotation
remain unverified. The previous Phase 2 core acceptance results are preserved; they do not
replace this remaining live-provider validation.

## Exact access blockers

| Source | Failing host/stage | Actual outcome |
| --- | --- | --- |
| `docker pull quay.io/keycloak/keycloak:26.1.4` | `quay.io`, registry `GET https://quay.io/v2/`, before manifest/layer fetch | Docker: `Forbidden` (403); consistent with the unlisted registry/policy, but the daemon message does not independently distinguish proxy from remote service |
| Official GitHub ZIP distribution | `release-assets.githubusercontent.com`, HTTPS CONNECT after redirect from `github.com/keycloak/keycloak/releases/download/26.1.4/keycloak-26.1.4.zip` | `Tunnel connection failed: 403 Forbidden`; proxy denial before remote TLS, not a Keycloak service response |

Neither failing host is listed in the environment network policy. Runtime enforcement state
is reported as unknown; these actual requests establish the access failure. Java 21 is
available (`openjdk 21.0.12.1`), so allowing **`release-assets.githubusercontent.com`** through
the supported environment configuration would enable the official native-distribution path
without needing a container registry. Apply that configuration change, then retry the
original official GitHub download, verify the release artifact, and execute the live test.
No proxy bypass, policy change, repeated identical download, or TLS disablement was attempted.

## Completed independent checks

- A disposable real Qdrant v1.12.6 instance used a newly generated **nonempty** service key.
  Missing and incorrect keys returned **HTTP 401**; the correct key authenticated successfully.
- Full Phase 1/2 regressions against that keyed service: **95 passed, 0 failed, 1 skipped**,
  36.91 seconds. The skip is exclusively the new opt-in live Keycloak test. Existing real CPU
  model ingestion/search/ask, offline restart, two-tenant isolation, sharing revocation,
  unauthorized-context exclusion from the LLM, JWT claims, and synthetic JWKS rotation ran.
- The direct Qdrant client in the existing compatibility integration test now honors
  `QDRANT_API_KEY`, matching the application client and enabling secure-backend regression runs.
- Five warnings: one existing Starlette/AnyIO deprecation and four Qdrant client warnings
  about API keys over plaintext **loopback-only development HTTP**. This is not TLS validation;
  production still requires private/TLS transport and managed secrets.
- Ruff, Python compilation, and diff hygiene passed. No application implementation, encoder,
  model artifacts, Terraform, or existing vector data changed.

Raw regression output: [keyed regressions](keycloak-keyed-regressions.txt).
Machine-readable results: [validation results](keycloak-validation-results.json).

## Prepared development setup and actual attempt

Added `tests/keycloak_fixtures.py` and `tests/test_keycloak_integration.py`, with explicit
opt-in selection and no automatic artifact downloading. They define a loopback-only native
Keycloak dev process, in-memory realm, confidential test client, administrator-managed tenant
attributes, sample users for both tenants, and real provider RSA rotation. Passwords, bootstrap
credentials, client secrets and Qdrant keys are random and kept in memory. No reusable test
credentials are committed. No authentication or model implementation is rewritten.

The live test was explicitly selected with:

```bash
RUN_KEYCLOAK_INTEGRATION=1 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests/test_keycloak_integration.py -q
```

Actual result: **one setup error** in 0.03 seconds because the official distribution is missing:
`Install the official Keycloak 26.1.4 distribution and set KEYCLOAK_HOME; the opt-in live test
cannot use the synthetic JWKS fixture`. Zero live-provider functional cases executed.
Therefore the new provisioning/issuance/rotation path is **prepared but not runtime-verified**.
See [development setup and rerun command](../docs/keycloak-validation.md).

The keyed regression runner used `QDRANT_URL` and a random `QDRANT_API_KEY` in its child process,
with all three existing integration opt-ins enabled. Credentials were neither printed nor
retained. The equivalent pytest invocation after provisioning a keyed local server is:

```bash
export HF_HOME=/workspace/.cache/phase1-embeddings
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
# Supply QDRANT_URL and its nonempty QDRANT_API_KEY through the trusted runtime environment.
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 RUN_SECURITY_INTEGRATION=1 \
  RUN_KEYCLOAK_INTEGRATION=0 /workspace/.cache/phase1-final/venv/bin/python \
  -m pytest services/rag-api/tests -q
/workspace/.cache/phase1-final/venv/bin/python -m ruff check services/rag-api
/workspace/.cache/phase1-final/venv/bin/python -m compileall -q services/rag-api/app services/rag-api/tests
git diff --check
```

## Remaining production-readiness gaps

1. Complete real Keycloak provisioning, issuance, role/tenant mapper compatibility, and live
   rotation validation after artifact access is restored; do not infer success from fixtures.
2. Use a reviewed/supported production IdP version, HTTPS, hardened client flows (PKCE or
   service accounts), administrator-controlled claims, durable IdP storage, backups/HA,
   secret management and ingress rate/size limits. The password grant and `start-dev` here
   are exclusively disposable validation settings.
3. Verify retired-key behavior after cache expiry and real deployment key-overlap policy;
   the API has a 300-second key-set TTL and 30-second unknown-key refresh bound.
4. Preserve the already documented short-lived-token/introspection limitations, in-flight
   permission-revocation semantics, private/TLS Qdrant access, and protected durable audit
   collection. No production deployment or remote CI/security scan was performed.

No push, merge, live deployment, Phase 3, or unrelated Terraform change was performed.
