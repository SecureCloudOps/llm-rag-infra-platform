# Runtime Log Evidence

Sanitized excerpts captured from the Kind workloads on 2026-07-26.

## RAG API

```text
"GET /health HTTP/1.1" 200 OK
"POST /documents/upload HTTP/1.1" 200 OK
"GET /documents HTTP/1.1" 200 OK
"POST /search HTTP/1.1" 200 OK
"POST /ask HTTP/1.1" 200 OK
"GET /metrics HTTP/1.1" 200 OK
```

## Qdrant

```text
Qdrant HTTP listening on 6333
Qdrant gRPC listening on 6334
"PUT /collections/documents/points?wait=true HTTP/1.1" 200
"POST /collections/documents/points/count HTTP/1.1" 200
"POST /collections/documents/points/query HTTP/1.1" 200
```

## Observability

```text
Prometheus: Server is ready to receive web requests.
Grafana: dashboard channel initialized for llm-rag-platform.
```

The full raw logs were intentionally not committed because they contain
ephemeral pod IP addresses and low-value runtime noise.

