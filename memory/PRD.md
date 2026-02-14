# APEX TRADER - Product Requirements Document

## Original Problem Statement
Build a sophisticated 5-lane trading bot (HFT, ALPHA, GAMMA, SPORTS, NEWS) with a centralized "Single Source of Truth" (SSOT) Risk Management layer for prediction market trading.

## Current Session Focus
- **Markets-First Architecture Implementation (Phase 1 - COMPLETED Feb 2026)**
- Sports Arbitrage exit logic fix (COMPLETED)
- News Lane (Lane 5) expansion with multi-source ingestion (COMPLETED)
- Cortex Audit to understand existing LLM/sentiment fusion (COMPLETED)
- 5-Lane Performance Dashboard UI Enhancement (COMPLETED - Feb 2026)

---

## Architecture Overview

### 5 Trading Lanes
1. **HFT Lane** - High-frequency trading with real-time orderbook analysis
2. **ALPHA Lane** - Alpha signal generation with Bayesian inference
3. **GAMMA Lane** - Volatility-based trading strategies
4. **SPORTS Lane** - Sports arbitrage using real odds APIs
5. **NEWS Lane** - News-driven trading with multi-source ingestion

### Markets-First Architecture (NEW - Feb 2026)
```
┌────────────────────────────────────────────────────────────────┐
│ LAYER 1: MARKET DATA FOUNDATION (WebSocket-Primary)           │
├────────────────────────────────────────────────────────────────┤
│ PolymarketScanner (NEW)                                        │
│ ├─ PRIMARY: WebSocket (realtime_market_service)               │
│ ├─ FALLBACK: Gamma REST API                                   │
│ ├─ Quality Scoring: Detect stale WS data                      │
│ ├─ Generate embeddings (semantic search)                      │
│ ├─ Cache in MongoDB (persistent): polymarket_cache            │
│ └─ Track 400-900 markets continuously                         │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│ LAYER 2: NEWS PROCESSING (Dual-Path, MongoDB Signals)         │
├────────────────────────────────────────────────────────────────┤
│ DualPathNewsInjector (NEW)                                     │
│ ├─ PATH A: Semantic search (5-10 markets) → LLM analysis      │
│ │  └─ Creates signals in MongoDB: db.signals collection       │
│ ├─ PATH B: Broadcast ALL 400-900 markets → opportunities      │
│ │  └─ Creates records in MongoDB: db.hft_opportunities        │
│ └─ Both paths parallel execution (non-blocking)               │
└────────────────────────────────────────────────────────────────┘
```

### Cortex (Brain) Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA INGESTION (NEWS)                       │
│  Apify Twitter ──┐                                               │
│  Exa.ai        ──┼── WebhookNews ── NewsInjector.process_news() │
│  Whale Alerts  ──┘                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                PATH A: NEWS → LLM → BAYES → CACHE               │
│  services/llm_service.py (EmergentLLMService)                   │
│       ↓ analyze_news_for_market() → LLMAnalysisResult            │
│  bayesian_math/event_bayes.py (EventBayesianUpdater)            │
│       ↓ update() → EventPosterior                                │
│  Signal Cache (AsyncSignalCache)                                 │
│       ↓ HFT reads from cache                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              PATH B: MARKET → FUSION → TRADE DECISION           │
│  ml/signal_fusion.py (SignalFusionEngine)                       │
│       Uses: ml/sentiment_analyzer.py (GPT-5.2 + Gemini fusion)  │
│       Uses: ml/enhanced_sentiment.py (EnhancedSentimentAnalyzer)│
│       Uses: ml/sentiment_llm.py (SmartLLMSentimentAnalyzer)     │
│       Output: generate_trading_signal() → WAIT/BUY/SELL         │
└─────────────────────────────────────────────────────────────────┘
```

---

## What's Been Implemented

### Session: February 2026

#### COMPLETED ✅
1. **Markets-First Architecture Phase 1**
   - Created `/app/backend/services/polymarket_scanner.py` - Continuous market scanning
   - Created `/app/backend/services/news_injector_dual_path.py` - Dual-path news processing
   - MongoDB collections: `polymarket_cache`, `signals`, `hft_opportunities`
   - TTL indexes for automatic signal expiration
   - WebSocket quality scoring for stale data detection
   - Semantic search with TF-IDF embeddings for market matching
   - Adaptive TTL based on market regime (Quiet/Normal/Volatile/Crisis)

2. **New API Endpoints**
   - `GET /api/health/scanner` - Scanner health status
   - `POST /api/webhooks/news` - News event webhook
   - `GET /api/markets-first/status` - Full system status
   - `GET /api/markets-first/signals` - Active PATH A signals
   - `GET /api/markets-first/opportunities` - PATH B HFT opportunities
   - `GET /api/markets-first/cached-markets` - In-memory cached markets

### Session: December 2025

#### COMPLETED ✅
1. **Sports Arbitrage Exit Logic Fix**
2. **Exa.ai Integration**
3. **Webhook Sources Integration**
4. **Live Fire Test**
5. **Cortex Audit**
6. **5-Lane Performance Dashboard Enhancement**

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/app/backend/services/polymarket_scanner.py` | **NEW** Markets-First scanner with WebSocket + REST fallback |
| `/app/backend/services/news_injector_dual_path.py` | **NEW** Dual-path news processing (PATH A + PATH B) |
| `/app/backend/services/llm_service.py` | Event Resolution Adjudicator (GPT-4o-mini) |
| `/app/backend/services/news_injector.py` | News processing orchestrator (original) |
| `/app/backend/services/webhook_sources.py` | Multi-source webhook manager |
| `/app/backend/bayesian_math/event_bayes.py` | Bayesian updater for news signals |
| `/app/backend/ml/signal_fusion.py` | Signal fusion engine |
| `/app/backend/paper_trading/paper_trader.py` | Paper trading with 5-lane support |
| `/app/backend/risk_config.py` | Risk configuration |

