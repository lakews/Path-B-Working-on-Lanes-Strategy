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
- **Frontend**: React + Tailwind CSS + Recharts
- **Database**: MongoDB
- **Deployment**: AWS (planned)

## What's Been Implemented

### January 14, 2026 - Session 8 (Strategy Filtering & Delta-Neutral Fix)
- ✅ **Wired Strategy/Asset Class Selection to Backtest**
  - Backtest now reads user config from database
  - Filters markets by enabled asset classes before processing
  - Only runs enabled strategies
  - API endpoint updated: `/api/backtest/start` accepts `asset_classes` query param
  - Frontend loads user's saved strategy preferences on page load

- ✅ **Fixed Delta-Neutral Strategy (Now Profitable!)**
  - **Before**: -$19.86, 56.7% WR, Profit Factor 0.89
  - **After**: +$13.40, 64.6% WR, Profit Factor 1.07
  - Key changes:
    - Time-based exits instead of tight price stops
    - Quick profit banking (0.1% after 2 snapshots)
    - Spread capture when spread narrows below 1.2%
    - Moderate stop loss (1.5%) with strict timeout for losers
    - Relaxed entry conditions for higher trade volume

- ✅ **Enabled Continuous Price Data Collection**
  - Automatically starts on server startup
  - Collects from 100 markets every 30 minutes
  - Uses Polymarket CLOB `/prices-history` endpoint
  - Provides real tick-level price data for backtesting

### January 14, 2026 - Session 7 (Strategy & Asset Class Selection)
- ✅ **Trading Strategy Selection UI**
  - Interactive cards for each strategy with risk levels and expected returns
  - Toggle on/off with visual feedback (green checkmark / X icon)
  - Risk badges: Low (green), Medium (yellow), High (red)
  - Expected return ranges displayed
  - "Select All" button for quick enabling

- ✅ **Asset Class Selection UI**
  - 6 asset categories: Finance, Politics, Sports, Crypto, Entertainment, Science & Tech
  - Toggle cards with icons and descriptions
  - Summary bar showing active strategies/classes count
  - Selections persist to MongoDB database
  - Tab renamed to "Asset Class - Strategy"

- ✅ **Enhanced Backtest Performance Breakdown**
  - **Strategy P&L Comparison Chart**: Vertical bar chart comparing all strategies
  - **Strategy Performance Table**: Detailed table with columns:
    - Strategy name, P&L, Trades, Win Rate, Avg Win, Avg Loss, Profit Factor, Status
  - **Asset Class P&L Chart**: Horizontal bar chart showing P&L by category
  - **Asset Class Detail Cards**: Grid of cards sorted by P&L with trades and win rate
  - Color-coded status indicators (Profitable=green, Loss=red)

- ✅ **Configuration Persistence**
  - User preferences stored in `user_config` collection
  - Auto-loaded on server startup
  - Real-time updates via `/api/config/update`

### January 14, 2026 - Session 6 (High-Fidelity Data Collection & Returns Distribution)
- ✅ **P0: Fixed Historical Data Collection (REAL PRICE DATA)**
  - Discovered Polymarket CLOB API has `/prices-history` endpoint for tick-level data
  - Added `get_price_history()` and `get_markets_with_tokens()` methods to `polymarket_api.py`
  - Added `collect_price_history()` method to `historical_collector.py` using real market data
  - Backtest engine now detects and uses real price data when available
  - Data quality metrics tracked: real vs simulated price points
  - New API endpoints:
    - `POST /api/historical/collect-prices` - Collect tick-level price history
    - `GET /api/historical/price-stats` - Get real price data statistics
    - `POST /api/historical/start-price-collection` - Start continuous collection
    - `POST /api/historical/stop-price-collection` - Stop continuous collection

