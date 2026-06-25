# Argo CD GitOps Bootstrap

This directory contains the Argo CD bootstrap Application for the LLM RAG Infrastructure Platform.

## Argo CD Applications

An Argo CD Application is a Kubernetes custom resource that tells Argo CD where a desired application state lives in Git and where that state should run in Kubernetes.

For this platform, `llm-rag-platform-app.yaml` points Argo CD at:

- Repository: `https://github.com/SecureCloudOps/llm-rag-infra-platform.git`
- Branch: `main`
- Path: `k8s/`
- Destination namespace: `ai-system`

The Application uses the existing `k8s/kustomization.yaml` entry point to render and apply the platform Kubernetes resources.

## Deployment Ordering

Argo CD sync waves are used to make platform dependencies explicit. The wave is declared with the `argocd.argoproj.io/sync-wave` annotation on each Kubernetes resource. Lower-numbered waves are applied before higher-numbered waves.

The platform deploys in this order:

| Wave | Resources | Why it runs here |
| --- | --- | --- |
| `0` | `ai-system` Namespace, `rag-api-config`, `vllm-config` | Namespaces and configuration must exist before workloads reference them. |
| `1` | Qdrant PVC, Service, StatefulSet | The vector database is a runtime dependency of the RAG API. |
| `2` | vLLM Deployment and Service | The RAG API is configured to call the OpenAI-compatible vLLM endpoint in Kubernetes mode. |
| `3` | RAG API Deployment, Service, and NetworkPolicies | The API starts last because it depends on the namespace, config, Qdrant endpoint, and vLLM service DNS. |

The root `k8s/kustomization.yaml` includes all deployable resources for the `ai-system` namespace:

- `namespace.yaml`
- `rag-api-configmap.yaml`
- `vllm/configmap.yaml`
- `qdrant-pvc.yaml`
- `qdrant-statefulset.yaml`
- `qdrant-service.yaml`
- `vllm/deployment.yaml`
- `vllm/service.yaml`
- `rag-api-deployment.yaml`
- `rag-api-service.yaml`
- `networkpolicy.yaml`

## Platform Dependencies

The RAG API depends on Qdrant for vector storage and retrieval. It also depends on the vLLM service when `LLM_PROVIDER=vllm`, which is the Kubernetes default in `rag-api-config`.

Qdrant depends on its persistent volume claim before the StatefulSet can become ready. vLLM depends on `vllm-config` for its model and server settings. The RAG API depends on `rag-api-config` for Qdrant, collection, provider, vLLM, and model settings.

NetworkPolicies are applied with the RAG API wave so traffic rules arrive after the workloads and services they select are declared.

## Why GitOps Ordering Matters

Kubernetes eventually converges resources, but applying dependent resources in an arbitrary order can create avoidable transient failures. Examples include pods starting before their ConfigMaps exist, applications failing DNS lookups for services that have not been created yet, and StatefulSets waiting on missing storage claims.

Sync waves keep the GitOps reconcile predictable. They do not replace application-level retry logic, readiness probes, or health checks, but they reduce noisy rollouts and make the intended dependency graph visible during Argo CD syncs.

## GitOps Flow

GitOps treats Git as the source of truth for Kubernetes state. Operators change manifests in the repository, review those changes, merge them to the tracked branch, and let the GitOps controller reconcile the cluster to match Git.

In this repository, a typical flow is:

1. Update Kubernetes manifests under `k8s/`.
2. Validate the rendered manifests with `kubectl kustomize k8s/`.
3. Merge the change to `main`.
4. Argo CD detects the new commit and syncs the cluster toward that desired state.

## Continuous Git Watching

Argo CD continuously compares the desired state in Git with the live state in the cluster. This matters because Kubernetes resources can drift after manual edits, failed rollouts, or partial operational changes.

This bootstrap enables `selfHeal`, so Argo CD can correct live cluster drift back to the Git-defined state. Pruning is intentionally disabled for now, so Argo CD will not automatically delete cluster resources that disappear from Git until that behavior is explicitly enabled.

`CreateNamespace=true` allows Argo CD to create the destination namespace when it does not already exist.

## Argo CD vs GitHub Actions

GitHub Actions is a CI/CD runner. It is useful for tests, builds, image publishing, manifest validation, and one-shot deployment jobs triggered by repository events.

Argo CD is a Kubernetes reconciliation controller. It runs in the cluster, continuously watches Git, compares Git against live Kubernetes state, and keeps the cluster aligned with the desired manifests.

The practical difference is:

- GitHub Actions answers: did this commit build, test, and validate successfully?
- Argo CD answers: does the cluster currently match the desired state declared in Git?

Both tools can work together. GitHub Actions should validate changes before merge, while Argo CD should continuously deploy and reconcile approved Kubernetes state from Git.

## Bootstrap

Apply the Application after Argo CD is installed in the cluster:

```bash
kubectl apply -f k8s/argocd/llm-rag-platform-app.yaml
```

Verify that the Argo CD repo-server can access the Git source over anonymous HTTPS before applying the Application. If GitHub returns an authentication challenge for the repository's git endpoint, Argo CD cannot clone the source and the Application will remain in `Unknown` sync status with a comparison error.

Check that Argo CD accepted the Application:

```bash
kubectl get applications -n argocd
```

Then open the Argo CD UI and confirm that the `llm-rag-platform` Application appears.

Check sync and health from the cluster:

```bash
kubectl get application llm-rag-platform -n argocd
kubectl get pods -n ai-system
kubectl get svc -n ai-system
```
