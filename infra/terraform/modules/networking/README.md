# Networking Module

Creates the VPC foundation for an EKS-backed RAG platform environment.

## Resources

- VPC with DNS support enabled
- Public and private subnets spread across available zones
- Internet gateway for public subnet egress
- Configurable NAT Gateways and elastic IPs for private subnet egress
- Public and private route tables
- Kubernetes subnet discovery tags for external and internal load balancers

## Inputs

- `cluster_name`: EKS cluster name used in resource names and Kubernetes tags
- `vpc_cidr`: VPC CIDR block
- `public_subnet_cidrs`: public subnet CIDR blocks
- `private_subnet_cidrs`: private subnet CIDR blocks
- `single_nat_gateway`: whether to share one NAT Gateway or create one per AZ

## Outputs

- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- `availability_zones`
- `nat_gateway_ids`
