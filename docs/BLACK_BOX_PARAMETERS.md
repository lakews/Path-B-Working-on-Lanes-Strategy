# "Black Box" Parameters: Lane 2 (Alpha) & Lane 5 (News)

## Overview

This document reveals the exact production logic for:
1. **Lane 2: SignalFusionEngine** - The Brain
2. **Lane 5: News Injector** - The Eyes
3. **Inter-Lane Communication** - The Kill Switches

---

## Part 1: Lane 2 - The SignalFusionEngine

### 1.1 Static Weights (Default Configuration)

```python
# Default weights for signal fusion
self.weights = {
    'sentiment': 0.30,        # LLM Sentiment
    'volatility': 0.25,       # Volatility Predictor
    'mispricing': 0.25,       # Bayesian Outlier Detection
    'sharp_alignment': 0.20   # Sharp Money Detection
}
```

### 1.2 Dynamic Weight Adjustment (Regime Classifier)

**Q: Is there a Regime Classifier that lowers LLM weight during high volatility?**

**A: YES.** The regime classification affects execution, not weights directly. But the formula accounts for volatility:

```python
def _calculate_fused_confidence(self, signals: Dict) -> float:
    """
    Volatility INVERSELY affects its contribution:
    - High vol → Lower vol_score (more uncertainty)
    - This naturally reduces aggressive positions during chaos
    """
    sent_score = signals.get('sentiment', 0.5) * signals.get('sentiment_confidence', 0)
    
    # KEY: (1 - volatility) means HIGH VOL reduces score
    vol_score = (1 - signals.get('volatility', 0.5)) * signals.get('volatility_confidence', 0)
    
    misp_score = signals.get('mispricing', 0)
    sharp_score = signals.get('sharp_alignment', 0.5)
    
    weighted_confidence = (
        sent_score * self.weights['sentiment'] +       # 0.30
        vol_score * self.weights['volatility'] +       # 0.25
        misp_score * self.weights['mispricing'] +      # 0.25
        sharp_score * self.weights['sharp_alignment']  # 0.20
    )
    
    return clamp(weighted_confidence, 0.0, 1.0)
```

**Regime Classification:**
```python
if price < 0.10:
    regime = "CONVEXITY_OPPORTUNITY"  # Route to GAMMA
elif spread > 2%:
    regime = "MAKER_WIDE"             # Post limit orders (lower risk)
elif spread <= 2%:
    regime = "TAKER_TIGHT"            # Market orders (higher vol impact)
else:
    regime = "ZOMBIE"                 # Skip market entirely
```

### 1.3 Sharp Money Detection

**Q: What specific metrics define 'Sharp Money'?**

**A: Four criteria must ALL be met:**

```python
class SharpDetector:
    sharp_threshold = 0.70      # Minimum win rate
    min_trades = 10             # Minimum trade count
    tracking_window = 7 days    # Lookback period
    
    def _is_sharp_trader(self, stats: Dict) -> bool:
        win_rate = stats.get('win_rate', 0)
        volume = stats.get('total_volume', 0)
        num_trades = stats.get('num_trades', 0)
        concentration = stats.get('category_concentration', 5)
        
        return (
            # 1. WIN RATE: Must win 70%+ of trades
            win_rate >= 0.70 and
            
            # 2. VOLUME: Minimum $5,000 total traded (from RISK.SHARP_DETECTION_MIN_VOLUME)
            volume >= 5000.0 and
            
            # 3. TRADE COUNT: At least 10 trades (statistical significance)
            num_trades >= 10 and
            
            # 4. CATEGORY FOCUS: Trades in max 2 categories (specialist)
            concentration <= 2
        )
```

**Consensus Calculation (Volume-Weighted):**
```python
def _calculate_consensus(self, positions: List[Dict], proposed_side: str) -> float:
    """
    Volume-weighted consensus, NOT count-weighted.
    A $50K position from a sharp counts more than a $500 position.
    """
    total_volume = sum(p.get('volume', 0) for p in positions)
    
    aligned_volume = sum(
        p.get('volume', 0) for p in positions 
        if p.get('side') == proposed_side
    )
    
    # Consensus: 0.0 = all sharps against you, 1.0 = all sharps with you
    consensus = aligned_volume / total_volume
    return consensus
```

