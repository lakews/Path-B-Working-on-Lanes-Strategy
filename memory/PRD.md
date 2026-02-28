# APEX Trader - Product Requirements Document

## Original Problem Statement
Build an advanced algorithmic trading system for Polymarket prediction markets with:
- Multi-lane trading strategies (HFT, Alpha, Gamma, Sports Arbitrage, News Sniper)
- Real-time market data via WebSocket and REST APIs
- Paper trading simulation with realistic execution
- Risk management and position sizing
- News-driven and sentiment-based trading signals

## User Personas
- **Quantitative Trader**: Needs low-latency market data and sophisticated exit strategies
- **Sports Arbitrage Trader**: Needs accurate sports market classification and routing
- **News Trader**: Needs real-time news signals for prediction market opportunities

## Core Requirements (Implemented)

### 1. Multi-Lane Trading Architecture ✅
- 5 independent trading lanes: HFT, Alpha, Gamma, Sports Arbitrage, News Sniper
- Lane-specific configuration and capital allocation
- Real-time P&L tracking per lane

### 2. WebSocket-Primary Data Architecture ✅ (Feb 2026)
- WebSocket orderbook cache as PRIMARY data source for exits
- REST API as FALLBACK only
- "Real Prices Only" principle - no default/0.5 prices for exits
- Exit blocking when no verified orderbook available

### 3. Sports Market Classification ✅ (Feb 2026)
- Keyword-based classification (ignores API 'entertainment' category)
- Sports markets routed to dedicated SPORTS lane
- HFT filter blocks sports markets

### 4. Paper Trading System ✅
- Simulated order execution
- Realistic P&L calculation
- Position tracking and management

## Architecture

### Key Files
- `/app/backend/paper_trading/paper_trader.py` - Main trading engine (9000+ lines)
- `/app/backend/services/tag_library_service.py` - Market classification
- `/app/backend/services/realtime_market_service.py` - WebSocket data
- `/app/backend/trading/hft_engine_v2.py` - HFT strategy execution

### Data Flow
```
Polymarket API → WebSocket/REST → RealTimeMarketService → PaperTrader
                                          ↓
                              TagLibraryService (Classification)
                                          ↓
                              Lane Router (HFT/Alpha/Gamma/Sports/News)
```

## Completed Work (Feb 2026)

### Session 51
- ✅ Verified WebSocket-primary exit logic (81/82 tests passed)
- ✅ Confirmed real-time orderbook prices for all exits
- ✅ REST API fallback working correctly
- ✅ Default price rejection working

### Previous Sessions
- ✅ Fixed sports market routing (multi-layer bug in TagLibraryService)
- ✅ Implemented "Real Prices Only" exit principle
- ✅ WebSocket-primary data architecture

## Known Issues

### P1 - Action Required
1. **Cumulative Stats Historical Error**: Old trades miscategorized as "Other" pollute metrics
   - Proposed: Add "Reset Cumulative Stats" button

### P2 - External Blockers
2. **Exa.ai API**: Credits exhausted (402 error)
3. **Apify Integration**: Billing issue affecting Twitter scraping

### P2 - Code Quality
4. **Pre-existing Lint Errors**: Bare `except` clauses in various files

## Backlog (Prioritized)

### P1 - Upcoming
- [ ] Deprecate Old News Pipeline (`news_injector.py`, `signal_cache.py`)
- [ ] Integrate Alpha/Gamma Lanes with Markets-First (PATH A)

### P2 - Future
- [ ] True Market Making Architecture (two-sided quoting)
- [ ] SSOT Refactoring (`EXIT_STRATEGY_CONFIG` → `risk_config.json`)
- [ ] LLM Result Caching (MongoDB)
- [ ] Refactor `paper_trader.py` into smaller modules

## API Endpoints

### Paper Trading
- `POST /api/paper-trading/start` - Start trading session
- `GET /api/paper-trading/status` - Current status with equity/P&L
- `GET /api/paper-trading/positions` - Open positions
- `GET /api/paper-trading/trades` - Closed trade history

### System
- `GET /api/health` - Backend health check
- `GET /api/websocket/status` - WebSocket connection status

## Technical Principles

1. **"Real Prices Only"**: All trade exits MUST use verified real-time orderbook prices
2. **WebSocket-Primary**: Prioritize WebSocket for speed, REST as fallback
3. **Defensive Classification**: Don't trust API categories, verify with keywords
4. **Exit Blocking**: Block exits without verified prices (no phantom P&L)

## Test Coverage
- `/app/backend/tests/test_websocket_primary_exit.py` - Exit data source tests
- `/app/backend/tests/test_sports_classification_fix.py` - Classification tests
- `/app/backend/tests/test_exits.py` - General exit logic tests

## Credentials (Test)
- Email: `admin@apex-trader.local`
- Password: `apex2026!`

## 3rd Party Integrations
| Service | Status | Notes |
|---------|--------|-------|
| Polymarket CLOB API | ✅ Working | Core market data |
| The Odds API | ✅ Working | Sports odds |
| OpenAI/Gemini | ✅ Working | LLM analysis |
| Exa.ai | ⚠️ Out of credits | News polling |
| Apify | ⚠️ Billing issue | Twitter scraping |
