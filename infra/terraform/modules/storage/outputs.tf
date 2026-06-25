output "document_bucket_name" {
  description = "S3 bucket name for uploaded documents."
  value       = aws_s3_bucket.documents.id
}

output "document_bucket_arn" {
  description = "S3 bucket ARN for uploaded documents."
  value       = aws_s3_bucket.documents.arn
}
