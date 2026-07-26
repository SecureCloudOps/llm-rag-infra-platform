# CI and Security Evidence

PR: [#1 — Add repeatable Docker Compose RAG smoke testing](https://github.com/SecureCloudOps/llm-rag-infra-platform/pull/1)

The latest checked commit was
`cb1cd6d0ff30d5623b00b1859ca4ec2ef6442d78`. All required jobs completed
successfully:

- [RAG API CI](https://github.com/SecureCloudOps/llm-rag-infra-platform/actions/runs/30220487691)
- [Kubernetes Validate](https://github.com/SecureCloudOps/llm-rag-infra-platform/actions/runs/30220487683)
- [Security Scan](https://github.com/SecureCloudOps/llm-rag-infra-platform/actions/runs/30220487709)

The security workflow enforced:

- Trivy filesystem scanning
- Gitleaks secret scanning
- Checkov Terraform policy checks
- Checkov Kubernetes policy checks

The workflow links are the authoritative evidence because they preserve job
logs, commit identity, timestamps, and pass/fail conclusions.

