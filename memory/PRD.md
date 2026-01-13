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

### January 13, 2026
- ✅ **Enhanced Dashboard Layout**
  - Mode control banner with LIVE TRADING, BACKTEST, STOP buttons
  - P&L hero card displayed prominently at top
  - Trade frequency metrics: Live trades, 10min, 30min, 1hr, 24hr counts
  - 8 stat cards with relevant trading metrics
  - New `/api/trades/stats` endpoint for trade frequency data
  - All tests passing (12/12 backend + frontend tests)

### Previous Implementation
- ✅ Backend scaffolding with modular architecture (data, ml, strategies, trading, services)
- ✅ Frontend dashboard with multi-page navigation
- ✅ 5 AI modules (stubs): Volatility Predictor, Sentiment Analyzer, Bayesian Outlier, Sharp Detector, Kelly-Sharpe Optimizer
- ✅ Spread Calibrator module added
- ✅ 4 Trading strategies: Delta-Neutral, Volatility Exploitation, Alpha-Directional, Arbitrage
- ✅ Core trading components: ExecutionEngine, PositionManager, RiskController, TradingBot
- ✅ Mode switcher (Live/Backtest/Stopped)
- ✅ Configurable parameters (Kelly Fraction, Max Drawdown)
- ✅ Analytics page with Sharpe, Sortino, Calmar ratios
- ✅ Multi-strategy backtesting selection

## Backlog

### P1 - High Priority
- [ ] **Detailed Analytics**: Win rate per strategy and by asset class
- [ ] **Historical Data Collector**: Build robust data collection for backtesting

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
- `GET /api/analytics` - Comprehensive analytics
- `POST /api/bot/start` - Start live trading
- `POST /api/bot/stop` - Stop live trading
- `POST /api/backtest/start` - Start backtesting

## Architecture
```
/app/
├── backend/
│   ├── server.py          # FastAPI application
│   ├── trading_bot.py     # Core trading orchestrator
│   ├── data/              # Data ingestion
│   ├── ml/                # AI/ML models (stubs)
│   ├── strategies/        # Trading strategies
│   ├── trading/           # Execution, risk management
│   └── services/          # Analytics services
├── frontend/
│   └── src/pages/         # Dashboard, Analytics, Backtest, Config
└── memory/
    └── PRD.md             # This document
```

## Notes
- All ML modules in `/app/backend/ml/` are currently stubs awaiting full implementation
- MongoDB ObjectId serialization handled - always exclude `_id` from responses
- Credentials stored in `/app/backend/.env`
