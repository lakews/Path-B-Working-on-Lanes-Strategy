# APEX TRADER - Sentiment Analysis Framework

## Complete Technical Documentation

**Last Updated:** January 2026
**Version:** 2.0 (Post-Consolidation)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Data Sources](#3-data-sources)
4. [Signal Processing Pipeline](#4-signal-processing-pipeline)
5. [Sentiment Fusion Algorithm](#5-sentiment-fusion-algorithm)
6. [Integration with Trading Engine](#6-integration-with-trading-engine)
7. [File Reference](#7-file-reference)
8. [Configuration & Tuning](#8-configuration--tuning)

---

## 1. System Overview

The sentiment analysis system combines **5 active data sources** into a single weighted sentiment score (0-1) that influences the probability model for trading decisions.

### Key Principles

- **All values are probabilities (0-1)** where 0.5 = neutral
- **Confidence-weighted fusion** - sources with higher confidence get more weight
- **Fail-safe defaults** - if a source fails, it returns 0.5 (neutral) with 0 confidence
- **Caching** - LLM results cached for 5 minutes to reduce costs

### Output

```
Final Sentiment (0-1)
├── > 0.55 → Bullish signal (favors YES)
├── 0.45-0.55 → Neutral (no directional signal)
└── < 0.45 → Bearish signal (favors NO)
```

---

## 2. Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    SENTIMENT ANALYSIS ARCHITECTURE                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

                              ┌─────────────────┐
                              │  MARKET DATA    │
                              │  (Polymarket)   │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
         ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
         │ Gamma API        │ │ CLOB API     │ │ Market Question  │
         │ - Price          │ │ - Order Book │ │ - Category       │
         │ - Volume         │ │ - Trades*    │ │ - Expiry         │
         │ - Liquidity      │ │ - Spreads    │ └────────┬─────────┘
         └────────┬─────────┘ └──────┬───────┘          │
                  │                  │                  │
                  ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SENTIMENT SOURCES (5 Active)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ 1. MARKET       │  │ 2. POLYMARKET   │  │ 3. LLM (GPT)    │             │
│  │ MICROSTRUCTURE  │  │ NATIVE          │  │                 │             │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤             │
│  │ Price sentiment │  │ Order flow      │  │ GPT-4o-mini     │             │
│  │ Momentum        │  │ Spread conf     │  │ via Emergent    │             │
│  │ Volume intensity│  │ Whale signal    │  │                 │             │
│  │ Liquidity score │  │ Volume momentum │  │ Analyzes:       │             │
│  │ Whale activity  │  │ Price velocity  │  │ - Question      │             │
│  │                 │  │ Price momentum  │  │ - Category      │             │
│  │ Weight: 25%     │  │ Weight: ≤25%    │  │ - Current price │             │
│  │ (Fixed)         │  │ (Confidence)    │  │                 │             │
│  └─────────────────┘  └─────────────────┘  │ Weight: ≤25%    │             │
│                                            │ (Confidence)    │             │
│  ┌─────────────────┐  ┌─────────────────┐  └─────────────────┘             │
│  │ 4. CORRELATION  │  │ 5. GITHUB       │                                  │
│  ├─────────────────┤  ├─────────────────┤  ┌─────────────────┐             │
│  │ Related markets │  │ Commit velocity │  │ 6. FINNHUB      │             │
│  │ Category trend  │  │ Releases        │  ├─────────────────┤             │
│  │ Group momentum  │  │ Issue health    │  │ ❌ DISABLED     │             │
│  │                 │  │ Community       │  │ Needs API key   │             │
│  │ Weight: ≤10%    │  │                 │  │                 │             │
│  │ (Strength)      │  │ CRYPTO ONLY     │  │ Weight: 0%      │             │
│  └─────────────────┘  │ Weight: ≤15%    │  └─────────────────┘             │
│                       └─────────────────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │     SENTIMENT FUSION ENGINE      │
                    │                                  │
                    │  Formula:                        │
                    │  sentiment = Σ(source × weight)  │
                    │              ─────────────────   │
                    │                 Σ(weights)       │
                    │                                  │
                    │  Output: 0.0 - 1.0              │
                    └─────────────────┬────────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │      P_SENTIMENT COMPONENT       │
                    │                                  │
                    │  Used in probability model:      │
                    │  P_final = w₁×P_market          │
                    │          + w₂×P_sentiment       │
                    │          + w₃×P_rl              │
                    └─────────────────┬────────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │         TRADING DECISION         │
                    │                                  │
                    │  Edge = P_final - Effective_Price│
                    │  If Edge > threshold → TRADE     │
                    └──────────────────────────────────┘

* Trades API requires authentication - currently using order book depth instead
```

---

## 3. Data Sources

### 3.1 Market Microstructure (Always Active)

**File:** `/app/backend/paper_trading/paper_trader.py` (lines 2459-2770)
**Weight:** 25% (fixed)

Analyzes raw market data to extract sentiment signals:

| Component | Calculation | Range | Interpretation |
|-----------|-------------|-------|----------------|
| **Price Sentiment** | `yes_price` directly | 0-1 | Higher price = more bullish |
| **Momentum** | SMA(5) vs SMA(20) crossover | 0-1 | Rising = bullish |
| **Volume Intensity** | `volume_24h / avg_volume` | 0-1 | High volume = confidence |
| **Liquidity Score** | `min(1, liquidity / 100000)` | 0-1 | More liquidity = reliable |
| **Whale Activity** | Large order detection | 0-1 | Whale buys = bullish |

**Formula:**
```python
market_sentiment = (
    price_sentiment * 0.35 +
    momentum_sentiment * 0.25 +
    volume_intensity * 0.15 +
    liquidity_sentiment * 0.15 +
    whale_sentiment * 0.10
)
```

---

### 3.2 Polymarket Native (Order Book Analysis)

**File:** `/app/backend/ml/polymarket_sentiment.py`
**Weight:** Up to 25% (based on confidence)

Extracts signals directly from Polymarket order book data:

| Signal | Source | Calculation | What It Means |
|--------|--------|-------------|---------------|
| **Order Flow** | Order book depth | `bid_depth / (bid_depth + ask_depth)` | More bids = buying pressure |
| **Spread Confidence** | Bid-ask spread | Tight spread = high confidence | Market agrees on price |
| **Whale Signal** | Large orders | Orders > $1000 | Smart money positioning |
| **Volume Momentum** | Volume history | `recent_vol / older_vol` | Interest increasing? |
| **Price Velocity** | Price history | Rate of change | How fast is price moving? |
| **Price Momentum** | SMA crossover | SMA(5) vs SMA(10) | Trend direction |

**Confidence Calculation:**
```python
confidence = 0.3  # Base
if has_order_book: confidence += 0.3
if price_history_points > 10: confidence += 0.2
if trade_history_points > 20: confidence += 0.2
# Max: 1.0
```

---

### 3.3 LLM Sentiment (GPT-4o-mini) - HYBRID SMART-CACHE

**File:** `/app/backend/ml/sentiment_llm.py`
**Weight:** Up to 35% (based on confidence)

Uses GPT-4o-mini via Emergent integration with **Hybrid Smart-Cache** strategy:

**Smart Cache Strategy:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID SMART-CACHE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  "Hot" Markets (Volume > $50,000/24h)                          │
│  ├── Cache TTL: 10 minutes                                      │
│  └── Reason: Catch breaking news quickly                        │
│                                                                 │
│  "Cold" Markets (Volume < $50,000/24h)                         │
│  ├── Cache TTL: 60 minutes                                      │
│  └── Reason: Save API costs on inactive markets                 │
│                                                                 │
│  Result: 100% market coverage without 100% of the cost          │
│  Safety: Returns (0.5, 0.0) on errors → neutral with zero weight│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Prompt Template:**
```
PREDICTION MARKET ANALYSIS

Question: {question}
Category: {category}
Description: {description}

Market Data:
- Current Price: {current_price} ({current_price*100}% implied probability)
- 24h Volume: ${volume_24h} (HOT/COLD indicator)

Task: Estimate the TRUE probability of this outcome.

Consider:
1. Is the market price ({current_price}) reasonable?
2. What factors might be over/under-weighted?
3. Any recent developments that could shift probability?

Return ONLY a number between 0.00 and 1.00
```

**Confidence Calculation:**
```python
# Base confidence
confidence = 0.3

# Price divergence component (more divergence = potential alpha)
price_diff = abs(llm_sentiment - market_price)
divergence_confidence = price_diff * 0.6

# Volume adjustment (hot markets are more efficient)
if volume_24h >= 50000:  # Hot market
    volume_factor = 0.7  # Reduce confidence in divergence
else:  # Cold market
    volume_factor = 1.0  # Higher confidence in divergence

confidence += divergence_confidence * volume_factor
# Final range: 0.1 - 0.9
```

**API Endpoint:**
```
GET /api/sentiment/llm/stats
Returns: cache hit/miss rates, call counts, configuration
```

---

### 3.4 Cross-Market Correlation

**File:** `/app/backend/ml/enhanced_sentiment.py` (lines 50-170)
**Weight:** Up to 10% (based on strength)

Tracks related markets to find correlation signals:

| Feature | How It Works |
|---------|--------------|
| **Category Tracking** | Groups markets by category (crypto, politics, sports) |
| **Related Groups** | Detects keywords (e.g., "trump", "fed", "bitcoin") |
| **Momentum** | If related markets moving same direction → stronger signal |

**Example:**
```
Market: "Will Fed cut rates in March?"
Related markets found: 3 other Fed markets
- Fed Jan meeting: 0.85 (bullish)
- Fed rate path: 0.72 (bullish)
- Treasury yields: 0.68 (bullish)

Category momentum: +0.08 (all moving up)
Correlation sentiment: 0.58 (slightly bullish)
Correlation strength: 0.4
```

---

### 3.5 GitHub Sentiment (Crypto/Tech Only)

**File:** `/app/backend/ml/github_sentiment.py`
**Weight:** Up to 15% (crypto markets only)

Analyzes GitHub repository activity for crypto/tech markets:

**Keyword Detection:**
```python
MARKET_REPO_MAP = {
    "ethereum": ["ethereum/go-ethereum", "ethereum/solidity"],
    "bitcoin": ["bitcoin/bitcoin", "bitcoin/bips"],
    "solana": ["solana-labs/solana"],
    "uniswap": ["Uniswap/v3-core", "Uniswap/v4-core"],
    "pectra": ["ethereum/go-ethereum", "ethereum/EIPs"],
    # ... 30+ mappings
}
```

**Signals Analyzed:**

| Signal | API Endpoint | Bullish If |
|--------|--------------|------------|
| Commit Velocity | `/repos/{repo}/commits` | > 5 commits/day |
| Release Activity | `/repos/{repo}/releases` | Recent releases |
| Issue Health | `/repos/{repo}/issues` | Features > Bugs |
| Community | `/repos/{repo}` | High stars/forks |
| Recency | `/repos/{repo}` | Code pushed recently |

**When It Activates:**
- Market question contains crypto keywords (bitcoin, ethereum, etc.)
- OR category is "crypto" or "technology"
- Otherwise returns 0 confidence → 0% weight

---

### 3.6 Finnhub External (DISABLED)

**File:** `/app/backend/ml/social_sentiment.py`
**Status:** ❌ DISABLED (requires API key)

Would provide:
- News sentiment from financial news
- Social media buzz (Twitter, Reddit)
- Trending topics

**To Enable:**
1. Get free API key from https://finnhub.io/register
2. Add to `/app/backend/.env`: `FINNHUB_API_KEY=your_key`
3. Uncomment code in `paper_trader.py` lines 2615-2640

---

## 4. Signal Processing Pipeline

### Step-by-Step Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Market Data Received                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Input:                                                                     │
│  {                                                                          │
│    "id": "0x1234...",                                                       │
│    "question": "Will Bitcoin reach $100k by Dec 2026?",                     │
│    "category": "crypto",                                                    │
│    "yes_price": 0.35,                                                       │
│    "volume_24h": 500000,                                                    │
│    "liquidity": 250000                                                      │
│  }                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Fetch Additional Data                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Parallel API calls:                                                        │
│  ├── Order Book → CLOB API /book?token_id=...                              │
│  ├── Trades → CLOB API /trades (requires auth, may fail)                   │
│  └── Price History → Gamma API (cached)                                    │
│                                                                             │
│  Output:                                                                    │
│  order_book = {"bids": [...], "asks": [...]}                               │
│  trades = [] (empty if auth required)                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Call Enhanced Sentiment Analyzer                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  enhanced_sentiment.analyze(market_data, trades, order_book)                │
│                                                                             │
│  Internally calls (in parallel where possible):                            │
│  1. polymarket_sentiment.analyze_market() → Polymarket Native              │
│  2. _get_llm_sentiment() → GPT-4o-mini (if not rate limited)              │
│  3. correlation_tracker.get_correlation_signal() → Related markets         │
│  4. github_sentiment.analyze_market() → GitHub (if crypto)                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Calculate Market Microstructure (Always)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  In paper_trader._get_signals():                                           │
│                                                                             │
│  price_sentiment = yes_price                           # 0.35              │
│  momentum_sentiment = calculate_momentum(price_history) # 0.48             │
│  volume_intensity = volume_24h / 1000000               # 0.50              │
│  liquidity_sentiment = min(1, liquidity / 100000)      # 1.00              │
│  whale_sentiment = detect_whale_orders(order_book)     # 0.45              │
│                                                                             │
│  market_sentiment = weighted_average(above)            # 0.44              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Sentiment Fusion                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Collect all sources:                                                       │
│  ┌────────────────────┬───────────┬────────────┬──────────────┐            │
│  │ Source             │ Sentiment │ Confidence │ Weight       │            │
│  ├────────────────────┼───────────┼────────────┼──────────────┤            │
│  │ Market Micro       │ 0.44      │ 1.00       │ 25.0%        │            │
│  │ Polymarket Native  │ 0.52      │ 0.50       │ 12.5%        │            │
│  │ LLM (GPT)          │ 0.40      │ 0.35       │ 8.75%        │            │
│  │ Correlation        │ 0.55      │ 0.30       │ 3.0%         │            │
│  │ GitHub             │ 0.62      │ 0.80       │ 12.0%        │            │
│  │ Finnhub            │ -         │ 0.00       │ 0.0%         │            │
│  ├────────────────────┴───────────┴────────────┼──────────────┤            │
│  │ TOTAL                                       │ 61.25%       │            │
│  └─────────────────────────────────────────────┴──────────────┘            │
│                                                                             │
│  Calculation:                                                               │
│  raw = (0.44×0.25 + 0.52×0.125 + 0.40×0.0875 + 0.55×0.03 + 0.62×0.12)     │
│      = 0.110 + 0.065 + 0.035 + 0.0165 + 0.0744                             │
│      = 0.3009                                                               │
│                                                                             │
│  normalized = 0.3009 / 0.6125 = 0.491                                      │
│                                                                             │
│  final_sentiment = 0.491 (slightly bearish)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Output Signals Object                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  {                                                                          │
│    "sentiment": 0.491,                                                      │
│    "sentiment_strength": 0.18,                                             │
│    "sentiment_layers": {                                                    │
│      "market_microstructure": 0.44,                                        │
│      "polymarket_native": 0.52,                                            │
│      "polymarket_confidence": 0.50,                                        │
│      "llm_sentiment": 0.40,                                                │
│      "llm_confidence": 0.35,                                               │
│      "correlation_sentiment": 0.55,                                        │
│      "correlation_strength": 0.30,                                         │
│      "github_sentiment": 0.62,                                             │
│      "github_confidence": 0.80                                             │
│    },                                                                       │
│    "sentiment_weights": {                                                   │
│      "market_weight": 0.25,                                                │
│      "polymarket_weight": 0.125,                                           │
│      "llm_weight": 0.0875,                                                 │
│      "correlation_weight": 0.03,                                           │
│      "github_weight": 0.12                                                 │
│    },                                                                       │
│    "polymarket_signals": {                                                  │
│      "order_flow": {"score": 0.52, "source": "order_book_depth"},         │
│      "spread_confidence": {"score": 0.48, "valid": true},                  │
│      "whale_signal": {"score": 0.55, "source": "order_book_whales"}       │
│    },                                                                       │
│    "polymarket_momentum": {                                                 │
│      "1h": {"change": 0.02, "direction": "bullish"},                       │
│      "6h": {"change": -0.01, "direction": "neutral"},                      │
│      "24h": {"change": 0.05, "direction": "bullish"}                       │
│    }                                                                        │
│  }                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Sentiment Fusion Algorithm

### Mathematical Formula

```
                    Σᵢ (sentimentᵢ × confidenceᵢ × max_weightᵢ)
final_sentiment = ──────────────────────────────────────────────
                    Σᵢ (confidenceᵢ × max_weightᵢ)
```

### Weight Configuration

```python
# In paper_trader.py _get_signals()

# Fixed weights (always applied)
market_weight = 0.25  # Market microstructure: 25%

# Dynamic weights (scaled by confidence)
polymarket_weight = polymarket_confidence * 0.25  # Max 25%
llm_weight = llm_confidence * 0.25               # Max 25%
github_weight = github_confidence * 0.15         # Max 15% (crypto only)
corr_weight = correlation_strength * 0.10        # Max 10%

# Disabled
external_weight = 0  # Finnhub disabled

total_weight = market_weight + polymarket_weight + llm_weight + github_weight + corr_weight
```

### Example Scenarios

**Scenario 1: Non-Crypto Market, LLM Rate Limited**
```
Market: "Will Fed cut rates?"
- Market Micro: 0.40 × 0.25 = 0.100
- Polymarket:   0.45 × 0.15 = 0.0675
- LLM:          skipped (rate limited)
- GitHub:       skipped (non-crypto)
- Correlation:  0.50 × 0.03 = 0.015

Total weight: 0.43
Final: (0.100 + 0.0675 + 0.015) / 0.43 = 0.424 (bearish)
```

**Scenario 2: Crypto Market, All Sources Active**
```
Market: "Will ETH reach $5000?"
- Market Micro: 0.55 × 0.25 = 0.1375
- Polymarket:   0.58 × 0.20 = 0.116
- LLM:          0.62 × 0.22 = 0.136
- GitHub:       0.70 × 0.12 = 0.084
- Correlation:  0.52 × 0.05 = 0.026

Total weight: 0.84
Final: (0.1375 + 0.116 + 0.136 + 0.084 + 0.026) / 0.84 = 0.595 (bullish)
```

---

## 6. Integration with Trading Engine

### How Sentiment Influences P_final

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PROBABILITY MODEL INTEGRATION                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  The sentiment becomes P_sentiment in the weighted probability model:      │
│                                                                             │
│  P_final = w_market × P_market                                             │
│          + w_sentiment × P_sentiment    ← SENTIMENT GOES HERE              │
│          + w_rl × P_rl                                                     │
│                                                                             │
│  Default weights (adjust based on signal agreement):                       │
│  - w_market: 50% (market price)                                            │
│  - w_sentiment: 25% (our sentiment analysis)                               │
│  - w_rl: 25% (RL model prediction)                                         │
│                                                                             │
│  Example:                                                                   │
│  - P_market = 0.35 (current market price)                                  │
│  - P_sentiment = 0.491 (from sentiment fusion)                             │
│  - P_rl = 0.42 (RL model thinks slightly higher)                           │
│                                                                             │
│  P_final = 0.50×0.35 + 0.25×0.491 + 0.25×0.42                             │
│          = 0.175 + 0.123 + 0.105                                           │
│          = 0.403                                                            │
│                                                                             │
│  Edge = P_final - Effective_Price                                          │
│       = 0.403 - 0.357 (price + fees)                                       │
│       = 0.046 (4.6% edge)                                                  │
│                                                                             │
│  → Positive edge → TRADE                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Weight Adjustment Based on Signal Agreement

```python
# In _calculate_model_probability()

# Check if sentiment agrees with RL
sentiment_agrees_with_rl = (
    (sentiment > 0.55 and rl_action.startswith('BUY')) or
    (sentiment < 0.45 and rl_action.startswith('SELL'))
)

if sentiment_agrees_with_rl:
    # Both signals agree → reduce market weight, trust our signals more
    w_market = 0.40
    w_sentiment = 0.30
    w_rl = 0.30
else:
    # Signals conflict → trust market more
    w_market = 0.55
    w_sentiment = 0.22
    w_rl = 0.23
```

---

## 7. File Reference

| File | Purpose | Key Functions |
|------|---------|---------------|
| `/app/backend/paper_trading/paper_trader.py` | Main trading engine | `_get_signals()`, `_calculate_model_probability()` |
| `/app/backend/ml/enhanced_sentiment.py` | Sentiment orchestrator | `analyze()`, `_get_llm_sentiment()` |
| `/app/backend/ml/polymarket_sentiment.py` | Polymarket native signals | `analyze_market()`, `_calculate_order_flow()` |
| `/app/backend/ml/github_sentiment.py` | GitHub analysis | `analyze_market()`, `_analyze_repo()` |
| `/app/backend/ml/social_sentiment.py` | Finnhub integration | `analyze_market_sentiment()` (disabled) |
| `/app/backend/data/polymarket_api.py` | API client | `get_order_book()`, `get_trades()` |

---

## 8. Configuration & Tuning

### Environment Variables

```bash
# /app/backend/.env

# Required
EMERGENT_LLM_KEY=sk-emergent-xxx     # For GPT-4o-mini
GITHUB_TOKEN=github_pat_xxx           # For GitHub API (5000 req/hr)

# Optional (disabled)
FINNHUB_API_KEY=xxx                   # For news/social sentiment
```

### Tunable Parameters

```python
# enhanced_sentiment.py
LLM_CACHE_TTL = 300              # 5 minutes
MIN_LLM_INTERVAL = 1.0           # 1 second rate limit
MAX_LLM_CALLS_PER_MINUTE = 30

# polymarket_sentiment.py
WHALE_THRESHOLD_USD = 1000       # $1000+ = whale
LARGE_TRADE_THRESHOLD = 500      # $500+ = large
MOMENTUM_WINDOWS = {
    '1h': 3600,
    '6h': 21600,
    '24h': 86400
}

# paper_trader.py (weight configuration)
MARKET_WEIGHT = 0.25             # Fixed 25%
MAX_POLYMARKET_WEIGHT = 0.25     # Up to 25%
MAX_LLM_WEIGHT = 0.25            # Up to 25%
MAX_GITHUB_WEIGHT = 0.15         # Up to 15%
MAX_CORRELATION_WEIGHT = 0.10    # Up to 10%
```

---

## Appendix: Value Interpretation Guide

| Range | Label | Trading Implication |
|-------|-------|---------------------|
| 0.00 - 0.20 | Strongly Bearish | Strong NO signal |
| 0.20 - 0.35 | Bearish | Lean NO |
| 0.35 - 0.45 | Slightly Bearish | Weak NO signal |
| 0.45 - 0.55 | Neutral | No directional edge |
| 0.55 - 0.65 | Slightly Bullish | Weak YES signal |
| 0.65 - 0.80 | Bullish | Lean YES |
| 0.80 - 1.00 | Strongly Bullish | Strong YES signal |

---

*Document generated by APEX TRADER system*
*For questions, see `/app/docs/TRADING_FRAMEWORK.md`*
