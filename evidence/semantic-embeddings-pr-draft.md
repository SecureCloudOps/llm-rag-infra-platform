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

- 50 tests passed, including real CPU model/Qdrant upload, search, ask, persisted actual
  encoder-vector comparison, restart, offline new process, and compatibility rejection.
- Docker image built; explicitly cached offline semantic container passed endpoints and
  restart persistence. Separate network-disabled container generated 384 finite CPU values
  with zero network attempts. Host and image dependency checks passed.
- Ruff, compile/static syntax, Compose configuration, and base/Kind Kubernetes rendering passed.
- Identical 30-question benchmark: mock Recall@1/Recall@3/MRR 6.67%/20.00%/0.221004;
  semantic 83.33%/96.67%/0.902778. Five semantic top-1 misses, including one top-3 miss,
  are documented with exact rankings. No questions or judgments were changed.
- Full dependency lock now uses the previously validated sentence-transformers 3.4.1,
  transformers 4.48.3, huggingface-hub 0.28.1, and torch 2.5.1+cpu stack.

See [execution evidence](semantic-embeddings.md), [benchmark results](../benchmarks/semantic-retrieval/results.json),
and [offline container evidence](semantic-container-real.json). Phase 1 acceptance passed;
no merge, remote push, image publication, or live deployment was performed.

## Operational considerations

Initialize new collection/manifest pairs before scaling workers. Provision an appropriate
model-cache strategy before multi-node HPA use; the current PVC is ReadWriteOnce. Publish
and select the reviewed image before Kubernetes deployment. Extend evaluation beyond the
small synthetic corpus before production relevance or capacity claims.

Terraform, its known provider-lockfile issue, authentication, authorization, and prompt
protections are outside this change. No merge or remote publication was performed.
