# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build a sophisticated 5-lane trading bot (HFT, ALPHA, GAMMA, SPORTS, NEWS) with a centralized "Single Source of Truth" (SSOT) Risk Management layer for prediction market trading.

## Current Session Focus
- **NEWS Lane Phase 2 Implementation (COMPLETED Feb 2026)** - MongoDB-integrated NEWS Sniper
- **HFT Engine V2 ENHANCED Implementation (COMPLETED Feb 2026)** - Merged all legacy features
- **Markets-First Architecture Phase 1 (COMPLETED Feb 2026)**
- **PATH A Engine Ultimate (COMPLETED Feb 26, 2026)** - Full-stack refactor of "Architecture C" to PATH A
- **Code Review & Testing (Feb 26, 2026)** - Verified WebSocket PRIMARY, PATH A signal generation, NewsSniper consumption

---

## Architecture Overview

### 5 Trading Lanes - All Now Integrated with Markets-First
1. **HFT Lane** - HFT Engine V2 ENHANCED (reads PATH A + PATH B from MongoDB)
2. **ALPHA Lane** - Alpha signal generation with Bayesian inference
3. **GAMMA Lane** - Volatility-based trading strategies
4. **SPORTS Lane** - Sports arbitrage using real odds APIs
5. **NEWS Lane** - NEWS Sniper MongoDB (reads PATH A, 5-factor conviction)

### Complete Markets-First Data Flow
```
NEWS EVENT ARRIVES
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ DualPathNewsInjector (Phase 1)                                  │
│       ↓                              ↓                          │
│ PATH A → MongoDB.signals        PATH B → MongoDB.hft_opportunities│
│ (LLM analysis, BF, confidence)  (Broadcast to all markets)      │
└─────────────────────────────────────────────────────────────────┘
       ↓                                    ↓
┌──────────────────────────────────┐    ┌─────────────────────────┐
│ NEWS SNIPER MONGODB (Phase 2)    │    │ HFT ENGINE V2 ENHANCED  │
│ ✅ Reads PATH A signals          │    │ ✅ Reads PATH B (speed) │
│ ✅ 5-Factor ConvictionEnhancer   │    │ ✅ Reads PATH A (intel) │
│ ✅ Kelly Tiering (5%-50%)        │    │ ✅ News strength mults  │
│ ✅ Whale Alignment               │    │ ✅ 5 sub-strategies     │
│ ✅ Source Credibility            │    │ ✅ Alpha integration    │
└──────────────────────────────────┘    └─────────────────────────┘
```

### NEWS Sniper MongoDB - 5-Factor ConvictionEnhancer
```
┌─────────────────────────────────────────────────────────────────┐
│ CONVICTION = BF × Source × Liquidity × Whale × Regime           │
├─────────────────────────────────────────────────────────────────┤
│ Factor 1: Bayes Factor (from PATH A signal)                     │
│                                                                 │
│ Factor 2: Source Credibility                                    │
│   Reuters/Bloomberg = 1.25x                                     │
│   Whale Alert = 1.35x                                           │
│   Twitter = 0.90x                                               │
│                                                                 │
│ Factor 3: Liquidity Multiplier                                  │
│   $100K+ = 1.20x, $50K+ = 1.10x, <$5K = 0.75x                  │
│                                                                 │
│ Factor 4: Whale Alignment                                       │
│   Aligned = up to 1.35x boost                                   │
│   Disagreement = down to 0.75x                                  │
│                                                                 │
│ Factor 5: Market Regime                                         │
│   Crisis = 0.7x, Volatile = 0.9x, Normal = 1.0x, Quiet = 1.1x  │
└─────────────────────────────────────────────────────────────────┘
```

### Kelly Tiering Based on Conviction
| Conviction | Kelly Fraction | Description |
|------------|----------------|-------------|
| >= 10.0 | 50% | Extreme conviction - maximum position |
| 8.0 - 10.0 | 40% | High conviction |
| 6.0 - 8.0 | 30% | Strong conviction |
| 3.0 - 6.0 | 15% | Moderate conviction |
| 1.0 - 3.0 | 5% | Low conviction |
| < 1.0 | 0% | Skip trade |

---

## What's Been Implemented

### Session: February 2026

