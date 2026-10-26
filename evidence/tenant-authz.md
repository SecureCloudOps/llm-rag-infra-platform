# Phase 2 tenant authentication and authorization evidence

Follow-up: [real Keycloak development validation](keycloak-validation.md) now passes with
the official digest-pinned Quay image and 96 tests. The original 95-test Phase 2 acceptance
record below predates that live-provider follow-up.

**Acceptance: PASS.** Local branch `feature/tenant-authz`, based on accepted Phase 1
`b10759f79a15f7a6cf89709261ff7eb4e9f30bb2`. No branch push, merge, live deployment,
Terraform changes, or Phase 3 work was performed.

## Engineering decisions

- Require RS256 JWT access tokens and an explicitly configured HTTPS issuer/audience/JWKS.
  Validate signature, expiry, iat/optional nbf, required claims, subject/tenant formats, access
  token type, and at least 2048-bit RSA keys. Use bounded JWKS set caching and unknown-key
  refresh throttling; never use token-supplied key URLs. Missing configuration stops startup.
- Derive immutable per-request principals from verified claims. Read is allowed to reader,
  uploader, and tenant_admin. Upload and ownership-based sharing require uploader/admin.
  Tenant administrators manage only their own tenant; metrics require tenant_admin.
- Preserve the existing CPU encoder, pinned model, batch behavior, worker lifespan, offline
  cache, cosine/dimension/model-identity checks, and explicit test mocks. The encoder source
  and benchmark corpus/questions are byte-identical to Phase 1.
- Default uploads to private, stamp every chunk with verified tenant/owner and versioned ACLs,
  and return the generated document UUID. Add owner/same-tenant-admin sharing replacement.
  Grant private reads to owner or explicit subjects, or tenant-wide reads when requested.
- Apply tenant and ACL conditions inside Qdrant before ranking, including document counts.
  Add payload indexes, strict payload checks, and another API authorization boundary before
  serialization/prompt construction. Missing or malformed ACLs are hidden even from admins.
- Preserve existing data and use a new `documents-minilm-v2-acl` collection default. Reingest
  retained files with verified owner identities; do not guess legacy tenant ownership.
- Emit JSON audit events with only safe metadata and hashed actor/tenant references. Disable
  generic Uvicorn access logging; use metric route templates. Never log bearer tokens,
  credentials, filenames, document contents, questions, prompts, or model outputs in audits.
- Update local Compose OIDC settings/private Qdrant bindings, require a nonempty Compose service Qdrant key,
  require operator OIDC configuration for Kubernetes, and retain the existing published image
  reference. Update authenticated smoke tools to consume token files rather than token arguments.

## Actual outcomes

| Check | Result |
| --- | --- |
| Full host suite, all integration opt-ins enabled | **95 passed, 0 failed, 0 skipped**, 35.34 seconds |
| Security suite inside final non-root image, actual Qdrant/model | **45 passed, 0 failed, 0 skipped**, 28.48 seconds |
| Genuine model | Phase 1 MiniLM revision, CPU, 384-dimensional vectors |
| Tenant isolation | Tenant A/B documents and counts remain isolated, including identical subject IDs across tenants |
| Document permissions | Owner/private, explicit grants, tenant sharing, admin scope, and revocation passed |
| LLM boundary | Spy verifies only authorized source names and document text occur in context/prompt; faulty-adapter test also passed |
| JWT/OIDC | Invalid signature/alg/issuer/audience/expiry/claims rejected; JWKS cache, rotation, outage and unknown-key refresh bound passed |
| Audit | JSON parsing, event coverage, and credential/content/filename redaction passed |
| Phase 1 regression | All original 50 cases, including both real Qdrant/semantic integrations, passed with explicit test authentication |
| Docker build | Passed, image `sha256:11af6fb240ed740b610c8c05c352eef1033737b597bdb9977a3779f146f63d7b` |
| Qdrant service-key smoke | Disposable real Qdrant denied unauthenticated access (401); configured application client authenticated successfully |
| Dependency checks | Host and final image: No broken requirements found |
| Ruff / Python compile / shell syntax / diff hygiene | Passed |
| Compose configuration | Passed with non-secret OIDC placeholders and an ephemeral nonempty service key |
| Kubernetes rendering | Base 29 resources, Kind 27; required OIDC ConfigMap reference verified |

Each pytest run reported one non-failing Starlette/AnyIO BlockingPortal deprecation warning.
Raw outputs are [host tests](tenant-authz-tests.txt) and
[container tests](tenant-authz-container-tests.txt). [Machine-readable results](tenant-authz-results.json).

The real security integration uses **production environment-based OIDC initialization**;
there is no authentication dependency override in that test. Its ephemeral local JWKS issuer
signs real RSA JWTs; HTTP is allowed explicitly only for literal loopback test URLs. All
actual signature/claim/role verification still executes. Earlier unit tests intentionally
inject identities/embeddings to retain isolated endpoint tests, not production bypasses.
The security integration's sole service override is the LLM spy, which inspects the actual
retrieved context and constructed prompt after real CPU/Qdrant retrieval.

