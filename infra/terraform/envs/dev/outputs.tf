output "vpc_id" {
  description = "ID of the dev VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets."
  value       = values(aws_subnet.public)[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets used by EKS worker nodes."
  value       = values(aws_subnet.private)[*].id
}

output "eks_cluster_name" {
  description = "EKS cluster name."
  value       = aws_eks_cluster.this.name
}

output "eks_cluster_endpoint" {
  description = "EKS API endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "eks_cluster_security_group_id" {
  description = "Security group attached to the EKS control plane."
  value       = aws_security_group.eks_cluster.id
}

output "node_group_name" {
  description = "Managed node group name."
  value       = aws_eks_node_group.default.node_group_name
}

output "rag_api_ecr_repository_url" {
  description = "ECR repository URL for rag-api images."
  value       = aws_ecr_repository.rag_api.repository_url
}

output "uploaded_documents_bucket_name" {
  description = "S3 bucket name for uploaded documents."
  value       = aws_s3_bucket.uploaded_documents.id
}

output "rag_api_role_arn" {
  description = "IAM role ARN to annotate on the rag-api Kubernetes service account."
  value       = aws_iam_role.rag_api.arn
}
