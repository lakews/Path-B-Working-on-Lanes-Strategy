# APEX TRADER - Complete Trading Framework

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRADING LOOP (continuous)                        │
│                                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │  MARKET  │───▶│ STRATEGY │───▶│ POSITION │───▶│  ENTRY   │           │
│  │  FILTER  │    │ SELECTOR │    │  SIZER   │    │ EXECUTE  │           │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘           │
│       │                                               │                  │
│       │         ┌──────────────────────────────────────┘                 │
│       │         │                                                        │
│       │         ▼                                                        │
│       │    ┌──────────┐    ┌──────────┐    ┌──────────┐                 │
│       │    │ POSITION │───▶│   EXIT   │───▶│  CLOSE   │                 │
│       │    │ MONITOR  │    │  CHECK   │    │ POSITION │                 │
│       │    └──────────┘    └──────────┘    └──────────┘                 │
│       │         │                                                        │
│       └─────────┴──────────── LOOP EVERY ~1 SECOND ─────────────────────│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. TRADE IDENTIFICATION (Market Filter)

**File:** `paper_trader.py` → `_get_active_markets()`, `_evaluate_entry()`

### Data Source
- **Polymarket Gamma API** - Fetches up to 200 live markets per cycle
- Filtered by user-enabled **asset classes** (politics, sports, crypto, etc.)

### Market Filters
```python
# Must pass ALL filters to be considered:
├── Asset Class: In user's enabled list
├── Liquidity: > min_liquidity ($5,000 default)
├── Volume 24h: > min_volume_24h ($1,000 default)  
├── Spread: < max_spread (5% default)
├── Not already in portfolio
└── Not recently rejected (cooldown)
```

---

## 2. SIGNAL GENERATION

**File:** `paper_trader.py` → `_get_signals()`

### Signal Sources
```
┌─────────────────────────────────────────────────────────────┐
│                      SIGNAL LAYERS                          │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: MARKET MICROSTRUCTURE                              │
│   • Price sentiment (YES price as base)                     │
│   • Volume momentum (24h vs total)                          │
│   • Spread analysis                                         │
│   • Liquidity depth                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: AI SENTIMENT (GPT-4o-mini via Emergent)            │
│   • Analyzes market question + current odds                 │
│   • Returns sentiment 0-1 and reasoning                     │
│   • Cached per market (5 min TTL)                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: SHARP MONEY DETECTION                              │
│   • Compares volume-weighted price vs spot                  │
│   • High alignment = institutional activity                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: DQN REINFORCEMENT LEARNING                         │
│   • Deep Q-Network with prioritized replay                  │
│   • Outputs: BUY_SMALL/MEDIUM/LARGE, SELL_*, HOLD           │
│   • Confidence score 0-1                                    │
└─────────────────────────────────────────────────────────────┘

OUTPUT → signals = {
    'sentiment': 0.0-1.0,
    'volatility': 0.0-0.15,
    'sharp_alignment': 0.0-1.0,
    'price_uncertainty': 0.0-1.0,
    'rl_action': 'BUY_MEDIUM',
    'rl_confidence': 0.0-1.0
}
```

---

## 3. STRATEGY SELECTION

**File:** `paper_trader.py` → `_determine_strategy()`

### Strategy Decision Tree
```python
def _determine_strategy(signals, market_data):
    yes_price = market_data['yes_price']
    
    # 1. ALPHA DIRECTIONAL: Extreme prices (<25% or >75%)
    if yes_price < 0.25 or yes_price > 0.75:
        return 'alpha_directional'
    
    # 2. ARBITRAGE: High sharp money alignment (>60%)
    if sharp_alignment > 0.60:
        return 'arbitrage'
    
    # 3. DELTA NEUTRAL: Mid-range (40-70%) + low volatility
    if 0.40 <= yes_price <= 0.70 and volatility < 0.06:
        return 'delta_neutral'
    
    # 4. ALPHA DIRECTIONAL: Strong sentiment (>15% from neutral)
    if abs(sentiment - 0.5) > 0.15:
        return 'alpha_directional'
    
    # 5. VOLATILITY EXPLOITATION: High volatility or uncertainty
    if volatility > 0.06 or price_uncertainty > 0.70:
        return 'volatility_exploitation'
    
    # 6. Fallback: Rotate based on price bucket
    return distribute_by_price_bucket()
```

