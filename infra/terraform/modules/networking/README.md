# Networking Module

Creates the VPC foundation for an EKS-backed RAG platform environment.

## Resources

- VPC with DNS support enabled
- Public and private subnets spread across available zones
- Internet gateway for public subnet egress
- NAT gateways and elastic IPs for private subnet egress
- Public and private route tables
- Kubernetes subnet discovery tags for external and internal load balancers

## Inputs

- `cluster_name`: EKS cluster name used in resource names and Kubernetes tags
- `vpc_cidr`: VPC CIDR block
- `public_subnet_cidrs`: public subnet CIDR blocks
- `private_subnet_cidrs`: private subnet CIDR blocks

## Outputs

- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- `availability_zones`
