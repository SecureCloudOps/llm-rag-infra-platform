output "repository_name" {
  description = "ECR repository name."
  value       = aws_ecr_repository.this.name
}

output "repository_url" {
  description = "ECR repository URL."
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "ECR repository ARN."
  value       = aws_ecr_repository.this.arn
}

output "image_tag_mutability" {
  description = "Configured image tag mutability for the repository."
  value       = aws_ecr_repository.this.image_tag_mutability
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used to encrypt ECR images."
  value       = aws_kms_key.ecr.arn
}
