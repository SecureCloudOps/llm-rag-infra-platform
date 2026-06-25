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

output "nat_gateway_ids" {
  description = "NAT Gateway IDs keyed by availability zone. Dev defaults to one shared NAT Gateway."
  value       = module.networking.nat_gateway_ids
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

output "node_group_names" {
  description = "Managed node group names keyed by system and workloads."
  value       = module.eks.node_group_names
}

output "eks_addon_versions" {
  description = "Pinned EKS managed add-on versions applied to the cluster."
  value       = module.eks.addon_versions
}

output "eks_oidc_provider_arn" {
  description = "IAM OIDC provider ARN used by IRSA roles."
  value       = module.eks.oidc_provider_arn
}

output "ebs_csi_role_arn" {
  description = "IAM role ARN used by the AWS EBS CSI Driver managed add-on."
  value       = module.eks.ebs_csi_role_arn
}

output "rag_api_ecr_repository_url" {
  description = "ECR repository URL for rag-api images."
  value       = module.ecr.repository_url
}

output "rag_api_ecr_image_tag_mutability" {
  description = "Configured ECR image tag mutability for rag-api."
  value       = module.ecr.image_tag_mutability
}

output "uploaded_documents_bucket_name" {
  description = "S3 bucket name for uploaded documents."
  value       = module.storage.document_bucket_name
}

output "rag_api_role_arn" {
  description = "IAM role ARN to annotate on the rag-api Kubernetes service account."
  value       = module.iam.rag_api_role_arn
}
