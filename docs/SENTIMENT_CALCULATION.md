# APEX TRADER - Sentiment Calculation System (Detailed)

## Overview

Sentiment is a **0.0 to 1.0 score** that drives trade direction:
- **< 0.45** = Bearish → Buy NO
- **0.45-0.55** = Neutral → RL-driven
- **> 0.55** = Bullish → Buy YES

---

## MASTER FLOWCHART

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           SENTIMENT CALCULATION MASTER FLOW                       ║
╚══════════════════════════════════════════════════════════════════════════════════╝

                                    ┌─────────────┐
                                    │ MARKET DATA │
                                    │ (Input)     │
                                    └──────┬──────┘
                                           │
                 ┌─────────────────────────┼─────────────────────────┐
                 │                         │                         │
                 ▼                         ▼                         ▼
    ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
    │   POLYMARKET       │   │      LLM           │   │   CORRELATION      │
    │   NATIVE DATA      │   │   ANALYSIS         │   │   TRACKER          │
    │                    │   │                    │   │                    │
    │ • Order Book       │   │ • Question Parse   │   │ • Category Price   │
    │ • Trade History    │   │ • Context Build    │   │ • Related Markets  │
    │ • Volume Data      │   │ • GPT-4o-mini      │   │ • Group Momentum   │
    │ • Price History    │   │ • Response Parse   │   │                    │
    └─────────┬──────────┘   └─────────┬──────────┘   └─────────┬──────────┘
              │                        │                        │
              ▼                        ▼                        ▼
    ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
    │ SIGNAL EXTRACTION  │   │ PROBABILITY EST.   │   │ MOMENTUM CALC      │
    │                    │   │                    │   │                    │
    │ 1. Order Flow 25%  │   │ sentiment: 0.0-1.0 │   │ category_momentum  │
    │ 2. Vol Momentum 15%│   │ confidence: 0.0-1.0│   │ correlation_strength│
    │ 3. Spread Conf 10% │   │                    │   │                    │
    │ 4. Price Vel   15% │   │ Based on:          │   │ Based on:          │
    │ 5. Whale Sign  20% │   │ • Base rates       │   │ • Same category    │
    │ 6. Price Mom   15% │   │ • Current evidence │   │ • Keyword groups   │
    └─────────┬──────────┘   │ • Time factors     │   │ • Price changes    │
              │              └─────────┬──────────┘   └─────────┬──────────┘
              │                        │                        │
              ▼                        ▼                        ▼
    ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
    │ polymarket_sent    │   │ llm_sentiment      │   │ correlation_sent   │
    │ polymarket_conf    │   │ llm_confidence     │   │ correlation_str    │
    │ (0.0-1.0 each)     │   │ (0.0-1.0 each)     │   │ (0.0-1.0 each)     │
    └─────────┬──────────┘   └─────────┬──────────┘   └─────────┬──────────┘
              │                        │                        │
              │    WEIGHT: 30%         │    WEIGHT: 35%         │    WEIGHT: 15%
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                            ┌──────────┴──────────┐
                            │                     │
                            │  + GITHUB (20%)     │◄── Only for tech/crypto
                            │    (if applicable)  │
                            │                     │
                            └──────────┬──────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   WEIGHTED COMBINATION  │
                         │                         │
                         │ combined = Σ(sent × w)  │
                         │           ─────────────  │
                         │              Σ(w)       │
                         │                         │
                         │ confidence = min(0.95,  │
                         │              Σ(w))      │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   FINAL SENTIMENT       │
                         │   (0.0 - 1.0)           │
                         └────────────┬────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
           ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
           │  < 0.45      │  │ 0.45 - 0.55  │  │  > 0.55      │
           │  BEARISH     │  │  NEUTRAL     │  │  BULLISH     │
           │              │  │              │  │              │
           │  → Buy NO    │  │  → RL-driven │  │  → Buy YES   │
           └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Sentiment Sources Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENTIMENT SOURCES                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐     Weight: 30%                           │