#### COMPLETED ✅
1. **NEWS Sniper MongoDB (Phase 2)**
   - File: `/app/backend/lanes/news_lane/news_sniper_mongodb.py`
   - 5-factor ConvictionEnhancer
   - Kelly tiering (5%-50% based on conviction)
   - MongoDB PATH A signal reading
   - Whale alignment checking
   - Source credibility scoring
   - Integrated into paper_trader.py asyncio.gather

2. **HFT Engine V2 ENHANCED**
   - File: `/app/backend/trading/hft_engine_v2.py`
   - Merged all legacy features (Alpha targets, Math Engine, Hysteresis, Tick Grid)
   - 5 sub-strategies with capital allocation
   - MongoDB PATH A + PATH B integration
   - Legacy HFT loop DEPRECATED
   - **Strategy-Specific Direction Logic (Feb 15, 2026)**:
     - DELTA_NEUTRAL & EXTREME_SPREAD: Fair value comparison with 2% edge threshold
     - VOLATILITY_EXPLOIT: Mean reversion at price extremes (<=0.15 or >=0.85)
     - LIQUIDITY_PROVISION: Order flow imbalance (20% imbalance ratio)
     - SHARP_FOLLOWING: Whale/sharp trader direction
     - PATH A override when Bayes Factor >= 5.0

3. **Markets-First Architecture Phase 1**
   - PolymarketScanner (500+ markets cached)
   - DualPathNewsInjector (PATH A + PATH B)
   - MongoDB collections with TTL indexes

4. **Optimized News Query Generation (Feb 15, 2026)**
   - Uses market description for richer context
   - Category-aware suffixes (crypto → "price news update", politics → "election news latest", etc.)
   - Time-aware modifiers ("breaking latest" for markets expiring within 7 days)
   - Key stored in MongoDB with DB_NAME-derived encryption

5. **PATH A Engine Ultimate (Feb 26, 2026)** ✅
   - File: `/app/backend/services/path_a_engine.py`
   - Renamed from "Architecture C Ultimate" to "PATH A Engine"
   - **Hybrid Relevance Scoring**: Category match + Entity match + Keyword overlap
   - **Two-Tier LLM Analysis**: Resolution prompt (Tier 1) → Sentiment prompt (Tier 2)
   - **330+ Entity Synonyms** for robust news-to-market matching
   - **7 Optimizations**: Dedup, Early Termination, Clustering, Adaptive TTL, Priority Queue, Bayes Multipliers, Hot-swap
   - **O(1) Keyword Lookup** via 2,800+ keyword reverse index
   - **MongoDB Cache Fallback** for scanner when Gamma API unavailable
   - **Signal Structure**: Includes `bayes_factor`, `market_question`, `signal_type`, `timestamp` for NewsSniper compatibility

6. **Polymarket News Aggregator (Feb 26, 2026)** ✅
   - File: `/app/backend/services/polymarket_news_sources.py`
   - Aggregates from Finnhub API (general + crypto)
   - 10 RSS feeds: AP News, Reuters, ESPN, Politico, CoinDesk, Federal Reserve

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/app/backend/lanes/news_lane/news_sniper_mongodb.py` | **NEWS Sniper MongoDB** - Phase 2 trade execution |
| `/app/backend/trading/hft_engine_v2.py` | **HFT Engine V2 ENHANCED** - Sole HFT implementation |
| `/app/backend/services/polymarket_scanner.py` | **PolymarketScanner** - Market caching + MongoDB fallback |
| `/app/backend/services/news_injector_dual_path.py` | **DualPathNewsInjector** - PATH A/B signal creation |
| `/app/backend/services/path_a_engine.py` | **PATH A Engine** - Hybrid scoring + Two-tier LLM |
| `/app/backend/services/polymarket_news_sources.py` | **News Aggregator** - Finnhub + RSS feeds |
| `/app/backend/services/api_key_store.py` | **API Key Persistence** - Encrypted MongoDB storage |
| `/app/backend/paper_trading/paper_trader.py` | Paper trading with all integrations |

---

## API Endpoints

### NEWS Sniper Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/news-sniper/status` | GET | NEWS Sniper MongoDB metrics and configuration |

