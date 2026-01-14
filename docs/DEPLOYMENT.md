# APEX TRADER - Deployment Guide

## Overview

This guide covers deploying APEX TRADER to AWS EC2 using Terraform. The setup creates:
- A VPC with public subnet
- An EC2 instance (t3.medium) with Docker, Nginx, Node.js, Python
- Security group with HTTP/HTTPS/SSH access
- CloudWatch monitoring alarms
- Elastic IP for stable addressing

---

## Prerequisites

### 1. AWS Account Setup
- Active AWS account with billing enabled
- IAM user with AdministratorAccess or these permissions:
  - EC2 (full access)
  - VPC (full access)
  - CloudWatch (full access)
  - IAM (read-only for role lookup)

### 2. Local Tools
```bash
# Install Terraform (v1.5+)
brew install terraform  # macOS
# OR
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# Verify
terraform --version
```

### 3. AWS CLI Configuration
```bash
# Install AWS CLI
pip install awscli

# Configure credentials
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1), Output (json)
```

### 4. SSH Key Pair
```bash
# Generate SSH key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/apex-trader-key

# Upload to AWS (via Console or CLI)
aws ec2 import-key-pair --key-name apex-trader-key --public-key-material fileb://~/.ssh/apex-trader-key.pub
```

### 5. MongoDB Atlas Account
- Create free cluster at https://cloud.mongodb.com
- Get connection string (mongodb+srv://...)
- Whitelist all IPs (0.0.0.0/0) or the EC2 Elastic IP after deployment

### 6. Polymarket API Credentials
- Get API credentials from Polymarket CLOB documentation
- You'll need: API Key, API Secret, API Passphrase

---

## Deployment Steps

### Step 1: Clone and Configure

```bash
cd /app/infrastructure/terraform/ec2

# Copy example config
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
nano terraform.tfvars
```

**terraform.tfvars contents:**
```hcl
# AWS Configuration
aws_region = "us-east-1"
environment = "production"
key_name = "apex-trader-key"

# Instance (t3.medium = 2 vCPU, 4GB RAM)
instance_type = "t3.medium"

# Database (MongoDB Atlas)
mongodb_uri = "mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority"

# Polymarket API (required for live trading)
polymarket_api_key = "your-api-key"
polymarket_api_secret = "your-api-secret"
polymarket_api_passphrase = "your-passphrase"
wallet_private_key = "0x..."  # ⚠️ Keep secure!

# Optional: Alerts
sendgrid_api_key = ""  # For email alerts
alert_email = "your@email.com"

# Optional: Custom domain
domain_name = ""  # Leave empty for IP-based access
```

### Step 2: Initialize Terraform

```bash
terraform init
```

Expected output:
```
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.x.x...

Terraform has been successfully initialized!
```

### Step 3: Review Plan

```bash
terraform plan
```

Review the resources to be created:
- 1 VPC
- 1 Internet Gateway
- 1 Subnet
- 1 Route Table
- 1 Security Group
- 1 EC2 Instance
- 1 Elastic IP
- 2 CloudWatch Alarms

### Step 4: Deploy

```bash
terraform apply
```

Type `yes` when prompted. Deployment takes ~5 minutes.

### Step 5: Verify Outputs

```
Apply complete! Resources: 11 added, 0 changed, 0 destroyed.

Outputs:

frontend_url = "http://1.2.3.4"
backend_api_url = "http://1.2.3.4/api"
ssh_command = "ssh -i ~/.ssh/apex-trader-key.pem ubuntu@1.2.3.4"
```

---

## Post-Deployment Setup

### Step 1: SSH into Server

```bash
ssh -i ~/.ssh/apex-trader-key.pem ubuntu@YOUR_IP
```

### Step 2: Check Setup Progress

```bash
# View setup log
sudo tail -f /var/log/apex-trader-setup.log

# Wait for "APEX TRADER setup completed"
```

### Step 3: Clone Application Code

```bash
cd /opt/apex-trader

# Clone from GitHub
git clone https://github.com/YOUR_USER/apex-trader.git app

# OR copy from local
# scp -i ~/.ssh/apex-trader-key.pem -r ./backend ubuntu@YOUR_IP:/opt/apex-trader/
# scp -i ~/.ssh/apex-trader-key.pem -r ./frontend ubuntu@YOUR_IP:/opt/apex-trader/
```

### Step 4: Setup Backend

```bash
cd /opt/apex-trader/backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file (already created by user_data.sh)
# Edit if needed:
nano /opt/apex-trader/backend.env
```

### Step 5: Setup Frontend

```bash
cd /opt/apex-trader/frontend

# Install dependencies
npm install

# Build for production
npm run build
```

### Step 6: Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable apex-backend apex-frontend

# Start services
sudo systemctl start apex-backend apex-frontend

# Check status
sudo systemctl status apex-backend apex-frontend
```

### Step 7: Verify Deployment

```bash
# Check Nginx
curl http://localhost

# Check Backend API
curl http://localhost/api/health

# Check logs
sudo journalctl -u apex-backend -f
sudo journalctl -u apex-frontend -f
```

---

## SSL Setup (Optional)

For production, enable HTTPS:

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate (requires domain pointing to server)
sudo certbot --nginx -d your-domain.com

# Auto-renew
sudo certbot renew --dry-run
```

---

## Monitoring

### CloudWatch Alarms
Two alarms are created automatically:
1. **CPU High** - Alerts when CPU > 80% for 10 minutes
2. **Status Check Failed** - Alerts on instance health issues

### View Logs

```bash
# Backend logs
sudo journalctl -u apex-backend -f

# Frontend logs
sudo journalctl -u apex-frontend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check System Resources

```bash
# CPU & Memory
htop

# Disk
df -h

# Network
netstat -tlnp
```

---

## Updating the Application

```bash
# SSH into server
ssh -i ~/.ssh/apex-trader-key.pem ubuntu@YOUR_IP

# Pull latest code
cd /opt/apex-trader/app
git pull

# Restart services
sudo systemctl restart apex-backend apex-frontend
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u apex-backend -n 50 --no-pager

# Check environment
cat /opt/apex-trader/backend.env

# Test manually
cd /opt/apex-trader/backend
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001
```

### MongoDB Connection Issues

```bash
# Test connection
python3 -c "from pymongo import MongoClient; c = MongoClient('YOUR_MONGO_URI'); print(c.list_database_names())"
```

### Nginx Errors

```bash
# Check config syntax
sudo nginx -t

# View error log
sudo tail -f /var/log/nginx/error.log

# Restart
sudo systemctl restart nginx
```

---

## Tear Down

To destroy all resources:

```bash
cd /app/infrastructure/terraform/ec2
terraform destroy
```

Type `yes` when prompted. This removes all AWS resources.

---

## Cost Estimate

| Resource | Monthly Cost (us-east-1) |
|----------|-------------------------|
| t3.medium EC2 | ~$30 |
| Elastic IP (attached) | $0 |
| EBS 30GB gp3 | ~$2.40 |
| CloudWatch Alarms | ~$0.20 |
| **Total** | **~$33/month** |

*Note: Data transfer charges may apply based on usage.*

---

## Security Best Practices

1. **Restrict SSH Access**: Change `allowed_ssh_cidrs` to your IP only
2. **Enable SSL**: Use Let's Encrypt for HTTPS
3. **Use Secrets Manager**: Store API keys in AWS Secrets Manager
4. **Regular Updates**: `sudo apt update && sudo apt upgrade`
5. **Backup**: Enable EBS snapshots for disaster recovery
6. **Monitor**: Set up CloudWatch dashboards and alerts
