# RAG API

Minimal FastAPI service for the LLM RAG Infrastructure Platform.

## Run

### Docker Compose

From the repository root:

```bash
docker compose up --build
```

The Compose stack starts this API and Qdrant. It keeps the mock LLM provider as
the default and uses non-secret local configuration:

```text
QDRANT_URL=http://qdrant:6333
COLLECTION_NAME=documents
LLM_PROVIDER=mock
VLLM_BASE_URL=http://vllm:8001
MODEL_NAME=mistral-7b-instruct
```

The API is available at <http://127.0.0.1:8000>.

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export QDRANT_URL=http://localhost:6333
export COLLECTION_NAME=documents
export LLM_PROVIDER=mock
uvicorn app.main:app --reload
```

`LLM_PROVIDER=mock` is the default. It uses a deterministic local provider for
development and tests, so no LLM server is required.

## Kubernetes vLLM Mode

Local Docker Compose keeps `LLM_PROVIDER=mock` by default, so no LLM server is
required for development or tests.

The Kubernetes manifests switch the RAG API to the in-cluster vLLM service:

```text
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://vllm.ai-system.svc.cluster.local:8000/v1
MODEL_NAME=placeholder-local-model
```

`MODEL_NAME` matches the default in `k8s/vllm/configmap.yaml`. Change both
values together, or use an overlay, when deploying a real model.

## Switching LLM Providers

Use mock mode for local development:

```bash
export LLM_PROVIDER=mock
```

Use vLLM mode only when a compatible OpenAI-style vLLM endpoint is reachable:

```bash
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://localhost:8000/v1
export MODEL_NAME=your-model-name
uvicorn app.main:app --reload
```

The provider calls the OpenAI-compatible chat completions endpoint.
`VLLM_BASE_URL` may include the `/v1` suffix, as shown above, or omit it.

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

Response:

```json
{"status":"ok","service":"rag-api"}
```

## Metrics

The API exposes Prometheus metrics at `/metrics`:

```bash
curl http://127.0.0.1:8000/metrics
```

Key metric families:

- `rag_api_http_requests_total`
- `rag_api_http_request_latency_seconds`
- `rag_api_ask_latency_seconds`
- `rag_api_qdrant_retrieval_latency_seconds`
- `rag_api_llm_provider_latency_seconds`
- `rag_api_retrieved_chunk_count`
- `rag_api_errors_total`

LLM latency is labeled by provider and model name where safe. Mock mode reports
`provider="mock"` and vLLM mode reports `provider="vllm"` with the configured
`MODEL_NAME`.

## Documents

```bash
curl http://127.0.0.1:8000/documents
```

Response:

```json
{"total_documents":0,"total_chunks":0}
```

## Tests

```bash
pytest
```