The Docker security run uses the actual installed image package, mounted test sources, a
read-only verified model cache, and the existing private Qdrant network. Finalization exposed
and fixed non-root read access to copied pyproject/README metadata; the final image was rebuilt
and its full security suite passed. No model download or network troubleshooting was repeated.

## Exact reproduction commands

From the repository root, the local validation environment was
`V=/workspace/.cache/phase1-final/venv`. New dependencies installed successfully from actual
PyPI artifacts: PyJWT 2.10.1, cryptography 44.0.2, cffi 1.17.1, pycparser 2.22. The full lock
preserves the Phase 1 CPU stack. Docker builds use the inherited platform proxy and combined
CA bundle; TLS verification remains enabled.

```bash
V=/workspace/.cache/phase1-final/venv
# New auth dependency installation during this execution:
$V/bin/pip --isolated install --retries 0 --index-url https://pypi.org/simple \
  'PyJWT[crypto]==2.10.1' 'cryptography==44.0.2' 'cffi==1.17.1' 'pycparser==2.22'
$V/bin/pip --isolated install --no-deps --no-build-isolation -e services/rag-api
# For fresh environments install the complete committed requirements.lock first.
export HF_HOME=/workspace/.cache/phase1-embeddings
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 RUN_SECURITY_INTEGRATION=1 \
  QDRANT_URL=http://localhost:6333 $V/bin/python -m pytest services/rag-api/tests -q
$V/bin/python -m pip check
$V/bin/python -m ruff check services/rag-api benchmarks/semantic-retrieval scripts/semantic-container-smoke.py
$V/bin/python -m compileall -q services/rag-api/app services/rag-api/tests scripts/semantic-container-smoke.py
bash -n scripts/compose-smoke-test.sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t rag-api:tenant-authz services/rag-api
docker run --rm --network llm-rag-infra-platform_default \
  --mount type=bind,src=/workspace/.cache/phase1-embeddings/hub,dst=/models,readonly \
  --mount type=bind,src=/workspace/llm-rag-infra-platform/services/rag-api/tests,dst=/tests,readonly \
  -e QDRANT_URL=http://qdrant:6333 \
  -e NO_PROXY=qdrant,localhost,127.0.0.1 -e no_proxy=qdrant,localhost,127.0.0.1 \
  -e EMBEDDING_CACHE_DIR=/models -e HF_HOME=/tmp/huggingface \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e RUN_SECURITY_INTEGRATION=1 \
  --entrypoint python rag-api:tenant-authz -m pytest -c /app/pyproject.toml \
  /tests/test_security.py /tests/test_security_integration.py -q -p no:cacheprovider
docker run --rm --network none --entrypoint python rag-api:tenant-authz -m pip check
QDRANT_API_KEY="$(openssl rand -hex 32)" \
  OIDC_ISSUER=https://identity.example.invalid/realms/rag OIDC_AUDIENCE=rag-api \
  OIDC_JWKS_URL=https://identity.example.invalid/realms/rag/protocol/openid-connect/certs \
  docker compose config --quiet
/workspace/.local/bin/kubectl kustomize k8s/ > /workspace/.cache/phase2/k8s.yaml
/workspace/.local/bin/kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/kind \
  > /workspace/.cache/phase2/kind.yaml
git diff --check
```

## Operational limitations

No live Keycloak realm, identity accounts, tokens, provider network grants, metrics scrape
credentials, or production Qdrant secrets were provisioned. A random temporary service key
was used only for the disposable Qdrant/config smoke and was not retained or printed.
An empty Qdrant key was found to enable authentication without a usable client key; Compose
now rejects empty keys instead of producing that broken configuration. Configure a trusted HTTPS provider
and administrator-controlled tenant/role mappings before use. Kubernetes remains render-only;
no remote CI, external security scans, live deployment, or image/branch publication occurred.
The authenticated operator smoke scripts were updated and syntax/lint checked; they were not
run with a live external IdP token. Container validation instead runs the automated genuine-JWT
security suite, including real model/Qdrant integration, through FastAPI's complete ASGI lifecycle.

JWT validation is local, not online introspection; use short-lived tokens. Cached key sets have
a bounded TTL, and negative-key refresh throttling can delay key rotation recognition briefly.
Permission revocation applies to the next retrieval; in-flight requests may finish under the
policy they read. Protect Qdrant as trusted infrastructure, use production TLS/secrets and ingress
limits, and protect audit transport/retention. The code does not claim native Qdrant row-level
security or a durable external audit store. Synthetic integration collections remain for inspection;
existing vector data was not deleted. No Phase 1 benchmark rerun was needed; its encoder, model
revision, chunker, and evaluation inputs were preserved.

See [security configuration, role matrix, API policy and migration](../docs/tenant-authz.md).