**Line Movement (PnL) Calculation:**
```python
def _calculate_line_movement(self, trade: Dict) -> float:
    """
    'Sharp' means the line moved IN YOUR FAVOR after entry.
    Positive = profitable direction, Negative = wrong direction.
    """
    entry_price = trade.get('price', 0.5)
    final_price = trade.get('final_price', entry_price)
    volume = trade.get('volume', 0)
    
    return (final_price - entry_price) * volume
```

### 1.4 Volatility Predictor

**Q: What is the specific lookback period? (Yang-Zhang / Rogers-Satchell?)**

**A: Simple standard deviation with ML ensemble, NOT Yang-Zhang.**

```python
class VolatilityPredictor:
    lookback_period = 60        # 60 data points lookback
    prediction_horizon = 15     # Predict next 15 periods
    
    def _extract_features(self, prices, volumes, liquidities):
        """
        6 features extracted from lookback window:
        """
        # PRICE FEATURES
        price_std = np.std(prices)                      # Standard deviation
        price_range = max(prices) - min(prices)         # High-Low range
        price_momentum = (prices[-1] - prices[0]) / prices[0]  # Directional move
        
        # VOLUME FEATURES
        volume_avg = np.mean(volumes)
        
        # LIQUIDITY FEATURES
        liquidity_avg = np.mean(liquidities)
        
        # RETURN FEATURES (Close-to-Close volatility)
        returns = np.diff(prices) / prices[:-1]
        return_std = np.std(returns)                    # Historical vol
        
        return [price_std, price_range, volume_avg, liquidity_avg, price_momentum, return_std]
    
    def predict_volatility(self, market_id: str) -> (predicted_vol, confidence):
        """
        Ensemble: Gradient Boosting + Random Forest
        """
        # Extract features from last 60 datapoints
        features = self._extract_features(prices, volumes, liquidities)
        features_scaled = self.scaler.transform([features])
        
        # Ensemble prediction (average of two models)
        gb_pred = self.gb_model.predict(features_scaled)[0]
        rf_pred = self.rf_model.predict(features_scaled)[0]
        
        ensemble_pred = (gb_pred + rf_pred) / 2
        
        return ensemble_pred, confidence
```

**Model Training:**
```python
# Gradient Boosting
self.gb_model = GradientBoostingRegressor(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.1,
    random_state=42
)

# Random Forest
self.rf_model = RandomForestRegressor(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    n_jobs=-1
)
```

---

## Part 2: Lane 5 - The News Injector

### 2.1 The "YES Literalism" Prompt (EXACT)

