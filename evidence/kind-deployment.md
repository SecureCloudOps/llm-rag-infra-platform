# Kind Deployment Evidence

Captured on 2026-07-26.

## Cluster

```text
Context: kind-llm-rag-platform-demo
Node: llm-rag-platform-demo-control-plane
Status: Ready
Role: control-plane
Kubernetes: v1.36.1
Container runtime: containerd 2.3.1
```

## Application and observability workloads

```text
NAMESPACE       WORKLOAD                 READY   STATUS
ai-system       deployment/rag-api       1/1     Available
ai-system       statefulset/qdrant       1/1     Ready
ai-system       deployment/vllm          0/0     Intentionally disabled in Kind
observability   deployment/prometheus    1/1     Available
observability   deployment/grafana       1/1     Available
```

All running workload pods reported `Running` with zero restarts. The
`qdrant-storage` PVC reported `Bound` with a 10 GiB request. Four network
policies were present: default-deny ingress and explicit ingress paths for the
RAG API, Qdrant, and vLLM.

## Immutable application image

```text
ghcr.io/securecloudops/llm-rag-infra-platform/rag-api:10334517d6e2c94b370d4d630f33939e829c8d5b # gitleaks:allow -- public immutable Git commit SHA
```

The Kind overlay intentionally uses the mock LLM provider so the complete RAG
workflow can be verified locally without a GPU or external model service.

## Reproduce

```bash
kind create cluster --name llm-rag-platform-demo
kubectl apply -k deploy/kind
kubectl get deploy,statefulset,pods,svc,pvc,networkpolicy -A
```
