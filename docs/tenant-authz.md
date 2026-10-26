# Phase 2: authenticated tenant-scoped retrieval

All document, search, ask, permission, and metrics requests require bearer authentication.
There is no production authentication-disable setting. `/health` and `/ready` expose only
service readiness/liveness and remain unauthenticated for probes. OpenAPI describes the
HTTP bearer scheme. TLS termination and request-size/rate limits belong at the trusted ingress.

## Trust boundary and OIDC configuration

Set these server-controlled values; startup fails if any are missing or insecure:

```dotenv
OIDC_ISSUER=https://identity.example.com/realms/rag
OIDC_AUDIENCE=rag-api
OIDC_JWKS_URL=https://identity.example.com/realms/rag/protocol/openid-connect/certs
```

The API accepts **RS256 access tokens** signed by an RSA key of at least 2048 bits from the
configured JWKS endpoint. It validates signature, exact issuer, API audience, expiration,
issued-at, optional not-before, nonempty subject, and trusted `tenant_id`. `exp`, `iat`, `iss`,
`aud`, `sub`, `tenant_id`, and `typ` are required; `typ` must be `Bearer` (the Keycloak access-token
claim). An ID token is not an API credential. Unknown algorithms, unsigned tokens, malformed
claims, and oversized tokens are rejected. Token `jku`, `x5u`, or embedded keys never select
an endpoint/key. Tenant and subject IDs are bounded ASCII identifiers (letters, digits,
`_.:@-`, first character alphanumeric; maximum 200 characters).

Both configured URLs require HTTPS with certificate validation. The only HTTP exception is
`OIDC_ALLOW_LOOPBACK_HTTP=true` for literal localhost/loopback addresses, used by the automated
JWKS fixture; it does not permit arbitrary insecure IdP hosts. Production must leave it unset.
The issuer and JWKS URL are separate trusted configuration, allowing a provider's documented
key endpoint; they never come from an unverified token or request header.

JWKS sets are cached for up to 300 seconds, not individual keys indefinitely. An unknown `kid`
can trigger one additional refresh per 30 seconds, serialized per worker. Planned rotations
should publish both old and new keys and use distinct key IDs. Negative lookup throttling can
delay recognition of a newly rotated key by up to 30 seconds; issuers must overlap keys.
An unavailable key endpoint fails closed (503) when a refresh is needed. Invalid credentials
produce 401 with `WWW-Authenticate: Bearer`; insufficient roles produce 403. Existing cached
keys continue to validate until their normal TTL. This service performs local JWT validation,
not per-request token introspection: use short-lived access tokens; IdP revocation/role changes
in an already issued token take effect at expiration. Apply ingress authentication rate limits.

### Keycloak setup

1. Create/use a realm with RS256 signing and an API audience named `rag-api`. Configure an
   audience mapper on clients permitted to call this API so **access tokens**, not ID tokens,
   contain that audience. Browser clients should use authorization code + PKCE; service
   accounts should use appropriately scoped confidential clients. The API does not implement
   password grants, login sessions, token issuance, or store client secrets.
2. Define realm roles `reader`, `uploader`, `tenant_admin`. Emit only appropriate assignments
   through `realm_access.roles` in the access token. Unrelated roles grant no access. Client
   roles in `resource_access` are not implicitly trusted as these API roles.
3. Add a single string `tenant_id` mapper from an **administrator-managed, immutable user or
   service-account attribute**. Disable user self-editing and arbitrary client scope overrides
   of this attribute and role assignments. Never map tenant identity from a browser-supplied
   parameter. A token represents exactly one tenant; issue a new appropriately authorized token
   for tenant switching. A tenant administrator is not a realm administrator.
4. Set the exact realm issuer, audience, and certs endpoint above. Permit this endpoint in
   the environment's network policy and configure the platform's CA trust if required.

