# EKS Module

Creates the Kubernetes control plane and one managed node group for the
platform environment.

## Resources

- EKS control plane security group
- IAM role and policy attachment for the EKS cluster
- EKS cluster with API, audit, and authenticator logs enabled
- IAM role and policy attachments for worker nodes
- EKS managed node group in private subnets

## Inputs

- `cluster_name`
- `cluster_version`
- `cluster_endpoint_public_access_cidrs`
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- Node group sizing and instance settings

## Outputs

- `cluster_name`
- `cluster_endpoint`
- `cluster_security_group_id`
- `node_group_name`
- `oidc_issuer_url`
