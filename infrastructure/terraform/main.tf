# APEX TRADER - AWS Infrastructure as Code (Terraform)
# Production-ready infrastructure for high-frequency trading engine

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # S3 backend for state management (recommended for production)
  # Uncomment and configure for your environment
  # backend "s3" {
  #   bucket         = "apex-trader-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "apex-trader-terraform-locks"
  # }
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
# VARIABLES
# =============================================

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "apex-trader"
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "mongodb_atlas_uri" {
  description = "MongoDB Atlas connection string"
  type        = string
  sensitive   = true
}

variable "sendgrid_api_key" {
  description = "SendGrid API key for alerts"
  type        = string
  sensitive   = true
  default     = ""
}

variable "finnhub_api_key" {
  description = "Finnhub API key for sentiment analysis"
  type        = string
  sensitive   = true
  default     = ""
}

variable "polymarket_api_key" {
  description = "Polymarket API key"
  type        = string
  sensitive   = true
}

variable "polymarket_api_secret" {
  description = "Polymarket API secret"
  type        = string
  sensitive   = true
}

variable "polymarket_api_passphrase" {
  description = "Polymarket API passphrase"
  type        = string
  sensitive   = true
}

variable "wallet_private_key" {
  description = "Wallet private key for trading"
  type        = string
  sensitive   = true
}

# =============================================
# VPC & NETWORKING
# =============================================

module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  
  name = "${var.app_name}-vpc"
  cidr = "10.0.0.0/16"
  
  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
  
  enable_nat_gateway = true
  single_nat_gateway = var.environment != "production"
  
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name = "${var.app_name}-vpc"
  }
}

# =============================================
# ECR REPOSITORIES
# =============================================

resource "aws_ecr_repository" "backend" {
  name                 = "${var.app_name}-backend"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.app_name}-frontend"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
}

# ECR Lifecycle policies (keep last 10 images)
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
  
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# =============================================
# SECRETS MANAGER
# =============================================

resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "${var.app_name}/secrets"
  description             = "Application secrets for APEX TRADER"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    MONGO_URL                 = var.mongodb_atlas_uri
    DB_NAME                   = "apex_trader"
    SENDGRID_API_KEY          = var.sendgrid_api_key
    FINNHUB_API_KEY           = var.finnhub_api_key
    API_KEY                   = var.polymarket_api_key
    API_SECRET                = var.polymarket_api_secret
    API_PASSPHRASE            = var.polymarket_api_passphrase
    PRIVATE_KEY               = var.wallet_private_key
  })
}

# =============================================
# ECS CLUSTER
# =============================================

resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name
  
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  
  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = var.environment == "production" ? "FARGATE" : "FARGATE_SPOT"
  }
}

# =============================================
# IAM ROLES
# =============================================

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.app_name}-ecs-task-execution"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "secrets-access"
  role = aws_iam_role.ecs_task_execution.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = [aws_secretsmanager_secret.app_secrets.arn]
    }]
  })
}

# ECS Task Role
resource "aws_iam_role" "ecs_task" {
  name = "${var.app_name}-ecs-task"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "task-permissions"
  role = aws_iam_role.ecs_task.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [aws_secretsmanager_secret.app_secrets.arn]
      }
    ]
  })
}

# =============================================
# CLOUDWATCH LOG GROUPS
# =============================================

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.app_name}/backend"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${var.app_name}/frontend"
  retention_in_days = 30
}

# =============================================
# SECURITY GROUPS
# =============================================

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb-sg"
  description = "Security group for ALB"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    from_port   = 443
    to_port     = 443
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

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.app_name}-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = module.vpc.vpc_id
  
  ingress {
    from_port       = 8001
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  
  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# =============================================
# APPLICATION LOAD BALANCER
# =============================================

resource "aws_lb" "main" {
  name               = "${var.app_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets
  
  enable_deletion_protection = var.environment == "production"
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.app_name}-backend-tg"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/api/health"
    port                = "traffic-port"
    timeout             = 10
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${var.app_name}-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/"
    port                = "traffic-port"
    timeout             = 10
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
  
  condition {
    path_pattern {
      values = ["/api/*", "/ws"]
    }
  }
}

# =============================================
# ECS TASK DEFINITIONS
# =============================================

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.app_name}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([{
    name  = "backend"
    image = "${aws_ecr_repository.backend.repository_url}:latest"
    
    portMappings = [{
      containerPort = 8001
      hostPort      = 8001
      protocol      = "tcp"
    }]
    
    environment = [
      { name = "DB_NAME", value = "apex_trader" },
      { name = "CORS_ORIGINS", value = "*" },
      { name = "INITIAL_CAPITAL", value = "1000" },
      { name = "KELLY_FRACTION", value = "0.25" },
      { name = "MAX_DRAWDOWN_PCT", value = "3" },
      { name = "TRADES_PER_10MIN", value = "500" }
    ]
    
    secrets = [
      { name = "MONGO_URL", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:MONGO_URL::" },
      { name = "SENDGRID_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:SENDGRID_API_KEY::" },
      { name = "FINNHUB_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:FINNHUB_API_KEY::" },
      { name = "API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:API_KEY::" },
      { name = "API_SECRET", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:API_SECRET::" },
      { name = "API_PASSPHRASE", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:API_PASSPHRASE::" },
      { name = "PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:PRIVATE_KEY::" }
    ]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.backend.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
    
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8001/api/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.app_name}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([{
    name  = "frontend"
    image = "${aws_ecr_repository.frontend.repository_url}:latest"
    
    portMappings = [{
      containerPort = 3000
      hostPort      = 3000
      protocol      = "tcp"
    }]
    
    environment = [
      { name = "REACT_APP_BACKEND_URL", value = "http://${aws_lb.main.dns_name}" }
    ]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.frontend.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

# =============================================
# ECS SERVICES
# =============================================

resource "aws_ecs_service" "backend" {
  name            = "${var.app_name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.environment == "production" ? 2 : 1
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8001
  }
  
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.app_name}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.environment == "production" ? 2 : 1
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }
  
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  
  depends_on = [aws_lb_listener.http]
}

# =============================================
# AUTO SCALING
# =============================================

resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 10
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${var.app_name}-backend-cpu-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace
  
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# =============================================
# CLOUDWATCH ALARMS
# =============================================

resource "aws_cloudwatch_metric_alarm" "backend_cpu_high" {
  alarm_name          = "${var.app_name}-backend-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Backend CPU utilization is high"
  
  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_memory_high" {
  alarm_name          = "${var.app_name}-backend-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Backend memory utilization is high"
  
  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.backend.name
  }
}

# =============================================
# OUTPUTS
# =============================================

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "backend_ecr_repository_url" {
  description = "ECR repository URL for backend"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_repository_url" {
  description = "ECR repository URL for frontend"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}
