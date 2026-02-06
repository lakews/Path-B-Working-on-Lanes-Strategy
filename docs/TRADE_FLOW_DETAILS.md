# 5-Lane Trade Flow Documentation

## Complete Trade Flow Architecture

This document details the **end-to-end trade flow** for each of the 5 trading lanes, including:
- Data sources used
- Analysis performed
- Signal generation
- Position sizing
- Risk checks
- Execution

---

## Chain of Command (All Lanes)

Every trade flows through this unified pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CHAIN OF COMMAND                                      │
│                                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐  │
│   │   STRATEGY   │ → │ POSITION     │ → │    RISK      │ → │  EXECUTION  │  │
│   │   ANALYSIS   │   │   SIZER      │   │   MANAGER    │   │             │  │
│   └──────────────┘    └──────────────┘    └──────────────┘    └─────────────┘  │
│                                                                                 │
│   Generates signal   Calculates raw     Validates against   Records trade,     │
│   with edge & conf   theoretical size   SSOT risk limits    updates position   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Lane 1: HFT (The Market Maker)

### Purpose
High-frequency, low-latency market making and spread capture. **Never blocks** for slow operations.

### Cycle Time
**0.5 seconds** (500ms)

### Data Sources

| Source | Type | Latency | Description |
|--------|------|---------|-------------|
| **WebSocket Orderbook** | Real-time | <100ms | Live bid/ask from Polymarket |
| **StrategyContext Cache** | Shared State | Instant | Alpha's pre-computed fair values |
| **REST Market Data** | Polling Fallback | 200-500ms | Used when WebSocket unavailable |

### Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HFT ANALYSIS PIPELINE                            │
│                                                                     │
│   1. FETCH ORDERBOOK                                                │
│      └─→ WebSocket: Best bid/ask, depth (5 levels)                 │
│                                                                     │
│   2. CHECK ALPHA CACHE                                              │
│      └─→ StrategyContext.get_target(market_id)                     │
│          ├─→ HIT: Use Alpha's fair_value for smart quoting         │
│          └─→ MISS: Pure scalp mode (microstructure only)           │
│                                                                     │
│   3. CALCULATE SPREAD                                               │
│      └─→ spread = best_ask - best_bid                              │
│      └─→ If spread > 12%: Skip (too wide for HFT)                  │
│                                                                     │
│   4. DETECT OPPORTUNITY                                             │
│      ├─→ SMART MODE: edge = fair_value - best_ask                  │
│      └─→ SCALP MODE: edge = spread * 0.5 (capture spread)          │
│                                                                     │
│   5. GENERATE SIGNAL                                                │
│      └─→ If edge > 1%: Signal = BUY_YES (or NO)                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Signal Sources (Priority Order)

1. **Alpha Target (from StrategyContext)**
   - Pre-computed Bayesian fair value
   - If available and not stale (<5 min): Use for smart quoting
   - Weight: 100% when available

2. **Microstructure Analysis**
   - Order Flow Imbalance (OFI)
   - Spread dynamics
   - Volume-weighted mid price
   - Used in "scalp mode" when no Alpha target

### Position Sizing

```python
# Fixed Unit Method (NO KELLY - too slow)
hft_size = min(
    capital * 0.02,        # 2% of capital
    $50,                   # Hard USD cap
    liquidity * 0.10       # 10% of available liquidity
)
```

### Execution

- **Strategy**: `hft_scalp`, `hft_maker`, `delta_neutral`
- **Order Type**: Limit (maker-first)
- **Side**: YES only (unless sports)

---

## Lane 2: ALPHA (The Strategist)

### Purpose
Slower, conviction-driven directional trading based on deep multi-source analysis.

### Cycle Time
**30 seconds**

### Data Sources

| Source | Type | Provider | Weight |
|--------|------|----------|--------|
| **LLM Sentiment** | Analysis | GPT-4o-mini (via Emergent) | 30% |
| **Bayesian Outlier Detection** | Model | Internal | 25% |
| **Volatility Predictor** | Model | Internal | 25% |
| **Sharp Money Detection** | Flow Analysis | Internal | 20% |
| **Cross-Market Correlation** | Pattern | Internal | Variable |
| **Order Flow Analysis** | Real-time | WebSocket | Supplementary |

### Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ALPHA ANALYSIS PIPELINE                                  │
│                                                                                 │
│   1. FETCH MARKET DATA                                                          │
│      └─→ REST API: Full market details, history, volume                        │
│                                                                                 │
│   2. RUN SIGNAL FUSION ENGINE                                                   │
│      │                                                                          │
│      ├─→ VOLATILITY PREDICTOR                                                  │
│      │   └─→ Input: Price history, time to expiry                             │
│      │   └─→ Output: Predicted 24h volatility (0-1)                           │
│      │                                                                          │
│      ├─→ LLM SENTIMENT ANALYZER (Hot/Cold Cache)                               │
│      │   └─→ Hot markets (high vol): 10 min TTL                               │
│      │   └─→ Cold markets: 60 min TTL                                         │
│      │   └─→ Output: Sentiment (-1 to +1), Confidence                         │
│      │                                                                          │
│      ├─→ BAYESIAN OUTLIER DETECTOR                                             │
│      │   └─→ Input: Market price vs historical distribution                   │
│      │   └─→ Output: is_mispriced, confidence, fair_value                     │
│      │                                                                          │
│      └─→ SHARP DETECTOR                                                        │
│          └─→ Input: Recent large trades, timing patterns                       │
│          └─→ Output: sharp_alignment (-1 to +1)                               │
│                                                                                 │
│   3. CALCULATE BAYESIAN POSTERIOR                                               │
│      └─→ P(YES) = weighted_fusion(sentiment, volatility, mispricing, sharp)   │
│                                                                                 │
│   4. GENERATE TRADING SIGNAL                                                    │
│      └─→ If |posterior - market_price| > min_edge:                            │
│          └─→ Signal = alpha_directional                                        │
│                                                                                 │
│   5. UPDATE STRATEGY CONTEXT                                                    │
│      └─→ Write fair_value to cache (for HFT to read)                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### LLM Analysis (Smart Cache)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      LLM SENTIMENT ANALYSIS                                │
│                                                                            │
│   Input:                                                                   │
│   ├─→ Market question: "Will Bitcoin exceed $100K by March 2026?"         │
│   ├─→ Current price: $0.45 (YES)                                          │
│   ├─→ Volume: $50,000 (24h)                                               │
│   └─→ Category: crypto                                                    │
│                                                                            │
│   LLM Prompt (GPT-4o-mini):                                               │
│   "Analyze the following prediction market..."                            │
│   "Return: sentiment_score (-1 to +1), confidence (0-1), reasoning"       │
│                                                                            │
│   Output:                                                                  │
│   ├─→ sentiment: 0.65 (bullish)                                           │
│   ├─→ confidence: 0.72                                                    │
│   └─→ reasoning: "Recent ETF approval momentum, institutional flow..."    │
│                                                                            │
│   Caching:                                                                 │
│   ├─→ Hot market (vol > $10K): Cache 10 minutes                           │
│   └─→ Cold market (vol < $10K): Cache 60 minutes                          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Position Sizing

```python
# Binary Kelly Criterion
raw_kelly = edge / (1 - model_probability)

# Fractional Kelly with bounds
adjusted_kelly = clamp(
    raw_kelly * 0.25,     # 25% Kelly
    0.10,                 # Min 10%
    0.50                  # Max 50%
)

# Apply utilization brake
brake = max(0, 1 - (utilization / 0.95) ^ 1.5)

# Final size
alpha_size = min(
    capital * adjusted_kelly * brake,
    $100,                 # Hard USD cap
    liquidity * 0.10      # 10% of liquidity
)
```

### Execution

- **Strategy**: `alpha_directional`, `arbitrage`
- **Order Type**: Maker-first with fallback to taker
- **Side**: YES or NO based on edge direction

---

## Lane 3: GAMMA (The Sniper)

### Purpose
Opportunistic convexity hunting in the **Whale Zone** (prices < $0.10). Targets mispriced out-of-the-money options.

### Cycle Time
**30 seconds**

### Data Sources