│  │ POLYMARKET DATA  │ ◄── Order flow, volume, spread, whales    │
│  └────────┬─────────┘                                           │
│           │                                                      │
│  ┌────────▼─────────┐     Weight: 35%                           │
│  │   LLM ANALYSIS   │ ◄── GPT-based question interpretation     │
│  └────────┬─────────┘                                           │
│           │                                                      │
│  ┌────────▼─────────┐     Weight: 15%                           │
│  │ CROSS-MARKET     │ ◄── Category momentum, related markets    │
│  │ CORRELATION      │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│  ┌────────▼─────────┐     Weight: 20%                           │
│  │ GITHUB SENTIMENT │ ◄── For crypto/tech markets only          │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ COMBINED         │ = Weighted average of all sources         │
│  │ SENTIMENT        │                                           │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. POLYMARKET-NATIVE SENTIMENT (30% weight)

**File:** `/app/backend/ml/polymarket_sentiment.py`

Extracts sentiment directly from Polymarket's own data (no external API).

### POLYMARKET SENTIMENT FLOWCHART

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                      POLYMARKET NATIVE SENTIMENT EXTRACTION                       ║
╚══════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INPUT DATA                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│  market_data: { yes_price, volume_24h, liquidity }                              │
│  trades: [ { side, size, price, timestamp }, ... ]                              │
│  order_book: { bids: [...], asks: [...] }                                       │
│  price_history: [ { timestamp, price }, ... ]                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│  1. ORDER FLOW      │   │  2. VOLUME MOMENTUM │   │  3. SPREAD CONF     │
│     (25% weight)    │   │     (15% weight)    │   │     (10% weight)    │
├─────────────────────┤   ├─────────────────────┤   ├─────────────────────┤
│                     │   │                     │   │                     │
│ IF order_book:      │   │ Compare volume:     │   │ spread = ask - bid  │
│   bid_depth = Σbids │   │  • current vs 1h    │   │                     │
│   ask_depth = Σasks │   │  • current vs 6h    │   │ IF spread < 0.04:   │
│   imbalance =       │   │  • current vs 24h   │   │   conf = HIGH (0.8) │
│     bid/(bid+ask)   │   │                     │   │ ELIF spread < 0.08: │
│                     │   │ momentum = cur/avg  │   │   conf = MED (0.6)  │
│ ELSE IF trades:     │   │                     │   │ ELSE:               │
│   buy_vol = Σbuys   │   │ IF momentum > 2.0:  │   │   conf = LOW (0.3)  │
│   sell_vol = Σsells │   │   score = 0.75      │   │                     │
│   imbalance =       │   │ ELIF momentum > 1.2:│   │ score = 1 -         │
│     buy/(buy+sell)  │   │   score = 0.6       │   │   (spread/neutral)  │
│                     │   │ ELIF momentum < 0.8:│   │                     │
│ score = 0.3 +       │   │   score = 0.4       │   │                     │
│   (imbalance × 0.4) │   │ ELSE:               │   │                     │
│                     │   │   score = 0.5       │   │                     │
│ Range: 0.3 - 0.7    │   │                     │   │                     │
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
           │                         │                         │
           ▼                         ▼                         ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│  4. PRICE VELOCITY  │   │  5. WHALE SIGNAL    │   │  6. PRICE MOMENTUM  │
│     (15% weight)    │   │     (20% weight)    │   │     (15% weight)    │
├─────────────────────┤   ├─────────────────────┤   ├─────────────────────┤
│                     │   │                     │   │                     │
│ velocity =          │   │ whale_thresh=$1000  │   │ IF price_history:   │
│   (price_now -      │   │                     │   │   trend = prices[-1]│
│    price_prev) /    │   │ FOR each trade:     │   │           - prices[0]│
│    time_delta       │   │   IF size > thresh: │   │                     │
│                     │   │     whale_count++   │   │ IF trend > 0.05:    │
│ IF velocity > 0:    │   │     IF side=BUY:    │   │   score = 0.75      │
│   bullish           │   │       bullish++     │   │ ELIF trend > 0.02:  │
│ ELSE:               │   │     ELSE:           │   │   score = 0.6       │
│   bearish           │   │       bearish++     │   │ ELIF trend < -0.05: │
│                     │   │                     │   │   score = 0.25      │
│ score = 0.5 +       │   │ net_whale =         │   │ ELIF trend < -0.02: │
│   (velocity × 10)   │   │   bullish - bearish │   │   score = 0.4       │
│                     │   │                     │   │ ELSE:               │
│ Clamped: 0.2 - 0.8  │   │ score = 0.5 +       │   │   score = 0.5       │
│                     │   │   (net × 0.1)       │   │                     │
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │     WEIGHTED COMBINATION       │
                    ├────────────────────────────────┤
                    │                                │
                    │ combined = 0.5 (base neutral)  │
                    │                                │
                    │ FOR each signal:               │
                    │   IF signal.valid:             │
                    │     combined += (score - 0.5)  │
                    │                  × weight      │
                    │                                │
                    │ combined = clamp(0.01, 0.99)   │
                    │                                │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │     CONFIDENCE CALCULATION     │
                    ├────────────────────────────────┤
                    │ confidence = 0.3 (base)        │
                    │ IF has_trades: +0.2            │
                    │ IF has_order_book: +0.2        │
                    │ IF price_history > 10: +0.15   │
                    │ IF trade_history > 20: +0.15   │
                    │ MAX confidence: 0.9            │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │         OUTPUT                 │
                    │ polymarket_sentiment: 0.0-1.0  │
                    │ polymarket_confidence: 0.0-0.9 │
                    └────────────────────────────────┘