- ✅ **Returns Distribution Chart (Histogram)**
  - Added `trade_returns` tracking to backtest engine
  - Implemented `_calculate_returns_distribution()` with:
    - 20 bins from -20% to +20%
    - Statistical metrics: mean, median, std, skewness, kurtosis
    - Positive/negative return counts
  - Frontend histogram with color-coded bars (green=positive, red=negative)
  - Stats display: Mean, Median, Std Dev, Skewness, Kurtosis

- ✅ **Data Quality Indicator Card**
  - Shows real vs simulated data percentage in results
  - Warning message when using simulated data
  - "Fetch Real Prices" button in data summary section

- ✅ **P1: Stop Backtest Button Verified**
  - Full UI regression test completed
  - Button properly switches state between Running/Stopped
  - Mode correctly updates on stop

### January 13, 2026 - Session 5 (HFT Backtest Engine Complete)
- ✅ **Fixed Position Closing Bug**: Positions now correctly track P&L through complete round-trips
- ✅ **Market Timeseries Processing**: Changed from sequential snapshots to grouping by market_id
- ✅ **Adaptive Exit Strategies**:
  - `profit_target`: Takes profit at configurable threshold (2% default)
  - `stop_loss`: Cuts losses at configurable limit (3% default)
  - `trailing_stop`: Locks in gains with trailing stop after 1.5% profit
  - `spread_capture`: Exits when market making spread narrows
  - `bank_profit`: Probabilistic small gain capture for HFT (0.5%+)
  - `momentum_reversal`: Exits on trend reversal signals
  - `timeout`: Closes stale positions after N snapshots
- ✅ **Strategy Selection**: Adaptive strategy selection based on volatility, trend, and performance history
- ✅ **Position Sizing**: Dynamic sizing based on volatility and volume profiles
- ✅ **Price Simulation**: Fallback for markets without real price history
- ✅ **Results**: Profitable backtests achieved - **$117.17 profit (+11.72% return), 70.6% win rate**

### January 13, 2026 - Session 4 (P3 + P0 ML Complete)
- ✅ **P3: Backtest History & Comparison System**
  - Store and retrieve up to 10+ past backtest results
  - History tab with selection checkboxes for comparison
  - Compare & Analyze tab with comprehensive metrics
  - Strategy Quality Score (A-F grade, 0-100 score)
  - Improvement Insights with severity levels (critical/high/medium/low)
  - Educational Analysis explaining all trading metrics
  - API endpoints: `/api/backtest/history`, `/api/backtest/compare`, `/api/backtest/{id}` (DELETE)
  - Learn tab with educational content about Sharpe Ratio, Max Drawdown, Profit Factor, Win Rate

- ✅ **P0: Trainable ML Models Implementation**
  - **Volatility Predictor**: Gradient Boosting + Random Forest ensemble
  - **Mispricing Detector**: Isolation Forest + Gradient Boosting classifier
  - Models persist to disk (`/app/backend/ml/models/`)
  - Auto-load on startup, fallback to heuristics if not trained
  - API endpoints: `/api/ml/stats`, `/api/ml/train/all`, `/api/ml/train/volatility`, `/api/ml/train/mispricing`

### January 13, 2026 - Session 3 (P2 Complete)
- ✅ **P2: Reinforcement Learning Engine**
  - Built `RLAdaptiveEngine` class with Q-learning and experience replay
  - Actions: WAIT, BUY_SMALL, BUY_MEDIUM, BUY_LARGE, SELL_SMALL, SELL_MEDIUM, SELL_LARGE
  - Endpoints: `/api/rl/stats`, `/api/rl/train`, `/api/rl/save`, `/api/rl/load`
  - Model persistence to disk

- ✅ **P2: Dashboard UI/UX Enhancements**
  - Real-time P&L chart with live updates
  - RL Engine status card
  - Historical Data status card
  - Risk Status card
  - Live Trade Feed

