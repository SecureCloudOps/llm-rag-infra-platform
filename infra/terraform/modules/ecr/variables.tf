variable "repository_name" {
  description = "Name of the ECR repository."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+([._/-]?[a-z0-9]+)*$", var.repository_name))
    error_message = "repository_name must be a valid ECR repository name using lowercase letters, numbers, separators, and optional path segments."
  }
}

variable "image_tag_mutability" {
  description = "Image tag mutability setting for the repository. Use IMMUTABLE for deployment reproducibility."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "max_image_count" {
  description = "Maximum number of images to retain before lifecycle expiration removes older images."
  type        = number
  default     = 20

  validation {
    condition     = var.max_image_count >= 1
    error_message = "max_image_count must be at least 1."
  }
}
