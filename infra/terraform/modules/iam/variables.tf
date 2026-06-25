variable "cluster_name" {
  description = "EKS cluster name used for IAM resource names."
  type        = string
}

variable "oidc_issuer_url" {
  description = "EKS OIDC issuer URL."
  type        = string
}

variable "document_bucket_arn" {
  description = "ARN of the uploaded documents bucket."
  type        = string
}

variable "rag_api_namespace" {
  description = "Kubernetes namespace for the rag-api service account."
  type        = string
}

variable "rag_api_service_account" {
  description = "Kubernetes service account name for rag-api."
  type        = string
}
