# Draft pull request

**Title:** Use pinned CPU semantic embeddings and enforce Qdrant model compatibility

**Base:** main  
**Head:** feature/semantic-embeddings

## Problem and behavior

Document ingestion and queries currently use eight-dimensional SHA-256 vectors, so similarity
search cannot represent meaning. Default local RAG now uses one pinned CPU MiniLM encoder
per API worker, producing 384 normalized values for cosine retrieval. Mock LLM generation
remains independent of embedding selection.

The existing upload/search/ask endpoints share the lifespan-managed provider. Uploads batch
and validate all embeddings before writing. Qdrant verifies dimensions, metric, and a
separate model/revision manifest on startup; incompatible or untracked collections fail with
instructions to create a new versioned collection and reingest original text. No old vectors
or populated collections are automatically altered or deleted.

Add a pinned CPU dependency lock, persistent model caching, readiness/startup probes, resource
allocations, real-model/Qdrant integration CI, and a 15-document / 30-question evaluation
with explicit document IDs and separate embedding/search/end-to-end latency metrics.
Operational documentation covers migration, cache prewarming, and concurrency limitations.

## Validation

- 48 unit tests passed; actual Qdrant v1.12.6 compatibility integration passed.
- Docker build passed. Explicit mock-mode container passed readiness, ingestion, documents,
  search, ask, and restart persistence. CPU Torch 2.5.1+cpu confirmed.
- Ruff, compileall, dependency consistency, and base/Kind manifest rendering passed.
- Actual mock baseline: Recall@1 **0.066667**, Recall@3 **0.200000**, MRR **0.221004**.
  End-to-end retrieval P50/P95 **2.496399 / 4.154656 ms**.
- **Blocked:** real-model integration and default semantic container startup fail because
  the managed proxy denies Hugging Face with HTTP 403. The model is not cached. No semantic
  relevance results or real cached-restart success are claimed; upstream SHA verification
  is pending. This draft is not ready for merge until real validation can be completed.

See [full execution evidence](semantic-embeddings.md), [benchmark data](../benchmarks/semantic-retrieval/results.json),
and [operations/migration](../docs/semantic-embeddings.md) for exact commands and tradeoffs.

## Operational considerations

Initialize new collection/manifest pairs before scaling workers. Provision an appropriate
model-cache strategy before multi-node HPA use; the current PVC is ReadWriteOnce. Publish
and select the reviewed image before Kubernetes deployment. Extend evaluation beyond the
small synthetic corpus before production relevance or capacity claims.

Terraform, its known provider-lockfile issue, authentication, authorization, and prompt
protections are outside this change. No merge or remote publication was performed.