| Source | Type | Description |
|--------|------|-------------|
| **Orderbook Depth** | Real-time | Full 10-level depth analysis |
| **Volume Profile** | Historical | 24h volume patterns |
| **Bid/Ask Walls** | Microstructure | Large order detection |
| **Gap Analysis** | Microstructure | Thin side detection |

### Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        GAMMA ANALYSIS PIPELINE                                  │
│                                                                                 │
│   1. FILTER: WHALE ZONE ONLY                                                    │
│      └─→ price < $0.10 (configured in SSOT)                                    │
│      └─→ If price >= $0.10: Route to ALPHA instead                             │
│                                                                                 │
│   2. FETCH ORDERBOOK (Full Depth)                                               │
│      └─→ All bids and asks, not just top-of-book                               │
│                                                                                 │
│   3. GAP VS WALL DETECTION                                                      │
│      │                                                                          │
│      ├─→ GAP: Thin asks + Strong bids                                          │
│      │   └─→ Indicates upward pressure                                         │
│      │   └─→ Action: Place bid just below gap                                  │
│      │                                                                          │
│      └─→ WALL: Large order at specific price                                   │
│          └─→ Wall strength = volume / average_volume                           │
│          └─→ If wall > 3x average: Consider breakout play                      │
│                                                                                 │
│   4. GENERATE SIGNAL                                                            │
│      ├─→ GAP_OPPORTUNITY: Place limit bid inside gap                           │
│      ├─→ WALL_CRUMBLING: Snipe weak ask wall (taker)                          │
│      └─→ WALL_STRONG: Join bid queue (maker)                                   │
│                                                                                 │
│   5. SIZE AS "LOTTERY TICKET"                                                   │
│      └─→ Max $15 (1% of capital)                                               │
│      └─→ These are asymmetric bets: small loss, large potential gain           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Position Sizing

```python
# Fixed Unit (Lottery Ticket)
gamma_size = min(
    capital * 0.01,       # 1% max
    $15,                  # Hard cap
    liquidity * 0.10      # 10% of depth
)
```

### Execution

- **Strategy**: `gamma_scalp`
- **Order Type**: Limit (join bid) or Market (snipe wall)
- **Side**: YES only (convexity hunting)

---

## Lane 4: SPORTS (The Bookie)

### Purpose
Isolated lane for sports arbitrage using **real bookmaker odds** from external APIs.

### Cycle Time
**30 seconds**

### Data Sources

| Source | API | Weight | Description |
|--------|-----|--------|-------------|
| **The Odds API** | External | 85% | Devigged fair values from 15+ bookmakers |
| **Order Flow** | WebSocket | 15% | Polymarket-specific flow |
| **LLM/GitHub** | ❌ DISABLED | 0% | Cannot predict live scores |

### Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        SPORTS ANALYSIS PIPELINE                                 │
│                                                                                 │
│   1. DETECT SPORTS MARKET                                                       │
│      └─→ is_sports_market(question)                                            │
│          ├─→ Keywords: "game", "match", "win", team names                      │
│          ├─→ Category: sports                                                   │
│          └─→ Pattern: "[Team A] vs [Team B]"                                   │
│                                                                                 │
│   2. FETCH BOOKMAKER ODDS (The Odds API)                                        │
│      │                                                                          │
│      ├─→ Match Polymarket market to sports event                               │
│      │   └─→ Fuzzy matching on team names, date, sport type                    │
│      │                                                                          │
│      ├─→ Fetch odds from 15+ bookmakers                                        │
│      │   └─→ DraftKings, FanDuel, BetMGM, Pinnacle, etc.                      │
│      │                                                                          │
│      └─→ Calculate DEVIGGED fair value                                         │
│          └─→ Remove bookmaker margin (vig)                                     │
│          └─→ Consensus across multiple books                                   │
│                                                                                 │
│   3. COMPARE TO POLYMARKET PRICE                                                │
│      │                                                                          │
│      │   Polymarket YES = 0.60                                                 │
│      │   Bookmaker Fair  = 0.55 (devigged)                                     │
│      │   Edge = 0.60 - 0.55 - 0.02 (fee) = 3%                                  │
│      │                                                                          │
│      └─→ If edge > 2%: Generate signal                                         │
│                                                                                 │
│   4. GENERATE SPORTS SIGNAL                                                     │
│      ├─→ side: YES or NO (arbitrage requires both)                             │
│      ├─→ fair_value: From bookmakers                                           │
│      ├─→ edge: Polymarket vs fair                                              │
│      └─→ confidence: Based on bookmaker consensus                              │
│                                                                                 │
│   5. SPECIAL: NO-SIDE BETTING ALLOWED                                           │
│      └─→ Required for proper arbitrage hedging                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Why No LLM for Sports?

