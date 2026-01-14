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
- **Deployment**: AWS with Terraform IaC

## What's Been Implemented

### January 14, 2026 - Session 11 (RL Enhancement, Alerts, Data Sources, Deep Dive Modal, AWS IaC)

- ✅ **Enhanced RL/ML with Detailed Performance Metrics** (`/app/backend/ml/rl_engine.py`)
  - Expanded `get_training_stats()` with:
    - Positive/negative reward tracking
    - Q-table analysis (nonzero %, mean, max values)
    - Action distribution across all strategies
    - Standard deviation of rewards
  - New `learn_from_backtest_results()` - RL learns from completed backtests
  - New `get_strategy_confidence()` - Get RL confidence for specific strategies
  - API endpoints:
    - `POST /api/rl/learn-from-backtest/{backtest_id}` - Trigger RL learning
    - `GET /api/rl/detailed-stats` - Get comprehensive RL stats

- ✅ **Backtest Data Source Selection** (`/app/backend/backtest/backtest_engine.py`)
  - New `data_source` parameter: `auto`, `real`, `snapshots`, `live`, `hybrid`
  - `auto`: Automatically selects best available data
  - `real`: Only real tick-level price history
  - `snapshots`: Only historical snapshots (faster)
  - `hybrid`: Combines real prices with snapshots for gaps
  - Data source breakdown in results

- ✅ **Clickable Backtest History with Deep Dive Modal** (`/app/frontend/src/pages/Backtest.js`)
  - Click any history row to open detailed modal overlay
  - Shows all key metrics, strategy breakdown, asset class breakdown
  - AI signal usage stats
  - Data quality information

- ✅ **SendGrid Email Alerts System** (`/app/backend/services/alert_service.py`)
  - Whale activity alerts (when score > 0.7)
  - Sentiment shift alerts (when change > 30%)
  - Drawdown alerts (when > 5%)
  - Trade execution alerts (for trades > $50)
  - Backtest completion alerts
  - Cooldown periods to prevent spam
  - Beautiful HTML email templates
  - API endpoints:
    - `GET /api/alerts/config` - Get alert configuration
    - `POST /api/alerts/config` - Update alert thresholds
    - `GET /api/alerts/history` - Get alert history
    - `POST /api/alerts/test` - Send test alert

- ✅ **AWS Infrastructure as Code (Terraform)** (`/app/infrastructure/terraform/`)
  - Complete production-ready infrastructure:
    - VPC with public/private subnets
    - ECS Fargate cluster for containers
    - ECR repositories for backend/frontend
    - Application Load Balancer with path-based routing
    - AWS Secrets Manager for credentials
    - CloudWatch logging and alarms
    - Auto-scaling policies (70% CPU target)
  - Estimated cost: ~$120-150/month for production
  - Deployment guide in `README.md`

### January 14, 2026 - Session 10 (AI Signal Integration, WebSocket & Documentation)

- ✅ **P1: AI Signals Wired into Trading Logic** (`/app/backend/backtest/backtest_engine.py`)
  - Integrated Sentiment and Whale signals into `_select_best_strategy()` method
  - AI signals now actively influence strategy selection during backtests:
    - **Delta-Neutral**: Prefers neutral sentiment, avoids high whale activity
    - **Volatility Exploitation**: Boosted by strong sentiment (any direction), high whale activity
    - **Alpha-Directional**: Aligns with sentiment direction, whale direction matching
    - **Arbitrage**: Prefers neutral sentiment, low whale activity
  - Pre-loads AI signals for all markets before backtest for efficiency
  - Position sizing adjusted based on AI signal confidence (+20% for high confidence)
  - New `ai_signals_stats` in backtest results showing:
    - Sentiment/whale signals count
    - Average sentiment & whale activity
    - Bullish/bearish whale market counts

- ✅ **P2: WebSocket Real-Time Integration** (`/app/backend/server.py`)
  - New `WebSocketConnectionManager` class for managing connections
  - Endpoint: `ws://host/ws` for real-time updates
  - Message types:
    - `connected`: Initial state on connection
    - `update`: Periodic updates (every 2 seconds)
    - `heartbeat`: Keep-alive ping
    - `pong`: Response to client ping
  - Broadcasts: trading mode, total P&L, open positions, recent trades, backtest status
  - Auto-starts on server startup
  - Client commands: `ping`, `get_update`

- ✅ **P3: Comprehensive Documentation** (`/app/docs/`)
  - `API_REFERENCE.md`: Complete API documentation with all endpoints
  - `ARCHITECTURE.md`: System architecture diagram and component details
  - `OPERATIONS.md`: Operations runbook for daily maintenance

- ✅ **UI Enhancement**: AI Signal Integration Stats Card
  - New section in Backtest results showing sentiment/whale signal usage
  - Shows average sentiment, whale activity, bullish/bearish counts

### January 14, 2026 - Session 9 (Sentiment Analysis, Whale Tracking & Strategy Tuning)
- ✅ **Social Sentiment Analyzer** (`/app/backend/ml/social_sentiment.py`)
  - Integrates with Finnhub API for news and social sentiment
  - Topic-to-symbol mapping (Bitcoin→BTCUSDT, Fed→SPY, etc.)
  - Multi-source fusion: news (40%), social (30%), keyword analysis (30%)
  - In-memory caching with 5-minute TTL
  - API endpoints:
    - `GET /api/sentiment/analyze` - Analyze market sentiment
    - `GET /api/sentiment/trending` - Get trending topics

