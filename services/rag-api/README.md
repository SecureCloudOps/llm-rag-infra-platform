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

## Future vLLM Mode

The API also has an OpenAI-compatible provider path for a future vLLM server.
Do not enable it unless a compatible vLLM endpoint is already running:

```bash
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://localhost:8001
export MODEL_NAME=your-model-name
uvicorn app.main:app --reload
```

The provider calls `POST /v1/chat/completions` on `VLLM_BASE_URL`.

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

Response:

```json
{"status":"ok","service":"rag-api"}
```

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