```
⚠️ CRITICAL: LLMs CANNOT predict live sports scores.

Bad Example (LLM Hallucination):
  Market: "Will Lakers beat Celtics tonight?"
  LLM: "Based on historical data, Lakers have 55% chance..."
  Reality: The game is IN PROGRESS with Celtics up by 20 points.
  
The Odds API provides REAL-TIME bookmaker odds that reflect:
- Live game state
- Injuries
- Weather
- Sharp money flow

This is why Sports lane uses 85% Odds API, 0% LLM.
```

### Position Sizing

```python
# Sports Kelly (More Conservative)
raw_kelly = edge / (1 - implied_odds)

# Clamped sports Kelly
sports_kelly = clamp(
    raw_kelly * 0.25,     # 25% Kelly
    0.05,                 # Min 5%
    0.20                  # Max 20% (tighter than Alpha)
)

sports_size = min(
    sports_capital * sports_kelly,
    $100                  # Hard cap
)
```

### Execution

- **Strategy**: `sports_arbitrage`
- **Order Type**: Market (speed > price)
- **Side**: YES or NO (both allowed)

---

## Lane 5: NEWS (The Injector)

### Purpose
Bridge between **slow LLM analysis** and **fast HFT execution** via the Async Injection Pattern.

### Cycle Time
**10 seconds** (polling) + **Instant** (webhook)

### Data Sources

| Source | Type | Provider | Description |
|--------|------|----------|-------------|
| **Exa.ai** | API (Pull) | External | Semantic news search |
| **Webhooks** | HTTP (Push) | Custom | Real-time news alerts |
| **EmergentLLMService** | Analysis | GPT-4o-mini | Event Resolution Adjudicator |
| **EventBayesianUpdater** | Model | Internal | Bayes Factor calculation |

