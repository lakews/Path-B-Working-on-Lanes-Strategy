# APEX TRADER - EC2 Deployment (Simple Single-Server)
# Faster to deploy, easier to debug - recommended for MVP/Testing

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "apex-trader"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# =============================================
# VARIABLES (now in variables.tf)
# =============================================

# See variables.tf for all variable definitions

# =============================================
# DATA SOURCES
# =============================================

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# =============================================
# VPC & NETWORKING
# =============================================

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "apex-trader-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "apex-trader-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "apex-trader-public-subnet"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "apex-trader-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# =============================================
# SECURITY GROUP
# =============================================

resource "aws_security_group" "apex_trader" {
  name        = "apex-trader-sg"
  description = "Security group for APEX TRADER"
  vpc_id      = aws_vpc.main.id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP in production
    description = "SSH"
  }

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP"
  }

  # HTTPS
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS"
  }

  # Application ports (for direct access during development)
  ingress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Frontend"
  }

  ingress {
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Backend API"
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "apex-trader-sg"
  }
}

# =============================================
# EC2 INSTANCE
# =============================================

resource "aws_instance" "apex_trader" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.apex_trader.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    mongodb_uri               = var.mongodb_uri
    polymarket_api_key        = var.polymarket_api_key
    polymarket_api_secret     = var.polymarket_api_secret
    polymarket_api_passphrase = var.polymarket_api_passphrase
    wallet_private_key        = var.wallet_private_key
    sendgrid_api_key          = var.sendgrid_api_key
    alert_email               = var.alert_email
    domain_name               = var.domain_name
  }))

  tags = {
    Name = "apex-trader-server"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================
# ELASTIC IP
# =============================================

resource "aws_eip" "apex_trader" {
  instance = aws_instance.apex_trader.id
  domain   = "vpc"

  tags = {
    Name = "apex-trader-eip"
  }
}

# =============================================
# CLOUDWATCH ALARMS
# =============================================

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "apex-trader-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "CPU utilization is high"

  dimensions = {
    InstanceId = aws_instance.apex_trader.id
  }
}

resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "apex-trader-status-check"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Instance status check failed"

  dimensions = {
    InstanceId = aws_instance.apex_trader.id
  }
}

# =============================================
# OUTPUTS
# =============================================

output "public_ip" {
  description = "Public IP address of the server"
  value       = aws_eip.apex_trader.public_ip
}

output "public_dns" {
  description = "Public DNS name"
  value       = aws_instance.apex_trader.public_dns
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_eip.apex_trader.public_ip}"
}

output "frontend_url" {
  description = "Frontend URL"
  value       = "http://${aws_eip.apex_trader.public_ip}"
}

output "backend_api_url" {
  description = "Backend API URL"
  value       = "http://${aws_eip.apex_trader.public_ip}/api"
}

output "instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.apex_trader.id
}