### HFT V2 Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/hft-v2/status` | GET | HFT Engine V2 ENHANCED metrics |

### Markets-First Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health/scanner` | GET | Scanner health status |
| `/api/webhooks/news` | POST | News event webhook |
| `/api/markets-first/status` | GET | Full system status |
| `/api/markets-first/signals` | GET | Active PATH A signals |
| `/api/markets-first/opportunities` | GET | PATH B HFT opportunities |
| `/api/path-a/health` | GET | PATH A Engine health check |
| `/api/path-a/stats` | GET | PATH A Engine statistics |

---

## Prioritized Backlog

### P0 - Critical (ALL COMPLETED ✅)
- [x] Markets-First Architecture Phase 1
- [x] HFT Engine V2 ENHANCED (merged legacy)
- [x] NEWS Lane Phase 2 (MongoDB integration)
- [x] Legacy HFT loop deprecation
- [x] **HFT V2 Strategy-Specific Direction Refactor (Feb 15, 2026)** - Each of 5 strategies now determines its own direction
- [x] **Tiered Kill Switch Implementation (Feb 15, 2026)** - Configurable extreme price validation with per-strategy overrides
- [x] **P&L Anomaly Resolution (Feb 15, 2026)** - Fixed expired markets sending 0.5 prices, tiered validation system
- [x] **System Audit (Dec 2025)** - Verified tiered kill switch working, hft_volatility_exploit trading at extreme prices
- [x] **Markets-First News Query Optimization (Feb 15, 2026)** - Optimized query generation using market description, category, and time-awareness; Fixed API key encryption issue
- [x] **Market Quality Score Optimization (Feb 26, 2026)** - Optimized for prediction markets: `spread*5` penalty (less aggressive), weights `0.4/0.6` (prioritize spread), threshold `0.5`
- [x] **PATH A Engine Ultimate (Feb 26, 2026)** - Full refactor from "Architecture C" to PATH A, hybrid scoring, two-tier LLM, MongoDB fallback for scanner
- [x] **HFT V2 Optimal Sports Filter (Feb 27, 2026)** - Replaced regex-based filter with authoritative `category` field check; 798+ sports markets filtered
- [x] **Frontend Data Inconsistency Fix (Feb 27, 2026)** - Added `closed_trades` field to cumulative-stats API for consistent display in Asset Class Performance table

### P1 - High Priority (NEXT)
- [ ] Verify BF-based Kelly sizing in NewsSniper
- [ ] Deprecate old news pipeline (news_injector.py, signal_cache.py)
- [ ] Integrate Alpha/Gamma Lanes with Markets-First signals
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`
- [ ] Clean up orphaned config variable (`sharp_alignment_threshold` in paper_trader.py)
- [ ] Live trading validation

### P2 - Future
- [ ] Reactivate CryptoPanic with premium API key
- [ ] Implement True Market Making Architecture (two-sided quoting for LIVE_MODE)
- [ ] Production deployment optimization
- [ ] Fix Apify test script error (`'WebhookNews' object has no attribute 'account'`)

---

## Test Reports
- `/app/test_reports/iteration_40.json` - Markets-First Phase 1 (20 tests passed)
- `/app/test_reports/iteration_41.json` - HFT Engine V2 (37 tests passed)
- `/app/test_reports/iteration_42.json` - HFT Engine V2 ENHANCED (64 tests passed)
- `/app/test_reports/iteration_43.json` - NEWS Sniper MongoDB Phase 2 (74 tests passed)
- `/app/test_reports/iteration_46.json` - HFT V2 Direction Refactor (61 tests passed)
- `/app/test_reports/iteration_47.json` - HFT V2 Deep Audit (84 tests passed)

---

## Paper Mode vs Live Mode (Feb 15, 2026)

### Current Implementation (Option 2)
| Mode | LIVE_MODE Flag | Entry Pricing | Exit Pricing | HFT Strategies |
|------|----------------|---------------|--------------|----------------|
| **Paper** | `False` | `current_price` (mid) | `current_price` (mid) | ✅ All 5 work |
| **Live** | `True` | Orderbook (maker) | Orderbook (spread-aware) | ✅ Real execution |

### How to Switch Modes
```python
# In hft_config.py
LIVE_MODE = False  # Paper mode (default) - mid-price for testing
LIVE_MODE = True   # Live mode - orderbook-based execution
```

### Files Modified
- `paper_trading/paper_trader.py`:
  - `_execute_paper_entry()` - Line ~5480
  - `_evaluate_exit()` - Line ~5040
  - `_execute_paper_exit()` - Line ~5780

---

## Pending Code Changes Log (For Future Reverting)

### Change #1: VOLATILITY_EXPLOIT Mode Selection (UPDATED - Dec 2025)
**File**: `/app/backend/trading/hft_engine_v2.py` (~Line 595)
**Status**: FIXED
**Previous Issue**: Allowed VOLATILITY_EXPLOIT to trigger on price extremes alone, bypassing volatility check. Also, markets with extreme prices but tight spreads fell back to EXTREME_SPREAD instead of being skipped.
**Fix Applied**: 
1. Now requires BOTH extreme price AND wide spread (≥7%) from real orderbook data for VOLATILITY_EXPLOIT
2. **Extreme-price markets with tight spreads are now SKIPPED entirely** (return None) instead of falling back to EXTREME_SPREAD
3. This prevents trading dead/resolved markets that sit at extreme prices with tight spreads

```python
# FIXED (Dec 2025):
if price_at_extreme:
    if vol_score >= VOLATILITY_MIN_SCORE or has_volatility_signal:
        return HFTMode.VOLATILITY_EXPLOIT  # Active volatile market
    else:
        return None  # SKIP - likely dead market
