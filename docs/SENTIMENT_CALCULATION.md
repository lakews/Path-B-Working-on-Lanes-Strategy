# APEX TRADER - Sentiment Calculation System

## Overview

Sentiment is a **0.0 to 1.0 score** that drives trade direction:
- **< 0.45** = Bearish → Buy NO
- **0.45-0.55** = Neutral → RL-driven
- **> 0.55** = Bullish → Buy YES

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

### Signals Extracted:

| Signal | Calculation | Interpretation |
|--------|-------------|----------------|
| **Order Flow Imbalance** | `buy_volume / (buy_volume + sell_volume)` | >0.5 = buying pressure |
| **Volume Momentum** | `current_vol / avg_vol` over 1h/6h/24h | >1.0 = increasing interest |
| **Spread Analysis** | `1 - (spread / spread_neutral)` | Tighter spread = more confidence |
| **Price Velocity** | `(current - prev) / time` | Positive = bullish momentum |
| **Whale Detection** | Count of trades > $1,000 | Whale buys = bullish signal |

### Combined Score Formula:
```python
polymarket_sentiment = (
    order_flow_imbalance * 0.30 +      # Order pressure
    volume_momentum * 0.20 +            # Volume trend
    spread_confidence * 0.15 +          # Market confidence
    price_velocity * 0.20 +             # Price direction
    whale_signal * 0.15                 # Smart money
)
```

### Confidence Calculation:
```python
confidence = 0.3  # Base
if has_trades: confidence += 0.2
if has_order_book: confidence += 0.2
if price_history_points > 10: confidence += 0.15
if trade_history_points > 20: confidence += 0.15
# Max: 0.9
```

---

## 2. LLM SENTIMENT (35% weight)

**File:** `/app/backend/ml/sentiment_llm.py`

Uses GPT to analyze the market question and estimate probability.

### How It Works:

1. **Build Prompt:**
```python
prompt = f"""
Analyze this prediction market:
Question: {question}
Category: {category}
Current Price: {current_price} (market's implied probability)

Estimate the TRUE probability (0.0-1.0) that this resolves YES.
Return ONLY a number between 0.0 and 1.0.
"""
```

2. **Parse Response:**
```python
# Extract float from LLM response
sentiment = float(response_text.strip())  # e.g., 0.65
```

3. **Calculate Confidence:**
```python
# Confidence based on divergence from market price
divergence = abs(llm_sentiment - market_price)

if divergence > 0.3:  # High divergence = potential alpha
    confidence = 0.7
elif divergence > 0.15:
    confidence = 0.5
else:
    confidence = 0.3  # Agrees with market

# Volume factor
if volume_24h > 100000:
    confidence *= 1.2  # High volume = more reliable
```

### Smart Caching:
```python
# Hot markets (volume > $50k): 10 minute cache
# Cold markets (volume < $50k): 60 minute cache
cache_ttl = 600 if volume_24h > 50000 else 3600
```

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
