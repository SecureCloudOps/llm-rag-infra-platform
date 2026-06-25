data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  az_count                = min(length(var.public_subnet_cidrs), length(var.private_subnet_cidrs), length(data.aws_availability_zones.available.names))
  availability_zones      = slice(data.aws_availability_zones.available.names, 0, local.az_count)
  nat_gateway_subnet_keys = var.single_nat_gateway ? [local.availability_zones[0]] : local.availability_zones
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.cluster_name}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.cluster_name}-igw"
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
    Name                                        = "${var.cluster_name}-public-${each.key}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
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
    Name                                        = "${var.cluster_name}-private-${each.key}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

resource "aws_eip" "nat" {
  for_each = {
    for key, subnet in aws_subnet.public : key => subnet
    if contains(local.nat_gateway_subnet_keys, key)
  }

  domain = "vpc"

  tags = {
    Name = "${var.cluster_name}-nat-${each.key}"
  }
}

resource "aws_nat_gateway" "this" {
  for_each = {
    for key, subnet in aws_subnet.public : key => subnet
    if contains(local.nat_gateway_subnet_keys, key)
  }

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = each.value.id

  tags = {
    Name = "${var.cluster_name}-nat-${each.key}"
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
    Name = "${var.cluster_name}-public"
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
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.this[local.availability_zones[0]].id : aws_nat_gateway.this[each.key].id
  }

  tags = {
    Name = "${var.cluster_name}-private-${each.key}"
  }
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}
