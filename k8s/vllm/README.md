# vLLM Kubernetes Manifests

This directory contains a production-style Kubernetes base for a future vLLM
OpenAI-compatible inference service. It is intentionally safe for local
development and public repositories:

- no secrets or private registry references
- no real model configured
- no GPU resource requirements
- `replicas: 0` by default so applying the manifests does not start vLLM or
  download model weights

## Resources

- `configmap.yaml`: non-secret runtime defaults, including `MODEL_NAME`
- `deployment.yaml`: vLLM OpenAI API server pod template with health probes and
  CPU-friendly placeholder resources
- `service.yaml`: internal ClusterIP service named `vllm`
- `kustomization.yaml`: local kustomize entry point

The Service exposes port `8001` inside the cluster to match the RAG API default:

```text
VLLM_BASE_URL=http://vllm:8001
```

The vLLM container listens on port `8000` and serves the OpenAI-compatible API
under paths such as:

```text
/v1/models
/v1/chat/completions
```

## Local Development Mode

Local mode is a manifest placeholder, not a model-serving setup. Apply it to
create the namespace, ConfigMap, Deployment, and Service without starting a pod:

```bash
kubectl apply -k k8s/vllm
kubectl get deploy,svc,configmap -n ai-system -l app.kubernetes.io/name=vllm
```

The Deployment defaults to:

```text
replicas=0
MODEL_NAME=placeholder-local-model
cpu request=250m
memory request=512Mi
cpu limit=1
memory limit=2Gi
```

Keep `replicas: 0` for normal local development unless you intentionally provide
a small CPU-compatible test model and accept the startup time and memory use. Do
not point this placeholder at private model names, private endpoints, or real
tokens in committed manifests.

If you need to experiment locally, use an uncommitted overlay or a one-off patch
with a public test model:

```bash
kubectl set env deployment/vllm -n ai-system MODEL_NAME=your-public-test-model
kubectl scale deployment/vllm -n ai-system --replicas=1
```

## Future GPU Deployment Mode

For a real GPU deployment, create a separate overlay instead of editing this base
directly. The overlay should set:

- a pinned vLLM image tag
- a real model name
- GPU node scheduling constraints
- GPU resource limits such as `nvidia.com/gpu: "1"`
- production memory and CPU requests sized for the selected model
- persistent or ephemeral model cache volumes, if needed
- any required image pull secrets or model registry credentials through
  Kubernetes Secrets, never ConfigMaps

Example GPU-oriented settings for a future overlay:

```yaml
resources:
  requests:
    cpu: "4"
    memory: 16Gi
    nvidia.com/gpu: "1"
  limits:
    cpu: "8"
    memory: 32Gi
    nvidia.com/gpu: "1"
nodeSelector:
  accelerator: nvidia
tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```

Those settings are intentionally not included in this base so the default
manifests remain runnable on clusters without GPU nodes.
