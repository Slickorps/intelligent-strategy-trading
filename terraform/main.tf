# ---------------------------------------------------------------------------
# IST Trading Platform — Terraform (HCL)
# AWS infrastructure for Intelligent Strategy Trading Platform
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    bucket  = "ist-trading-terraform-state"
    key     = "terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

# ---------------------------------------------------------------------------
# Provider

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Variables

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "instance_type" {
  description = "EC2 instance type for the trading engine"
  type        = string
  default     = "t3.medium"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

# ---------------------------------------------------------------------------
# VPC & Networking

resource "aws_vpc" "ist" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "ist-${var.environment}"
    Environment = var.environment
    Project     = "intelligent-strategy-trading"
  }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.ist.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "ist-${var.environment}-public-a"
  }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.ist.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "ist-${var.environment}-public-b"
  }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.ist.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "ist-${var.environment}-private-a"
  }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.ist.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "ist-${var.environment}-private-b"
  }
}

resource "aws_internet_gateway" "ist" {
  vpc_id = aws_vpc.ist.id

  tags = {
    Name = "ist-${var.environment}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ist.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ist.id
  }

  tags = {
    Name = "ist-${var.environment}-public"
  }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "api" {
  name        = "ist-${var.environment}-api"
  description = "Security group for IST API server"
  vpc_id      = aws_vpc.ist.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "db" {
  name        = "ist-${var.environment}-db"
  description = "Security group for RDS database"
  vpc_id      = aws_vpc.ist.id

  ingress {
    description     = "PostgreSQL"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

# ---------------------------------------------------------------------------
# RDS (PostgreSQL)

resource "aws_db_subnet_group" "ist" {
  name       = "ist-${var.environment}"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = {
    Environment = var.environment
  }
}

resource "aws_db_instance" "ist" {
  identifier           = "ist-${var.environment}"
  engine               = "postgres"
  engine_version       = "16"
  instance_class       = var.db_instance_class
  allocated_storage    = 20
  max_allocated_storage= 100
  storage_encrypted    = true
  db_name              = "ist_trading"
  username             = "ist_admin"
  password             = var.db_password
  skip_final_snapshot  = var.environment != "prod"
  db_subnet_group_name = aws_db_subnet_group.ist.name
  vpc_security_group_ids = [aws_security_group.db.id]

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  tags = {
    Environment = var.environment
    Project     = "intelligent-strategy-trading"
  }
}

# ---------------------------------------------------------------------------
# ElastiCache (Redis)

resource "aws_elasticache_cluster" "ist" {
  cluster_id           = "ist-cache-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.ist.name
  security_group_ids   = [aws_security_group.api.id]
}

resource "aws_elasticache_subnet_group" "ist" {
  name       = "ist-cache-subnet-${var.environment}"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# ---------------------------------------------------------------------------
# EC2 (Trading Engine)

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

resource "aws_instance" "engine" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.api.id]
  key_name               = var.ec2_key_name

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    environment = var.environment
    db_host     = aws_db_instance.ist.address
    db_password = var.db_password
    redis_host  = aws_elasticache_cluster.ist.cache_nodes[0].address
  })

  tags = {
    Name        = "ist-engine-${var.environment}"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------------------
# Outputs

output "api_endpoint" {
  description = "Public IP of the trading engine"
  value       = "http://${aws_instance.engine.public_ip}:8000"
}

output "db_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.ist.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache endpoint"
  value       = aws_elasticache_cluster.ist.cache_nodes[0].address
}