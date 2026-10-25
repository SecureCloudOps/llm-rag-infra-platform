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

See [results.json](results.json) for the actual local execution. The SHA-256 baseline ran
against Qdrant v1.12.6: Recall@1 0.066667, Recall@3 0.200000, MRR 0.221004.
Only q03 and q05 ranked their labeled document first; the other 28 top-1 failures are
listed in JSON. P50/P95 latency in milliseconds:

| Stage | P50 | P95 |
| --- | ---: | ---: |
| Mock embedding | 0.009719 | 0.017227 |
| Vector search | 2.486928 | 4.116371 |
| End-to-end retrieval | 2.496399 | 4.154656 |

**Semantic results are unavailable.** This environment's proxy returns HTTP 403 for
`huggingface.co`, and the model was not pre-cached. There is no measured semantic-versus-mock
improvement yet. The immutable model revision is configured but could not be verified
against the upstream host in this environment. Rerun after approved network access or
pre-population of the pinned model cache. Do not interpret the blocked result as zero recall.
