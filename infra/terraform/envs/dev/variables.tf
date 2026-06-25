variable "aws_region" {
  description = "AWS region where the dev infrastructure is created."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must be a valid AWS region name such as us-east-1."
  }
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
  description = "IPv4 CIDR block for the dev VPC."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets. Provide one per availability zone."
  type        = list(string)
  default     = ["10.40.0.0/20", "10.40.16.0/20"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2 && alltrue([for cidr in var.public_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "At least two valid public subnet CIDR blocks are required for EKS."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets. Provide one per availability zone."
  type        = list(string)
  default     = ["10.40.128.0/20", "10.40.144.0/20"]

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2 && alltrue([for cidr in var.private_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "At least two valid private subnet CIDR blocks are required for EKS."
  }
}

variable "single_nat_gateway" {
  description = "Use one shared NAT Gateway for dev cost control. Set false in production-like environments for one NAT Gateway per AZ."
  type        = bool
  default     = true
}

variable "cluster_version" {
  description = "Kubernetes minor version for the EKS cluster. Review pinned EKS add-on versions when changing this."
  type        = string
  default     = "1.33"

  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.cluster_version))
    error_message = "cluster_version must use the EKS minor version format, for example 1.33."
  }
}

variable "cluster_endpoint_public_access" {
  description = "Keep the EKS API endpoint public for dev access. Set false for private-only production clusters."
  type        = bool
  default     = true

  validation {
    condition     = var.cluster_endpoint_public_access || var.cluster_endpoint_private_access
    error_message = "At least one EKS endpoint access mode must be enabled."
  }
}

variable "cluster_endpoint_private_access" {
  description = "Allow the EKS API endpoint to be reached from inside the VPC."
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint. Defaults to a documentation-only placeholder; replace before applying."
  type        = list(string)
  default     = ["203.0.113.10/32"]

  validation {
    condition     = alltrue([for cidr in var.cluster_endpoint_public_access_cidrs : can(cidrhost(cidr, 0))])
    error_message = "cluster_endpoint_public_access_cidrs must contain valid CIDR blocks."
  }
}

variable "eks_addons" {
  description = "Pinned EKS managed add-on versions for the dev cluster."
  type = map(object({
    version                  = string
    resolve_conflicts_create = optional(string, "OVERWRITE")
    resolve_conflicts_update = optional(string, "PRESERVE")
  }))
  default = {
    vpc-cni = {
      version = "v1.20.4-eksbuild.1"
    }
    coredns = {
      version = "v1.12.2-eksbuild.4"
    }
    kube-proxy = {
      version = "v1.33.3-eksbuild.6"
    }
    aws-ebs-csi-driver = {
      version = "v1.48.0-eksbuild.2"
    }
  }

  validation {
    condition = alltrue([
      for addon_name in keys(var.eks_addons) :
      contains(["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"], addon_name)
    ])
    error_message = "eks_addons may only configure vpc-cni, coredns, kube-proxy, and aws-ebs-csi-driver."
  }
}

variable "node_groups" {
  description = "EKS managed node groups for platform system pods and application workloads."
  type = map(object({
    instance_types = list(string)
    min_size       = number
    desired_size   = number
    max_size       = number
    disk_size      = number
    ami_type       = optional(string, "AL2023_x86_64_STANDARD")
    capacity_type  = optional(string, "ON_DEMAND")
    labels         = optional(map(string), {})
    taints = optional(list(object({
      key    = string
      value  = optional(string)
      effect = string
    })), [])
  }))
  default = {
    system = {
      instance_types = ["t3.medium"]
      min_size       = 1
      desired_size   = 1
      max_size       = 2
      disk_size      = 30
      labels = {
        role = "system"
      }
    }
    workloads = {
      instance_types = ["t3.medium"]
      min_size       = 1
      desired_size   = 1
      max_size       = 3
      disk_size      = 30
      labels = {
        role = "workloads"
      }
    }
  }

  validation {
    condition     = alltrue([for required in ["system", "workloads"] : contains(keys(var.node_groups), required)])
    error_message = "node_groups must include both system and workloads entries."
  }

  validation {
    condition = alltrue([
      for group in values(var.node_groups) :
      group.min_size >= 0 &&
      group.desired_size >= group.min_size &&
      group.max_size >= group.desired_size &&
      group.disk_size >= 20 &&
      length(group.instance_types) > 0 &&
      alltrue([for taint in group.taints : contains(["NO_SCHEDULE", "NO_EXECUTE", "PREFER_NO_SCHEDULE"], taint.effect)])
    ])
    error_message = "Each node group must have min <= desired <= max, disk_size >= 20, at least one instance type, and valid EKS taint effects."
  }
}

variable "ecr_image_tag_mutability" {
  description = "Image tag mutability for the rag-api ECR repository. IMMUTABLE prevents retagging pushed images."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.ecr_image_tag_mutability)
    error_message = "ecr_image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
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