---

## API Endpoints

### Markets-First Endpoints (NEW)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health/scanner` | GET | Check PolymarketScanner health |
| `/api/webhooks/news` | POST | Receive news events for dual-path processing |
| `/api/markets-first/status` | GET | Full system status (scanner + injector + MongoDB) |
| `/api/markets-first/signals` | GET | Get active PATH A signals |
| `/api/markets-first/opportunities` | GET | Get PATH B HFT opportunities |
| `/api/markets-first/cached-markets` | GET | Get in-memory cached markets |

### Existing Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/hooks/news-alert` | POST | Central webhook receiver |
| `/api/hooks/webhook-sources/start` | POST | Start all polling loops |
| `/api/hooks/webhook-sources/stop` | POST | Stop all polling loops |
| `/api/hooks/webhook-sources/status` | GET | Get status of all sources |

---

## MongoDB Collections (Markets-First)

### polymarket_cache
- `market_id` (unique index)
- `question`, `category`, `price`, `liquidity`, `volume_24h`
- `embedding` (vector for semantic search)
- `_data_quality` (freshness scoring)
- `cached_at`

### signals
- `market_id`, `type: "path_a"`
- `bayes_factor`, `direction`, `confidence`, `sentiment`, `impact_level`
- `news_headline`, `news_source`
- `expires_at` (TTL index - auto-delete)
- `market_regime`, `adaptive_ttl`

### hft_opportunities
- `market_id`, `type: "path_b"`
- `market_*` (full market context)
- `news_headline`, `news_source`, `news_urgency`
- `expires_at` (10s TTL for fast trades)
- `requires_fast_execution`

---

## Prioritized Backlog

### P0 - Critical (COMPLETED)
- [x] Markets-First Architecture Phase 1
- [x] 5-Lane Performance Dashboard Enhancement
- [x] Sports Arbitrage Exit Logic Fix
- [x] Capital Accounting Bug Fixes

### P1 - High Priority
- [ ] **Phase 2: NEWS Lane Integration** - Update NEWS lane to read from MongoDB signals
- [ ] **Phase 3: HFT V2 Integration** - Connect HFT engine to PATH A signals
- [ ] SSOT Refactoring: Move `EXIT_STRATEGY_CONFIG` to `risk_config.json`

### P2 - Future
- [ ] Reactivate CryptoPanic with premium API key
- [ ] Production deployment optimization
- [ ] Advanced embedding models (sentence-transformers)

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

## Known Issues / Paused Features

1. **CryptoPanic API** - Intentionally PAUSED via `CRYPTOPANIC_ENABLED=false` in `.env` due to 24h delay on free tier.
2. **WebSocket Returns 0 Markets** - Expected during initial startup; falls back to REST API automatically.

---

## User Notes
- Use platform's "Save to Github" feature to persist codebase
- All API keys stored in `/app/backend/.env`
- Markets-First system runs in PARALLEL to existing 5-lane system (zero breaking changes)
