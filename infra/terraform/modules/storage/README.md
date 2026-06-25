# Storage Module

Creates the S3 bucket used for uploaded documents.

## Resources

- S3 bucket with generated name from a safe prefix
- Public access block
- Bucket owner enforced object ownership
- Versioning
- AES256 server-side encryption
- Lifecycle rule for incomplete multipart uploads
- Bucket policy that denies non-TLS access

## Inputs

- `bucket_prefix`
- `force_destroy`

## Outputs

- `document_bucket_name`
- `document_bucket_arn`