```

### Signal Weights (Total: 100%):

| Signal | Weight | What It Measures |
|--------|--------|------------------|
| **Order Flow** | 25% | Buy vs Sell pressure from orderbook depth or trades |
| **Whale Signal** | 20% | Large trades (>$1000) direction |
| **Volume Momentum** | 15% | Volume increase/decrease vs historical |
| **Price Velocity** | 15% | Rate of price change |
| **Price Momentum** | 15% | Overall price trend direction |
| **Spread Confidence** | 10% | Tighter spread = more market confidence |

---

## 2. LLM SENTIMENT (35% weight)

**File:** `/app/backend/ml/sentiment_llm.py`

Uses GPT-4o-mini to analyze the market question and estimate probability.

### LLM SENTIMENT FLOWCHART

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           LLM SENTIMENT ANALYSIS                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INPUT                                               │
│  question: "Will Bitcoin reach $100k by Dec 2026?"                              │
│  category: "crypto"                                                             │
│  current_price: 0.35 (market's implied probability)                             │
│  volume_24h: $125,000                                                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌────────────────────────────────┐
                    │       CHECK CACHE              │
                    ├────────────────────────────────┤
                    │ cache_key = hash(question)     │
                    │                                │
                    │ IF cached AND not expired:     │
                    │   return cached_result         │
                    │                                │
                    │ Cache TTL:                     │
                    │  • Hot (vol>$50k): 10 min      │
                    │  • Cold (vol<$50k): 60 min     │
                    └───────────────┬────────────────┘
                                    │ Cache Miss
                                    ▼
                    ┌────────────────────────────────┐
                    │       BUILD PROMPT             │
                    ├────────────────────────────────┤
                    │ """                            │
                    │ Analyze this prediction market:│
                    │                                │
                    │ Question: {question}           │
                    │ Category: {category}           │
                    │ Current Price: {price}         │
                    │ Volume 24h: ${volume}          │
                    │                                │
                    │ Consider:                      │
                    │ 1. Base Rate (historical)      │
                    │ 2. Current Evidence            │
                    │ 3. Market Context              │
                    │ 4. Time Factor                 │
                    │ 5. Contrarian Check            │
                    │                                │
                    │ Return probability 0.00-1.00   │
                    │ """                            │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │       CALL GPT-4o-mini         │
                    ├────────────────────────────────┤
                    │ Via Emergent LLM Integration   │
                    │                                │
                    │ model: gpt-4o-mini             │
                    │ temperature: 0.3               │
                    │ max_tokens: 10                 │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │       PARSE RESPONSE           │
                    ├────────────────────────────────┤
                    │ response = "0.65"              │
                    │                                │
                    │ TRY:                           │
                    │   sentiment = float(response)  │
                    │   sentiment = clamp(0, 1, val) │
                    │ EXCEPT:                        │
                    │   sentiment = 0.5 (neutral)    │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │    CALCULATE CONFIDENCE        │
                    ├────────────────────────────────┤
                    │ divergence = |llm - market|    │
                    │                                │
                    │ // High divergence = alpha     │
                    │ IF divergence > 0.30:          │
                    │   base_conf = 0.7              │
                    │ ELIF divergence > 0.15:        │
                    │   base_conf = 0.5              │
                    │ ELSE:                          │
                    │   base_conf = 0.3              │
                    │                                │
                    │ // Volume adjustment           │
                    │ IF volume > 100k:              │
                    │   conf = base_conf × 1.2       │
                    │ ELIF volume > 50k:             │
                    │   conf = base_conf × 1.1       │
                    │ ELSE:                          │
                    │   conf = base_conf             │
                    │                                │
                    │ confidence = min(0.85, conf)   │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │       CACHE RESULT             │
                    ├────────────────────────────────┤
                    │ cache[key] = {                 │
                    │   sentiment: 0.65,             │
                    │   confidence: 0.7,             │
                    │   timestamp: now(),            │
                    │   ttl: 600 or 3600             │
                    │ }                              │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                    ┌────────────────────────────────┐
                    │         OUTPUT                 │
                    │ llm_sentiment: 0.65            │
                    │ llm_confidence: 0.7            │
                    └────────────────────────────────┘
```

