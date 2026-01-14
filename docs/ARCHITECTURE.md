# APEX TRADER Architecture

## Overview

APEX TRADER is a high-frequency algorithmic trading engine for Polymarket prediction markets. It uses a multi-layer architecture combining real-time data ingestion, AI/ML decision making, and automated trade execution.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React)                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │Dashboard │ │ Backtest │ │  Tuning  │ │  Config  │ │Analytics │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP/WebSocket
┌──────────────────────────────▼──────────────────────────────────────┐
│                         BACKEND (FastAPI)                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      API Layer (server.py)                   │    │
│  │  /api/status  /api/backtest/*  /api/sentiment  /ws          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────┼────────────────────────────────┐    │
│  │                     Trading Engine                           │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │    │
│  │  │  ApexTrader  │  │BacktestEngine│  │StrategyTuner │       │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────┼────────────────────────────────┐    │
│  │                      AI/ML Layer                             │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │    │
│  │  │  Sentiment │  │   Whale    │  │Signal      │             │    │
│  │  │  Analyzer  │  │  Tracker   │  │Fusion      │             │    │
│  │  └────────────┘  └────────────┘  └────────────┘             │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │    │
│  │  │ Volatility │  │  Bayesian  │  │    RL      │             │    │
│  │  │ Predictor  │  │  Outlier   │  │  Engine    │             │    │
│  │  └────────────┘  └────────────┘  └────────────┘             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────┼────────────────────────────────┐    │
│  │                   Strategy Layer                             │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │    │
│  │  │Delta-Neutral │  │  Volatility  │  │    Alpha     │       │    │
│  │  │Market Making │  │ Exploitation │  │ Directional  │       │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │    │
│  │  ┌──────────────┐  ┌──────────────┐                         │    │
│  │  │  Arbitrage   │  │Kelly-Sharpe  │                         │    │
│  │  │              │  │  Optimizer   │                         │    │
│  │  └──────────────┘  └──────────────┘                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        DATA LAYER                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │    MongoDB       │  │   Polymarket     │  │    Finnhub       │  │
│  │  (Historical,    │  │   CLOB API       │  │  (Sentiment)     │  │
│  │   Trades, ML)    │  │  (Price Data)    │  │                  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Frontend (React + Tailwind CSS)

**Location:** `/app/frontend/src/`

| Page | Purpose |
|------|---------|
| Dashboard | Real-time P&L, trade feed, system status |
| Backtest | Run backtests, view results, returns distribution |
| Tuning | Automatic strategy parameter optimization |
| Configuration | Enable/disable strategies and asset classes |
| Analytics | Performance metrics and charts |

### 2. API Layer (FastAPI)

**Location:** `/app/backend/server.py`

Handles all HTTP and WebSocket requests. Key responsibilities:
- Route requests to appropriate services
- Manage WebSocket connections for real-time updates
- Handle background tasks for data collection

### 3. Trading Engine

#### ApexTrader (`/app/backend/trading_bot.py`)
Core orchestrator for live trading. Manages:
- Market scanning
- Signal generation
- Order execution
- Position management

#### BacktestEngine (`/app/backend/backtest/backtest_engine.py`)
High-frequency backtesting with:
- AI signal integration (sentiment, whale tracking)
- Adaptive position management
- Multiple exit strategies
- Performance tracking by strategy and asset class

#### StrategyTuner (`/app/backend/ml/strategy_tuner.py`)
Automatic parameter optimization using grid search:
- Tests parameter combinations
- Scores by return, Sharpe, win rate, profit factor
- Stores best parameters in database

### 4. AI/ML Layer

| Module | File | Purpose |
|--------|------|---------|
| SocialSentimentAnalyzer | `ml/social_sentiment.py` | Finnhub API for news/social sentiment |
| WhaleTracker | `ml/whale_tracker.py` | Detect large trader activity |
| SignalFusionEngine | `ml/signal_fusion.py` | Combine all signals via Bayesian inference |
| VolatilityPredictor | `ml/volatility_predictor.py` | ML-based volatility prediction |
| BayesianOutlierDetector | `ml/bayesian_outlier.py` | Detect mispriced markets |
| RLAdaptiveEngine | `ml/rl_engine.py` | Q-learning for adaptive strategy selection |

### 5. Strategy Layer

| Strategy | Risk | Description |
|----------|------|-------------|
| Delta-Neutral | Low | Market making with minimal directional exposure |
| Volatility Exploitation | Medium | Profit from price swings in volatile markets |
| Alpha-Directional | Medium-High | High-confidence directional bets using AI signals |
| Multi-Market Arbitrage | Low | Cross-market price inefficiency exploitation |

### 6. Data Layer

#### MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `historical_data` | Market snapshots and price history |
| `price_history` | Tick-level price data from Polymarket CLOB |
| `trades` | Executed trades |
| `positions` | Open positions |
| `backtest_results` | Saved backtest outcomes |
| `user_config` | User preferences (strategies, asset classes) |
| `strategy_tuning` | Optimized parameters |
| `social_sentiment` | Cached sentiment analysis |
| `whale_signals` | Cached whale activity signals |
| `rl_pending_actions` | RL action-reward tracking |

---

## Data Flow

### Backtest Flow

```
1. User configures backtest (dates, strategies, asset classes)
                    ↓
2. BacktestEngine loads historical data
                    ↓
3. Pre-loads AI signals (sentiment, whale) for all markets
                    ↓
4. For each market timeseries:
   a. Calculate volatility, trend
   b. Get AI signal adjustments
   c. Select best strategy using _select_best_strategy()
   d. Open/close positions based on signals
                    ↓
5. Calculate results (P&L, Sharpe, drawdown, etc.)
                    ↓
6. Store results in MongoDB
                    ↓
7. Return results to frontend
```

### AI Signal Integration Flow

```
Market Data → SignalFusionEngine
                    ↓
        ┌──────────┼──────────┐
        ↓          ↓          ↓
  Sentiment   Volatility   Whale
  Analyzer    Predictor    Tracker
        ↓          ↓          ↓
        └──────────┼──────────┘
                    ↓
         Bayesian Posterior
                    ↓
         Strategy Selection
```

### WebSocket Real-Time Updates

```
Client connects → ws://host/ws
                    ↓
Server sends initial state (type: "connected")
                    ↓
Every 2 seconds:
  - Gather latest trades, P&L, positions
  - Broadcast to all connected clients (type: "update")
                    ↓
Client receives JSON with latest data
```

---

## Configuration

### Environment Variables (`/app/backend/.env`)

```bash
# Database
MONGO_URL=mongodb://localhost:27017
DB_NAME=apex_trader

# Trading
INITIAL_CAPITAL=1000
KELLY_FRACTION=0.25
MAX_DRAWDOWN_PCT=3
TRADES_PER_10MIN=500

# External APIs
FINNHUB_API_KEY=your_key_here

# Polymarket
API_KEY=your_key
API_SECRET=your_secret
```

### User Configuration (MongoDB)

Stored in `user_config` collection:
```json
{
  "type": "trading_preferences",
  "enabled_strategies": ["delta_neutral", "volatility_exploitation"],
  "enabled_asset_classes": ["finance", "crypto", "politics"]
}
```

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Execution Latency | <100ms |
| ML Inference | <50ms |
| Trades per 10min | 500 (configurable) |
| Max Drawdown | 3% (configurable) |

---

## Directory Structure

```
/app/
├── backend/
│   ├── server.py              # FastAPI application
│   ├── trading_bot.py         # Live trading orchestrator
│   ├── database.py            # MongoDB connection
│   ├── config.py              # Configuration management
│   ├── data/
│   │   ├── historical_collector.py
│   │   └── polymarket_api.py
│   ├── ml/
│   │   ├── social_sentiment.py
│   │   ├── whale_tracker.py
│   │   ├── signal_fusion.py
│   │   ├── volatility_predictor.py
│   │   ├── bayesian_outlier.py
│   │   ├── rl_engine.py
│   │   ├── strategy_tuner.py
│   │   └── models/            # Saved ML models
│   ├── strategies/
│   │   ├── delta_neutral.py
│   │   ├── volatility_exploitation.py
│   │   ├── alpha_directional.py
│   │   └── arbitrage.py
│   ├── trading/
│   │   ├── execution_engine.py
│   │   ├── position_manager.py
│   │   └── risk_controller.py
│   ├── backtest/
│   │   └── backtest_engine.py
│   └── services/
│       └── performance_analytics.py
├── frontend/
│   └── src/
│       ├── App.js
│       ├── pages/
│       │   ├── Dashboard.js
│       │   ├── Backtest.js
│       │   ├── StrategyTuning.js
│       │   ├── Configuration.js
│       │   └── Analytics.js
│       └── components/
│           └── ui/            # Shadcn components
├── docs/
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   └── OPERATIONS.md
└── memory/
    └── PRD.md
```
