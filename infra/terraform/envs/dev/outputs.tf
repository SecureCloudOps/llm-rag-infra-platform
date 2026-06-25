output "vpc_id" {
  description = "ID of the dev VPC."
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of public subnets."
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets used by EKS worker nodes."
  value       = module.networking.private_subnet_ids
}

output "eks_cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API endpoint."
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_security_group_id" {
  description = "Security group attached to the EKS control plane."
  value       = module.eks.cluster_security_group_id
}

output "node_group_name" {
  description = "Managed node group name."
  value       = module.eks.node_group_name
}

output "rag_api_ecr_repository_url" {
  description = "ECR repository URL for rag-api images."
  value       = module.ecr.repository_url
}

output "uploaded_documents_bucket_name" {
  description = "S3 bucket name for uploaded documents."
  value       = module.storage.document_bucket_name
}

output "rag_api_role_arn" {
  description = "IAM role ARN to annotate on the rag-api Kubernetes service account."
  value       = module.iam.rag_api_role_arn
}
