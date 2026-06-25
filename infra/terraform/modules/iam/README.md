# IAM Module

Creates IAM resources that connect EKS workloads to AWS permissions without
static credentials.

## Resources

- EKS IAM OIDC provider
- IRSA role for the `rag-api` Kubernetes service account
- Least-privilege S3 policy scoped to the uploaded documents bucket
- Policy attachment for the IRSA role

## Inputs

- `cluster_name`
- `oidc_issuer_url`
- `document_bucket_arn`
- `rag_api_namespace`
- `rag_api_service_account`

## Outputs

- `oidc_provider_arn`
- `rag_api_role_arn`
- `rag_api_policy_arn`
