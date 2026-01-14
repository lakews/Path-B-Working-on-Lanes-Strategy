#!/bin/bash
# APEX TRADER - EC2 User Data Script
# Automatically configures the server on first boot

set -e

# Log all output
exec > >(tee /var/log/apex-trader-setup.log) 2>&1
echo "Starting APEX TRADER setup at $(date)"

# =============================================
# SYSTEM UPDATES
# =============================================

apt-get update
apt-get upgrade -y

# =============================================
# INSTALL MONGODB
# =============================================

# Import MongoDB public GPG key
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

# Add MongoDB repository
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list

apt-get update
apt-get install -y mongodb-org

# Start and enable MongoDB
systemctl start mongod
systemctl enable mongod

# Wait for MongoDB to be ready
sleep 5
echo "MongoDB installed and running"

# =============================================
# INSTALL DEPENDENCIES
# =============================================

# Docker
apt-get install -y ca-certificates curl gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Nginx for reverse proxy
apt-get install -y nginx certbot python3-certbot-nginx

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Python 3.11
apt-get install -y python3.11 python3.11-venv python3-pip

# Git
apt-get install -y git

# =============================================
# CREATE APP DIRECTORY
# =============================================

mkdir -p /opt/apex-trader
cd /opt/apex-trader

# =============================================
# CREATE ENVIRONMENT FILES
# =============================================

cat > /opt/apex-trader/backend.env << 'ENVFILE'
MONGO_URL=${mongodb_uri}
DB_NAME=apex_trader
API_KEY=${polymarket_api_key}
API_SECRET=${polymarket_api_secret}
API_PASSPHRASE=${polymarket_api_passphrase}
PRIVATE_KEY=${wallet_private_key}
SENDGRID_API_KEY=${sendgrid_api_key}
ALERT_EMAIL=${alert_email}
CORS_ORIGINS=*
INITIAL_CAPITAL=1000
KELLY_FRACTION=0.25
MAX_DRAWDOWN_PCT=3
TRADES_PER_10MIN=500
ENVFILE

cat > /opt/apex-trader/frontend.env << 'ENVFILE'
REACT_APP_BACKEND_URL=http://localhost/api
ENVFILE

# =============================================
# NGINX CONFIGURATION
# =============================================

cat > /etc/nginx/sites-available/apex-trader << 'NGINXCONF'
server {
    listen 80;
    server_name _;
    
    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
    
    # Backend API
    location /api {
        proxy_pass http://localhost:8001/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://localhost:8001/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
NGINXCONF

ln -sf /etc/nginx/sites-available/apex-trader /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# =============================================
# SYSTEMD SERVICES
# =============================================

# Backend Service
cat > /etc/systemd/system/apex-backend.service << 'SERVICEEOF'
[Unit]
Description=APEX TRADER Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/apex-trader/backend
EnvironmentFile=/opt/apex-trader/backend.env
ExecStart=/opt/apex-trader/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Frontend Service
cat > /etc/systemd/system/apex-frontend.service << 'SERVICEEOF'
[Unit]
Description=APEX TRADER Frontend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/apex-trader/frontend
EnvironmentFile=/opt/apex-trader/frontend.env
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
SERVICEEOF

# =============================================
# CLONE AND SETUP APPLICATION
# =============================================

# Note: Replace with your actual git repo URL
# git clone https://github.com/YOUR_USER/apex-trader.git /opt/apex-trader/app

# For now, create placeholder directories
mkdir -p /opt/apex-trader/backend
mkdir -p /opt/apex-trader/frontend

# Create setup completion marker
touch /opt/apex-trader/.setup_complete

echo "APEX TRADER setup completed at $(date)"
echo ""
echo "======================================"
echo "NEXT STEPS:"
echo "1. Clone your repository to /opt/apex-trader/"
echo "2. Set up Python virtual environment:"
echo "   cd /opt/apex-trader/backend"
echo "   python3.11 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo "3. Install frontend dependencies:"
echo "   cd /opt/apex-trader/frontend"
echo "   npm install"
echo "4. Start services:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable apex-backend apex-frontend"
echo "   sudo systemctl start apex-backend apex-frontend"
echo "======================================"