```python
SYSTEM_PROMPT_EMERGENT = """
### Role & Objective
You are the **Event Resolution Adjudicator** for a high-frequency prediction market algorithm. Your sole purpose is to determine if the provided **News Text** constitutes concrete **Evidence** that alters the probability of the **Market Question** resolving to "YES".

---

## Core Logic: The "YES" Literalism Rule
You must evaluate the impact strictly on the **YES outcome** of the specific contract, not the general sentiment of the subject.

**Scenario A (Inverse Correlation):**
- Question: "Will Bitcoin DROP below $60k?"
- News: "Bitcoin rallies to $72k on ETF approval."
- Analysis: Good for Bitcoin, but FATAL for the YES share.
- Output: `is_bullish_for_yes: false`

**Scenario B (Literal Wording):**
- Question: "Will SpaceX launch Starship by Friday?"
- News: "SpaceX delays launch due to wind."
- Analysis: The event (launch) is not happening within the timeframe.
- Output: `is_bullish_for_yes: false`

---

## Sector-Specific Evidence Guide

### 1. Politics & Macro (Elections, Fed Rates, Bills)
- **High Value:** Official White House/Fed statements, Passed Bills, Concession Speeches.
- **Low Value:** Op-Eds, Campaign rallies, "Anonymous sources".

### 2. Culture & Entertainment (Box Office, Awards, Cancellations)
- **High Value:** Variety/Deadline "Exclusive", Verified Artist Tweets, Official Studio Press Releases.
- **Low Value:** Fan theories, Reddit threads, Tabloid gossip.

### 3. Science & Tech (Space, Climate, AI)
- **High Value:** FAA Licenses, NOAA/NHC Advisories, Company Engineering Blogs.
- **Low Value:** YouTube commentary, Influencer predictions.

---

## Bayesian Confidence Scale (Calibration)
Assign confidence strictly based on **Evidentiary Weight**:

- **0.50 (Noise):** Irrelevant, stale news, or pure opinion. (Bot will NOT trade).
- **0.60 (Weak Signal):** Credible rumors ("Sources say"), strong correlated asset moves, or "leading indicators" (e.g., Early polls).
- **0.75 (Strong Signal):** Direct quotes from key decision-makers, preliminary data releases, reputable mainstream reporting (Bloomberg, Reuters, AP).
- **0.95 (Resolution):** The event has concluded. The result is known facts (e.g., "The bill has passed", "The game is over").

---

## JSON Output Schema
Return ONLY this raw JSON object. No markdown, no code blocks.

{
  "is_relevant": boolean,        // Is this text actually about the specific subject in the question?
  "is_bullish_for_yes": boolean, // TRUE = Evidence supports "YES" winning. FALSE = Evidence supports "NO".
  "confidence": float,           // 0.50 to 0.99. Be conservative.
  "rationale": "string"          // Max 15 words. Focus on the causal link (e.g. 'Official denial reduces probability of dropout').
}
"""
```

### 2.2 Confidence → Bayes Factor Mapping

**Q: How does LLM confidence (0-100) translate to Bayes Factor?**

**A: Impact classification + Source reliability adjustment:**

```python
class EventBayesianUpdater:
    """
    Step 1: LLM confidence → Impact classification
    Step 2: Impact → Base likelihood
    Step 3: Base likelihood × Source reliability = Adjusted likelihood
    Step 4: Adjusted likelihood → Bayes Factor
    """
    
    # STEP 1: Confidence thresholds (from LLM output)
    # 0.95+ = resolution, 0.75+ = strong, 0.60+ = moderate, else = weak
    
    # STEP 2: Impact → Likelihood mapping
    LIKELIHOOD_MAP = {
        'resolution': 0.95,     # P(news | YES true) for market-resolving news
        'strong': 0.80,         # P(news | YES true) for strong evidence
        'moderate': 0.65,       # P(news | YES true) for moderate evidence
        'weak': 0.55,           # P(news | YES true) for weak evidence
        'irrelevant': 0.50      # Neutral - no update
    }
    
    def _get_likelihood_for_impact(self, impact: NewsImpact) -> float:
        return self.LIKELIHOOD_MAP.get(impact.value, 0.5)
    
    # STEP 3: Source reliability adjustment
    def update(self, ...):
        base_likelihood = self._get_likelihood_for_impact(impact)
        source_reliability = self._get_source_reliability(news_source)
        
        # FORMULA: Shrink likelihood toward 0.5 by (1 - reliability)
        adjusted_likelihood = 0.5 + (base_likelihood - 0.5) * source_reliability
        
        # Example: Strong signal (0.80) from Twitter (0.60 reliability)
        # adjusted = 0.5 + (0.80 - 0.5) × 0.60 = 0.5 + 0.18 = 0.68
        
    # STEP 4: Bayes Factor calculation
    def _calculate_bayes_factor(self, likelihood_yes, likelihood_no):
        """
        BF = P(news | YES) / P(news | NO)
        """
        return likelihood_yes / max(likelihood_no, 0.001)
```

**Complete Mapping Table:**

| LLM Confidence | Impact | Base L(YES) | Source (Reuters) | Adjusted | BF (approx) |
|----------------|--------|-------------|------------------|----------|-------------|
| 0.95+ | Resolution | 0.95 | 0.95 | 0.9275 | ~12.8 |
| 0.75-0.94 | Strong | 0.80 | 0.95 | 0.785 | ~3.7 |
| 0.60-0.74 | Moderate | 0.65 | 0.95 | 0.6425 | ~1.8 |
| 0.50-0.59 | Weak | 0.55 | 0.95 | 0.5475 | ~1.2 |
| <0.50 | Irrelevant | 0.50 | - | 0.50 | 1.0 |