else:
    return HFTMode.EXTREME_SPREAD  # Non-extreme price
```

### Change #2: Directional Strategy Orderbook Bypass (REVERTED Feb 15, 2026)
**File**: `/app/backend/paper_trading/paper_trader.py` (~Line 5474)
**Status**: REVERTED
**Issue**: Caused PnL calculation mismatch (entry used current_price, exit used orderbook prices)
**Result**: Inflated returns (+321% in 10 mins with 29.9% win rate - impossible)

### Change #3: Paper Mode Uses Real Orderbook Prices (UPDATED - Dec 2025)
**File**: `/app/backend/paper_trading/paper_trader.py`
**Status**: FIXED (was using mid-price, now uses orderbook)
**Previous Issue**: Paper mode used mid-price for entry/exit, ignoring real spread costs
**Fix Applied**: All directional trades now use orderbook prices:
- Entry: Buy YES = pay YES ask, Buy NO = pay NO bid
- Exit: Sell YES = hit YES bid, Sell NO = hit NO bid (then convert to YES-equivalent)
- `LIVE_MODE` flag now only controls two-sided market making logic, not orderbook usage
- **CRITICAL FIX (Dec 2025)**: Exit now fetches correct token orderbook based on position side
  - YES position exit → fetches `token_ids[0]` (YES orderbook)
  - NO position exit → fetches `token_ids[1]` (NO orderbook)
**Locations Modified**:
- `_execute_paper_entry()` (~Line 5650) - Fetches orderbook, uses ask/bid for entry
- `_evaluate_exit()` (~Line 5215) - Fetches CORRECT token orderbook, hits bid, converts to YES-equivalent
- `_execute_paper_exit()` (~Line 6000) - Fetches CORRECT token orderbook, hits bid, converts to YES-equivalent

### Change #4: Tiered Kill Switch / Extreme Price Validation (ACTIVE - Feb 15, 2026)
**Files Modified**:
- `/app/backend/config/risk_config.json` - New `extreme_price_validation` config section
- `/app/backend/data/polymarket_api.py` - Expiration check at API source
- `/app/backend/services/realtime_market_service.py` - Expiration check on cache and WebSocket
- `/app/backend/paper_trading/paper_trader.py`:
  - `get_kill_switch_for_strategy()` - Returns strategy-specific bounds
  - `validate_extreme_price_entry()` - Tiered validation with orderbook/volume/spread/expiry checks
  - `_get_active_markets()` - Uses tiered validation instead of blanket kill switch
- `/app/backend/server.py` - API endpoint for extreme_price_validation config
- `/app/frontend/src/components/RiskSettings.js` - UI for configuring tiered kill switch

**Architecture**:
- **Global thresholds** define where prices become "extreme" (default: <3% or >97%)
- **Tiered validation** for extreme prices requires:
  - Orderbook depth > $100
  - Spread < 5%
  - Volume > $50/hour
  - Time to expiry > 24 hours
- **Strategy overrides** allow specific strategies to bypass global thresholds:
  - `hft_volatility_exploit`: 0.5% - 99.5% (maximum convexity access)
  - `hft_gamma_scalp`: 1% - 99% (OTM gamma capture)

**UI Configuration** (Settings > Extreme Price Validation):
- Enable/disable tiered validation toggle
- Global extreme thresholds
- Validation requirements (depth, spread, volume, expiry)
- Per-strategy kill switch overrides with individual toggles and bounds

### Change #5: Duplicate Position Deletion Bug Fix (ACTIVE - Feb 15, 2026)
**File**: `/app/backend/paper_trading/paper_trader.py` (~Line 6130)
**Status**: ACTIVE
**Issue**: `_execute_paper_exit()` was deleting positions twice, causing KeyError
**Fix**: Removed duplicate `del self.paper_positions[market_id]` call

---

## Future Roadmap

### P0 - Immediate
- [x] Paper mode mid-price consistency (Option 2)
- [x] **Sharp Detector Full Implementation (Feb 15, 2026)** - All 3 phases
- [x] **P&L Anomaly Investigation & Fix (Feb 15, 2026)** - Suspicious 0.5 price safety check
- [ ] Deprecate old news pipeline (news_injector.py, signal_cache.py)
- [ ] Integrate Alpha/Gamma Lanes with Markets-First signals

### P1 - High Priority
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`
- [ ] Live trading validation with real orderbook execution

