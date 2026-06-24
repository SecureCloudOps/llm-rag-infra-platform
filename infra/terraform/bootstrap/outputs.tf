output "aws_account_id" {
  description = "AWS account ID where bootstrap resources were created."
  value       = data.aws_caller_identity.current.account_id
}

output "state_bucket_name" {
  description = "S3 bucket name for Terraform remote state."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "S3 bucket ARN for Terraform remote state."
  value       = aws_s3_bucket.terraform_state.arn
}

output "state_key_prefix" {
  description = "S3 key prefix intended for Terraform state objects."
  value       = local.state_object_prefix
}

output "github_actions_oidc_provider_arn" {
  description = "IAM OIDC provider ARN for GitHub Actions."
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "terraform_github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions Terraform workflows."
  value       = aws_iam_role.terraform_github_actions.arn
}

output "backend_example" {
  description = "Example Terraform S3 backend configuration using S3 native locking."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket       = "${aws_s3_bucket.terraform_state.id}"
        key          = "${local.state_object_prefix}/envs/dev/terraform.tfstate"
        region       = "${var.aws_region}"
        encrypt      = true
        use_lockfile = true
      }
    }
  EOT
}
