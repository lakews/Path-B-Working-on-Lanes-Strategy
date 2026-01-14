# APEX TRADER API Reference

## Base URL
```
Production: https://your-domain.com/api
Local: http://localhost:8001/api
```

## Authentication
Currently, the API does not require authentication. Future versions will implement JWT-based auth.

---

## System Endpoints

### GET /api/status
Get current system status and configuration.

**Response:**
```json
{
  "status": "operational",
  "bot_running": false,
  "trading_mode": "stopped",
  "configuration": {
    "trades_per_10min": 500,
    "initial_capital": 1000,
    "capital_deployment_pct": 80,
    "max_position_size_pct": 3,
    "kelly_fraction": 0.25,
    "max_drawdown_pct": 3,
    "enabled_strategies": ["delta_neutral", "volatility_exploitation"],
    "enabled_asset_classes": ["finance", "crypto", "politics"]
  }
}
```

### GET /api/health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-15T10:00:00Z"
}
```

---

## Trading Bot Endpoints

### POST /api/bot/start
Start the live trading bot.

**Response:**
```json
{
  "message": "Trading bot started"
}
```

### POST /api/bot/stop
Stop the live trading bot.

**Response:**
```json
{
  "message": "Trading bot stopped"
}
```

### GET /api/trades
Get recent trades.

**Query Parameters:**
- `limit` (int, default: 50): Maximum number of trades to return
- `strategy` (str, optional): Filter by strategy name

**Response:**
```json
{
  "trades": [
    {
      "id": "trade-uuid",
      "market_id": "market-uuid",
      "strategy": "delta_neutral",
      "side": "BUY",
      "price": 0.55,
      "shares": 100,
      "pnl": 2.50,
      "timestamp": "2026-01-15T10:00:00Z"
    }
  ],
  "count": 1
}
```

### GET /api/positions
Get current open positions.

**Response:**
```json
{
  "positions": [
    {
      "id": "position-uuid",
      "market_id": "market-uuid",
      "strategy": "alpha_directional",
      "side": "YES",
      "entry_price": 0.45,
      "shares": 200,
      "current_pnl": 5.00,
      "opened_at": "2026-01-15T09:00:00Z"
    }
  ],
  "count": 1
}
```

---

## Backtest Endpoints

### POST /api/backtest/start
Start a new backtest.

**Query Parameters:**
- `start_date` (str): ISO format date (e.g., "2026-01-01T00:00:00Z")
- `end_date` (str): ISO format date
- `strategies` (list, optional): List of strategy names to test
- `asset_classes` (list, optional): List of asset classes to include
- `use_tuned_params` (bool, default: true): Use optimized parameters

**Response:**
```json
{
  "backtest_id": "uuid",
  "message": "Backtest started"
}
```

### POST /api/backtest/stop
Stop a running backtest.

**Response:**
```json
{
  "message": "Backtest stopped"
}
```

### GET /api/backtest/results
Get backtest results.

**Query Parameters:**
- `backtest_id` (str, optional): Specific backtest ID. If not provided, returns latest.

**Response:**
```json
{
  "backtest_id": "uuid",
  "status": "completed",
  "initial_capital": 1000.0,
  "final_capital": 1117.17,
  "total_pnl": 117.17,
  "total_return_pct": 11.72,
  "total_trades": 1250,
  "winning_trades": 882,
  "losing_trades": 368,
  "win_rate": 0.706,
  "profit_factor": 1.45,
  "sharpe_ratio": 0.31,
  "max_drawdown": 0.05,
  "strategy_results": {
    "delta_neutral": {
      "trades": 400,
      "wins": 258,
      "pnl": 13.40,
      "win_rate": 0.646
    }
  },
  "asset_class_results": {
    "finance": {
      "trades": 500,
      "pnl": 50.00
    }
  },
  "ai_signals_stats": {
    "sentiment_signals_used": 150,
    "whale_signals_used": 150,
    "avg_sentiment": 0.52
  },
  "returns_distribution": {
    "bins": [...],
    "stats": {
      "mean": 0.5,
      "median": 0.3,
      "std": 2.1
    }
  }
}
```

### GET /api/backtest/history
Get list of past backtests.

**Query Parameters:**
- `limit` (int, default: 10): Maximum results

**Response:**
```json
{
  "history": [
    {
      "backtest_id": "uuid",
      "total_pnl": 117.17,
      "total_return_pct": 11.72,
      "completed_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

### POST /api/backtest/compare
Compare multiple backtests.

**Request Body:**
```json
["backtest-id-1", "backtest-id-2"]
```

**Response:**
```json
{
  "backtests": [...],
  "summary": {
    "total_backtests": 2,
    "avg_return": 10.5
  },
  "educational_analysis": {
    "strategy_quality_score": {
      "grade": "B",
      "total_score": 75
    }
  }
}
```

### DELETE /api/backtest/{backtest_id}
Delete a backtest result.

---

## Historical Data Endpoints

### GET /api/historical/stats
Get historical data collection statistics.

**Response:**
```json
{
  "total_snapshots": 83881,
  "unique_markets": 1047,
  "oldest_snapshot": "2026-01-01T00:00:00Z",
  "newest_snapshot": "2026-01-15T10:00:00Z",
  "category_distribution": {
    "finance": 35449,
    "sports": 31703
  }
}
```

### POST /api/historical/collect-prices
Collect high-fidelity price history.

**Query Parameters:**
- `market_limit` (int, default: 50): Number of markets
- `interval` (str, default: "1w"): Time interval
- `fidelity` (int, default: 60): Resolution in minutes

**Response:**
```json
{
  "message": "Price history collection completed",
  "stats": {
    "markets_processed": 50,
    "stored_snapshots": 5000
  }
}
```

### GET /api/historical/price-stats
Get real price data statistics.

---

## AI/ML Endpoints

### GET /api/sentiment/analyze
Analyze market sentiment.

**Query Parameters:**
- `market_id` (str, optional): Market to analyze
- `question` (str, optional): Market question text
- `category` (str, default: "unknown"): Market category

**Response:**
```json
{
  "overall_sentiment": 0.65,
  "confidence": 0.72,
  "news_sentiment": 0.70,
  "social_sentiment": 0.60,
  "news_count": 15,
  "trending_score": 0.3
}
```

### GET /api/whale/detect
Detect whale activity.

**Query Parameters:**
- `market_id` (str): Market ID
- `volume24hr` (float, default: 0): 24hr volume
- `liquidity` (float, default: 0): Market liquidity

**Response:**
```json
{
  "whale_activity_score": 0.75,
  "volume_spike": true,
  "large_orders_detected": 5,
  "whale_direction": "bullish",
  "confidence": 0.68
}
```

### GET /api/whale/statistics
Get overall whale tracking stats.

### POST /api/whale/track-sharp
Analyze sharp (smart money) traders.

---

## Strategy Tuning Endpoints

### POST /api/tuning/strategy
Tune a single strategy's parameters.

**Query Parameters:**
- `strategy_name` (str): Strategy to tune
- `start_date` (str): Backtest start date
- `end_date` (str): Backtest end date
- `max_combinations` (int, default: 30): Max parameter combinations

**Response:**
```json
{
  "strategy": "delta_neutral",
  "results": [
    {
      "params": {"profit_target": 0.005},
      "return_pct": 12.5,
      "sharpe": 0.45,
      "composite_score": 78
    }
  ]
}
```

### POST /api/tuning/all
Tune all strategies.

### GET /api/tuning/best/{strategy_name}
Get best parameters for a strategy.

### GET /api/tuning/history
Get tuning history.

### POST /api/tuning/stop
Stop current tuning.

---

## Configuration Endpoints

### POST /api/config/update
Update trading configuration.

**Request Body:**
```json
{
  "initial_capital": 1000,
  "kelly_fraction": 0.25,
  "enabled_strategies": ["delta_neutral", "alpha_directional"],
  "enabled_asset_classes": ["finance", "crypto"]
}
```

---

## RL Engine Endpoints

### GET /api/rl/stats
Get RL engine training statistics.

**Response:**
```json
{
  "total_iterations": 5000,
  "epsilon": 0.15,
  "avg_reward_100": 0.05,
  "buffer_size": 2500
}
```

### POST /api/rl/train
Trigger RL batch training.

### POST /api/rl/save
Save RL model to disk.

### POST /api/rl/load
Load RL model from disk.

---

## WebSocket API

### Endpoint: ws://your-domain.com/ws

Connect to receive real-time updates.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};

// Keep alive
setInterval(() => ws.send('ping'), 25000);
```

**Message Types:**

1. **connected** - Initial state on connection
```json
{
  "type": "connected",
  "trading_mode": "stopped",
  "total_pnl": 0
}
```

2. **update** - Periodic updates (every 2 seconds)
```json
{
  "type": "update",
  "timestamp": "2026-01-15T10:00:00Z",
  "trading_mode": "backtest",
  "total_pnl": 50.0,
  "open_positions": 5,
  "recent_trades": [...]
}
```

3. **heartbeat** - Keep-alive ping
```json
{
  "type": "heartbeat",
  "timestamp": "2026-01-15T10:00:00Z"
}
```

4. **pong** - Response to client ping
```json
{
  "type": "pong",
  "timestamp": "2026-01-15T10:00:00Z"
}
```

**Client Commands:**
- `ping` - Request a pong response
- `get_update` - Request immediate data update

---

## Error Responses

All endpoints return errors in this format:
```json
{
  "message": "Error description"
}
```

HTTP Status Codes:
- `200` - Success
- `400` - Bad Request
- `500` - Internal Server Error
