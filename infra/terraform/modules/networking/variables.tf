variable "cluster_name" {
  description = "EKS cluster name used for resource names and Kubernetes subnet discovery tags."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets. Provide one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2
    error_message = "At least two public subnets are required for EKS."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets. Provide one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2
    error_message = "At least two private subnets are required for EKS."
  }
}