### P2 - Future (Complex)
- [ ] **True Market Making Architecture** - Two-sided quoting with:
  - Simultaneous bid/ask order posting
  - Inventory/delta tracking and management
  - Quote adjustment engine (continuous re-quoting)
  - Risk controls for inventory skew
  - This requires significant new architecture beyond current directional approach

---

## Sharp Detector Implementation (Feb 15, 2026)

### Phase 1: Proxy Methods (Immediate Detection)
Uses existing data when real sharp trader data is unavailable:
- **Volume spike detection**: >$50k suggests institutional activity
- **Price momentum**: >5% recent move indicates sharp activity
- **Order flow imbalance**: >30% directional flow
- **News catalyst**: PATH B opportunity exists

### Phase 2: Data Collection Pipeline
Background tasks for real sharp trader identification:
- **Trade fetcher**: Fetches trades from Polymarket CLOB API every 5 minutes
- **Data storage**: Stores in `market_trades` MongoDB collection
- **Outcome tracking**: Updates trade outcomes with current prices for P&L calculation

### Phase 3: Sharp Trader Identification
Scheduled job every 6 hours:
- **Win rate analysis**: Identifies traders with >70% win rate
- **Volume threshold**: Requires >$10k total volume
- **Trade minimum**: At least 10 trades required
- **Category focus**: Specialists (<=3 categories) preferred

### Sharp Alignment Integration (Feb 15, 2026)
Fixed naming collision and integrated real sharp data:
- **`market_quality_score`**: Renamed from old `sharp_alignment` - measures liquidity + spread
- **`sharp_alignment`**: Now uses real SharpDetector data - measures smart money alignment
- **`get_alignment_signal()`**: New method added to SharpDetector
- **Strategy selection**: Uses both metrics appropriately
  - `market_quality_score > 0.7` + `sharp_alignment > 0.6` → triggers arbitrage

### MongoDB Collections
| Collection | Purpose |
|------------|---------|
| `market_trades` | Historical trades with trader addresses |
| `sharp_traders` | Identified sharp traders and their stats |
| `sharp_positions` | Current positions of sharp traders |

### API Endpoint
`GET /api/sharp-detector/status` - Returns stats and configuration

---

## User Notes
- Use platform's "Save to Github" feature to persist codebase
- All API keys stored in `/app/backend/.env`
- HFT Engine V2 ENHANCED is the **sole HFT implementation** (legacy disabled)
- NEWS Sniper MongoDB handles **trade execution** (legacy loop handles ingestion)
- Markets-First system provides unified signal pipeline for HFT and NEWS lanes
