# Terraform Bootstrap

This layer creates the AWS resources Terraform needs before the rest of the
LLM RAG Infrastructure Platform can use remote state and GitHub Actions OIDC.

## Resources

- S3 bucket for Terraform remote state
- S3 versioning, server-side encryption, ownership controls, and public access blocking
- IAM OIDC provider for `token.actions.githubusercontent.com`
- IAM role trusted by configured GitHub Actions OIDC subjects
- Least-privilege IAM policy for Terraform state and S3 native lockfile access
- Optional attachment points for separately managed, narrowly scoped infrastructure policies

## Why this layer is local first

Terraform cannot use an S3 backend until the S3 state bucket already exists.
Run this bootstrap layer with the default local backend, then configure later
Terraform layers to use the generated S3 backend.

## Usage

```bash
cd infra/terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

Use a globally unique `state_bucket_name`. Keep
`force_destroy_state_bucket = false` for real environments so Terraform cannot
delete state history by accident.

## Remote State Backend Example

After applying this layer, configure downstream Terraform layers with the S3
backend and Terraform's S3 native lockfile support:

```hcl
terraform {
  backend "s3" {
    bucket       = "llm-rag-infra-platform-terraform-state-123456789012"
    key          = "llm-rag-infra-platform/envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

`use_lockfile = true` makes Terraform create an S3 lock object beside the state
object during operations. This avoids the older DynamoDB lock table pattern for
new Terraform versions that support S3 native locking.

## S3 Native Locking Permissions

The GitHub Actions Terraform role receives access only to:

- List the configured state prefix in the state bucket
- Read and write state objects under that prefix
- Create and delete S3 lockfile objects under that prefix

The lockfiles are normal S3 objects managed by Terraform. Bucket versioning is
enabled so state history remains recoverable.

## GitHub OIDC Authentication

GitHub Actions jobs should request an OIDC token and assume the output role ARN
instead of using long-lived AWS access keys.

Example workflow permissions:

```yaml
permissions:
  id-token: write
  contents: read
```

Example AWS credential step:

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/llm-rag-terraform-github-actions
    aws-region: us-east-1
```

By default, only `repo:<owner>/<repo>:ref:refs/heads/main` can assume the role.
Add explicit entries to `github_allowed_refs` or `github_extra_oidc_subjects`
when plan workflows need additional refs, environments, or pull request
subjects.

## Avoid Static AWS Keys

Static AWS keys in GitHub secrets are avoided because they are long-lived,
copyable credentials. If a key is exposed through logs, dependency compromise,
or repository misconfiguration, it remains usable until manually rotated.

OIDC uses short-lived credentials issued for a specific workflow run. AWS IAM
conditions restrict which repository and GitHub subject can assume the role,
and no AWS secret needs to be stored in GitHub.

## Downstream Infrastructure Permissions

This bootstrap layer intentionally does not attach broad infrastructure
permissions such as `AdministratorAccess`. Create narrowly scoped policies for
the concrete downstream Terraform layers, then pass their ARNs through
`terraform_additional_policy_arns`.
