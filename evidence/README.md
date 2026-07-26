# Rebuild Evidence

Captured on 2026-07-26 from branch `feature/platform-rebuild`.

This directory records evidence that can be reproduced without provisioning
billable cloud infrastructure. The application is deployed to a dedicated Kind
cluster, while GitHub Actions validates the application, Kubernetes manifests,
Terraform configuration, and security controls.

## Evidence index

| Area | Status | Evidence |
| --- | --- | --- |
| Kubernetes deployment | Reproduced on Kind | [Kind deployment](kind-deployment.md) |
| Application workflow | Passed | [RAG smoke test](application-smoke-test.md) |
| Runtime logs | Captured | [Runtime logs](runtime-logs.md) |
| Metrics and dashboards | Captured | [Grafana dashboard](screenshots/grafana-rag-dashboard.jpg), [Prometheus targets](screenshots/prometheus-targets.jpg) |
| CI and security scans | Passed | [GitHub Actions evidence](ci-security.md) |
| Terraform syntax and configuration | Validated without apply | [Terraform evidence](terraform-validation.md) |
| AWS resource deployment | Not reproduced in this rebuild | Historical deployment only; no current AWS resource or screenshot claim |
| Terraform plan | Not captured | A trustworthy plan requires configured AWS identity and live provider reads |

## Scope statement

No AWS resources were created, changed, or destroyed while collecting this
evidence. Kind is the verified runtime environment for this rebuild. The
Terraform code remains a reviewed and CI-scanned design, not evidence of a
currently deployed AWS environment.