- ✅ **Whale/Sharp Tracker** (`/app/backend/ml/whale_tracker.py`)
  - Volume spike detection against historical averages
  - Price impact scoring based on volume/liquidity ratio
  - Whale direction analysis (bullish/bearish/neutral)
  - Sharp trader tracking by market volatility patterns
  - API endpoints:
    - `GET /api/whale/detect` - Detect whale activity for a market
    - `GET /api/whale/statistics` - Overall whale tracking stats
    - `POST /api/whale/track-sharp` - Analyze sharp traders

- ✅ **Strategy Tuning Mode** (`/app/backend/ml/strategy_tuner.py`)
  - Grid search parameter optimization
  - Parameter grids for all 4 strategies:
    - Delta-Neutral: profit_target, stop_loss, bank_profit_threshold, timeout, spread_threshold
    - Volatility Exploitation: profit_target, stop_loss, min/max_volatility, trend_threshold
    - Alpha-Directional: profit_target, stop_loss, trend_threshold, trailing_stop params
    - Arbitrage: profit_target, stop_loss, min_spread, position_timeout
  - Composite scoring: Return (25%), Sharpe (25%), Win Rate (20%), Profit Factor (20%), Drawdown (10%)
  - API endpoints:
    - `POST /api/tuning/strategy` - Tune single strategy
    - `POST /api/tuning/all` - Tune all strategies
    - `GET /api/tuning/best/{strategy}` - Get best parameters
    - `GET /api/tuning/history` - Tuning history

- ✅ **New "Tuning" Page** (`/app/frontend/src/pages/StrategyTuning.js`)
  - 4 strategy cards with scores, win rates, and Sharpe ratios
  - "Tune All Strategies" button
  - Max combinations slider (10-100)
  - Results display with best parameters and metrics
  - Top 5 parameter sets chart
  - Recent tuning history table

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
- [x] ~~**Wire AI Signals into Trading Logic**~~ - COMPLETED (Jan 14, 2026)
- [x] ~~**Refine Trading Strategies for Profitability**~~ - COMPLETED (Delta-Neutral fixed, AI integration)
- [x] ~~**Further RL/ML Refinement**~~ - COMPLETED (Detailed metrics, learn from backtest)

### P2 - Medium Priority
- [x] ~~**AWS Infrastructure as Code**~~ - COMPLETED (Terraform scripts in /app/infrastructure/terraform/)
- [x] ~~**WebSocket Integration**~~ - COMPLETED (Jan 14, 2026)
- [x] ~~**Comprehensive Documentation**~~ - COMPLETED (API_REFERENCE.md, ARCHITECTURE.md, OPERATIONS.md)
- [x] ~~**SendGrid Email Alerts**~~ - COMPLETED (requires SENDGRID_API_KEY to activate)

### P3 - Lower Priority
- [ ] **SMS Alerts via Twilio** - Add SMS notification support
- [ ] **Mobile-responsive Dashboard** - Optimize for mobile devices
- [ ] **Real-time Portfolio Tracking** - Live positions with unrealized P&L

## Bug Fixes - Session 11 (Jan 14, 2026)
- ✅ Fixed: Equity curve chart was empty (now shows data points)
- ✅ Fixed: Equity curve tooltip not showing values on hover
- ✅ Fixed: Volatility Exploitation strategy couldn't be selected (server config issue)
- ✅ Fixed: Data Source dropdown visibility (now clearly visible)
- ✅ Enhanced: Tuning page parameter transparency (shows all values being tested)

## Bug Fixes - Session 12 (Jan 14, 2026)
- ✅ **CRITICAL FIX: Repaired broken Backtest.js** - Removed ~1000 lines of orphaned/duplicate JSX code that caused syntax errors
  - Lines 1063-1176: Orphaned tooltip and table code mixed into History tab
  - Lines 1741-2732: Duplicate component code after export statement
- ✅ Fixed: JSX escape warnings for quotes and apostrophes
- ✅ Verified: AI Model Learning section populates correctly (was showing 0s because model not trained yet - expected behavior)
- ✅ Verified: All 4 tabs working (Results, History, Compare & Analyze, Learn)
- ✅ Verified: Deep Dive Modal opens correctly from history items
- ✅ Verified: Strategy Tuning page displays parameter transparency

## Key API Endpoints
- `GET /api/status` - System status and trading mode
- `GET /api/health` - Health check
- `GET /api/trades/stats` - Trade frequency statistics
- `GET /api/performance` - Performance metrics
- `GET /api/positions` - Open positions
- `GET /api/trades` - Recent trades
- `GET /api/analytics` - Comprehensive analytics
- `GET /api/historical/stats` - Historical data statistics
- `POST /api/historical/collect` - Trigger snapshot collection
- `POST /api/historical/collect-prices` - Collect tick-level price history
- `GET /api/historical/price-stats` - Real price data statistics
- `GET /api/rl/stats` - RL engine training statistics
- `POST /api/rl/train` - Trigger RL batch training
- `GET /api/backtest/history` - Get list of past backtests
- `GET /api/backtest/results` - Get latest or specific backtest results
- `POST /api/backtest/compare` - Compare multiple backtests with educational analysis
- `DELETE /api/backtest/{id}` - Delete a backtest
- `POST /api/bot/start` - Start live trading
- `POST /api/bot/stop` - Stop live trading
- `GET /api/sentiment/analyze` - Analyze market sentiment
- `GET /api/whale/detect` - Detect whale activity
- `POST /api/tuning/strategy` - Tune single strategy
- `POST /api/tuning/all` - Tune all strategies
- `WS /ws` - WebSocket real-time updates

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
