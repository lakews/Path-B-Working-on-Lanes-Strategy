# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build "APEX TRADER", a complete, production-ready, end-to-end AI-driven prediction market trading engine for high-frequency algorithmic trading on Polymarket.

## Core Requirements
- **Multi-layer Architecture**: Data ingestion, AI/ML decision layer, trade execution engine, monitoring/risk management
- **AI/ML Models**: Volatility Prediction, Sentiment Fusion, Bayesian Outlier Detection, Sharp Trader Detection, Kelly-Sharpe Optimizer
- **Trading Strategies**: Delta-Neutral Market Making, Volatility Exploitation, Alpha-Directional, Multi-Market Arbitrage
- **Performance**: <100ms execution latency, <50ms ML inference, 500+ trades per 10 minutes (configurable)
- **Risk Management**: Kelly Criterion position sizing (capped at 3%), configurable max drawdown limit

## Tech Stack
- **Backend**: FastAPI (Python)
- **Frontend**: React + Tailwind CSS
- **Database**: MongoDB
- **Deployment**: AWS (planned)

## What's Been Implemented

### January 13, 2026 - Session 2
- ✅ **P0: Spread Calibrator Integration Verified**
  - SpreadCalibrator module working correctly
  - Integrated into DeltaNeutralStrategy (line 11, 29, 44)
  - Calculates optimal spreads based on volatility, liquidity, volume, timing
  
- ✅ **P1: Historical Data Collector**
  - Built robust data collection for backtesting
  - Successfully collected 6000+ market snapshots from Polymarket API
  - Proper market categorization (crypto, sports, politics, finance, entertainment)
  - New API endpoints:
    - `GET /api/historical/stats` - Collection statistics
    - `POST /api/historical/collect` - Trigger one-time collection
    - `GET /api/historical/data` - Retrieve historical data
    - `POST /api/historical/start-continuous` - Start background collection
    - `POST /api/historical/stop-continuous` - Stop background collection

- ✅ **P1: Analytics with Strategy & Asset Class Performance**
  - Analytics endpoint returns `strategy_performance` and `asset_class_performance`
  - Per-strategy metrics: win rate, total trades, P&L, classification
  - Per-asset-class metrics: win rate, trades, P&L by category

### January 13, 2026 - Session 1
- ✅ **Enhanced Dashboard Layout**
  - Mode control banner with LIVE TRADING, BACKTEST, STOP buttons
  - P&L hero card displayed prominently at top
  - Trade frequency metrics: Live trades, 10min, 30min, 1hr, 24hr counts
  - New `/api/trades/stats` endpoint

### Previous Implementation
- ✅ Backend scaffolding with modular architecture
- ✅ Frontend dashboard with multi-page navigation
- ✅ 6 AI modules: Volatility Predictor, Sentiment Analyzer, Bayesian Outlier, Sharp Detector, Kelly-Sharpe Optimizer, Spread Calibrator
- ✅ 4 Trading strategies: Delta-Neutral, Volatility Exploitation, Alpha-Directional, Arbitrage
- ✅ Core trading components: ExecutionEngine, PositionManager, RiskController, TradingBot
- ✅ Mode switcher (Live/Backtest/Stopped)
- ✅ Configurable parameters (Kelly Fraction, Max Drawdown)
- ✅ Analytics page with Sharpe, Sortino, Calmar ratios, strategy/asset class breakdowns

## Backlog

### P2 - Medium Priority
- [ ] **Full ML Model Logic**: Implement actual model loading, feature engineering, inference in `/app/backend/ml/`
- [ ] **Reinforcement Learning Engine**: RL-based adaptive strategy
- [ ] **Dashboard UI/UX Enhancements**: Real-time charts, trade feed, risk dashboard

### P3 - Lower Priority
- [ ] **AWS Infrastructure as Code**: Terraform/CloudFormation deployment
- [ ] **Comprehensive Documentation**: API references, architecture diagrams, operational runbooks

## Key API Endpoints
- `GET /api/status` - System status and trading mode
- `GET /api/trades/stats` - Trade frequency statistics (10min, 30min, 1hr, 24hr)
- `GET /api/performance` - Performance metrics
- `GET /api/positions` - Open positions
- `GET /api/trades` - Recent trades
- `GET /api/analytics` - Comprehensive analytics with strategy/asset class breakdowns
- `GET /api/historical/stats` - Historical data collection statistics
- `POST /api/historical/collect` - Trigger market data collection
- `GET /api/historical/data` - Retrieve historical market data
- `POST /api/bot/start` - Start live trading
- `POST /api/bot/stop` - Stop live trading
- `POST /api/backtest/start` - Start backtesting

## Architecture
```
/app/
├── backend/
│   ├── server.py          # FastAPI application
│   ├── trading_bot.py     # Core trading orchestrator
│   ├── data/              # Data ingestion (historical_collector, polymarket_api)
│   ├── ml/                # AI/ML models (stubs pending full implementation)
│   ├── strategies/        # Trading strategies
│   ├── trading/           # Execution, risk management, spread_calibrator
│   └── services/          # Analytics services
├── frontend/
│   └── src/pages/         # Dashboard, Analytics, Backtest, Config
└── memory/
    └── PRD.md             # This document
```

## Testing Status
- **Iteration 1**: 12/12 tests passed (Dashboard, Trade Stats, API endpoints)
- **Iteration 2**: 15/15 tests passed (Spread Calibrator, Historical Data Collection)
- **Total**: 27/27 backend tests passing

## Notes
- All ML modules in `/app/backend/ml/` are currently stubs awaiting full implementation
- Historical data collection is working - 6000+ market snapshots available for backtesting
- MongoDB ObjectId serialization handled - always exclude `_id` from responses
- Credentials stored in `/app/backend/.env`