### LLM System Prompt:
```
You are an expert prediction market analyst.

CALIBRATION GUIDELINES:
- 0.00-0.10: Near impossible (< 10% chance)
- 0.10-0.30: Unlikely (10-30% chance)
- 0.30-0.50: Somewhat unlikely (30-50% chance)
- 0.50: Maximum uncertainty / coin flip
- 0.50-0.70: Somewhat likely (50-70% chance)
- 0.70-0.90: Likely (70-90% chance)
- 0.90-1.00: Near certain (> 90% chance)

Return ONLY a decimal number between 0.00 and 1.00.
```

### Smart Caching Logic:
| Market Type | Volume Threshold | Cache TTL | Reason |
|-------------|------------------|-----------|--------|
| Hot Market | > $50,000 | 10 min | Fast-moving, needs fresh analysis |
| Cold Market | < $50,000 | 60 min | Slow-moving, save API calls |

---

## 3. CROSS-MARKET CORRELATION (15% weight)

**File:** `/app/backend/ml/enhanced_sentiment.py` (CrossMarketCorrelation class)

Tracks related markets to identify category-wide momentum.

### Market Groups:
```python
market_groups = {
    'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana'],
    'trump': ['trump', 'donald', 'maga', 'republican'],
    'biden': ['biden', 'democrat', 'democratic'],
    'fed': ['fed', 'interest rate', 'inflation', 'fomc'],
    'ai': ['ai', 'openai', 'chatgpt', 'google', 'microsoft'],
    'sports_nba': ['nba', 'basketball', 'lakers', 'celtics'],
    'sports_nfl': ['nfl', 'football', 'superbowl', 'chiefs'],
}
```

### Calculation:
```python
# Track price changes across related markets
for market in same_category_markets:
    price_changes.append(market.current_price - market.prev_price)

# Average momentum
category_momentum = np.mean(price_changes)

# Convert to sentiment
correlation_sentiment = 0.5 + (category_momentum * 5)  # Scale up
correlation_sentiment = clamp(0.1, 0.9, correlation_sentiment)
```

---

## 4. GITHUB SENTIMENT (20% weight) - Tech/Crypto Only

**File:** `/app/backend/ml/github_sentiment.py`

Analyzes GitHub activity for technology-related markets.

### Triggers:
- Only activates for markets with keywords: `ai`, `crypto`, `bitcoin`, `ethereum`, etc.

### Signals:
- Repository star growth
- Commit frequency
- Issue/PR activity
- Developer sentiment in discussions

---

## 5. HEURISTIC SENTIMENT (Fallback/Backtest Mode)

**File:** `/app/backend/ml/signal_fusion.py:190`

Fast sentiment estimation when LLM is disabled.

```python
def _heuristic_sentiment(self, market_data):
    yes_price = market_data.get('yes_price')
    volume = market_data.get('volume', 0)
    
    # Use market price as sentiment proxy
    sentiment = yes_price  # Market's implied probability
    
    # Volume-adjusted confidence
    confidence = min(volume / 10000, 0.8)
    
    return sentiment, confidence
```

**When Used:**
- `backtest_mode = True`
- `sentiment_analyzer = None`
- LLM API failure/timeout

---

## 6. FINAL COMBINATION

**File:** `/app/backend/ml/enhanced_sentiment.py:370-404`

