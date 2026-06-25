# EKS Module

Creates the Kubernetes control plane, managed add-ons, and managed node groups
for the platform environment.

## Resources

- EKS control plane security group
- IAM role and policy attachment for the EKS cluster
- EKS cluster with API, audit, and authenticator logs enabled
- EKS OIDC provider for IRSA
- IRSA role for the AWS EBS CSI Driver
- IAM role and policy attachments for worker nodes
- EKS managed add-ons for VPC CNI, CoreDNS, kube-proxy, and the AWS EBS CSI driver
- EKS managed node groups in private subnets

## Inputs

- `cluster_name`
- `cluster_version`
- `cluster_endpoint_public_access`
- `cluster_endpoint_private_access`
- `cluster_endpoint_public_access_cidrs`
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- `eks_addons`
- `node_groups`

## Outputs

- `cluster_name`
- `cluster_endpoint`
- `cluster_security_group_id`
- `node_group_names`
- `addon_versions`
- `oidc_issuer_url`
- `oidc_provider_arn`
- `oidc_provider_host`
- `ebs_csi_role_arn`
