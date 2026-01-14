# APEX TRADER - AWS Infrastructure Deployment Guide

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.5.0 installed
3. **Docker** for building container images
4. **MongoDB Atlas** account (or self-hosted MongoDB)

## Quick Start

### 1. Configure Variables

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review Plan

```bash
terraform plan
```

### 4. Deploy Infrastructure

```bash
terraform apply
```

### 5. Build and Push Docker Images

```bash
# Get ECR login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push backend
cd /app/backend
docker build -t apex-trader-backend .
docker tag apex-trader-backend:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/apex-trader-backend:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/apex-trader-backend:latest

# Build and push frontend
cd /app/frontend
docker build -t apex-trader-frontend .
docker tag apex-trader-frontend:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/apex-trader-frontend:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/apex-trader-frontend:latest
```

### 6. Force ECS Service Update

```bash
aws ecs update-service --cluster apex-trader-cluster --service apex-trader-backend --force-new-deployment
aws ecs update-service --cluster apex-trader-cluster --service apex-trader-frontend --force-new-deployment
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Internet                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Application Load    │
                    │      Balancer         │
                    │   (Public Subnets)    │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       │
┌───────────────┐       ┌───────────────┐              │
│   Frontend    │       │   Backend     │              │
│   Service     │       │   Service     │              │
│   (Fargate)   │       │   (Fargate)   │              │
└───────────────┘       └───────┬───────┘              │
                                │                       │
                    ┌───────────▼───────────┐          │
                    │   AWS Secrets         │          │
                    │   Manager             │          │
                    └───────────────────────┘          │
                                                       │
                    ┌───────────────────────┐          │
                    │   MongoDB Atlas       │◄─────────┘
                    │   (External)          │
                    └───────────────────────┘
```

## Resources Created

| Resource | Description | Estimated Monthly Cost |
|----------|-------------|----------------------|
| VPC | Networking with public/private subnets | ~$45 (NAT Gateway) |
| ECS Cluster | Fargate container orchestration | Included |
| Backend Service | 2x 0.5 vCPU, 1GB (Fargate) | ~$30 |
| Frontend Service | 2x 0.25 vCPU, 512MB (Fargate) | ~$15 |
| ALB | Application Load Balancer | ~$20 |
| ECR | Container image storage | ~$1-5 |
| CloudWatch | Logs and monitoring | ~$5-10 |
| Secrets Manager | Secure credential storage | ~$1 |

**Estimated Total:** ~$120-150/month for production setup

## Security Best Practices

1. **Never commit secrets** - Use `terraform.tfvars` (gitignored) or environment variables
2. **Enable encryption** - All data encrypted at rest and in transit
3. **Use private subnets** - Services run in private subnets with NAT
4. **Rotate credentials** - Regularly rotate API keys and passwords
5. **Enable CloudWatch alarms** - Monitor for anomalies

## Scaling

The infrastructure includes auto-scaling:

- **Target CPU**: 70% utilization
- **Min instances**: 1 (dev) / 2 (prod)
- **Max instances**: 10

To adjust scaling:

```hcl
# In main.tf, modify:
resource "aws_appautoscaling_target" "backend" {
  max_capacity = 20  # Increase max
  min_capacity = 3   # Increase min
}
```

## Monitoring

Access logs and metrics:

```bash
# View backend logs
aws logs tail /ecs/apex-trader/backend --follow

# View frontend logs
aws logs tail /ecs/apex-trader/frontend --follow
```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning:** This will delete all data. Backup MongoDB first!

## Troubleshooting

### ECS Tasks Not Starting

```bash
# Check task events
aws ecs describe-services --cluster apex-trader-cluster --services apex-trader-backend

# Check CloudWatch logs
aws logs tail /ecs/apex-trader/backend --since 1h
```

### Connection Issues

1. Check security group rules
2. Verify NAT Gateway is running
3. Check MongoDB Atlas IP whitelist

### High Costs

1. Switch to FARGATE_SPOT for non-production
2. Reduce min instances
3. Use single NAT Gateway (already configured for non-prod)