A live Keycloak realm was not provisioned by this change. Automated tests use real RSA-signed
Keycloak-shaped access tokens and an actual HTTP JWKS server, including cache/rotation tests.

## Roles and document policy

| Operation | reader | uploader | tenant_admin |
| --- | --- | --- | --- |
| Search/ask/authorized counts | Authorized documents | Authorized documents | All ACL-tagged documents in own tenant |
| Upload | Denied | Allowed | Allowed |
| Replace sharing permissions | Denied | Own documents | Any document in own tenant |
| Operational `/metrics` | Denied | Denied | Allowed |

Uploader includes read permission. Role membership alone never grants cross-tenant access.
Metrics are aggregate service counters, without document contents or tenant identities;
restrict network access to metrics, and supply a suitably protected admin service token to
Prometheus. The former anonymous scrape configuration needs operator token/Secret provisioning.
Do not expose the Qdrant HTTP/gRPC interfaces or its administrative credentials to API users.

Uploads are **private by default** and return a generated `document_id` alongside the existing
chunk metadata. The API stamps every chunk with:

- `tenant_id` and `owner_id` from the verified token, never multipart fields or headers;
- `acl_version=1`, `visibility=private`, and `allowed_subjects=[]`;
- the existing document UUID, filename, chunk index, and chunk text.

Multipart attempts to set tenant/owner/visibility do not change these trusted defaults.
Owners with the uploader role and same-tenant administrators may replace sharing via:

```http
PATCH /documents/{document_id}/permissions
Authorization: Bearer <access token>
Content-Type: application/json

{"visibility":"private","allowed_subjects":["recipient-subject-id"]}
```

`visibility=tenant` grants read access to role-bearing users in the **same tenant**.
Private documents may be read by their owner, explicitly listed same-tenant subjects, and the
same-tenant administrator. Sharing with a subject ID that also exists in another tenant does
not grant that tenant access. Maximum 100 subject IDs. The request replaces the sharing
configuration: omitted visibility defaults to private and omitted subject list clears grants.
Tenant, owner, and schema version cannot be patched. A nonexistent, foreign-tenant, or non-owned
UUID returns the same 404 to an otherwise role-authorized caller; reader management is 403.
No document deletion or automatic ownership reassignment is introduced.

Qdrant receives tenant **and** document-permission filters before similarity ranking and before
scrolling/counting. Payload indexes support those filters. API results are checked again against
strict ACL metadata before response serialization and before prompt construction. Missing,
malformed, or legacy ACL data is hidden even from tenant administrators. `/documents` counts
only readable documents/chunks. Requests use the one existing worker CPU encoder; its revision,
normalization, model cache, collection dimensionality, and cosine checks remain unchanged.
Permission changes are checked on the next retrieval; already in-flight requests may complete
under the policy they read. Permission updates across all document chunks are filter-scoped and
waited; this is not a transaction spanning an entire retrieval/LLM operation.

## Storage and migration

The new default collection is `documents-minilm-v2-acl`. Preserve Phase 1 collections and their
embedding manifests. No automatic attribution, vector conversion, collection deletion, or ACL
backfill runs. Reingest retained source files with the intended owner's verified token into a
new versioned collection. Keep returned UUIDs and explicitly grant sharing as needed. Verify
tenant-scoped counts/retrieval before moving traffic. Documents in an explicitly reused Phase 1
collection remain hidden until securely attributed; the API has no bulk backfill endpoint.

The internal Python vector-store interface permits unscoped maintenance/benchmark calls for
trusted operators. That capability is not exposed through any API route; every data route passes
the verified principal. Run these administrative tools only with trusted access to private Qdrant.
Compose binds Qdrant development ports to 127.0.0.1; Kubernetes retains its API-to-Qdrant network
policy. `QDRANT_API_KEY` is supported and passed to the Qdrant service/client in Compose. Compose requires a nonempty shared key for both services (an empty Qdrant key enables
authentication but cannot be used by the client). Direct loopback-only test servers may run
without a key. Production must use private access, a strong secret
injected by the runtime, and TLS when traversing untrusted networks. The key is service-wide;
Qdrant itself is not the tenant authorization layer. Protect it as privileged infrastructure.

