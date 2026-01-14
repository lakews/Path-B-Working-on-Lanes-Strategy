# APEX TRADER - EC2 Deployment Update Guide

## Updating Your Production Server

After making changes to the codebase, follow these steps to deploy updates to your AWS EC2 instance.

### Prerequisites
- SSH access to your EC2 instance using `apex-key.pem`
- The EC2 instance public IP: `107.22.9.8`

### Step 1: Connect to EC2

```bash
# From your local machine
ssh -i ~/.ssh/apex-key.pem ubuntu@107.22.9.8
```

### Step 2: Navigate to Application Directory

```bash
cd /home/ubuntu/apex-trader
```

### Step 3: Pull Latest Changes

If you've pushed changes to a Git repository:
```bash
git pull origin main
```

Or, to manually copy files from your development environment, use `scp`:
```bash
# From your local machine (example for backend files)
scp -i ~/.ssh/apex-key.pem -r /app/backend/* ubuntu@107.22.9.8:/home/ubuntu/apex-trader/backend/

# For frontend files
scp -i ~/.ssh/apex-key.pem -r /app/frontend/* ubuntu@107.22.9.8:/home/ubuntu/apex-trader/frontend/
```

### Step 4: Install Dependencies (if changed)

```bash
# Backend dependencies
cd /home/ubuntu/apex-trader/backend
source venv/bin/activate
pip install -r requirements.txt

# Frontend dependencies
cd /home/ubuntu/apex-trader/frontend
yarn install
```

### Step 5: Rebuild Frontend (if frontend changes)

```bash
cd /home/ubuntu/apex-trader/frontend
yarn build
```

### Step 6: Restart Services

```bash
# Restart backend
sudo systemctl restart apex-backend

# Restart frontend (if using separate service)
sudo systemctl restart apex-frontend

# Or restart both
sudo systemctl restart apex-backend apex-frontend

# Restart Nginx (if config changed)
sudo systemctl restart nginx
```

### Step 7: Verify Deployment

```bash
# Check service status
sudo systemctl status apex-backend apex-frontend nginx

# Check backend logs
sudo journalctl -u apex-backend -f

# Check frontend logs  
sudo journalctl -u apex-frontend -f

# Test API
curl http://localhost:8001/api/status
```

---

## New Paper Trading Features Deployed

The following new features have been added and need to be deployed:

### Backend Changes

1. **Paper Trading Engine** (`/backend/paper_trading/`)
   - `paper_trader.py` - Full paper trading simulation with RL learning
   - `strategy_optimizer.py` - Auto-tunes parameters from paper trading results

2. **Trading Bot Update** (`/backend/trading_bot.py`)
   - Full RL integration
   - Paper mode support
   - ML signal fusion

3. **Server Routes** (`/backend/server.py`)
   - `/api/paper/start` - Start paper trading
   - `/api/paper/stop` - Stop paper trading
   - `/api/paper/status` - Get status
   - `/api/paper/positions` - Get open positions
   - `/api/paper/trades` - Get trade history
   - `/api/paper/sessions` - List all sessions
   - `/api/paper/analytics` - Comprehensive analytics
   - `/api/optimizer/run/{session_id}` - Run optimization
   - `/api/optimizer/params` - Get optimized parameters
   - `/api/optimizer/apply` - Apply parameters

### Frontend Changes

1. **Paper Trading Page** (`/frontend/src/pages/PaperTrading.js`)
   - Live session monitoring
   - Session history
   - Strategy optimizer UI
   - RL learning status

2. **Navigation Update** (`/frontend/src/App.js`)
   - Added "Paper Trade" navigation link

---

## Quick Deploy Script

Create this script on your EC2 instance:

```bash
#!/bin/bash
# /home/ubuntu/deploy.sh

echo "🚀 Starting APEX TRADER deployment..."

cd /home/ubuntu/apex-trader

# Pull latest code (if using git)
# git pull origin main

# Backend setup
echo "📦 Installing backend dependencies..."
cd backend
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
echo "📦 Installing frontend dependencies..."
cd ../frontend
yarn install
echo "🔨 Building frontend..."
yarn build

# Restart services
echo "🔄 Restarting services..."
sudo systemctl restart apex-backend
sudo systemctl restart nginx

echo "✅ Deployment complete!"
echo "🔍 Checking status..."
sudo systemctl status apex-backend --no-pager
curl -s http://localhost:8001/api/status | head -c 200
```

Make it executable:
```bash
chmod +x /home/ubuntu/deploy.sh
```

Run deployment:
```bash
./deploy.sh
```

---

## Environment Variables

Ensure these are set in `/home/ubuntu/apex-trader/backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017/
DB_NAME=apex_trader
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
POLYMARKET_API_KEY=your_key_here
POLYMARKET_PRIVATE_KEY=your_key_here
```

---

## Monitoring

### View Real-time Logs
```bash
# Backend logs
sudo journalctl -u apex-backend -f

# All logs combined
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Check System Resources
```bash
htop
df -h
free -m
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs for errors
sudo journalctl -u apex-backend -n 100

# Check Python imports work
cd /home/ubuntu/apex-trader/backend
source venv/bin/activate
python -c "from server import app; print('OK')"
```

### Port Already in Use
```bash
sudo lsof -i :8001
sudo kill <PID>
```

### Database Connection Issues
```bash
# Check MongoDB is running
sudo systemctl status mongod

# Test connection
mongosh --eval "db.serverStatus()"
```
