variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint."
  type        = list(string)
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

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group."
  type        = list(string)
}

variable "node_desired_size" {
  description = "Desired number of worker nodes."
  type        = number
}

variable "node_min_size" {
  description = "Minimum number of worker nodes."
  type        = number
}

variable "node_max_size" {
  description = "Maximum number of worker nodes."
  type        = number
}

variable "node_disk_size" {
  description = "Worker node root volume size in GiB."
  type        = number
}