### Analysis Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        NEWS ANALYSIS PIPELINE                                   │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                     ASYNC INJECTION PATTERN                             │   │
│   │                                                                         │   │
│   │   SLOW PATH (Background)          FAST PATH (HFT Loop)                  │   │
│   │   ─────────────────────           ──────────────────────                │   │
│   │                                                                         │   │
│   │   1. Receive News ────────────────────────────────────────┐             │   │
│   │      │                                                     │             │   │
│   │   2. LLM Analysis                                          │             │   │
│   │      │                                                     │             │   │
│   │   3. Bayesian Update                                       │             │   │
│   │      │                                                     │             │   │
│   │   4. If BF > 3.0: ───────────→ SIGNAL CACHE ←────── Read every 0.5s    │   │
│   │                                     │                       │             │   │
│   │                                     └───────────────────────┘             │   │
│   │                                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│   STEP 1: NEWS INGESTION                                                        │
│   ├─→ PULL (Exa.ai): Poll every 10s for market-relevant news                   │
│   │   └─→ Query: Market question keywords                                       │
│   │   └─→ Results: Title, URL, source, text                                     │
│   │                                                                             │
│   └─→ PUSH (Webhook): Immediate processing of alerts                            │
│       └─→ Endpoint: POST /api/hooks/news                                        │
│                                                                                 │
│   STEP 2: LLM ANALYSIS (Event Resolution Adjudicator)                           │
│   │                                                                             │
│   │   Specialized prompt: "YES Literalism Rule"                                 │
│   │                                                                             │
│   │   Example:                                                                  │
│   │     Question: "Will Bitcoin DROP below $60k?"                               │
│   │     News: "Bitcoin rallies to $72k on ETF approval"                         │
│   │                                                                             │
│   │     WRONG: "Good for Bitcoin → Bullish"                                     │
│   │     RIGHT: "Good for Bitcoin, but FATAL for the YES share"                  │
│   │                                                                             │
│   │   Output:                                                                   │
│   │   ├─→ is_bullish_for_yes: true/false                                       │
│   │   ├─→ confidence: 0-1                                                       │
│   │   └─→ reasoning: "..."                                                      │
│   │                                                                             │
│   STEP 3: BAYESIAN UPDATE                                                       │
│   │                                                                             │
│   │   EventBayesianUpdater.update()                                             │
│   │   ├─→ prior = market_price                                                  │
│   │   ├─→ likelihood = f(llm_confidence, source_reliability)                   │
│   │   ├─→ posterior = bayes_update(prior, likelihood)                          │
│   │   └─→ bayes_factor = posterior / prior                                      │
│   │                                                                             │
│   │   Source Reliability Weights:                                               │
│   │   ├─→ Reuters/AP: 95%                                                       │
│   │   ├─→ Bloomberg: 90%                                                        │
│   │   ├─→ CoinDesk: 85%                                                         │
│   │   ├─→ Twitter: 60%                                                          │
│   │   └─→ Unknown: 50%                                                          │
│   │                                                                             │
│   STEP 4: SIGNAL INJECTION                                                      │
│   │                                                                             │
│   │   If bayes_factor > 3.0 (strong evidence):                                  │
│   │   └─→ Inject to EmergentSignalCache                                        │
│   │       ├─→ key: "emergent_signal:{market_id}"                               │
│   │       ├─→ direction: YES or NO                                              │
│   │       ├─→ posterior: Updated probability                                    │
│   │       ├─→ ttl: 300s (5 min) or 3600s (resolution news)                     │
│   │       └─→ timestamp: Now                                                    │
│   │                                                                             │
│   STEP 5: HFT EXECUTION (news_sniper)                                           │
│       └─→ HFT loop reads cache every 0.5s                                       │
│       └─→ If signal found: Execute immediately                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Position Sizing

```python
# News Kelly (Bayes Factor weighted)
bf_confidence = log10(bayes_factor) / log10(10)  # BF=10 → 1.0

raw_kelly = edge / (1 - posterior)
news_kelly = raw_kelly * 0.25 * bf_confidence * llm_confidence

news_size = min(
    capital * news_kelly,
    capital * 0.05,       # 5% max
    $100                  # Hard cap
)
```

### Execution

- **Strategy**: `news_sniper`
- **Order Type**: Market (speed critical)
- **Side**: Based on LLM analysis

---

## Summary Comparison

| Lane | Cycle | Data Sources | Analysis | Sizing | Max Position |
|------|-------|--------------|----------|--------|--------------|
| **HFT** | 0.5s | Orderbook, Alpha Cache | Microstructure | Fixed 2% | $50 |
| **ALPHA** | 30s | LLM, Bayesian, Volatility, Sharp | Full Fusion | Binary Kelly | $100 |
| **GAMMA** | 30s | Full Orderbook Depth | Gap vs Wall | Fixed 1% | $15 |
| **SPORTS** | 30s | The Odds API (85%) | Arbitrage vs Books | Sports Kelly | $100 |
| **NEWS** | 10s | Exa.ai, Webhooks, LLM | Event Bayes | News Kelly | $100 |

---

## Exit Strategies by Lane

| Lane | Exit Type | Take Profit | Stop Loss | Max Hold |
|------|-----------|-------------|-----------|----------|
| **HFT** | Mechanical | +1.5% | -1.5% | 4 hours |
| **ALPHA** | Asset-Modified | 15-45%* | 7.5-22.5%* | 18-360h* |
| **GAMMA** | Whale Zone | 2x (Free Roll), 5x (Moonbag) | 0.5x | 168 hours |
| **SPORTS** | Time-Bounded | +30% | -25% | 48 hours |
| **NEWS** | TTL-Based | Signal TTL | Signal TTL | 5-60 min |

*Alpha exits are modified by asset class (crypto 1.5x, politics 1.2x, etc.)

---

*Document Version: 1.0*
*Last Updated: February 2026*
