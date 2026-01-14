# APEX TRADER Operations Runbook

## Quick Start

### Starting the System

1. **Backend:**
```bash
cd /app/backend
sudo supervisorctl restart backend
```

2. **Frontend:**
```bash
cd /app/frontend
sudo supervisorctl restart frontend
```

3. **Check Status:**
```bash
sudo supervisorctl status
curl http://localhost:8001/api/health
```

---

## Common Operations

### Running a Backtest

**Via API:**
```bash
curl -X POST "http://localhost:8001/api/backtest/start?start_date=2026-01-01T00:00:00Z&end_date=2026-01-14T23:59:59Z"
```

**Via Frontend:**
1. Navigate to Backtest page
2. Set date range
3. Select strategies
4. Click "Run Backtest"

### Collecting Price Data

**One-time collection:**
```bash
curl -X POST "http://localhost:8001/api/historical/collect-prices?market_limit=100"
```

**Start continuous collection:**
```bash
curl -X POST "http://localhost:8001/api/historical/start-price-collection"
```

### Strategy Tuning

**Tune all strategies:**
```bash
curl -X POST "http://localhost:8001/api/tuning/all"
```

**Get best parameters:**
```bash
curl "http://localhost:8001/api/tuning/best/delta_neutral"
```

### Starting Live Trading

```bash
curl -X POST "http://localhost:8001/api/bot/start"
```

**⚠️ Warning:** Ensure you have:
- Valid Polymarket API credentials
- Funded wallet
- Understood the risks

---

## Monitoring

### Log Files

```bash
# Backend logs
tail -f /var/log/supervisor/backend.out.log
tail -f /var/log/supervisor/backend.err.log

# Frontend logs
tail -f /var/log/supervisor/frontend.out.log
```

### Health Checks

```bash
# API health
curl http://localhost:8001/api/health

# System status
curl http://localhost:8001/api/status

# Historical data stats
curl http://localhost:8001/api/historical/stats
```

### WebSocket Testing

```bash
# Using websocat
websocat ws://localhost:8001/ws
```

---

## Troubleshooting

### Backend Won't Start

1. **Check logs:**
```bash
tail -100 /var/log/supervisor/backend.err.log
```

2. **Common issues:**
   - Missing environment variables
   - MongoDB not running
   - Port 8001 already in use

3. **Fix MongoDB connection:**
```bash
sudo systemctl status mongod
sudo systemctl restart mongod
```

### Backtest Stuck

1. **Stop the backtest:**
```bash
curl -X POST http://localhost:8001/api/backtest/stop
```

2. **Check for errors:**
```bash
grep -i error /var/log/supervisor/backend.err.log | tail -20
```

### No Price Data

1. **Check data stats:**
```bash
curl http://localhost:8001/api/historical/price-stats
```

2. **Trigger collection:**
```bash
curl -X POST "http://localhost:8001/api/historical/collect-prices?market_limit=50"
```

3. **Verify Polymarket API:**
```bash
curl "https://clob.polymarket.com/markets" | head -100
```

### WebSocket Not Connecting

1. **Check if server is running:**
```bash
curl http://localhost:8001/api/health
```

2. **Test WebSocket endpoint:**
```bash
# In browser console:
new WebSocket('ws://localhost:8001/ws')
```

3. **Check CORS settings in .env:**
```bash
CORS_ORIGINS=*
```

---

## Database Operations

### MongoDB Shell

```bash
mongosh
use test_database
```

### Useful Queries

```javascript
// Count historical data
db.historical_data.countDocuments()

// Get recent backtests
db.backtest_results.find().sort({completed_at: -1}).limit(5)

// Check tuned parameters
db.strategy_tuning.find().sort({timestamp: -1}).limit(1)

// Count trades
db.trades.countDocuments()
```

### Backup

```bash
mongodump --db test_database --out /backup/
```

### Restore

```bash
mongorestore --db test_database /backup/test_database/
```

---

## Performance Optimization

### Backtest Performance

1. **Reduce market count:**
```bash
# In backtest config, limit to fewer asset classes
```

2. **Use real price data:**
   - Collect more price history
   - Real data backtests are more accurate

### Memory Usage

1. **Monitor memory:**
```bash
ps aux | grep python
```

2. **Reduce buffer sizes:**
   - Edit `rl_engine.py`: `max_buffer_size = 5000`

---

## Security

### API Keys

Store all API keys in `/app/backend/.env`:
```bash
FINNHUB_API_KEY=xxx
API_KEY=xxx
API_SECRET=xxx
```

**Never commit .env to git!**

### Wallet Security

- Store private key securely
- Use hardware wallet for production
- Limit trading capital

---

## Maintenance

### Daily Tasks

1. Check system health
2. Review overnight P&L
3. Check for failed trades

### Weekly Tasks

1. Run strategy tuning
2. Review backtest results
3. Update price history data

### Monthly Tasks

1. Backup database
2. Review and update strategies
3. Check for API changes

---

## Emergency Procedures

### Stop All Trading

```bash
# Stop bot immediately
curl -X POST http://localhost:8001/api/bot/stop

# Stop all services
sudo supervisorctl stop all
```

### Rollback Changes

Use the Emergent rollback feature to restore to a previous checkpoint.

### Contact Support

For platform issues, contact Emergent support via the dashboard.
