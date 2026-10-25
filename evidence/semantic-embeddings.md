# Semantic embeddings implementation and verification

Branch: `feature/semantic-embeddings`. Local validation performed on 2026-10-25,
Python 3.12.14, Linux x86_64, Qdrant v1.12.6. Terraform, authentication,
authorization, and prompt handling were not changed.

**Acceptance is incomplete:** the implementation defaults to real embeddings, but this
managed environment denies `huggingface.co` with HTTP 403 and contains no cached model.
Real semantic integration, relevance, and offline cached-model startup could not pass.
The selected immutable revision could not be independently checked against upstream.
No semantic scores have been invented, and mock plumbing success is not semantic evidence.

## Design and tradeoffs

- Preserve the original `embed(text)` interface and dependency injection points. A new CPU
  Sentence Transformers provider loads the pinned MiniLM snapshot once per worker and
  verifies `modules.json`, output dimension, and finite values. Remote code is disabled;
  safetensors weights are required. Model/download errors are fatal and actionable.
- Select providers through validated settings. Normal local configuration uses MiniLM,
  384 dimensions, normalized vectors, and cosine similarity. Mock SHA-256 remains explicit
  for unit tests and benchmark baselines, with an isolated collection identity.
- Lifecycle state holds the initialized provider and vector store. Threaded startup,
  upload processing, and synchronous search/ask avoid running model work on the event loop.
  A per-model inference lock bounds CPU contention at the cost of queueing under load.
- Batch all chunk embeddings and validate the complete batch before a document write.
  Preserve filenames, chunk indexes, document UUIDs, and existing text chunking. A single
  waited Qdrant upsert follows validation; this does not introduce distributed upload transactions.
- Validate existing Qdrant dimension and cosine distance, then compare a separate one-point
  model-identity manifest. This avoids polluting search results and counts. Collection pairs
  are idempotent after successful creation, but initial creation is not transactional.
  Legacy/untracked, partially initialized, or mismatched collections fail closed. No old
  vectors are converted and no populated collection is automatically deleted.
- Pin CPU runtime/test dependencies in `requirements.lock`; use persistent model-cache
  volumes, UID/GID 1000, startup/readiness probes, and increased CPU/memory allocations.
  No NVIDIA/CUDA dependency is installed. The lock targets Linux x86_64 / Python 3.12.

## Commands and actual outcomes

Commands below run from the repository root. The local Python executable is
`services/rag-api/.venv/bin/python`. Network-enabled execution was needed for HTTP tests
because the sandbox's network restriction also affected TestClient worker threads.
Docker required the managed daemon permission path; ordinary sandbox socket access failed.

| Validation | Exact command | Outcome |
| --- | --- | --- |
| Existing and expanded unit suite | `services/rag-api/.venv/bin/python -m pytest services/rag-api/tests -q` | 48 passed, 2 opt-in integration tests skipped; one Starlette/AnyIO deprecation warning |
| Actual Qdrant compatibility integration | `RUN_QDRANT_INTEGRATION=1 services/rag-api/.venv/bin/python -m pytest services/rag-api/tests/test_qdrant_integration.py -v` | 1 passed against real Qdrant; persistence, dimension, identity, and metric guards exercised |
| Actual real-model integration | `RUN_SEMANTIC_INTEGRATION=1 HF_HOME=/tmp/rag-hf EMBEDDING_CACHE_DIR=/tmp/rag-models HF_HUB_ETAG_TIMEOUT=3 HF_HUB_DOWNLOAD_TIMEOUT=3 services/rag-api/.venv/bin/python -m pytest services/rag-api/tests/test_semantic_integration.py -v` | 1 failed at startup: proxy CONNECT 403 for the pinned Hub snapshot; ingestion was not reached |
| Docker build | `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t rag-api:semantic services/rag-api` | Passed; final image ID in smoke JSON |
| CPU container and endpoint smoke | `services/rag-api/.venv/bin/python scripts/semantic-container-smoke.py --mock --ca-bundle /etc/ssl/certs/ca-certificates.crt --output evidence/semantic-container-mock.json` | Passed: CPU Torch 2.5.1+cpu, readiness, upload, documents, search, ask, restart, unchanged counts |
| Default semantic container | `services/rag-api/.venv/bin/python scripts/semantic-container-smoke.py --port 8002 --ca-bundle /etc/ssl/certs/ca-certificates.crt --output evidence/semantic-container-real.json` | Blocked by model-host HTTP 403; startup exits without becoming ready or falling back |
| Benchmark | `PYTHONPATH=services/rag-api EMBEDDING_CACHE_DIR=/tmp/rag-models HF_HUB_ETAG_TIMEOUT=3 HF_HUB_DOWNLOAD_TIMEOUT=3 services/rag-api/.venv/bin/python benchmarks/semantic-retrieval/run.py --output benchmarks/semantic-retrieval/results.json` | Exit 1: actual mock measurements recorded; semantic provider blocked by 403 |
| Lint | `services/rag-api/.venv/bin/python -m ruff check services/rag-api benchmarks/semantic-retrieval scripts/semantic-container-smoke.py` | Passed |
| Compile/static syntax check | `services/rag-api/.venv/bin/python -m compileall -q services/rag-api/app benchmarks/semantic-retrieval scripts/semantic-container-smoke.py` | Passed |
| Installed dependency consistency | `services/rag-api/.venv/bin/python -m pip check` | No broken requirements |
| Kubernetes base render | `/tmp/kubectl kustomize k8s/ > /tmp/semantic-k8s-rendered.yaml` | Passed, 29 resources; kubectl v1.32.0 downloaded to /tmp |
| Kubernetes Kind render | `/tmp/kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/kind > /tmp/semantic-kind-rendered.yaml` | Passed, 27 resources |
| Compose validation | `docker compose config --quiet` | Passed |
| Diff hygiene | `git diff --check` | Passed |

