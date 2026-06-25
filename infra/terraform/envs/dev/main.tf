data "aws_availability_zones" "available" {
  state = "available"
}

data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

data "aws_iam_policy_document" "eks_cluster_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eks_node_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "rag_api_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_host}:sub"
      values   = ["system:serviceaccount:${var.rag_api_namespace}:${var.rag_api_service_account_name}"]
    }
  }
}

data "aws_iam_policy_document" "rag_api_documents" {
  statement {
    sid    = "ListUploadedDocumentsBucket"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.uploaded_documents.arn,
    ]
  }

  statement {
    sid    = "ReadWriteUploadedDocuments"
    effect = "Allow"

    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.uploaded_documents.arn}/*",
    ]
  }
}

data "aws_iam_policy_document" "uploaded_documents_bucket" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.uploaded_documents.arn,
      "${aws_s3_bucket.uploaded_documents.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

locals {
  az_count           = min(length(var.public_subnet_cidrs), length(var.private_subnet_cidrs), length(data.aws_availability_zones.available.names))
  availability_zones = slice(data.aws_availability_zones.available.names, 0, local.az_count)
  cluster_name       = "${var.name_prefix}-${var.environment}"
  oidc_provider_host = replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")

  common_tags = {
    Project     = "llm-rag-infra-platform"
    Environment = var.environment
    ManagedBy   = "terraform"
    Layer       = "dev"
  }

  tags = merge(local.common_tags, var.tags)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${local.cluster_name}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.cluster_name}-igw"
  }
}

resource "aws_subnet" "public" {
  for_each = {
    for index, cidr in slice(var.public_subnet_cidrs, 0, local.az_count) :
    local.availability_zones[index] => cidr
  }

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = {
    Name                                          = "${local.cluster_name}-public-${each.key}"
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                      = "1"
  }
}

resource "aws_subnet" "private" {
  for_each = {
    for index, cidr in slice(var.private_subnet_cidrs, 0, local.az_count) :
    local.availability_zones[index] => cidr
  }

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value
  availability_zone = each.key

  tags = {
    Name                                          = "${local.cluster_name}-private-${each.key}"
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"             = "1"
  }
}

resource "aws_eip" "nat" {
  for_each = aws_subnet.public

  domain = "vpc"

  tags = {
    Name = "${local.cluster_name}-nat-${each.key}"
  }
}

resource "aws_nat_gateway" "this" {
  for_each = aws_subnet.public

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = each.value.id

  tags = {
    Name = "${local.cluster_name}-nat-${each.key}"
  }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${local.cluster_name}-public"
  }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = aws_subnet.private

  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[each.key].id
  }

  tags = {
    Name = "${local.cluster_name}-private-${each.key}"
  }
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_security_group" "eks_cluster" {
  name        = "${local.cluster_name}-cluster"
  description = "EKS control plane security group"
  vpc_id      = aws_vpc.this.id

  egress {
    description = "Allow cluster egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.cluster_name}-cluster"
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${local.cluster_name}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume_role.json
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "this" {
  name     = local.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }

  enabled_cluster_log_types = [
    "api",
    "audit",
    "authenticator",
  ]

  vpc_config {
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.cluster_endpoint_public_access_cidrs
    security_group_ids      = [aws_security_group.eks_cluster.id]
    subnet_ids              = concat(values(aws_subnet.private)[*].id, values(aws_subnet.public)[*].id)
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster,
  ]
}

resource "aws_iam_role" "eks_node" {
  name               = "${local.cluster_name}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume_role.json
}

resource "aws_iam_role_policy_attachment" "eks_node_worker" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_registry" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${local.cluster_name}-default"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = values(aws_subnet.private)[*].id

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  disk_size      = var.node_disk_size
  instance_types = var.node_instance_types

  scaling_config {
    desired_size = var.node_desired_size
    max_size     = var.node_max_size
    min_size     = var.node_min_size
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_node_cni,
    aws_iam_role_policy_attachment.eks_node_registry,
    aws_iam_role_policy_attachment.eks_node_worker,
  ]
}

resource "aws_ecr_repository" "rag_api" {
  name                 = "${var.name_prefix}/rag-api"
  image_tag_mutability = "MUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "rag_api" {
  repository = aws_ecr_repository.rag_api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last 20 rag-api images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

resource "aws_s3_bucket" "uploaded_documents" {
  bucket_prefix = "${var.name_prefix}-${var.environment}-documents-"
  force_destroy = var.force_destroy_document_bucket
}

resource "aws_s3_bucket_public_access_block" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id

  rule {
    id     = "expire-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "uploaded_documents" {
  bucket = aws_s3_bucket.uploaded_documents.id
  policy = data.aws_iam_policy_document.uploaded_documents_bucket.json
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "rag_api" {
  name               = "${local.cluster_name}-rag-api"
  description        = "IRSA role for rag-api access to uploaded documents"
  assume_role_policy = data.aws_iam_policy_document.rag_api_assume_role.json
}

resource "aws_iam_policy" "rag_api_documents" {
  name        = "${local.cluster_name}-rag-api-documents"
  description = "Least-privilege rag-api access to the uploaded documents bucket"
  policy      = data.aws_iam_policy_document.rag_api_documents.json
}

resource "aws_iam_role_policy_attachment" "rag_api_documents" {
  role       = aws_iam_role.rag_api.name
  policy_arn = aws_iam_policy.rag_api_documents.arn
}
