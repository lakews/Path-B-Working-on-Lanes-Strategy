# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build a sophisticated 5-lane trading bot (HFT, ALPHA, GAMMA, SPORTS, NEWS) with a centralized "Single Source of Truth" (SSOT) Risk Management layer for prediction market trading.

## Current Session Focus
- **HFT Engine V2 Implementation (COMPLETED Feb 2026)**
- **Markets-First Architecture Phase 1 (COMPLETED Feb 2026)**
- Sports Arbitrage exit logic fix (COMPLETED)
- News Lane (Lane 5) expansion with multi-source ingestion (COMPLETED)
- 5-Lane Performance Dashboard UI Enhancement (COMPLETED)

---

## Architecture Overview

### 5 Trading Lanes
1. **HFT Lane** - High-frequency trading with 5 sub-strategies (HFT Engine V2)
2. **ALPHA Lane** - Alpha signal generation with Bayesian inference
3. **GAMMA Lane** - Volatility-based trading strategies
4. **SPORTS Lane** - Sports arbitrage using real odds APIs
5. **NEWS Lane** - News-driven trading with multi-source ingestion

### HFT Engine V2 Architecture (NEW - Feb 2026)
```
┌─────────────────────────────────────────────────────────────────┐
│ HFT ENGINE V2 - 5 SUB-STRATEGIES                                │
├─────────────────────────────────────────────────────────────────┤
│ 1. Delta-Neutral Market Making (35%)                            │
│    - Quote YES/NO bid/ask, capture spreads                      │
│    - Zone: Standard prices (0.10-0.90)                          │
│                                                                 │
│ 2. Volatility Exploitation (10%)                                │
│    - Mean reversion at extreme prices                           │
│    - Zone: 0.00-0.10 or 0.90-1.00                               │
│                                                                 │
│ 3. Extreme Spread Capture (15%)                                 │
│    - Wide spreads (5-15x normal) at extremes                    │
│    - Compensate volatility with wider spreads                   │
│                                                                 │
│ 4. Sharp Trader Following (20%)                                 │
│    - Detect institutional flow via z-score                      │
│    - Follow 50% of sharp size                                   │
│                                                                 │
│ 5. Liquidity Provision (20%)                                    │
│    - Standing quotes on high-volume markets                     │
│    - Minimum $50K daily volume                                  │
└─────────────────────────────────────────────────────────────────┘
```

### News Strength Classification
```
┌─────────────────────────────────────────────────────────────────┐
│ BAYES FACTOR → NEWS STRENGTH → MULTIPLIERS                      │
├─────────────────────────────────────────────────────────────────┤
│ BF >= 10.0 → PAUSE    → Skip entire cycle                       │
│ BF 5.0-10  → EXTREME  → Spread 2.5x, Position 0.5x              │
│ BF 3.0-5.0 → CAUTION  → Spread 1.3x, Position 0.75x             │
│ BF < 3.0   → NORMAL   → No adjustment                           │
└─────────────────────────────────────────────────────────────────┘
```

### Markets-First Architecture (Phase 1)
```
┌────────────────────────────────────────────────────────────────┐
│ LAYER 1: MARKET DATA FOUNDATION                                │
│ PolymarketScanner → 500+ markets cached continuously           │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│ LAYER 2: NEWS PROCESSING (Dual-Path)                           │
│ PATH A: Semantic search → LLM → signals collection             │
│ PATH B: Broadcast ALL → hft_opportunities collection           │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│ LAYER 3: SIGNAL CONSUMPTION                                    │
│ HFT V2: Reads PATH B (speed) + PATH A (intelligence)           │
│ NEWS Lane: Reads PATH A (conviction calculation) [PENDING]     │
└────────────────────────────────────────────────────────────────┘
```

---

## What's Been Implemented

### Session: February 2026

#### COMPLETED ✅
1. **HFT Engine V2** (`/app/backend/trading/hft_engine_v2.py`)
   - 5 sub-strategies with proper capital allocation
   - News strength classification (PAUSE/EXTREME/CAUTION/NORMAL)
   - MongoDB signal integration (PATH A + PATH B)
   - Kelly criterion (0.25) and 3% position cap constraints
   - Integration with paper_trader.py start/stop lifecycle

2. **HFT Configuration** (`/app/backend/trading/hft_config.py`)
   - NewsStrength enum
   - HFTConfig class with all thresholds and allocations
   - Helper functions: get_news_strength(), get_multipliers(), get_price_zone()

3. **Markets-First Architecture Phase 1**
   - PolymarketScanner with WebSocket + REST fallback
   - DualPathNewsInjector with PATH A (LLM) + PATH B (broadcast)
   - MongoDB collections with TTL indexes

4. **API Endpoints**
   - `GET /api/hft-v2/status` - HFT Engine V2 metrics
   - `GET /api/health/scanner` - Scanner health
   - `POST /api/webhooks/news` - News processing
   - `GET /api/markets-first/status` - Full system status

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/app/backend/trading/hft_engine_v2.py` | **NEW** HFT Engine V2 with 5 sub-strategies |
| `/app/backend/trading/hft_config.py` | **NEW** HFT configuration and enums |
| `/app/backend/services/polymarket_scanner.py` | **NEW** Continuous market scanner |
| `/app/backend/services/news_injector_dual_path.py` | **NEW** Dual-path news processing |
| `/app/backend/paper_trading/paper_trader.py` | Paper trading with HFT V2 integration |
| `/app/backend/risk_config.py` | Risk configuration |

---

## API Endpoints

### HFT V2 Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/hft-v2/status` | GET | HFT Engine V2 metrics and configuration |

### Markets-First Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health/scanner` | GET | Scanner health status |
| `/api/webhooks/news` | POST | News event webhook |
| `/api/markets-first/status` | GET | Full system status |
| `/api/markets-first/signals` | GET | Active PATH A signals |
| `/api/markets-first/opportunities` | GET | PATH B HFT opportunities |
| `/api/markets-first/cached-markets` | GET | In-memory cached markets |

---

## Prioritized Backlog

### P0 - Critical (COMPLETED)
- [x] HFT Engine V2 Implementation
- [x] Markets-First Architecture Phase 1
- [x] 5-Lane Performance Dashboard Enhancement
- [x] Capital Accounting Bug Fixes

### P1 - High Priority (NEXT)
- [ ] **NEWS Lane Integration (Phase 2)** - Update NEWS lane to read from MongoDB signals with ConvictionEnhancer
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`

### P2 - Future
- [ ] HFT V3 with direct order placement
- [ ] Reactivate CryptoPanic with premium API key
- [ ] Production deployment optimization

---

## 3rd Party Integrations

| Service | Status | Key Location |
|---------|--------|--------------|
| OpenAI GPT-4o-mini | ✅ Active | Emergent LLM Key |
| OpenAI GPT-5.2 | ✅ Active | Emergent LLM Key |
| Gemini 3 Flash | ✅ Active | Emergent LLM Key |
| The Odds API | ✅ Active | User API Key |
| Exa.ai | ✅ Active | User API Key |
| Apify | ✅ Active | User API Key |
| CryptoPanic | ⏸️ PAUSED | User API Key |

---

## Test Reports
- `/app/test_reports/iteration_40.json` - Markets-First Phase 1 (20 tests passed)
- `/app/test_reports/iteration_41.json` - HFT Engine V2 (37 tests passed)

---

## User Notes
- Use platform's "Save to Github" feature to persist codebase
- All API keys stored in `/app/backend/.env`
- HFT Engine V2 initializes ONLY when paper trading starts
- Markets-First system runs in PARALLEL to existing system (zero breaking changes)
