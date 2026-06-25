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

Check that Argo CD accepted the Application:

```bash
kubectl get applications -n argocd
```

Then open the Argo CD UI and confirm that the `llm-rag-platform` Application appears.