The two opt-in integrations are deliberately distinct: a passing real-Qdrant test with
explicit test vectors does **not** replace the failed real-model integration. The semantic
test contains no fake encoder. When its prerequisite is available, it checks paraphrase
retrieval, ask with mocked LLM, persistent API restarts, a fresh-process offline cached API
startup, and isolated mock collections. CI provisions real Qdrant and runs this test plus
both-provider benchmarking with a cached model directory.

Container execution exposed and fixed two concrete issues: source-file ownership for the
non-root runtime, and Docker-injected lowercase `no_proxy` overriding uppercase `NO_PROXY`.
Final smoke commands use both cases to keep Qdrant traffic on its private Compose network.

## Measured retrieval quality

Same 15-document corpus, 30 questions, three sequential latency passes, fresh provider
collections. Explicit document-ID labels and complete rankings are in
[results.json](../benchmarks/semantic-retrieval/results.json).

| Provider | Recall@1 | Recall@3 | MRR | Status |
| --- | ---: | ---: | ---: | --- |
| SHA-256 mock, 8 dimensions | 0.066667 | 0.200000 | 0.221004 | Measured against actual Qdrant |
| MiniLM, 384 dimensions | — | — | — | Model download denied; no measurements |

| Mock latency stage | P50 ms | P95 ms |
| --- | ---: | ---: |
| Embedding | 0.009719 | 0.017227 |
| Qdrant vector search | 2.486928 | 4.116371 |
| End-to-end retrieval | 2.496399 | 4.154656 |

Only q03 and q05 retrieved the labeled document at rank 1; all other 28 mock top-1 failures
are recorded individually. These latency samples use top-15 retrieval to calculate full
MRR; they exclude API HTTP transport and LLM generation. See the
[benchmark methodology](../benchmarks/semantic-retrieval/README.md) for warmup, percentiles,
document deduplication, and limitations. No numerical relevance threshold is imposed.

## Remaining work and risks

1. Permit the required Hub/model artifact hosts through the supported environment policy,
   or provide a complete cache for the pinned revision. Verify the upstream immutable SHA,
   then rerun the real integration, default container smoke, and both-provider benchmark.
   Inspect every relevance failure before asserting semantic improvement.
2. Model snapshot/cache validation and real encoder behavior remain unverified here. A
   cached real API restart is implemented in the integration test but could not execute.
3. Publish the reviewed image and update the Kubernetes immutable image reference before
   rollout. The existing tag is retained; manifests alone cannot install unpublished code.
4. Initial data/manifest provisioning can fail closed under concurrency or interruption.
   Initialize before scaling; use a new collection name after an incomplete creation.
5. A ReadWriteOnce model-cache PVC may constrain multi-node HPA/rolling updates. Choose an
   appropriate cache strategy and profile resource limits before production scaling.
6. The benchmark is deliberately small and synthetic. Extend with representative documents,
   load/concurrency testing, and retrieval evaluation before capacity or quality claims.
7. The pinned toolchain includes test tools in the runtime image; a separate runtime-only
   lock/build stage could reduce image size. Dependency/security scan results still need CI
   review; this task ran lint/syntax/dependency checks, not the remote security workflows.
8. The pre-existing Terraform provider lockfile issue is a separate known limitation.
   No Terraform files or lockfiles were modified and no Terraform remediation was attempted.

## Acceptance status

- Implemented: real provider default, mock option, shared lifecycle model, validated batch
  ingestion, safe collection compatibility, endpoint schemas, deployment cache/probes,
  reproducible labeled benchmark, unit tests, integration tests, CI, migration documentation.
- Verified: 48 unit tests, actual Qdrant compatibility integration, Docker build, explicit
  mock container endpoints/restart, baseline relevance measurements, lint, syntax, manifest rendering.
- Not verified / blocked: real semantic integration success, semantic quality comparison,
  real semantic endpoint smoke, real offline cached API restart, upstream model revision check.


## Complete changed-file inventory

