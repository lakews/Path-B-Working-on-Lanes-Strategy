# Bayesian Model Tuning Suggestions

**Created:** January 24, 2026  
**Status:** PENDING - Not yet implemented  
**Priority:** P1 - Affects trade distribution balance

---

## Problem Statement

After boosting Bayesian Log-Odds weights from 0.40 to 0.60, trade volume increased but resulted in **100% NO trades** (bearish bias). The root cause is that LLM sentiment consistently returns values in the 0.30-0.45 range, creating negative deltas that pull model probabilities down.

### Observed Data Pattern

| Trade | Market Price | Sentiment | RL | Sent Delta | RL Delta |
|-------|-------------|-----------|-----|------------|----------|
| NO | 0.380 | 0.422 | 0.280 | -0.1885 | -0.1366 |
| NO | 0.305 | 0.444 | 0.275 | -0.1342 | -0.0437 |
| NO | 0.165 | 0.348 | 0.137 | -0.3778 | -0.0313 |
| NO | 0.281 | 0.405 | 0.250 | -0.2298 | -0.0239 |
| YES | 0.675 | 0.583 | 0.708 | +0.2018 | +0.0249 |

**Key Insight:** Sentiment clusters around 0.35-0.45 regardless of market price. Only when market price is high (>0.65) does sentiment exceed neutral, allowing YES trades.

---

## Suggested Solutions

### Option 1: Recalibrate Neutral Zone (Quick Fix)

**Current:** Neutral zone is 0.45-0.55  
**Problem:** LLM baseline is ~0.40, so most signals fall just below neutral and create bearish deltas

**Suggested Change:**
```python
# In paper_trader.py _calculate_model_probability()
NEUTRAL_LOW = 0.38   # Was 0.45 - lowered to match LLM baseline
NEUTRAL_HIGH = 0.52  # Was 0.55 - slightly asymmetric
```

**Pros:** Simple, quick to implement  
**Cons:** Doesn't address root cause, may need re-tuning as LLM behavior changes

---

### Option 2: Sentiment Baseline Correction (Recommended)

**Concept:** Track rolling average of LLM sentiment outputs and normalize against it

**Implementation:**
```python
class SentimentBaselineCorrector:
    def __init__(self, window_size=100):
        self.history = deque(maxlen=window_size)
        self.baseline = 0.5  # Start neutral
    
    def correct(self, raw_sentiment: float) -> float:
        self.history.append(raw_sentiment)
        if len(self.history) >= 10:
            self.baseline = sum(self.history) / len(self.history)
        
        # Normalize: if baseline is 0.40, a 0.45 sentiment becomes 0.55
        corrected = 0.5 + (raw_sentiment - self.baseline)
        return max(0.05, min(0.95, corrected))
```

**Pros:** Self-calibrating, adapts to LLM drift over time  
**Cons:** Needs warm-up period, adds complexity

---

### Option 3: Reduce Sentiment Weight, Keep RL Higher

**Current:** SENTIMENT_WEIGHT = 0.60, RL_WEIGHT = 0.60  
**Problem:** High sentiment weight amplifies the bearish bias

**Suggested Change:**
```python
SENTIMENT_WEIGHT = 0.35  # Reduced - sentiment is less reliable
RL_WEIGHT = 0.50         # Higher - RL learns from actual outcomes
```

**Pros:** Reduces impact of biased sentiment  
**Cons:** May reduce responsiveness to genuine sentiment shifts

---

### Option 4: Relative Sentiment (Context-Aware)

**Concept:** Instead of absolute sentiment, use sentiment relative to market price

**Implementation:**
```python
def calculate_relative_sentiment(sentiment: float, market_price: float) -> float:
    """
    If market is at 30% and sentiment is 40%, that's BULLISH (+10%)
    If market is at 70% and sentiment is 40%, that's BEARISH (-30%)
    """
    relative = sentiment - market_price
    # Convert to probability-like scale
    return 0.5 + relative  # Range: ~0.0 to ~1.0
```

Then use this relative sentiment for the Bayesian update:
```python
relative_sent = calculate_relative_sentiment(p_sentiment, p_market)
# Only apply delta if relative sentiment diverges from neutral
if relative_sent < 0.45 or relative_sent > 0.55:
    sent_delta = weight * logit(relative_sent)
```

**Pros:** More intuitive - sentiment of 0.40 is bullish for a 0.20 market  
**Cons:** Changes interpretation of sentiment signal

---

### Option 5: Directional Agreement Gate

**Concept:** Only apply full weights when sentiment and RL agree on direction

**Implementation:**
```python
sent_direction = 1 if p_sentiment > 0.5 else -1
rl_direction = 1 if rl_action in ['BUY_STRONG', 'BUY_MEDIUM'] else -1

if sent_direction == rl_direction:
    # Agreement - use full weights
    effective_sent_weight = SENTIMENT_WEIGHT
    effective_rl_weight = RL_WEIGHT
else:
    # Disagreement - reduce weights to avoid conflicting signals
    effective_sent_weight = SENTIMENT_WEIGHT * 0.5
    effective_rl_weight = RL_WEIGHT * 0.5
```

**Pros:** Reduces noise from conflicting signals  
**Cons:** May reduce trade volume when signals conflict

---

## Recommended Approach

Combine **Option 2 (Baseline Correction)** with **Option 4 (Relative Sentiment)**:

1. Track LLM sentiment baseline over rolling window
2. Calculate relative sentiment = raw_sentiment - market_price
3. Apply baseline correction to the relative sentiment
4. Use corrected relative sentiment for Bayesian updates

This approach:
- Self-calibrates to LLM drift
- Provides context-aware signals (sentiment relative to market)
- Naturally balances YES/NO trade distribution

---

## Files to Modify

1. `/app/backend/paper_trading/paper_trader.py`
   - `_calculate_model_probability()` method
   - Add baseline correction logic

2. `/app/backend/ml/enhanced_sentiment.py`
   - Add `SentimentBaselineCorrector` class
   - Track rolling average of LLM outputs

3. `/app/backend/ml/sentiment_llm.py`
   - Optionally add relative sentiment calculation

---

## Testing Plan

After implementation:
1. Run paper trader for 10-15 minutes
2. Check `/api/paper/trades` endpoint
3. Verify trade distribution is closer to 50/50 YES/NO
4. Monitor for any reduction in trade volume
5. Check that edges remain above 1% threshold

---

## Related Files

- `/app/backend/paper_trading/paper_trader.py` - Bayesian model implementation
- `/app/backend/ml/sentiment_llm.py` - LLM sentiment module
- `/app/backend/ml/enhanced_sentiment.py` - Sentiment orchestration
- `/app/docs/SENTIMENT_ANALYSIS_FRAMEWORK.md` - Sentiment architecture docs
