# APEX TRADER - EC2 Deployment

Simple single-server deployment for APEX TRADER on AWS EC2.

## Overview

This Terraform configuration deploys:
- **EC2 Instance** (t3.medium by default) with Ubuntu 22.04
- **VPC** with public subnet
- **Elastic IP** for static public address
- **Security Group** with necessary ports
- **Nginx** reverse proxy
- **CloudWatch** monitoring alarms

## Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| t3.medium EC2 | ~$30 |
| EIP | ~$3 |
| Storage (30GB gp3) | ~$3 |
| **Total** | **~$36/month** |

## Prerequisites

1. **AWS Account** with credentials configured
2. **SSH Key Pair** created in AWS Console
3. **MongoDB Atlas** cluster (free tier works)
4. **Polymarket API** credentials
5. **Terraform** installed (v1.5+)

## Quick Start

### 1. Configure Variables

```bash
cd /app/infrastructure/terraform/ec2
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:
- MongoDB connection string
- Polymarket API credentials
- SSH key name
- Optional: SendGrid API key for alerts

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review Plan

```bash
terraform plan
```

### 4. Deploy

```bash
terraform apply
```

### 5. Connect to Server

After deployment, Terraform outputs the SSH command:

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<public-ip>
```

### 6. Deploy Application Code

```bash
# On the server
cd /opt/apex-trader

# Clone your repo (or upload via scp)
git clone https://github.com/YOUR_USER/apex-trader.git app

# Setup backend
cd /opt/apex-trader/backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup frontend
cd /opt/apex-trader/frontend
npm install
npm run build  # For production

# Start services
sudo systemctl daemon-reload
sudo systemctl enable apex-backend apex-frontend
sudo systemctl start apex-backend apex-frontend
```

## Architecture

```
Internet
    │
    ▼
[Elastic IP] ──► [EC2 Instance]
                      │
                      ├── Nginx (port 80/443)
                      │     ├── / → Frontend (3000)
                      │     └── /api → Backend (8001)
                      │
                      ├── Frontend Service (React)
                      │
                      └── Backend Service (FastAPI)
                            │
                            ▼
                      [MongoDB Atlas]
```

## Security Notes

1. **SSH Access**: Consider restricting SSH to your IP only
2. **Secrets**: Never commit terraform.tfvars to git
3. **SSL**: For production, add domain and enable certbot

## Adding SSL (Optional)

If you have a domain:

```bash
# On the server
sudo certbot --nginx -d yourdomain.com
```

## Monitoring

- CloudWatch alarms for CPU and instance health
- Logs: `/var/log/apex-trader-setup.log`
- Service logs: `journalctl -u apex-backend -f`

## Scaling Up

If you need more power:

```hcl
# In terraform.tfvars
instance_type = "t3.large"   # 2 vCPU, 8GB RAM
# or
instance_type = "t3.xlarge"  # 4 vCPU, 16GB RAM
```

Then:
```bash
terraform apply
```

## Destroying

To tear down all resources:

```bash
terraform destroy
```

## Troubleshooting

### Services not starting

```bash
# Check service status
sudo systemctl status apex-backend
sudo systemctl status apex-frontend

# View logs
journalctl -u apex-backend -n 100
journalctl -u apex-frontend -n 100
```

### Nginx issues

```bash
sudo nginx -t
sudo systemctl status nginx
```

### MongoDB connection issues

- Verify IP whitelist in MongoDB Atlas (add EC2 public IP)
- Test connection: `mongosh "your-connection-string"`
