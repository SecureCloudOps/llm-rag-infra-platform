output "oidc_provider_arn" {
  description = "IAM OIDC provider ARN for the EKS cluster."
  value       = var.oidc_provider_arn
}

output "rag_api_role_arn" {
  description = "IAM role ARN for the rag-api Kubernetes service account."
  value       = aws_iam_role.rag_api.arn
}

output "rag_api_policy_arn" {
  description = "IAM policy ARN for rag-api document bucket access."
  value       = aws_iam_policy.rag_api_documents.arn
}
