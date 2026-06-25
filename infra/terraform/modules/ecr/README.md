# ECR Module

Creates an Amazon ECR repository for application container images.

## Resources

- ECR repository with AES256 encryption
- Image scan on push
- Lifecycle policy that keeps the most recent images

## Inputs

- `repository_name`
- `image_tag_mutability`
- `max_image_count`

## Outputs

- `repository_name`
- `repository_url`
- `repository_arn`
