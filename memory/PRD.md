# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build a sophisticated 5-lane trading bot (HFT, ALPHA, GAMMA, SPORTS, NEWS) with a centralized "Single Source of Truth" (SSOT) Risk Management layer for prediction market trading.

## Current Session Focus
- **NEWS Lane Phase 2 Implementation (COMPLETED Feb 2026)** - MongoDB-integrated NEWS Sniper
- **HFT Engine V2 ENHANCED Implementation (COMPLETED Feb 2026)** - Merged all legacy features
- **Markets-First Architecture Phase 1 (COMPLETED Feb 2026)**

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

3. **Markets-First Architecture Phase 1**
   - PolymarketScanner (500+ markets cached)
   - DualPathNewsInjector (PATH A + PATH B)
   - MongoDB collections with TTL indexes

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/app/backend/lanes/news_lane/news_sniper_mongodb.py` | **NEWS Sniper MongoDB** - Phase 2 trade execution |
| `/app/backend/trading/hft_engine_v2.py` | **HFT Engine V2 ENHANCED** - Sole HFT implementation |
| `/app/backend/services/polymarket_scanner.py` | **PolymarketScanner** - Market caching |
| `/app/backend/services/news_injector_dual_path.py` | **DualPathNewsInjector** - PATH A/B signal creation |
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

---

## Prioritized Backlog

### P0 - Critical (ALL COMPLETED ✅)
- [x] Markets-First Architecture Phase 1
- [x] HFT Engine V2 ENHANCED (merged legacy)
- [x] NEWS Lane Phase 2 (MongoDB integration)
- [x] Legacy HFT loop deprecation
- [x] **HFT V2 Strategy-Specific Direction Refactor (Feb 15, 2026)** - Each of 5 strategies now determines its own direction

### P1 - High Priority (NEXT)
- [ ] Deprecate old news pipeline (news_injector.py, signal_cache.py)
- [ ] Integrate Alpha/Gamma Lanes with Markets-First signals
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`
- [ ] Live trading validation

### P2 - Future
- [ ] Reactivate CryptoPanic with premium API key
- [ ] Production deployment optimization

---

## Test Reports
- `/app/test_reports/iteration_40.json` - Markets-First Phase 1 (20 tests passed)
- `/app/test_reports/iteration_41.json` - HFT Engine V2 (37 tests passed)
- `/app/test_reports/iteration_42.json` - HFT Engine V2 ENHANCED (64 tests passed)
- `/app/test_reports/iteration_43.json` - NEWS Sniper MongoDB Phase 2 (74 tests passed)

---

## User Notes
- Use platform's "Save to Github" feature to persist codebase
- All API keys stored in `/app/backend/.env`
- HFT Engine V2 ENHANCED is the **sole HFT implementation** (legacy disabled)
- NEWS Sniper MongoDB handles **trade execution** (legacy loop handles ingestion)
- Markets-First system provides unified signal pipeline for HFT and NEWS lanes