**Action Thresholds:**
```python
min_bayes_factor = 3.0       # Minimum BF to inject signal (trade)
strong_bayes_factor = 10.0   # BF for high-priority injection
```

### 2.3 Source Reliability Application

**Q: Is it a multiplier on BF or a threshold?**

**A: It's a MULTIPLIER on the likelihood (before BF calculation):**

```python
SOURCE_RELIABILITY = {
    'apnews.com': 0.95,
    'reuters.com': 0.95,
    'bloomberg.com': 0.90,
    'bbc.com': 0.90,
    'coindesk.com': 0.85,
    'theblock.co': 0.85,
    'fivethirtyeight.com': 0.90,
    'polymarket.com': 0.80,     # User comments, less reliable
    'twitter.com': 0.60,
    'x.com': 0.60,
    'unknown': 0.50
}

def _adjust_likelihood(self, base_likelihood, source_reliability):
    """
    FORMULA: Shrink toward 0.5 based on unreliability
    
    - Perfect source (1.0): No shrinkage, use base_likelihood
    - Zero reliability (0.0): Shrink to 0.5 (neutral)
    - Partial reliability: Linear interpolation
    """
    return 0.5 + (base_likelihood - 0.5) * source_reliability
```

**Example Calculation:**
```
News: "Bitcoin hits $100K" from Twitter
LLM: is_bullish_for_yes=True, confidence=0.75 (Strong)

Step 1: Impact = STRONG_SIGNAL
Step 2: base_likelihood = 0.80
Step 3: source_reliability (Twitter) = 0.60
Step 4: adjusted = 0.5 + (0.80 - 0.5) × 0.60 = 0.68

Step 5: Calculate BF
  - If direction = YES: L(YES) = 0.68, L(NO) = 0.32
  - BF = 0.68 / 0.32 = 2.125

Result: BF = 2.125 < 3.0 threshold → DO NOT TRADE
        (Twitter source too unreliable for strong action)
```

---

## Part 3: Inter-Lane Communication

### 3.1 The Kill Switch Architecture

**Q: Does Lane 5 (News) have authority to force liquidate Lane 1 (HFT)?**

**A: NO direct liquidation. News has THREE levels of authority:**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     KILL SWITCH HIERARCHY                                       │
│                                                                                 │
│   LEVEL 1: PAUSE_BUYING (Soft)                                                  │
│   ─────────────────────────────                                                │
│   - News sets HFTContext.status = PAUSED                                        │
│   - HFT will NOT open new positions                                             │
│   - Existing positions continue to be managed (exits OK)                        │
│   - Usage: "Potential news event, reduce risk exposure"                         │
│                                                                                 │
│   LEVEL 2: KILL (Hard)                                                          │
│   ─────────────────────                                                        │
│   - News sets HFTContext.status = KILL                                          │
│   - HFT will NOT trade this market AT ALL (no new, no close)                   │
│   - Manual intervention required to resume                                      │
│   - Usage: "Market is about to resolve, stop all activity"                      │
│                                                                                 │
│   LEVEL 3: EMERGENCY_STOPLOSS (Global - NOT from News)                          │
│   ─────────────────────────────────────────────────────                        │
│   - Background task monitors ALL positions                                      │
│   - If PnL < -50%: Force close regardless of lane                              │
│   - If drawdown > 5%: Circuit breaker triggers                                  │
│   - This is NOT controlled by News - it's a global safety                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 HFTContext Status Codes

```python
class ContextStatus(str, Enum):
    ACTIVE = "ACTIVE"       # Normal trading allowed
    PAUSED = "PAUSED"       # Temporarily paused (no new positions)
    KILL = "KILL"           # Trading disabled (no activity)
    STALE = "STALE"         # Data too old, treated as KILL
```

### 3.3 News → HFT Communication Flow

