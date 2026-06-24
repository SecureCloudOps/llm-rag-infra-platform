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

## Kubernetes vLLM Mode

The root Kubernetes manifests render the RAG API, Qdrant, and the vLLM service
in the `ai-system` namespace. In Kubernetes, `rag-api-config` switches the API
from local mock mode to vLLM:

```text
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://vllm.ai-system.svc.cluster.local:8000/v1
MODEL_NAME=placeholder-local-model
```

`MODEL_NAME` intentionally matches the default in `k8s/vllm/configmap.yaml`.
The vLLM Deployment still defaults to `replicas: 0`, so set a real model and
scale it when you are ready to run inference:

```bash
kubectl set env deployment/vllm -n ai-system MODEL_NAME=your-public-test-model
kubectl scale deployment/vllm -n ai-system --replicas=1
```

Render or apply the Kubernetes stack from the repository root:

```bash
kubectl kustomize k8s/
kubectl apply -k k8s/
```

## Switching LLM Providers

For local Docker Compose and Python development, keep mock mode:

```bash
export LLM_PROVIDER=mock
```

To point a local RAG API process at a compatible vLLM endpoint, switch the
provider and use the model served by vLLM:

```bash
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://localhost:8000/v1
export MODEL_NAME=your-model-name
uvicorn app.main:app --reload
```

`LLM_PROVIDER` accepts `mock` or `vllm`. In vLLM mode, the API calls
the OpenAI-compatible chat completions endpoint. `VLLM_BASE_URL` may include
the `/v1` suffix, as shown above, or omit it.

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
