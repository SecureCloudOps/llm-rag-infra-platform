variable "cluster_name" {
  description = "EKS cluster name used for resource names and Kubernetes subnet discovery tags."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets. Provide one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2 && alltrue([for cidr in var.public_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "At least two valid public subnet CIDR blocks are required for EKS."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets. Provide one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2 && alltrue([for cidr in var.private_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "At least two valid private subnet CIDR blocks are required for EKS."
  }
}

variable "single_nat_gateway" {
  description = "When true, create one NAT Gateway shared by all private subnets. When false, create one NAT Gateway per public subnet/AZ."
  type        = bool
  default     = true
}