| File | Change |
| --- | --- |
| `.env.example` | Document explicit provider, model, immutable revision, dimension, cache, and CPU settings. |
| `.github/workflows/rag-api-ci.yml` | Install the CPU lock; run real Qdrant/model integration and upload benchmark evidence. |
| `README.md` | Update embedding architecture and local collection defaults; link operations and benchmarks. |
| `benchmarks/semantic-retrieval/README.md` | Benchmark methodology, reproduction commands, results, and relevance failures. |
| `benchmarks/semantic-retrieval/corpus.json` | Fifteen labeled infrastructure corpus documents including distractors. |
| `benchmarks/semantic-retrieval/questions.json` | Thirty paraphrase questions with explicit relevant document identifiers. |
| `benchmarks/semantic-retrieval/results.json` | Actual provider outcomes, baseline metrics, timings, and per-question rankings. |
| `benchmarks/semantic-retrieval/run.py` | Fresh per-provider indexing, relevance scoring, stage latency measurements, and blocker reporting. |
| `docker-compose.yml` | Select semantic defaults, persist model cache, and configure internal proxy bypass. |
| `docs/architecture.md` | Describe the shared worker model and compatibility checks. |
| `docs/semantic-embeddings.md` | Operational configuration, architecture diagram, caching, migration, performance, and limitations. |
| `evidence/semantic-container-mock.json` | Actual explicit-mock container endpoint and restart results. |
| `evidence/semantic-container-real.json` | Actual default semantic startup failure evidence. |
| `evidence/semantic-embeddings-pr-draft.md` | Reviewable draft PR title and description with pending acceptance clearly identified. |
| `evidence/semantic-embeddings.md` | Implementation decisions, exact validation commands, measured results, blockers, and file inventory. |
| `k8s/embedding-cache-pvc.yaml` | Persistent model cache claim. |
| `k8s/kustomization.yaml` | Include the cache claim. |
| `k8s/rag-api-configmap.yaml` | Semantic model defaults, cache path, revision, and CPU thread settings. |
| `k8s/rag-api-deployment.yaml` | Mount cache; add startup/readiness probes and CPU/memory capacity. |
| `rendered.yaml` | Update only embedding-related configuration in the historical tracked render. |
| `scripts/semantic-container-smoke.py` | Reproducible isolated API container startup, endpoint, and restart verification. |
| `services/rag-api/Dockerfile` | Install pinned CPU dependencies, preserve non-root access, mount-aware caching, and readiness healthcheck. |
| `services/rag-api/README.md` | Update installation, collection default, and embedding operations links. |
| `services/rag-api/app/config.py` | Validated embedding settings and versioned semantic default collection. |
| `services/rag-api/app/document_service.py` | Optional batch embedding, complete-batch validation, explicit provider requirement. |
| `services/rag-api/app/embeddings.py` | Pinned safetensors CPU provider, identity, finite/dimension validation, batch support; preserve mock. |
| `services/rag-api/app/main.py` | Worker lifespan provider/store state, thread offloading, readiness, cleanup, and injectable overrides. |
| `services/rag-api/app/vector_store.py` | Dimension/distance/model identity checks, companion manifests, validated writes, internal document-ID retrieval. |
| `services/rag-api/pyproject.toml` | Pin direct dependencies and configure test markers and Ruff. |
| `services/rag-api/requirements.lock` | Pin the complete validated Linux/Python CPU runtime and test toolchain. |
| `services/rag-api/tests/conftest.py` | Explicit mock dependency injection for isolated unit tests. |
| `services/rag-api/tests/test_ask.py` | Ruff import/blank-line normalization only; existing endpoint assertions retained. |
| `services/rag-api/tests/test_collection_compatibility.py` | Local unit coverage for idempotence, dimensions, metric, model/revision identity, untracked legacy state, and invalid writes. |
| `services/rag-api/tests/test_documents.py` | Ruff import/blank-line normalization only; existing endpoint assertions retained. |
| `services/rag-api/tests/test_health.py` | Ruff import/blank-line normalization only; existing endpoint assertions retained. |
| `services/rag-api/tests/test_metrics.py` | Ruff import/blank-line normalization only; existing endpoint assertions retained. |
| `services/rag-api/tests/test_qdrant_integration.py` | Actual server compatibility, identity/metric rejection, and persistence verification. |
| `services/rag-api/tests/test_search.py` | Ruff import/blank-line normalization only; existing endpoint assertions retained. |
| `services/rag-api/tests/test_semantic_embeddings.py` | Provider/config/batch/empty/initialization validation unit coverage with a fake encoder. |
| `services/rag-api/tests/test_semantic_integration.py` | Opt-in genuine-model ingestion, paraphrase retrieval, ask, restart, offline cache, and isolation checks. |
| `services/rag-api/tests/test_startup.py` | Startup initialization/readiness tests and original embed-only override compatibility. |
| `services/rag-api/tests/test_vector_store.py` | Remove obsolete test that required blindly accepting existing collections. |
