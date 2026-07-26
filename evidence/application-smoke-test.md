# Application Smoke-Test Evidence

The committed repeatable smoke test was run against the services deployed in
Kind on 2026-07-26.

```text
Qdrant is ready
RAG API is ready
PASS: document upload generated embeddings
PASS: Qdrant reports stored documents and chunks
PASS: semantic search retrieved the expected content
PASS: RAG answer includes retrieved sources
PASS: metric rag_api_http_requests_total is exposed
PASS: metric rag_api_ask_latency_seconds is exposed
PASS: metric rag_api_qdrant_retrieval_latency_seconds is exposed
Compose smoke test passed
```

Despite its historical filename, `scripts/compose-smoke-test.sh` accepts
endpoint overrides and was executed against temporary Kind service
port-forwards:

```bash
RAG_API_URL=http://127.0.0.1:18000 \
QDRANT_HTTP_URL=http://127.0.0.1:16333 \
scripts/compose-smoke-test.sh
```

The port-forwards were stopped after evidence collection.