### Weighted Average:
```python
poly_weight = polymarket_confidence * 0.30    # Max 30%
llm_weight = llm_confidence * 0.35            # Max 35%
corr_weight = correlation_strength * 0.15     # Max 15%
github_weight = github_confidence * 0.20      # Max 20%

total_weight = poly_weight + llm_weight + corr_weight + github_weight

combined_sentiment = (
    polymarket_sentiment * poly_weight +
    llm_sentiment * llm_weight +
    correlation_sentiment * corr_weight +
    github_sentiment * github_weight
) / total_weight

combined_confidence = min(0.95, total_weight)
```

### Fallback (No External Signals):
```python
if total_weight == 0:
    combined_sentiment = yes_price  # Use market price
    combined_confidence = 0.1       # Low confidence
```

---

## 7. SENTIMENT → TRADE DECISION

**File:** `/app/backend/paper_trading/paper_trader.py:1096-1113`

### Decision Logic:
```python
sentiment = signals.get('sentiment', 0.5)

if sentiment > bullish_sentiment_threshold:  # Default: 0.55
    side = 'YES'  # Bullish = Buy YES
    
elif sentiment < bearish_sentiment_threshold:  # Default: 0.45
    side = 'NO'   # Bearish = Buy NO
    
else:
    # Neutral - use RL action
    side = 'YES' if 'BUY' in rl_action else 'NO'
```

### Configurable Thresholds (UI Settings):
| Setting | Default | Effect |
|---------|---------|--------|
| `bullish_sentiment_threshold` | 0.55 | Sentiment above this → YES |
| `bearish_sentiment_threshold` | 0.45 | Sentiment below this → NO |

---

## 8. BAYESIAN POSTERIOR (Signal Fusion)

**File:** `/app/backend/ml/signal_fusion.py:108-120`

Combines sentiment with other signals for final confidence.

```python
def _calculate_bayesian_posterior(self, signals):
    sentiment = signals.get('sentiment', 0.5)
    sharp_align = signals.get('sharp_alignment', 0.5)
    mispricing_conf = signals.get('mispricing', 0.0)
    
    # Base posterior
    posterior = sentiment * sharp_align
    
    # Boost if mispricing detected
    if mispricing_conf > 0.7:
        posterior *= 1.3
    
    return clamp(0.0, 1.0, posterior)
```

---

## 9. CONFIGURATION SUMMARY

| Component | File | Key Settings |
|-----------|------|--------------|
| **Polymarket Weight** | enhanced_sentiment.py:373 | `0.30` (30%) |
| **LLM Weight** | enhanced_sentiment.py:374 | `0.35` (35%) |
| **Correlation Weight** | enhanced_sentiment.py:375 | `0.15` (15%) |
| **GitHub Weight** | enhanced_sentiment.py:376 | `0.20` (20%) |
| **Bullish Threshold** | paper_trader.py (UI Config) | `0.55` |
| **Bearish Threshold** | paper_trader.py (UI Config) | `0.45` |
| **LLM Cache (Hot)** | sentiment_llm.py | `600s` (10 min) |
| **LLM Cache (Cold)** | sentiment_llm.py | `3600s` (60 min) |
| **Whale Threshold** | polymarket_sentiment.py:43 | `$1,000` |
| **Spread Neutral** | polymarket_sentiment.py:51 | `0.04` (4%) |

---

## 10. DATA FLOW DIAGRAM

```
Market Data
    │
    ▼
┌───────────────────────────────────────────────────────┐
│              SIGNAL FUSION ENGINE                      │
│                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Polymarket  │  │    LLM      │  │ Correlation │   │
│  │ Sentiment   │  │ Sentiment   │  │ Sentiment   │   │
│  │   (30%)     │  │   (35%)     │  │   (15%)     │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │           │
│         └────────────────┼────────────────┘           │
│                          │                            │
│                          ▼                            │
│               ┌─────────────────┐                     │
│               │    COMBINED     │                     │
│               │   SENTIMENT     │                     │
│               │   (0.0 - 1.0)   │                     │
│               └────────┬────────┘                     │
│                        │                              │
└────────────────────────┼──────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   TRADE DECISION    │
              │                     │
              │  > 0.55 → Buy YES   │
              │  < 0.45 → Buy NO    │
              │  else → RL-driven   │
              └─────────────────────┘
```

---

*Last Updated: January 25, 2026*
