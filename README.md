# LLM RAG Infrastructure Platform

Production-style reference project for serving an open-source LLM with retrieval-augmented generation infrastructure.

The platform is intended to combine:

- vLLM for OpenAI-compatible inference serving
- Qdrant for vector search
- FastAPI for a RAG API layer
- Kubernetes manifests for application deployment
- Terraform for AWS EKS infrastructure

This repository is an infrastructure portfolio project. It is safe for public sharing and does not include secrets, cloud account IDs, private endpoints, or claims of a live production deployment.

## Current Status

Initial scaffold:

- `services/rag-api`: minimal FastAPI service with `GET /health`
- `docs/architecture.md`: target architecture and component responsibilities
- `infra/terraform`: Terraform entry point for cloud infrastructure
- `k8s`: Kubernetes manifest areas for platform components
- `.github/workflows`: CI/CD workflow definitions
- `scripts`: operational and developer helper scripts

Planned follow-up areas:

- `infra/terraform`: AWS EKS, networking, and managed infrastructure
- `k8s`: Kubernetes manifests or Helm charts
- `services/rag-api`: retrieval and generation endpoints
- `services/ingestion`: document ingestion and embedding pipeline

## Repository Layout

```text
llm-rag-infra-platform/
├── README.md
├── .github/
│   └── workflows/
├── docs/
├── infra/
│   └── terraform/
├── k8s/
│   ├── base/
│   ├── apps/
│   ├── qdrant/
│   ├── vllm/
│   └── observability/
├── scripts/
└── services/
    └── rag-api/
        ├── app/
        │   ├── __init__.py
        │   └── main.py
        ├── tests/
        │   └── test_health.py
        ├── pyproject.toml
        └── README.md
```

## Run the RAG API Locally

### Docker Compose

From the repository root:

```bash
docker compose up --build
```

This starts:

- `rag-api` on <http://127.0.0.1:8000>
- `qdrant` on <http://127.0.0.1:6333>

The Compose configuration uses non-secret local defaults:

```text
QDRANT_URL=http://qdrant:6333
COLLECTION_NAME=documents
LLM_PROVIDER=mock
VLLM_BASE_URL=http://vllm:8001
MODEL_NAME=mistral-7b-instruct
```

Mock mode is the default and does not require vLLM or any API keys.

Check the API:

```bash
curl http://127.0.0.1:8000/health
```

Stop the stack:

```bash
docker compose down
```

If a host port is already in use, override only the host-side mapping:

```bash
QDRANT_HTTP_PORT=6335 QDRANT_GRPC_PORT=6336 docker compose up --build
```

Remove the local Qdrant volume as well:

```bash
docker compose down -v
```

### Python

From `services/rag-api`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export LLM_PROVIDER=mock
uvicorn app.main:app --reload
```

Mock mode is the default and does not require vLLM. It returns deterministic
answers from the RAG API so local development and unit tests can run without an
LLM server.

Then call:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"rag-api"}
```

## Future vLLM Mode

The RAG API includes an opt-in OpenAI-compatible LLM provider for a future vLLM
deployment. This repository does not deploy vLLM yet. Once a compatible vLLM
server is running, configure the API with:

```bash
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://localhost:8001
export MODEL_NAME=your-model-name
uvicorn app.main:app --reload
```

`LLM_PROVIDER` accepts `mock` or `vllm`. In vLLM mode, the API calls
`POST /v1/chat/completions` on `VLLM_BASE_URL`.

## Run Tests

From `services/rag-api`:

```bash
pytest
```

## Public Repo Safety

Do not commit:

- AWS account IDs or resource ARNs from a real account
- API keys, tokens, kubeconfigs, or Terraform state
- Private endpoint URLs
- Customer, employer, or proprietary data

Use environment variables, local `.env` files excluded by `.gitignore`, and documented placeholders for configuration.
