variable "aws_region" {
  description = "AWS region where the dev infrastructure is created."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Short environment name used in resource names and tags."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.environment))
    error_message = "environment must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "name_prefix" {
  description = "Prefix used for named platform resources."
  type        = string
  default     = "llm-rag"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,24}$", var.name_prefix))
    error_message = "name_prefix must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the dev VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets. Provide one per availability zone."
  type        = list(string)
  default     = ["10.40.0.0/20", "10.40.16.0/20"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2
    error_message = "At least two public subnets are required for EKS."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets. Provide one per availability zone."
  type        = list(string)
  default     = ["10.40.128.0/20", "10.40.144.0/20"]

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2
    error_message = "At least two private subnets are required for EKS."
  }
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
  default     = "1.33"
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint. Restrict this for real environments."
  type        = list(string)
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes."
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes."
  type        = number
  default     = 3
}

variable "node_disk_size" {
  description = "Worker node root volume size in GiB."
  type        = number
  default     = 30
}

variable "rag_api_namespace" {
  description = "Kubernetes namespace for the rag-api service account allowed to read and write uploaded documents."
  type        = string
  default     = "rag"
}

variable "rag_api_service_account_name" {
  description = "Kubernetes service account name for rag-api IRSA."
  type        = string
  default     = "rag-api"
}

variable "force_destroy_document_bucket" {
  description = "Whether Terraform may delete the uploaded documents bucket even when it contains objects. Keep false for shared environments."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags applied to supported resources."
  type        = map(string)
  default     = {}
}
