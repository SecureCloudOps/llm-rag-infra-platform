locals {
  cluster_name = "${var.name_prefix}-${var.environment}"

  common_tags = {
    Project     = "llm-rag-infra-platform"
    Environment = var.environment
    ManagedBy   = "terraform"
    Layer       = "dev"
  }

  tags = merge(local.common_tags, var.tags)
}

module "networking" {
  source = "../../modules/networking"

  cluster_name         = local.cluster_name
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
}

module "eks" {
  source = "../../modules/eks"

  cluster_name                         = local.cluster_name
  cluster_version                      = var.cluster_version
  cluster_endpoint_public_access       = var.cluster_endpoint_public_access
  cluster_endpoint_private_access      = var.cluster_endpoint_private_access
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs
  vpc_id                               = module.networking.vpc_id
  public_subnet_ids                    = module.networking.public_subnet_ids
  private_subnet_ids                   = module.networking.private_subnet_ids
  eks_addons                           = var.eks_addons
  node_groups                          = var.node_groups
}

module "ecr" {
  source = "../../modules/ecr"

  repository_name      = "${var.name_prefix}/rag-api"
  image_tag_mutability = var.ecr_image_tag_mutability
}

module "storage" {
  source = "../../modules/storage"

  bucket_prefix = "${var.name_prefix}-${var.environment}-documents-"
  force_destroy = var.force_destroy_document_bucket
}

module "iam" {
  source = "../../modules/iam"

  cluster_name            = local.cluster_name
  oidc_provider_arn       = module.eks.oidc_provider_arn
  oidc_provider_host      = module.eks.oidc_provider_host
  document_bucket_arn     = module.storage.document_bucket_arn
  rag_api_namespace       = var.rag_api_namespace
  rag_api_service_account = var.rag_api_service_account_name
}
