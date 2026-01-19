# APEX TRADER - System Architecture & Flow Charts

## 1. HIGH-LEVEL SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              APEX TRADER SYSTEM ARCHITECTURE                             │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────────┐
                                    │     USER        │
                                    │   (Browser)     │
                                    └────────┬────────┘
                                             │
                                             │ HTTP/WebSocket
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    FRONTEND (React)                                      │
│                                    Port: 3000                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   Dashboard  │  │    Paper     │  │   Config     │  │   Markets    │               │
│  │    Page      │  │   Trading    │  │    Page      │  │    Page      │               │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                                         │
│  Components:                                                                            │
│  • Position Cards with Sizing Breakdown                                                │
│  • Probability Model Diagnostics Panel                                                 │
│  • Sizing Analytics Dashboard                                                          │
│  • Historical Performance Charts                                                       │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ REST API (/api/*)
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   BACKEND (FastAPI)                                      │
│                                    Port: 8001                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              API LAYER (server.py)                               │   │
│  ├─────────────────────────────────────────────────────────────────────────────────┤   │
│  │  /api/paper/*      Paper trading endpoints                                      │   │
│  │  /api/markets      Market data endpoints                                        │   │
│  │  /api/config       Configuration endpoints                                      │   │
│  │  /api/sentiment/*  Sentiment analysis endpoints                                 │   │
│  │  /api/analytics    Analytics & reporting                                        │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│                    ┌─────────────────────┼─────────────────────┐                       │
│                    │                     │                     │                       │
│                    ▼                     ▼                     ▼                       │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐            │
│  │   PAPER TRADING     │  │   ML/AI ENGINES     │  │   DATA SERVICES     │            │
│  │      ENGINE         │  │                     │  │                     │            │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤            │
│  │ • Position Manager  │  │ • RL Engine (DQN)   │  │ • Market Data Svc   │            │
│  │ • Signal Processor  │  │ • Sentiment Fusion  │  │ • Historical Data   │            │
│  │ • Risk Manager      │  │ • Position Sizer    │  │ • Price Tracker     │            │
│  │ • P&L Tracker       │  │ • Volatility Pred   │  │                     │            │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘            │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    ▼                        ▼                        ▼
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│       MONGODB           │  │    EXTERNAL APIs        │  │    AI/ML SERVICES       │
│                         │  │                         │  │                         │
├─────────────────────────┤  ├─────────────────────────┤  ├─────────────────────────┤
│ Collections:            │  │ • Polymarket Gamma API  │  │ • OpenAI GPT-4o-mini    │
│ • markets               │  │ • Polymarket CLOB API   │  │   (via Emergent)        │
│ • paper_trades          │  │ • GitHub API            │  │                         │
│ • paper_positions       │  │ • Finnhub API (disabled)│  │ • TensorFlow (RL)       │
│ • analytics_history     │  │                         │  │ • PyTorch (Models)      │
│ • rl_training_data      │  │                         │  │                         │
└─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘
```

---

## 2. COMPLETE DATA FLOW - MARKET TO TRADE

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE TRADING DATA FLOW                                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

 EXTERNAL DATA SOURCES                    PROCESSING LAYERS                    OUTPUT
 ═══════════════════                     ══════════════════                   ════════

┌─────────────────┐
│  POLYMARKET     │
│  Gamma API      │─────┐
│  • Markets list │     │
│  • Prices       │     │
│  • Volume       │     │
│  • Liquidity    │     │
└─────────────────┘     │
                        │     ┌─────────────────────────────────────┐
┌─────────────────┐     │     │                                     │
│  POLYMARKET     │     ├────▶│     MARKET DATA SERVICE             │
│  CLOB API       │─────┤     │     (market_data_service.py)        │
│  • Order Book   │     │     │                                     │
│  • Trades*      │     │     │  • Normalize data formats           │
│  • Spreads      │     │     │  • Calculate derived metrics        │
└─────────────────┘     │     │  • Cache recent data                │
                        │     │                                     │
┌─────────────────┐     │     └──────────────┬──────────────────────┘
│  PRICE HISTORY  │─────┘                    │
│  (Cached)       │                          │
└─────────────────┘                          │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │      SIGNAL GATHERING               │
                              │      (_get_signals)                 │
                              │                                     │
                              │  For each market:                   │
                              │  1. Fetch order book                │
                              │  2. Call sentiment sources          │
                              │  3. Get RL prediction               │
                              │  4. Calculate volatility            │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
          ┌──────────────────────────────────┼──────────────────────────────────┐
          │                                  │                                  │
          ▼                                  ▼                                  ▼
┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐
│  SENTIMENT FUSION   │        │    RL ENGINE        │        │  VOLATILITY PRED    │
│                     │        │    (DQN Model)      │        │                     │
│  5 Sources:         │        │                     │        │  • Historical vol   │
│  • Market Micro     │        │  Input: State       │        │  • Implied vol      │
│  • Polymarket       │        │  • Price            │        │  • Time decay       │
│  • LLM (GPT)        │        │  • Sentiment        │        │                     │
│  • Correlation      │        │  • Volatility       │        │  Output:            │
│  • GitHub           │        │  • Position         │        │  volatility (0-1)   │
│                     │        │                     │        │                     │
│  Output:            │        │  Output:            │        └──────────┬──────────┘
│  sentiment (0-1)    │        │  action + conf      │                   │
│  confidence (0-1)   │        │  BUY/SELL/HOLD      │                   │
└──────────┬──────────┘        └──────────┬──────────┘                   │
           │                              │                              │
           └──────────────────────────────┼──────────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │    MODEL PROBABILITY CALCULATOR     │
                              │    (_calculate_model_probability)   │
                              │                                     │
                              │  P_final = w₁×P_market              │
                              │          + w₂×P_sentiment           │
                              │          + w₃×P_rl                  │
                              │                                     │
                              │  Output: P_final (0.01-0.99)        │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │       POSITION SIZER                │
                              │       (polymarket_position_sizer)   │
                              │                                     │
                              │  1. Calculate Edge                  │
                              │     edge = P_final - eff_price      │
                              │                                     │
                              │  2. Binary Kelly Criterion          │
                              │     kelly = edge / (1 - P_final)    │
                              │                                     │
                              │  3. Apply Multipliers               │
                              │     • Utilization brake             │
                              │     • Time penalty                  │
                              │     • Oracle risk                   │
                              │     • Correlation dampener          │
                              │                                     │
                              │  4. Apply Caps                      │
                              │     • Max position                  │
                              │     • Sector limit                  │
                              │     • Liquidity limit               │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │       TRADE DECISION                │
                              │                                     │
                              │  IF edge > threshold (2%)           │
                              │  AND position_size > minimum        │
                              │  AND risk_checks_pass               │
                              │                                     │
                              │  THEN → EXECUTE TRADE               │
                              │  ELSE → REJECT (log reason)         │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │       PAPER POSITION                │
                              │                                     │
                              │  Store in memory + MongoDB:         │
                              │  • position_id                      │
                              │  • market_id                        │
                              │  • side (YES/NO)                    │
                              │  • entry_price                      │
                              │  • size                             │
                              │  • signals (full breakdown)         │
                              │  • sizing_breakdown                 │
                              │                                     │
                              └─────────────────────────────────────┘
```

---

## 3. SENTIMENT ANALYSIS FLOW CHART

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           SENTIMENT ANALYSIS FLOW CHART                                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────────┐
                                    │  MARKET DATA    │
                                    │  {              │
                                    │   question,     │
                                    │   category,     │
                                    │   yes_price,    │
                                    │   volume,       │
                                    │   token_id      │
                                    │  }              │
                                    └────────┬────────┘
                                             │
                                             ▼
                    ┌────────────────────────────────────────────┐
                    │         FETCH ADDITIONAL DATA              │
                    │                                            │
                    │  ┌──────────────┐    ┌──────────────┐     │
                    │  │ Order Book   │    │ Price Hist   │     │
                    │  │ (CLOB API)   │    │ (Cached)     │     │
                    │  └──────┬───────┘    └──────┬───────┘     │
                    │         │                   │              │
                    └─────────┼───────────────────┼──────────────┘
                              │                   │
                              ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│                              PARALLEL SENTIMENT SOURCES                                 │
│                                                                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐            │
│  │                     │  │                     │  │                     │            │
│  │  SOURCE 1           │  │  SOURCE 2           │  │  SOURCE 3           │            │
│  │  Market Micro       │  │  Polymarket Native  │  │  LLM (GPT-4o-mini)  │            │
│  │                     │  │                     │  │                     │            │
│  │  Input:             │  │  Input:             │  │  Input:             │            │
│  │  • yes_price        │  │  • order_book       │  │  • question         │            │
│  │  • volume_24h       │  │  • price_history    │  │  • category         │            │
│  │  • liquidity        │  │                     │  │  • current_price    │            │
│  │                     │  │  Signals:           │  │                     │            │
│  │  Components:        │  │  • order_flow       │  │  Process:           │            │
│  │  • price_sent       │  │  • spread_conf      │  │  1. Check cache     │            │
│  │  • momentum         │  │  • whale_signal     │  │  2. Rate limit      │            │
│  │  • volume_int       │  │  • vol_momentum     │  │  3. Call GPT        │            │
│  │  • liquidity        │  │  • price_velocity   │  │  4. Parse response  │            │
│  │  • whale_activity   │  │  • price_momentum   │  │                     │            │
│  │                     │  │                     │  │  Output:            │            │
│  │  Output:            │  │  Output:            │  │  sentiment (0-1)    │            │
│  │  sentiment: 0.44    │  │  sentiment: 0.52    │  │  confidence (0-1)   │            │
│  │  weight: 25%        │  │  confidence: 0.50   │  │                     │            │
│  │                     │  │                     │  │                     │            │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘            │
│                                                                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐            │
│  │                     │  │                     │  │                     │            │
│  │  SOURCE 4           │  │  SOURCE 5           │  │  SOURCE 6           │            │
│  │  Correlation        │  │  GitHub             │  │  Finnhub            │            │
│  │                     │  │  (Crypto Only)      │  │  (DISABLED)         │            │
│  │  Input:             │  │                     │  │                     │            │
│  │  • category         │  │  Activated if:      │  │  Would provide:     │            │
│  │  • question         │  │  question contains  │  │  • News sentiment   │            │
│  │  • related_markets  │  │  crypto keywords    │  │  • Social buzz      │            │
│  │                     │  │                     │  │                     │            │
│  │  Process:           │  │  Analyzes:          │  │  Status:            │            │
│  │  1. Find related    │  │  • Commits          │  │  Needs API key      │            │
│  │  2. Calc momentum   │  │  • Releases         │  │                     │            │
│  │  3. Group signals   │  │  • Issues           │  │  Output:            │            │
│  │                     │  │  • Stars/Forks      │  │  weight: 0%         │            │
│  │  Output:            │  │                     │  │                     │            │
│  │  sentiment: 0.55    │  │  Output:            │  │                     │            │
│  │  strength: 0.30     │  │  sentiment: 0.62    │  │                     │            │
│  │                     │  │  confidence: 0.80   │  │                     │            │
│  │                     │  │  (0 if non-crypto)  │  │                     │            │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘            │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             │ All sources complete
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│                              WEIGHTED FUSION ENGINE                                     │
│                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│  │                                                                                   │ │
│  │   actual_weight = confidence × max_weight                                         │ │
│  │                                                                                   │ │
│  │   ┌────────────────┬───────────┬────────────┬──────────┬──────────┬───────────┐  │ │
│  │   │ Source         │ Sentiment │ Confidence │ Max Wt   │ Actual   │ Contrib   │  │ │
│  │   ├────────────────┼───────────┼────────────┼──────────┼──────────┼───────────┤  │ │
│  │   │ Market Micro   │   0.44    │    1.00    │   25%    │  25.0%   │  0.110    │  │ │
│  │   │ Polymarket     │   0.52    │    0.50    │   25%    │  12.5%   │  0.065    │  │ │
│  │   │ LLM            │   0.40    │    0.35    │   25%    │   8.7%   │  0.035    │  │ │
│  │   │ Correlation    │   0.55    │    0.30    │   10%    │   3.0%   │  0.017    │  │ │
│  │   │ GitHub         │   0.62    │    0.80    │   15%    │  12.0%   │  0.074    │  │ │
│  │   │ Finnhub        │    -      │    0.00    │   10%    │   0.0%   │  0.000    │  │ │
│  │   ├────────────────┴───────────┴────────────┼──────────┼──────────┼───────────┤  │ │
│  │   │ TOTAL                                   │  100%    │  61.2%   │  0.301    │  │ │
│  │   └─────────────────────────────────────────┴──────────┴──────────┴───────────┘  │ │
│  │                                                                                   │ │
│  │   final_sentiment = 0.301 / 0.612 = 0.491                                        │ │
│  │                                                                                   │ │
│  └───────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │     OUTPUT: SIGNALS OBJECT          │
                              │                                     │
                              │  {                                  │
                              │    sentiment: 0.491,                │
                              │    sentiment_strength: 0.18,        │
                              │    sentiment_layers: {...},         │
                              │    sentiment_weights: {...},        │
                              │    polymarket_signals: {...},       │
                              │    polymarket_momentum: {...}       │
                              │  }                                  │
                              │                                     │
                              └─────────────────────────────────────┘
```

---

## 4. PROBABILITY MODEL FLOW

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           PROBABILITY MODEL (P_FINAL) FLOW                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│                     │   │                     │   │                     │
│     P_MARKET        │   │    P_SENTIMENT      │   │       P_RL          │
│                     │   │                     │   │                     │
│  = yes_price        │   │  = final_sentiment  │   │  = market ± deviation│
│  = 0.35             │   │  = 0.491            │   │                     │
│                     │   │                     │   │  Based on:          │
│  (What market       │   │  (What our          │   │  • RL action        │
│   thinks)           │   │   analysis says)    │   │  • RL confidence    │
│                     │   │                     │   │                     │
│                     │   │                     │   │  If BUY: higher     │
│                     │   │                     │   │  If SELL: lower     │
│                     │   │                     │   │  = 0.42             │
│                     │   │                     │   │                     │
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
           │                         │                         │
           │      ┌──────────────────┼──────────────────┐      │
           │      │                  │                  │      │
           │      │   WEIGHT ADJUSTMENT                │      │
           │      │                                    │      │
           │      │   Check signal agreement:          │      │
           │      │                                    │      │
           │      │   IF sentiment agrees with RL:    │      │
           │      │      w_market = 40%               │      │
           │      │      w_sentiment = 30%            │      │
           │      │      w_rl = 30%                   │      │
           │      │                                    │      │
           │      │   ELSE (signals conflict):        │      │
           │      │      w_market = 55%               │      │
           │      │      w_sentiment = 22%            │      │
           │      │      w_rl = 23%                   │      │
           │      │                                    │      │
           │      └──────────────────┬─────────────────┘      │
           │                         │                         │
           ▼                         ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                         WEIGHTED ENSEMBLE                                   │
│                                                                             │
│   P_final = w_market × P_market + w_sentiment × P_sentiment + w_rl × P_rl  │
│                                                                             │
│   Example (signals agree):                                                  │
│   P_final = 0.40 × 0.35 + 0.30 × 0.491 + 0.30 × 0.42                       │
│           = 0.140 + 0.147 + 0.126                                          │
│           = 0.413                                                           │
│                                                                             │
│   Example (signals conflict):                                               │
│   P_final = 0.55 × 0.35 + 0.22 × 0.491 + 0.23 × 0.42                       │
│           = 0.193 + 0.108 + 0.097                                          │
│           = 0.398                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │           CLAMP OUTPUT              │
                              │                                     │
                              │   P_final = clamp(P_final, 0.01, 0.99)
                              │                                     │
                              │   Prevents impossible probabilities │
                              │   (never 0% or 100%)                │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │         EDGE CALCULATION            │
                              │                                     │
                              │   effective_price = ask + fees      │
                              │                   = 0.35 + 0.007    │
                              │                   = 0.357           │
                              │                                     │
                              │   edge = P_final - effective_price  │
                              │        = 0.413 - 0.357              │
                              │        = 0.056 (5.6%)               │
                              │                                     │
                              │   IF edge > 0.02 (2%):              │
                              │      → Positive edge, consider trade│
                              │   ELSE:                             │
                              │      → No edge, skip                │
                              │                                     │
                              └─────────────────────────────────────┘
```

---

## 5. POSITION SIZING WATERFALL

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           POSITION SIZING WATERFALL                                      │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────────────────────────┐
                              │                                     │
                              │      STEP 1: KELLY CRITERION        │
                              │                                     │
                              │   kelly_fraction = edge / (1 - P)   │
                              │                  = 0.056 / 0.587    │
                              │                  = 0.095 (9.5%)     │
                              │                                     │
                              │   kelly_base = equity × kelly × 0.25│
                              │             = $10,000 × 0.095 × 0.25│
                              │             = $237.50               │
                              │                                     │
                              └──────────────┬──────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│                              STEP 2: APPLY MULTIPLIERS                                  │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                 │   │
│  │   MULTIPLIER 1: UTILIZATION BRAKE                                              │   │
│  │   ─────────────────────────────────                                            │   │
│  │   current_deployed = $2,500                                                    │   │
│  │   utilization = $2,500 / $10,000 = 25%                                        │   │
│  │   brake = 1 / (1 + utilization) = 1 / 1.25 = 0.80                             │   │
│  │                                                                                 │   │
│  │   Purpose: Reduce size as portfolio fills up                                   │   │
│  │   ───────────────────────────────────────────                                  │   │
│  │                                                                                 │   │
│  │   kelly_base × 0.80 = $237.50 × 0.80 = $190.00                                │   │
│  │                                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                           │
│                                             ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                 │   │
│  │   MULTIPLIER 2: TIME/DURATION PENALTY                                          │   │
│  │   ────────────────────────────────────                                         │   │
│  │   days_to_expiry = 45 days                                                     │   │
│  │   time_mult = 1 - (1 / (1 + days/30))                                         │   │
│  │             = 1 - (1 / 2.5) = 0.60                                            │   │
│  │                                                                                 │   │
│  │   Purpose: Prefer shorter-term markets                                         │   │
│  │   ─────────────────────────────────────                                        │   │
│  │                                                                                 │   │
│  │   $190.00 × 0.60 = $114.00                                                    │   │
│  │                                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                           │
│                                             ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                 │   │
│  │   MULTIPLIER 3: ORACLE RISK                                                    │   │
│  │   ─────────────────────────────                                                │   │
│  │   category = "crypto"                                                          │   │
│  │   oracle_mult = 0.90 (crypto has some subjectivity)                           │   │
│  │                                                                                 │   │
│  │   Oracle Risk Multipliers:                                                     │   │
│  │   • Sports: 1.00 (objective)                                                   │   │
│  │   • Crypto price: 0.90                                                         │   │
│  │   • Politics: 0.75                                                             │   │
│  │   • Subjective: 0.60                                                           │   │
│  │   • Highly ambiguous: 0.40                                                     │   │
│  │                                                                                 │   │
│  │   $114.00 × 0.90 = $102.60                                                    │   │
│  │                                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                           │
│                                             ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                 │   │
│  │   MULTIPLIER 4: CORRELATION DAMPENER                                           │   │
│  │   ───────────────────────────────────                                          │   │
│  │   overlapping_positions = 2 (other crypto positions)                           │   │
│  │   corr_mult = 1 / (1 + N) = 1 / 3 = 0.33                                      │   │
│  │                                                                                 │   │
│  │   Purpose: Reduce concentration in correlated markets                          │   │
│  │   ────────────────────────────────────────────────────                         │   │
│  │                                                                                 │   │
│  │   $102.60 × 0.33 = $33.86                                                     │   │
│  │                                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                         │
│                              STEP 3: APPLY CAPS                                         │
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                                                                                 │  │
│   │   CAP 1: MAX POSITION (10% of equity)                                          │  │
│   │   max_position = $10,000 × 0.10 = $1,000                                       │  │
│   │   $33.86 < $1,000 ✓                                                            │  │
│   │                                                                                 │  │
│   │   CAP 2: SECTOR LIMIT (25% of equity per sector)                               │  │
│   │   crypto_deployed = $1,500                                                     │  │
│   │   sector_limit = $2,500 - $1,500 = $1,000 remaining                           │  │
│   │   $33.86 < $1,000 ✓                                                            │  │
│   │                                                                                 │  │
│   │   CAP 3: LIQUIDITY LIMIT (5% of market liquidity)                              │  │
│   │   liquidity = $250,000                                                         │  │
│   │   liq_limit = $250,000 × 0.05 = $12,500                                       │  │
│   │   $33.86 < $12,500 ✓                                                           │  │
│   │                                                                                 │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────────────┐
                              │                                     │
                              │      FINAL POSITION SIZE            │
                              │                                     │
                              │      $33.86                         │
                              │                                     │
                              │      (86% reduction from Kelly base │
                              │       due to multipliers)           │
                              │                                     │
                              └─────────────────────────────────────┘
```

---

## 6. FILE STRUCTURE & DEPENDENCIES

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              FILE STRUCTURE & DEPENDENCIES                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

/app/
├── backend/
│   │
│   ├── server.py                          ◄── Main FastAPI application
│   │   └── imports: paper_trader, ml/*, data/*, services/*
│   │
│   ├── paper_trading/
│   │   └── paper_trader.py                ◄── Trading engine (3200+ lines)
│   │       ├── _get_signals()             ◄── Signal gathering & sentiment fusion
│   │       ├── _calculate_model_probability() ◄── P_final calculation
│   │       ├── _evaluate_entry_opportunity()  ◄── Trade decision
│   │       └── _execute_paper_entry()     ◄── Position creation
│   │
│   ├── ml/
│   │   ├── enhanced_sentiment.py          ◄── Sentiment orchestrator
│   │   │   ├── analyze()                  ◄── Main entry point
│   │   │   ├── _get_llm_sentiment()       ◄── GPT-4o-mini integration
│   │   │   └── CrossMarketCorrelation     ◄── Related markets
│   │   │
│   │   ├── polymarket_sentiment.py        ◄── Polymarket native signals
│   │   │   ├── analyze_market()           ◄── Main entry point
│   │   │   ├── _calculate_order_flow()    ◄── Bid/ask imbalance
│   │   │   ├── _calculate_spread_confidence()
│   │   │   ├── _calculate_whale_signal()
│   │   │   ├── _calculate_volume_momentum()
│   │   │   ├── _calculate_price_velocity()
│   │   │   └── _calculate_price_momentum()
│   │   │
│   │   ├── github_sentiment.py            ◄── GitHub analysis (crypto only)
│   │   │   ├── analyze_market()           ◄── Main entry point
│   │   │   ├── _find_repos_for_market()   ◄── Keyword → repo mapping
│   │   │   └── _analyze_repo()            ◄── Fetch & analyze repo data
│   │   │
│   │   ├── polymarket_position_sizer.py   ◄── Kelly + multipliers
│   │   │   └── calculate_position_size()
│   │   │
│   │   ├── rl_engine.py                   ◄── DQN reinforcement learning
│   │   │   ├── get_action()               ◄── BUY/SELL/HOLD decision
│   │   │   └── train_step()               ◄── Learning from outcomes
│   │   │
│   │   ├── social_sentiment.py            ◄── Finnhub (DISABLED)
│   │   │
│   │   └── volatility_predictor.py        ◄── Volatility estimation
│   │
│   ├── data/
│   │   ├── polymarket_api.py              ◄── Gamma & CLOB API client
│   │   │   ├── get_markets()
│   │   │   ├── get_order_book()
│   │   │   └── get_trades()
│   │   │
│   │   └── polymarket_websocket.py        ◄── Real-time WebSocket (optional)
│   │
│   ├── services/
│   │   └── market_data_service.py         ◄── Data normalization & caching
│   │
│   └── tests/
│       └── test_position_sizer.py         ◄── 37 unit tests
│
├── frontend/
│   └── src/
│       └── pages/
│           ├── PaperTrading.js            ◄── Main trading UI
│           │   ├── SizingBreakdownModal   ◄── Probability diagnostics
│           │   └── PositionCard           ◄── Position display
│           │
│           └── Configuration.js           ◄── Settings UI
│
└── docs/
    ├── TRADING_FRAMEWORK.md               ◄── Trading logic docs
    ├── SENTIMENT_ANALYSIS_FRAMEWORK.md    ◄── Sentiment docs
    └── SYSTEM_ARCHITECTURE.md             ◄── This file
```

---

## 7. API ENDPOINTS REFERENCE

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              API ENDPOINTS                                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

PAPER TRADING
─────────────
POST /api/paper/start          Start paper trading session
POST /api/paper/stop           Stop session, calculate P&L
GET  /api/paper/status         Current session status
GET  /api/paper/positions      List open positions with signals

SENTIMENT
─────────
GET  /api/sentiment/enhanced/{market_id}    Full sentiment analysis
GET  /api/sentiment/momentum/{market_id}    Sentiment momentum (1h/6h/24h)
GET  /api/sentiment/github/{market_id}      GitHub analysis (crypto only)

MARKETS
───────
GET  /api/markets              List active markets
GET  /api/markets/{id}         Single market details

CONFIGURATION
─────────────
GET  /api/config               Current configuration
POST /api/config               Update configuration

ANALYTICS
─────────
GET  /api/paper/analytics/history    Historical session data
GET  /api/analytics                  Real-time analytics
```

---

*Document Version: 2.0*
*Generated: January 2026*
*File: /app/docs/SYSTEM_ARCHITECTURE.md*