```python
# In News Injector (Lane 5):
async def _inject_resolution_signal(self, market_id, news):
    """When news indicates market resolution"""
    
    # 1. Inject signal to cache (for news_sniper execution)
    await self.signal_cache.set(f"emergent_signal:{market_id}", {
        'direction': 'YES',
        'posterior': 0.99,
        'bayes_factor': 50.0,
        'ttl': 3600,  # 1 hour for resolution
        'is_resolution': True
    })
    
    # 2. Update HFT context to PAUSED
    hft_ctx = get_hft_context()
    hft_ctx.update(
        market_id=market_id,
        status=ContextStatus.PAUSED,  # Stop HFT from opening new positions
        ...
    )
    
    logger.warning(f"[NEWS] Resolution detected for {market_id}, HFT PAUSED")
```

### 3.4 Price Kill Switches (Global)

```python
# From risk_config.json (SSOT):
"global": {
    "kill_switch_low": 0.03,   # Don't trade below $0.03
    "kill_switch_high": 0.97   # Don't trade above $0.97
}

# In execution logic:
if yes_price < KILL_SWITCH_LOW or yes_price > KILL_SWITCH_HIGH:
    logger.debug(f"Price {yes_price} outside safe zone, skipping")
    return None  # No trade
```

### 3.5 Emergency Stop Loss (Global Safety)

```python
async def _emergency_stoploss_task(self):
    """
    Background task checking ALL positions for emergency stop loss.
    This is NOT controlled by any lane - it's a global safety net.
    """
    EMERGENCY_SL_THRESHOLD = -0.50  # -50% emergency stop
    
    while self.running:
        for market_id, position in self.paper_positions.items():
            current_pnl_pct = calculate_pnl_pct(position)
            
            if current_pnl_pct <= EMERGENCY_SL_THRESHOLD:
                logger.critical(f"🚨 EMERGENCY SL: {market_id} at {current_pnl_pct:.0%}")
                await self._execute_paper_exit(market_id, ..., f"emergency_sl_{current_pnl_pct:.0%}")
        
        await asyncio.sleep(5)  # Check every 5 seconds
```

---

## Summary: Black Box Parameters

### Lane 2 (Alpha) Key Numbers

| Parameter | Value | Notes |
|-----------|-------|-------|
| LLM Weight | 30% | Sentiment analysis |
| Volatility Weight | 25% | Inverted (high vol = low score) |
| Mispricing Weight | 25% | Bayesian outlier detection |
| Sharp Money Weight | 20% | Volume-weighted consensus |
| Sharp Win Rate Threshold | 70% | Must win 70%+ |
| Sharp Min Volume | $5,000 | Total traded |
| Sharp Min Trades | 10 | Statistical significance |
| Sharp Category Focus | ≤2 | Specialist traders |
| Vol Lookback | 60 periods | Feature extraction window |
| Vol Prediction Horizon | 15 periods | Forward prediction |

### Lane 5 (News) Key Numbers

| Parameter | Value | Notes |
|-----------|-------|-------|
| Min Bayes Factor | 3.0 | Threshold to inject signal |
| Strong Bayes Factor | 10.0 | High-priority injection |
| Resolution Likelihood | 0.95 | P(news\|YES) for resolution |
| Strong Likelihood | 0.80 | P(news\|YES) for strong |
| Moderate Likelihood | 0.65 | P(news\|YES) for moderate |
| Weak Likelihood | 0.55 | P(news\|YES) for weak |
| Default TTL | 300s | 5 minutes |
| Resolution TTL | 3600s | 1 hour |
| Reuters Reliability | 0.95 | Source weight |
| Twitter Reliability | 0.60 | Source weight |
| Unknown Reliability | 0.50 | Source weight |

### Kill Switch Summary

| Level | Trigger | Effect | Controlled By |
|-------|---------|--------|---------------|
| PAUSED | News event | No new HFT positions | News Lane |
| KILL | Resolution news | No HFT activity | News Lane |
| Emergency SL | -50% PnL | Force close | Global Task |
| Circuit Breaker | 5% drawdown | Stop all trading | Global Task |
| Price Kill | <$0.03 or >$0.97 | Skip market | SSOT Config |

---

*Document Version: 1.0*
*Last Updated: February 2026*
