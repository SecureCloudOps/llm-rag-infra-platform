# Terraform Validation Evidence

Captured on 2026-07-26 without applying infrastructure.

```text
$ terraform fmt -check -recursive infra/terraform
Exit code: 0

$ terraform -chdir=infra/terraform/envs/dev validate
Success! The configuration is valid.

$ terraform -chdir=infra/terraform/bootstrap validate
Success! The configuration is valid.
```

The GitHub Security Scan also passed the repository's explicit Checkov
Terraform policy gate. See [CI and security evidence](ci-security.md).

No `terraform plan` is presented as current evidence. A meaningful AWS plan
requires live provider reads using configured AWS identity. No `terraform
apply` was performed, and this rebuild makes no claim that the AWS resources
currently exist.

