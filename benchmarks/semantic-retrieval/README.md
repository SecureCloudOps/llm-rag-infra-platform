# Semantic retrieval benchmark

This corpus contains 15 synthetic infrastructure documents, including five distractors,
and 30 manually labeled questions. Each question has one explicitly relevant document ID.
The labels cover IAM, Kubernetes operations, incident response, monitoring, networking,
backup recovery, credentials, and vector migration. Documents and questions are version controlled.
This small smoke benchmark is not a representative production relevance evaluation.

## Run

From the repository root, after installing the API's CPU dependencies:

```bash
docker compose up -d qdrant
export EMBEDDING_PROVIDER=sentence_transformers EMBEDDING_DIMENSIONS=384
export EMBEDDING_CACHE_DIR=/tmp/rag-models HF_HOME=/tmp/rag-hf
export OMP_NUM_THREADS=2
services/rag-api/.venv/bin/python benchmarks/semantic-retrieval/run.py \
  --qdrant-url http://localhost:6333 --repeats 3 \
  --output benchmarks/semantic-retrieval/results.json
```

Each provider indexes the same corpus and questions in a **fresh UUID-named collection**
with a separate identity manifest. The runner never deletes existing data. Collections are
printed in the results so an operator can remove only disposable benchmark collections
and their `__embedding_manifest` companions later.

The runner uses the existing chunker, providers, and Qdrant HTTP adapter. It embeds all
chunks before writing. Results are scored by `document_id`, never by text matching.
Rankings are deduplicated by document ID, keeping the highest scoring chunk per document.
Recall@k is the fraction of labeled relevant documents within the first k unique documents;
MRR uses the first relevant document in the complete returned corpus ranking. There are
currently 15 chunks, so vector-search latency measures top-15 retrieval, not top-3.

Latency uses monotonic wall-clock measurements, one warm-up query, and three sequential
passes of the same 30 questions. NumPy linear percentiles report P50/P95 across 90 samples.
Embedding latency includes any inference-lock wait; vector search includes Qdrant HTTP
transport, search, and result parsing; end-to-end includes both. It excludes API HTTP
handling, LLM generation, model initialization, and ingestion; initialization and ingestion
are reported separately. No approximate quality threshold is used to declare success.
Question rankings and every top-1 relevance failure are retained in JSON. The runner exits
nonzero and records an explicit blocker if either requested provider fails.

## Recorded execution

Real Qdrant v1.12.6, Python 3.12.14, immutable MiniLM revision
`c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, two CPU threads.
Both providers used byte-identical corpus/questions from `e5b9948`, fresh collections,
and three sequential passes (90 latency samples each). Final measurements ran after
the regression and container workloads completed.

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

The historical mock retrieval P50/P95 was 2.496399 / 4.154656 ms. Current timings
vary with the host; compare relevance using identical labels, and do not infer production
capacity from this small warm sequential workload. Semantic initialization was
2721.491 ms; ingestion was 176.371 ms.

## Semantic top-1 misses

| Question | Query | Labeled document | Actual top result | Relevant rank |
| --- | --- | --- | --- | ---: |
| q01 | How can I limit what a workload is allowed to do in my cloud account? | iam-least-privilege | billing-tags | 2 |
| q06 | What evidence helps diagnose repeated workload restarts? | k8s-crashloop | k8s-readiness | 3 |
| q07 | How do I safely remove a worker machine from service for patching? | k8s-drain | iam-least-privilege | 2 |
| q15 | How should we learn from an outage after restoring availability? | incident-response | backup-recovery | 2 |
| q28 | How do I prevent traffic reaching an API before its model has loaded? | k8s-readiness | tls-renewal | 4 |

Only q28 also missed top-3 (relevant rank 4). All questions had a relevant result
in the complete ranking. No corpus, questions, or judgments were adjusted. The
28 mock top-1 misses and all per-question rankings remain in [results.json](results.json).
