data "aws_iam_policy_document" "rag_api_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_host}:sub"
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
