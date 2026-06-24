variable "aws_region" {
  description = "AWS region where the bootstrap resources are created."
  type        = string
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform remote state."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "state_bucket_name must be a valid S3 bucket name between 3 and 63 characters."
  }
}

variable "state_key_prefix" {
  description = "S3 key prefix used by Terraform state files in this platform."
  type        = string
  default     = "llm-rag-infra-platform"

  validation {
    condition     = !startswith(var.state_key_prefix, "/") && !endswith(var.state_key_prefix, "/")
    error_message = "state_key_prefix must not start or end with a slash."
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name allowed to assume the Terraform role."
  type        = string
}

variable "github_allowed_refs" {
  description = "Git refs allowed to assume the Terraform role, for example refs/heads/main."
  type        = list(string)
  default     = ["refs/heads/main"]
}

variable "github_extra_oidc_subjects" {
  description = "Additional exact or wildcard GitHub OIDC subject patterns allowed to assume the Terraform role, for example repo:owner/repo:pull_request."
  type        = list(string)
  default     = []
}

variable "terraform_role_name" {
  description = "Name of the IAM role assumed by GitHub Actions Terraform workflows."
  type        = string
  default     = "llm-rag-terraform-github-actions"
}

variable "terraform_role_max_session_duration" {
  description = "Maximum STS session duration, in seconds, for the GitHub Actions Terraform role."
  type        = number
  default     = 3600
}

variable "terraform_additional_policy_arns" {
  description = "Additional narrowly scoped managed policy ARNs to attach to the GitHub Actions Terraform role for non-state infrastructure permissions."
  type        = list(string)
  default     = []
}

variable "force_destroy_state_bucket" {
  description = "Whether Terraform may delete the state bucket even when it contains objects. Keep false for real environments."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to supported bootstrap resources."
  type        = map(string)
  default = {
    Project   = "llm-rag-infra-platform"
    ManagedBy = "terraform"
    Layer     = "bootstrap"
  }
}
