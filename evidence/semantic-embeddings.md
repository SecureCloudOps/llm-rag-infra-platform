# Phase 1 semantic embeddings acceptance

**PASS for Phase 1 acceptance.** Validated on 2026-10-25 (America/New_York),
Python 3.12.14, Linux x86_64, Qdrant v1.12.6. Branch `feature/semantic-embeddings`
contains the required implementation commit `e5b9948`.

## Implementation review and minimal changes

The existing implementation already selects real embeddings by default, initializes one
provider per worker during startup, batches uploads, and shares that provider across upload,
search, and ask. Model failures stop startup without a SHA-256 fallback. Qdrant uses 384
normalized vectors and cosine similarity, and rejects incompatible dimensions, distance,
or model/revision manifests. Migration requires a new versioned collection and reingestion;
no existing vector data was deleted. Mock embeddings remain explicit in unit tests.

Preserved that working implementation. Updated direct model dependencies to the validated
sentence-transformers 3.4.1 / transformers 4.48.3 / huggingface-hub 0.28.1 stack and regenerated
the complete CPU lock from an isolated environment constrained by the earlier verified freeze.
Torch remains 2.5.1+cpu; tokenizers 0.21.0, safetensors 0.5.3, NumPy 1.26.4, SciPy 1.15.2,
scikit-learn 1.6.1. Both the host environment and built image passed `pip check`.

Removed the optional external Dockerfile frontend directive after its registry manifest
request was denied; the managed BuildKit built the actual Dockerfile using its built-in
frontend, cached Python base, CA secret, and normal managed proxy. No TLS verification or
network policy was bypassed. The final build succeeded.

Strengthened the real integration test to inspect actual encoder CPU placement, collection
dimensions/cosine distance, stored vectors equal to genuine encoder outputs, and the same
provider instance throughout requests. Added explicit read-only cache provisioning and offline
checks to the existing container smoke script.

## Actual validation results

- **50 passed, 0 failed, 0 skipped**, 9.57 seconds. Both real integrations executed.
  One non-failing Starlette/AnyIO deprecated BlockingPortal alias warning. See
  [raw pytest output](semantic-tests.txt).
- Real API: three document uploads, chunking/batch inference, Qdrant storage, semantic
  paraphrase retrieval, `/ask` context with mock LLM, API restart, independent offline
  process restart, and incompatible mock/model/metric/dimension rejection passed.
- Actual stored 384-dimensional vectors matched the real provider's CPU output, not just
  a configuration label. Identity manifests and legacy rejection checks passed.
- Cached assets rehashed during finalization: all 11 selected runtime/configuration assets
  complete, including safetensors and tokenizer/pooling assets. Weight SHA-256:
  `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`.
  [Artifact evidence](semantic-model-artifacts.json) retains the official Hub client's prior
  verified HEAD redirect to `us.aws.cdn.hf.co` followed by GET HTTP 200; no new download or
  network troubleshooting was needed during finalization.
- Docker image built successfully. Real semantic container passed `/ready`, upload,
  documents, search, ask, restart, identical persisted Qdrant counts, and search after restart.
  Its host cache was explicitly bind-mounted read-only at `/models`, rather than assumed
  available inside the image. A separate `--network none` container loaded the actual model
  and generated 384 finite CPU values with a Python audit hook rejecting network attempts.
  Zero attempts occurred. See [container evidence](semantic-container-real.json).
- Ruff, compile/static syntax, host/image dependency consistency, Compose configuration,
  base/Kind Kubernetes rendering, and diff hygiene passed. Rendered manifests were not deployed.

## Benchmark

| Provider | Recall@1 | Recall@3 | MRR |
| --- | ---: | ---: | ---: |
| Historical mock baseline | 6.67% | 20.00% | 0.2210 |
| Mock, current execution | 6.67% | 20.00% | 0.221004 |
| MiniLM CPU, current execution | 83.33% | 96.67% | 0.902778 |

| Stage (milliseconds) | Mock P50 | Mock P95 | Semantic P50 | Semantic P95 |
| --- | ---: | ---: | ---: | ---: |
| Embedding | 0.006951 | 0.009356 | 12.729065 | 16.692691 |
| Qdrant search | 1.525641 | 2.594860 | 4.220398 | 6.593522 |
| End-to-end retrieval | 1.533183 | 2.601433 | 17.612695 | 21.888164 |

The previous mock retrieval P50/P95 was 2.496399 / 4.154656 ms. Final measurements use
15 documents, identical 30 questions/judgments, three warm sequential passes, and fresh
collections for each provider. Corpus and questions are byte-identical to `e5b9948`.
The final benchmark ran after CPU-heavy test/container workloads completed. Latency excludes
API HTTP transport and LLM generation; Qdrant search includes HTTP and top-15 result parsing.
Model initialization and ingestion are measured separately in raw JSON.

| Question | Query | Labeled document | Actual top result | Relevant rank |
| --- | --- | --- | --- | ---: |
| q01 | How can I limit what a workload is allowed to do in my cloud account? | iam-least-privilege | billing-tags | 2 |
| q06 | What evidence helps diagnose repeated workload restarts? | k8s-crashloop | k8s-readiness | 3 |
| q07 | How do I safely remove a worker machine from service for patching? | k8s-drain | iam-least-privilege | 2 |
| q15 | How should we learn from an outage after restoring availability? | incident-response | backup-recovery | 2 |
| q28 | How do I prevent traffic reaching an API before its model has loaded? | k8s-readiness | tls-renewal | 4 |