### Strategy Characteristics
| Strategy | Trigger | Typical Edge | Risk Level |
|----------|---------|--------------|------------|
| Alpha Directional | Price <25% or >75% | 3-8% | Medium |
| Delta Neutral | Price 40-70%, low vol | 1-3% | Low |
| Volatility Exploitation | High volatility | 2-5% | High |
| Arbitrage | Sharp alignment >60% | 1-4% | Low |

---

## 4. SIDE SELECTION (YES vs NO)

**File:** `paper_trader.py` → `_evaluate_entry()`

```python
# Based on sentiment thresholds (configurable):
bullish_threshold = 0.55  # Above this → YES
bearish_threshold = 0.45  # Below this → NO

if sentiment > bullish_threshold:
    side = 'YES'
elif sentiment < bearish_threshold:
    side = 'NO'
else:
    # Neutral: Use RL action direction
    side = 'YES' if 'BUY' in rl_action else 'NO'
```

---

## 5. MODEL PROBABILITY & EDGE CALCULATION

**File:** `paper_trader.py` → `_calculate_model_probability()`

### Multiplicative Adjustment (NEW)
```python
# Base multiplier by signal strength:
SMALL  → ×1.12 (12% more/less likely)
MEDIUM → ×1.22 (22% more/less likely)
LARGE  → ×1.35 (35% more/less likely)

# Scaled by confidence + sentiment agreement:
total_multiplier = base_mult * conf_scale * sentiment_factor * alignment_factor

# Apply direction:
if BUY:  model_prob = yes_price * total_multiplier
if SELL: model_prob = yes_price / total_multiplier
```

### Edge Calculation
```python
# For YES bet:
effective_price = ask_price * (1 + fee_pct)  # Include 2% exit fee
edge = model_probability - effective_price

# For NO bet:
effective_price = (1 - yes_price) * (1 + fee_pct)
edge = (1 - model_probability) - effective_price

# Must have positive edge to trade
```

---

## 6. POSITION SIZING

**File:** `polymarket_position_sizer.py` → `calculate_position_size()`

### Sizing Waterfall
```
┌────────────────────────────────────────────────────────────┐
│                  POSITION SIZING ENGINE                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  STEP 1: Binary Kelly Criterion                            │
│  ─────────────────────────────────                         │
│  kelly_fraction = edge / (1 - effective_price)             │
│  kelly_base = equity × kelly_fraction × 0.25               │
│                                                            │
│  STEP 2: Utilization Brake                                 │
│  ─────────────────────────────                             │
│  utilization = deployed / equity                           │
│  brake = (1 - utilization)²                                │
│  → At 50% deployed: ×0.25                                  │
│  → At 80% deployed: ×0.04                                  │
│                                                            │
│  STEP 3: Time Penalty                                      │
│  ────────────────────                                      │
│  → 30+ days: ×1.0                                          │
│  → 7 days: ×0.85                                           │
│  → 1 day: ×0.50                                            │
│                                                            │
│  STEP 4: Oracle Risk (Ambiguity Matrix)                    │
│  ──────────────────────────────────────                    │
│  sports/crypto: ×1.00 (clear binary outcome)               │
│  finance: ×0.95                                            │
│  politics: ×0.75-0.90                                      │
│  conflict/war: ×0.40 (vague definitions)                   │
│  social: ×0.50 (linguistic ambiguity)                      │
│                                                            │
│  STEP 5: Correlation Dampener                              │
│  ────────────────────────────                              │
│  → Reduces size if same-category positions exist           │
│  → 3+ correlated: ×0.50                                    │
│                                                            │
│  STEP 6: Caps                                              │
│  ─────────                                                 │
│  liquidity_cap = market_liquidity × 1%                     │
│  sector_cap = equity × sector_pct (e.g., 20% for crypto)   │
│  max_position = equity × max_position_pct                  │
│                                                            │
│  FINAL_SIZE = min(adjusted_kelly, liquidity, sector, max)  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## 7. ENTRY EXECUTION

**File:** `paper_trader.py` → `_evaluate_entry()`

### Entry Checklist
```python
# All must pass:
✓ Market passes filters (liquidity, volume, spread)
✓ Strategy is enabled
✓ Side determined (YES/NO)
✓ Positive edge calculated
✓ Position size > min_position_size ($5)
✓ Not at max_open_positions limit
✓ Circuit breaker not triggered
✓ Strategy-specific expiry rules pass

