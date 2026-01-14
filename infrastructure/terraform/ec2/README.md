# APEX TRADER - EC2 Deployment

Deploy APEX TRADER to a single AWS EC2 instance. Simple, cost-effective, easy to debug.

## Quick Start

```bash
# 1. Configure
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Fill in your values

# 2. Deploy
terraform init
terraform plan
terraform apply

# 3. Connect
ssh -i ~/.ssh/YOUR_KEY.pem ubuntu@ELASTIC_IP
```

## Files

| File | Purpose |
|------|---------|
| `main.tf` | Main infrastructure (VPC, EC2, Security Groups) |
| `variables.tf` | All variable definitions with validation |
| `outputs.tf` | Connection info and URLs after deployment |
| `user_data.sh` | Server bootstrap script (Docker, Nginx, Node, Python) |
| `terraform.tfvars.example` | Example configuration (copy to terraform.tfvars) |

## Requirements

- AWS Account with EC2/VPC permissions
- Terraform v1.5+
- SSH key pair uploaded to AWS
- MongoDB Atlas connection string
- Polymarket API credentials (for live trading)

## Resources Created

- **VPC** with public subnet and internet gateway
- **EC2 Instance** (t3.medium by default)
- **Elastic IP** for stable addressing
- **Security Group** with ports: 22 (SSH), 80 (HTTP), 443 (HTTPS), 3000, 8001
- **CloudWatch Alarms** for CPU and health monitoring

## Cost

~$33/month (t3.medium in us-east-1)

## Full Documentation

See [/app/docs/DEPLOYMENT.md](/app/docs/DEPLOYMENT.md) for complete deployment guide.