### Previous Implementation
- ✅ Backend scaffolding with modular architecture
- ✅ Frontend dashboard with multi-page navigation
- ✅ 6 AI modules: Volatility Predictor, Sentiment Analyzer, Bayesian Outlier, Sharp Detector, Kelly-Sharpe Optimizer, Spread Calibrator
- ✅ Signal Fusion Engine
- ✅ 4 Trading strategies
- ✅ Core trading components: ExecutionEngine, PositionManager, RiskController, TradingBot
- ✅ Mode switcher (Live/Backtest/Stopped)
- ✅ Configurable parameters

## Backlog

### P1 - High Priority
- [ ] **Refine Trading Strategies for Profitability** - Re-evaluate with high-quality real data
- [ ] **Implement Full ML Model Logic** - Complete sentiment_analyzer, sharp_detector integration

### P2 - Medium Priority
- [ ] **AWS Infrastructure as Code** - Terraform/CloudFormation deployment
- [ ] **Comprehensive Documentation** - API references, architecture diagrams, runbooks

### P3 - Lower Priority
- [ ] **WebSocket Integration** - Real-time trade updates without polling
- [ ] **Alerts System** - Email/SMS notifications for risk events

## Key API Endpoints
- `GET /api/status` - System status and trading mode
- `GET /api/trades/stats` - Trade frequency statistics
- `GET /api/performance` - Performance metrics
- `GET /api/positions` - Open positions
- `GET /api/trades` - Recent trades
- `GET /api/analytics` - Comprehensive analytics
- `GET /api/historical/stats` - Historical data statistics
- `POST /api/historical/collect` - Trigger snapshot collection
- `POST /api/historical/collect-prices` - **NEW** Collect tick-level price history
- `GET /api/historical/price-stats` - **NEW** Real price data statistics
- `GET /api/rl/stats` - RL engine training statistics
- `POST /api/rl/train` - Trigger RL batch training
- `GET /api/backtest/history` - Get list of past backtests
- `GET /api/backtest/results` - Get latest or specific backtest results (includes returns_distribution, data_quality)
- `POST /api/backtest/compare` - Compare multiple backtests with educational analysis
- `DELETE /api/backtest/{id}` - Delete a backtest
- `POST /api/bot/start` - Start live trading
- `POST /api/bot/stop` - Stop live trading

## Architecture
```
/app/
├── backend/
│   ├── server.py          # FastAPI application
│   ├── trading_bot.py     # Core trading orchestrator
│   ├── data/
│   │   ├── historical_collector.py  # Snapshot + price history collection
│   │   └── polymarket_api.py        # Gamma API + CLOB API (price history)
│   ├── ml/                # AI/ML models
│   │   ├── volatility_predictor.py
│   │   ├── sentiment_analyzer.py
│   │   ├── bayesian_outlier.py
│   │   ├── sharp_detector.py
│   │   ├── kelly_sharpe_optimizer.py
│   │   ├── signal_fusion.py
│   │   └── rl_engine.py
│   ├── strategies/        # Trading strategies
│   ├── backtest/
│   │   └── backtest_engine.py  # HFT engine with returns distribution
│   ├── trading/           # Execution, risk management
│   └── services/          # Analytics services
├── frontend/
│   └── src/pages/
│       └── Backtest.js    # 4 tabs + Returns Distribution + Data Quality
└── memory/
    └── PRD.md
```

## Current Stats (Jan 14, 2026)
- **Total snapshots**: 83,881+
- **Real price data**: 14,881+ points (17.74%)
- **Unique markets**: 1,047+
- **Categories**: Finance (35,449), Sports (31,703), Politics (9,789), Crypto (6,250)
- **Latest backtest**: +11.72% return, 70.6% win rate, 0.31 Sharpe

## Notes
- MongoDB ObjectId serialization handled - always exclude `_id` from responses
- Credentials stored in `/app/backend/.env`
- Real price data collection uses Polymarket CLOB `/prices-history` endpoint
- Backtest engine auto-detects and uses real price data when available
- Price simulation (Brownian motion) used as fallback for markets without history