# If all pass → CREATE POSITION
position = {
    'market_id': ...,
    'market_question': ...,
    'side': 'YES' or 'NO',
    'size': $X.XX,
    'entry_price': 0.XX,
    'strategy': 'alpha_directional',
    'entry_time': datetime,
    'sizing_breakdown': {...}  # Full audit trail
}
```

---

## 8. EXIT CONDITIONS

**File:** `paper_trader.py` → `_evaluate_exit()`, `_calculate_dynamic_exit_params()`

### Exit Modes

#### Mode 1: Dynamic Exit (Recommended)
```python
# Based on price extremeness and time-to-expiry:

if price < 0.15 or price > 0.85:  # Extreme
    max_gain = 50-70%
    tp = max_gain × 0.10  # Take profit at 10% of max gain
    sl = -10% to -15%
    
elif price < 0.30 or price > 0.70:  # Moderate
    max_gain = 30-50%
    tp = max_gain × 0.10
    sl = -15% to -20%
    
else:  # Mid-range (40-60%)
    # Hold to resolution (no TP)
    tp = None
    sl = -25% to -30%  # Protective only
```

#### Mode 2: Simple Exit (Legacy)
```python
# Per-strategy configurable:
exit_params = {
    'delta_neutral': {'tp': 8%, 'sl': -5%, 'max_hours': 48},
    'volatility': {'tp': 15%, 'sl': -10%, 'max_hours': 72},
    'alpha': {'tp': 25%, 'sl': -15%, 'max_hours': 168},
    'arbitrage': {'tp': 5%, 'sl': -3%, 'max_hours': 24}
}
```

### Exit Triggers
```python
# Checked every loop cycle:
if pnl_pct >= take_profit:
    EXIT("take_profit")
    
if pnl_pct <= stop_loss:
    EXIT("stop_loss")
    
if hours_held > max_hours:
    EXIT("time_limit")
    
if market_resolved:
    EXIT("resolution")
```

---

## 9. CONTINUOUS OPERATION

### Trading Loop Timing
```python
# Configurable: trades_per_10min (default: 500)
trade_interval = 600 / trades_per_10min  # ~1.2 seconds

while running:
    markets = fetch_markets()  # Up to 200 markets
    
    for market in markets[:100]:
        if market in positions:
            evaluate_exit(market)
        else:
            evaluate_entry(market)
        
        sleep(trade_interval / num_markets)
    
    record_equity_curve()
    check_circuit_breaker()
```

### Circuit Breaker
```python
# Stops trading if drawdown exceeds limit:
total_equity = cash + deployed_capital + unrealized_pnl
drawdown_pct = (initial_capital - total_equity) / initial_capital

if drawdown_pct > max_drawdown_pct:  # Default 5%
    STOP_TRADING("circuit_breaker")
```

---

## 10. MONITORING & ANALYTICS

### Real-time Tracking
- Open positions with live P&L
- Strategy-level equity curves
- Asset class distribution
- Win rate by oracle risk tier
- Sizing efficiency (actual vs Kelly)

### Session Analytics (saved on stop)
- Total trades, P&L, win rate
- Category breakdown
- Oracle tier performance
- Historical comparison charts

---

## Configuration Reference

| Setting | Default | Location |
|---------|---------|----------|
| trades_per_10min | 500 | /config |
| initial_capital | $10,000 | /config |
| max_drawdown_pct | 5% | /config |
| use_polymarket_sizer | true | /config → Position Sizer |
| oracle_multipliers | varies | /config → Position Sizer |
| exit_params | varies | /config → Exit Parameters |

---

## File Reference

| Component | File |
|-----------|------|
| Main Loop | `/app/backend/paper_trading/paper_trader.py` |
| Position Sizer | `/app/backend/ml/polymarket_position_sizer.py` |
| Market Classifier | `/app/backend/ml/market_classifier.py` |
| DQN Engine | `/app/backend/ml/dqn.py` |
| API Endpoints | `/app/backend/server.py` |
| Frontend | `/app/frontend/src/pages/PaperTrading.js` |
| Config UI | `/app/frontend/src/pages/Configuration.js` |
