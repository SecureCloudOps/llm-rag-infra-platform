output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets."
  value       = values(aws_subnet.public)[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets."
  value       = values(aws_subnet.private)[*].id
}

output "availability_zones" {
  description = "Availability zones selected for the subnet layout."
  value       = local.availability_zones
}
