data "tls_certificate" "eks_oidc" {
  url = var.oidc_issuer_url
}

locals {
  oidc_provider_host = replace(var.oidc_issuer_url, "https://", "")
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
      values   = ["system:serviceaccount:${var.rag_api_namespace}:${var.rag_api_service_account}"]
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
      var.document_bucket_arn,
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
      "${var.document_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = var.oidc_issuer_url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "rag_api" {
  name               = "${var.cluster_name}-rag-api"
  description        = "IRSA role for rag-api access to uploaded documents"
  assume_role_policy = data.aws_iam_policy_document.rag_api_assume_role.json
}

resource "aws_iam_policy" "rag_api_documents" {
  name        = "${var.cluster_name}-rag-api-documents"
  description = "Least-privilege rag-api access to the uploaded documents bucket"
  policy      = data.aws_iam_policy_document.rag_api_documents.json
}

resource "aws_iam_role_policy_attachment" "rag_api_documents" {
  role       = aws_iam_role.rag_api.name
  policy_arn = aws_iam_policy.rag_api_documents.arn
}
