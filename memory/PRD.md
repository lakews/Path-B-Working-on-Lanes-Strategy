# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build a sophisticated 5-lane trading bot (HFT, ALPHA, GAMMA, SPORTS, NEWS) with a centralized "Single Source of Truth" (SSOT) Risk Management layer for prediction market trading.

## Current Session Focus
- **HFT Engine V2 ENHANCED Implementation (COMPLETED Feb 2026)** - Merged all legacy features
- **Markets-First Architecture Phase 1 (COMPLETED Feb 2026)**
- Sports Arbitrage exit logic fix (COMPLETED)
- News Lane (Lane 5) expansion with multi-source ingestion (COMPLETED)
- 5-Lane Performance Dashboard UI Enhancement (COMPLETED)

---

## Architecture Overview

### 5 Trading Lanes
1. **HFT Lane** - High-frequency trading with 5 sub-strategies (HFT Engine V2 ENHANCED)
2. **ALPHA Lane** - Alpha signal generation with Bayesian inference
3. **GAMMA Lane** - Volatility-based trading strategies
4. **SPORTS Lane** - Sports arbitrage using real odds APIs
5. **NEWS Lane** - News-driven trading with multi-source ingestion

### HFT Engine V2 ENHANCED Architecture (Feb 2026)
```
┌─────────────────────────────────────────────────────────────────┐
│ HFT ENGINE V2 ENHANCED - UNIFIED HFT IMPLEMENTATION             │
│ (Legacy HFT loop DEPRECATED and DISABLED)                       │
├─────────────────────────────────────────────────────────────────┤
│ MERGED LEGACY FEATURES:                                         │
│ ├─ Alpha Target Integration (strategy_context bridge)           │
│ ├─ HFT Math Engine (cubic skew, jump detection, cliff)          │
│ ├─ Active Order Tracking (Polymarket compliance)                │
│ ├─ Hysteresis Logic (anti-churn, 1 cent threshold)              │
│ └─ Tick Grid Compliance ($0.01, kill zones $0.05-$0.95)         │
│                                                                 │
│ NEW V2 FEATURES:                                                │
│ ├─ 5 Sub-Strategies with capital allocation                     │
│ ├─ News Strength Classification (PAUSE/EXTREME/CAUTION/NORMAL)  │
│ ├─ MongoDB Signal Integration (PATH A + PATH B)                 │
│ └─ Spread & Position Multipliers based on news                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 5 SUB-STRATEGIES                                                │
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

### Polymarket Compliance Constants
| Constant | Value | Purpose |
|----------|-------|---------|
| TICK_SIZE | $0.01 | Price grid alignment |
| MIN_PRICE | $0.05 | Kill zone lower bound |
| MAX_PRICE | $0.95 | Kill zone upper bound |
| MIN_SPREAD_TICKS | 2 | Minimum spread ($0.02) |
| HYSTERESIS_THRESHOLD | $0.01 | Anti-churn drift tolerance |
| ORDER_STALE_SECONDS | 120 | Order refresh time |

---

## What's Been Implemented

### Session: February 2026

#### COMPLETED ✅
1. **HFT Engine V2 ENHANCED** (`/app/backend/trading/hft_engine_v2.py`)
   - Merged ALL legacy HFT features:
     - Alpha Target Integration via strategy_context
     - HFT Math Engine (cubic skew, jump detection, cliff protection)
     - Active Order Tracking for Polymarket compliance
     - Hysteresis Logic (anti-churn)
     - Tick Grid Compliance ($0.01)
   - Plus NEW V2 features:
     - 5 sub-strategies with proper capital allocation
     - News strength classification
     - MongoDB signal integration
   - **Legacy _run_hft_loop() is now DEPRECATED and DISABLED**

2. **HFT Configuration** (`/app/backend/trading/hft_config.py`)
   - NewsStrength enum
   - HFTConfig class with all thresholds and allocations
   - Helper functions

3. **Markets-First Architecture Phase 1**
   - PolymarketScanner (500+ markets cached)
   - DualPathNewsInjector (PATH A + PATH B)
   - MongoDB collections with TTL indexes

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/app/backend/trading/hft_engine_v2.py` | **HFT Engine V2 ENHANCED** - Sole HFT implementation |
| `/app/backend/trading/hft_config.py` | HFT configuration and enums |
| `/app/backend/strategies/hft_math.py` | HFT Math Engine (cubic skew, cliff protection) |
| `/app/backend/services/polymarket_scanner.py` | Continuous market scanner |
| `/app/backend/services/news_injector_dual_path.py` | Dual-path news processing |
| `/app/backend/paper_trading/paper_trader.py` | Paper trading (HFT V2 integrated) |

---

## API Endpoints

### HFT V2 Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/hft-v2/status` | GET | HFT Engine V2 ENHANCED metrics and configuration |

### Markets-First Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health/scanner` | GET | Scanner health status |
| `/api/webhooks/news` | POST | News event webhook |
| `/api/markets-first/status` | GET | Full system status |
| `/api/markets-first/signals` | GET | Active PATH A signals |
| `/api/markets-first/opportunities` | GET | PATH B HFT opportunities |

---

## Prioritized Backlog

### P0 - Critical (COMPLETED)
- [x] HFT Engine V2 ENHANCED Implementation (merged legacy + new)
- [x] Markets-First Architecture Phase 1
- [x] Legacy HFT loop deprecation
- [x] Capital Accounting Bug Fixes

### P1 - High Priority (NEXT)
- [ ] **NEWS Lane Integration (Phase 2)** - Update NEWS lane to read from MongoDB signals with ConvictionEnhancer
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`

### P2 - Future
- [ ] Reactivate CryptoPanic with premium API key
- [ ] Production deployment optimization

---

## Test Reports
- `/app/test_reports/iteration_40.json` - Markets-First Phase 1 (20 tests passed)
- `/app/test_reports/iteration_41.json` - HFT Engine V2 (37 tests passed)
- `/app/test_reports/iteration_42.json` - HFT Engine V2 ENHANCED (64 tests passed)

---

## User Notes
- Use platform's "Save to Github" feature to persist codebase
- All API keys stored in `/app/backend/.env`
- HFT Engine V2 ENHANCED is now the **sole HFT implementation**
- Legacy `_run_hft_loop()` is **DEPRECATED and DISABLED**
- Markets-First system runs in PARALLEL to existing system (zero breaking changes)