Only q28 misses top-3; no question misses its relevant document in the complete ranking.
The full mock and semantic rankings, UUID collection names, dataset hashes, and raw timings
are in [results.json](../benchmarks/semantic-retrieval/results.json). No benchmark data or
labels were changed to improve accuracy.

## Exact commands and environment

All commands run from the repository root. Existing Qdrant on localhost:6333 was reused;
new UUID-named integration/benchmark/smoke collections preserve existing data. Docker
operations used the managed daemon with normal platform proxy and CA trust. The initial
sandbox-only unit invocation stalled in TestClient; the final full suite used the supported
network-enabled execution permission for local HTTP/threading and completed successfully.

```bash
V=/workspace/.cache/phase1-final/venv
python -m venv "$V"
export HF_HOME=/workspace/.cache/phase1-embeddings
export EMBEDDING_CACHE_DIR=/workspace/.cache/phase1-embeddings/hub
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
# install_torch
$V/bin/pip --isolated install --retries 0 --index-url https://download.pytorch.org/whl/cpu -c /workspace/.cache/phase1-embeddings/requirements.freeze.txt 'torch==2.5.1+cpu'
# install_application
$V/bin/pip --isolated install --retries 0 --index-url https://pypi.org/simple -c /workspace/.cache/phase1-embeddings/requirements.freeze.txt -e 'services/rag-api[dev]'
# full_tests
RUN_QDRANT_INTEGRATION=1 RUN_SEMANTIC_INTEGRATION=1 QDRANT_URL=http://localhost:6333 $V/bin/python -m pytest services/rag-api/tests -q
# build
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt --tag rag-api:semantic services/rag-api
# container
$V/bin/python scripts/semantic-container-smoke.py --image rag-api:semantic --port 8003 --offline --model-cache /workspace/.cache/phase1-embeddings/hub --output evidence/semantic-container-real.json
# benchmark
$V/bin/python benchmarks/semantic-retrieval/run.py --qdrant-url http://localhost:6333 --provider both --repeats 3 --output benchmarks/semantic-retrieval/results.json
# lint
$V/bin/python -m ruff check services/rag-api benchmarks/semantic-retrieval scripts/semantic-container-smoke.py
# compile
$V/bin/python -m compileall -q services/rag-api/app benchmarks/semantic-retrieval scripts/semantic-container-smoke.py
# dependencies
$V/bin/python -m pip check
# container_dependencies
docker run --rm --network none --entrypoint python rag-api:semantic -m pip check
# kubernetes
/workspace/.local/bin/kubectl kustomize k8s/ > /workspace/.cache/phase1-final/k8s.yaml
# kind
/workspace/.local/bin/kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/kind > /workspace/.cache/phase1-final/kind.yaml
# compose
docker compose config --quiet
# diff
git diff --check
```

For a fresh checkout, install the committed `services/rag-api/requirements.lock` and then
install the application with `--no-deps --no-build-isolation -e services/rag-api`. The original
verified freeze supplied constraints during this execution; the committed lock records the
complete resolved application/test environment. Cache provisioning instructions are in
[operations](../docs/semantic-embeddings.md). Machine-readable outcomes and commands are in
[phase1-acceptance.json](phase1-acceptance.json).

## Modified files in this finalization

- `services/rag-api/pyproject.toml`, `requirements.lock`: validated CPU dependency stack.
- `services/rag-api/Dockerfile`: use built-in Dockerfile frontend.
- `services/rag-api/tests/test_semantic_integration.py`: verify genuine stored CPU vectors.
- `scripts/semantic-container-smoke.py`: explicit cache mount, disconnected inference, restart search.
- `benchmarks/semantic-retrieval/results.json`, `README.md`: real comparison and relevance misses.
- `docs/semantic-embeddings.md`: cache provisioning and verified outcomes.
- `evidence/semantic-container-real.json`, `semantic-model-artifacts.json`, `semantic-tests.txt`,
  `phase1-acceptance.json`, `semantic-embeddings.md`, `semantic-embeddings-pr-draft.md`: actual evidence.

## Limits and remaining operational work

No critical Phase 1 acceptance check remains blocked. This is a small synthetic benchmark,
not production quality/capacity proof; five semantic top-1 misses remain. Warm sequential
single-host timing does not establish concurrent performance. Model memory, worker count,
and resource limits still need production profiling. Initial collection/manifest creation is
not transactional; initialize before scaling. The Kubernetes ReadWriteOnce cache claim can
constrain multi-node rollouts. Kubernetes was rendered only; remote CI, security workflows,
and live deployment were not executed. The existing immutable Kubernetes image reference
was retained because image publication is outside this task. Historical mock-only container
JSON remains prior-run evidence and was not rerun or represented as current semantic proof.

No JWT/OIDC, tenant filtering, prompt-injection defenses, Phase 2, Terraform changes,
vector deletion, merge, push, or publication was performed.
