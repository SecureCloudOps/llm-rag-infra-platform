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
}

module "eks" {
  source = "../../modules/eks"

  cluster_name                         = local.cluster_name
  cluster_version                      = var.cluster_version
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs
  vpc_id                               = module.networking.vpc_id
  public_subnet_ids                    = module.networking.public_subnet_ids
  private_subnet_ids                   = module.networking.private_subnet_ids
  node_instance_types                  = var.node_instance_types
  node_min_size                        = var.node_min_size
  node_desired_size                    = var.node_desired_size
  node_max_size                        = var.node_max_size
  node_disk_size                       = var.node_disk_size
}

module "ecr" {
  source = "../../modules/ecr"

  repository_name = "${var.name_prefix}/rag-api"
}

module "storage" {
  source = "../../modules/storage"

  bucket_prefix = "${var.name_prefix}-${var.environment}-documents-"
  force_destroy = var.force_destroy_document_bucket
}

module "iam" {
  source = "../../modules/iam"

  cluster_name            = local.cluster_name
  oidc_issuer_url         = module.eks.oidc_issuer_url
  document_bucket_arn     = module.storage.document_bucket_arn
  rag_api_namespace       = var.rag_api_namespace
  rag_api_service_account = var.rag_api_service_account_name
}