## Containers and Kubernetes

Copy `.env.example` to an untracked mode-0600 `.env`, replace the OIDC placeholders, and
generate/store a strong `QDRANT_API_KEY` without printing it. Compose requires the shared key
and issuer/audience/JWKS values. Existing model-cache volumes still work; tokens are never baked
into the image. The image contains the pinned JWT/cryptography stack and disables generic
Uvicorn access logs, avoiding query strings in logs. Structured audit events remain enabled.
When running Uvicorn directly, also use `--no-access-log` and do not enable HTTP/token debug logs.

Kubernetes references an operator-provided `rag-api-oidc-config` ConfigMap containing the three
OIDC variables. It deliberately ships no live provider or arbitrary issuer. Provision the
ConfigMap before rollout; an absent map prevents startup. The immutable published image
reference is unchanged because this task does not publish or deploy. Any production Qdrant
key must be injected into both workloads using a separately managed Secret, not a ConfigMap.

The authenticated smoke tools require a token file and trusted IdP configuration:

```bash
python scripts/semantic-container-smoke.py --image rag-api:tenant-authz \
  --oidc-issuer https://identity.example.com/realms/rag --oidc-audience rag-api \
  --oidc-jwks-url https://identity.example.com/realms/rag/protocol/openid-connect/certs \
  --bearer-token-file /secure/path/access.jwt \
  --offline --model-cache /path/to/verified/hub-cache --output /tmp/smoke.json

RAG_ACCESS_TOKEN_FILE=/secure/path/admin-access.jwt bash scripts/compose-smoke-test.sh
```

Export the same `QDRANT_API_KEY` to the Python smoke process; it forwards the environment
variable to Docker without putting its value in arguments or logs. Compose loading `.env`
does not export variables to an unrelated Python process.

Use an uploader/admin for the container smoke and a tenant_admin for the Compose smoke's
metrics check. Keep credential files mode 0600; do not commit them or place tokens in command
arguments/query strings. Offline here means **model** offline; authenticated requests still
need an available trusted JWKS endpoint on initial key fetch. Use `--ca-bundle` when appropriate.
No identity-provider configuration or credentials are persisted by the smoke scripts.

## Audit logging

`rag.audit` emits one JSON object per line to stderr. Events include authentication failure,
authorization denial, successful upload, access, and permission replacement. Only generated
document IDs, operation/outcome enums, counts, timestamps, and hashed tenant/actor references
are included. Tokens, credentials, raw subject/tenant IDs, filenames, questions, prompts,
model outputs, document contents, and exception messages are not audit fields. Protect log
transport/retention and access in the deployment; this is application auditing, not a durable
external audit store. Metrics use route templates rather than user-controlled URL paths.

## Verification

Install `services/rag-api/requirements.lock` and the application as in Phase 1. With real
Qdrant and the verified model cache, run:

```bash
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HOME=/workspace/.cache/phase1-embeddings
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 RUN_SECURITY_INTEGRATION=1 \
  python -m pytest services/rag-api/tests -q
python -m ruff check services/rag-api benchmarks/semantic-retrieval scripts/semantic-container-smoke.py
```

Security tests use genuine signature verification; only earlier non-security endpoint tests
inject test identities through FastAPI's test dependency overrides. The real security
integration uses the actual cached MiniLM model and real Qdrant HTTP service, two tenants,
private and shared documents, admin boundaries, malicious tenant/owner fields, top-k
prefiltering, legacy/corrupt ACL denial, sharing revocation, and an LLM spy that rejects
unauthorized content in both prompt and retrieved context. A separate faulty-adapter test
checks the API's second boundary. See [Phase 2 evidence](../evidence/tenant-authz.md).
