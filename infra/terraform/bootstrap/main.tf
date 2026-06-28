data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "github_actions_trust" {
  statement {
    sid     = "AllowGitHubActionsOidc"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_oidc_subjects
    }
  }
}

data "aws_iam_policy_document" "terraform_state_bucket" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

data "aws_iam_policy_document" "terraform_state" {
  statement {
    sid    = "ListTerraformStateBucketPrefix"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.terraform_state.arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.state_object_prefix,
        "${local.state_object_prefix}/*",
      ]
    }
  }

  statement {
    sid    = "ReadWriteTerraformStateAndLockfiles"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.state_object_prefix}/*",
    ]
  }

  statement {
    sid    = "DeleteTerraformLockfiles"
    effect = "Allow"

    actions = [
      "s3:DeleteObject",
    ]

    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.state_object_prefix}/*.tflock",
    ]
  }
}

locals {
  github_ref_subjects = [
    for ref in var.github_allowed_refs :
    "repo:${var.github_owner}/${var.github_repository}:ref:${ref}"
  ]

  github_oidc_subjects = distinct(concat(local.github_ref_subjects, var.github_extra_oidc_subjects))
  state_object_prefix  = trim(var.state_key_prefix, "/")
}

resource "aws_s3_bucket" "terraform_state" {
  bucket        = var.state_bucket_name
  force_destroy = var.force_destroy_state_bucket
}

resource "aws_kms_key" "terraform_state" {
  description             = "KMS key for Terraform state bucket encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "terraform_state" {
  name          = "alias/${var.state_bucket_name}-terraform-state"
  target_key_id = aws_kms_key.terraform_state.key_id
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.terraform_state_bucket.json
}

resource "aws_s3_bucket_ownership_controls" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.terraform_state.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    id     = "retain-noncurrent-state-versions"
    status = "Enabled"

    filter {
      prefix = local.state_object_prefix
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]
}

resource "aws_iam_role" "terraform_github_actions" {
  name                 = var.terraform_role_name
  description          = "GitHub Actions role for Terraform plan and apply in ${var.github_owner}/${var.github_repository}"
  assume_role_policy   = data.aws_iam_policy_document.github_actions_trust.json
  max_session_duration = var.terraform_role_max_session_duration
}

resource "aws_iam_policy" "terraform_state" {
  name        = "${var.terraform_role_name}-state"
  description = "Least-privilege access to Terraform state and S3 native lockfiles"
  policy      = data.aws_iam_policy_document.terraform_state.json
}

resource "aws_iam_role_policy_attachment" "terraform_state" {
  role       = aws_iam_role.terraform_github_actions.name
  policy_arn = aws_iam_policy.terraform_state.arn
}

resource "aws_iam_role_policy_attachment" "additional" {
  for_each = toset(var.terraform_additional_policy_arns)

  role       = aws_iam_role.terraform_github_actions.name
  policy_arn = each.value
}
