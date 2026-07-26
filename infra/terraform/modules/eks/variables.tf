variable "cluster_name" {
  description = "Name of the EKS cluster and prefix for cluster-scoped resources."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,99}$", var.cluster_name))
    error_message = "cluster_name must start with a letter and contain only letters, numbers, and hyphens."
  }
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string

  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.cluster_version))
    error_message = "cluster_version must use the EKS minor version format, for example 1.33."
  }
}

variable "cluster_endpoint_private_access" {
  description = "Whether the EKS API endpoint is reachable from inside the VPC."
  type        = bool
  default     = true

  validation {
    condition     = var.cluster_endpoint_private_access
    error_message = "Private EKS endpoint access must remain enabled because public endpoint access is disabled."
  }
}

variable "cluster_security_group_egress_cidrs" {
  description = "CIDR blocks allowed for EKS control plane security group egress."
  type        = list(string)

  validation {
    condition     = length(var.cluster_security_group_egress_cidrs) > 0 && alltrue([for cidr in var.cluster_security_group_egress_cidrs : can(cidrhost(cidr, 0))])
    error_message = "cluster_security_group_egress_cidrs must contain at least one valid CIDR block."
  }
}

variable "vpc_id" {
  description = "VPC ID where the EKS cluster is created."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the EKS control plane."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the EKS control plane and managed nodes."
  type        = list(string)
}

variable "eks_addons" {
  description = "EKS managed add-ons keyed by add-on name. Versions are intentionally pinned and should be reviewed when upgrading cluster_version."
  type = map(object({
    version                  = string
    resolve_conflicts_create = optional(string, "OVERWRITE")
    resolve_conflicts_update = optional(string, "PRESERVE")
  }))

  validation {
    condition = alltrue([
      for addon_name in keys(var.eks_addons) :
      contains(["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"], addon_name)
    ])
    error_message = "eks_addons may only configure vpc-cni, coredns, kube-proxy, and aws-ebs-csi-driver."
  }

  validation {
    condition     = alltrue([for addon in values(var.eks_addons) : length(addon.version) > 0])
    error_message = "Each EKS add-on must include a pinned version."
  }
}

variable "node_groups" {
  description = "Managed node groups keyed by logical role, for example system and workloads."
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
