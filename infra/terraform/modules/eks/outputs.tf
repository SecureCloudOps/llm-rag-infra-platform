output "cluster_name" {
  description = "EKS cluster name."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS API endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_security_group_id" {
  description = "Security group attached to the EKS control plane."
  value       = aws_security_group.cluster.id
}

output "node_group_names" {
  description = "Managed node group names keyed by logical node group."
  value       = { for name, group in aws_eks_node_group.managed : name => group.node_group_name }
}

output "addon_versions" {
  description = "Pinned EKS managed add-on versions keyed by add-on name."
  value       = { for name, addon in aws_eks_addon.managed : name => addon.addon_version }
}

output "oidc_issuer_url" {
  description = "EKS OIDC issuer URL used by IRSA."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

output "oidc_provider_arn" {
  description = "IAM OIDC provider ARN used by IRSA roles."
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "oidc_provider_host" {
  description = "OIDC provider host without the https scheme, used in IAM trust policy conditions."
  value       = local.oidc_provider_host
}

output "ebs_csi_role_arn" {
  description = "IAM role ARN used by the AWS EBS CSI Driver managed add-on."
  value       = aws_iam_role.ebs_csi.arn
}
