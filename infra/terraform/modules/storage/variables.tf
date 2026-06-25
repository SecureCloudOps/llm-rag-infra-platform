variable "bucket_prefix" {
  description = "Prefix for the generated S3 bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Whether Terraform may delete the bucket when it contains objects."
  type        = bool
  default     = false
}
