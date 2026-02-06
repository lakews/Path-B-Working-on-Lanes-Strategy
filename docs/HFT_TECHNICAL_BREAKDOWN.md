# Lane 1: HFT (Market Maker) - Technical Breakdown

## Executive Summary

The HFT lane runs on a **500ms cycle** and operates in two distinct modes:
- **Smart Mode** (Alpha-Guided): Uses pre-computed fair values from the Alpha loop
- **Scalp Mode** (Microstructure Fallback): Pure orderbook analysis when Alpha cache is stale/unavailable

Both modes share the same **Chain of Command**: Signal → PositionSizer → RiskManager → Execution

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        HFT LOOP (Every 500ms)                                   │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                     MODE SELECTION                                      │   │
│   │                                                                         │   │
│   │   alpha_target = StrategyContext.get_target(market_id)                 │   │
│   │                                                                         │   │
│   │   IF alpha_target AND NOT stale:                                        │   │
│   │       └─→ SMART MODE (Alpha-Guided)                                    │   │
│   │   ELSE:                                                                │   │
│   │       └─→ SCALP MODE (Microstructure Fallback)                        │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│   BOTH MODES SHARE:                                                             │
│   ├─→ Cubic Inventory Skew (Risk Management)                                   │
│   ├─→ Adaptive Signal Smoothing (Noise Filtering)                              │
│   ├─→ Cliff Protection (Edge Zone Spread Widening)                             │
│   └─→ RiskManager.check_order() (SSOT Enforcement)                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Smart Mode (Alpha-Guided)

### Overview
Uses the **Alpha Loop's pre-computed fair value** to make informed quoting decisions.

### Data Source: HFTContext (Shared Cache)

```python
# Alpha Loop WRITES (every 30s):
HFTContext.set(market_id, MarketParams(
    fair_value=0.52,           # AI's "True Price"
    bias=0.15,                 # Bullish (+) or Bearish (-)
    base_spread_bps=50,        # Spread to quote in basis points
    max_inventory_skew=0.30,   # Max inventory imbalance
    reference_volatility=0.02, # Vol at analysis time
    confidence=0.72,           # AI confidence
    status=ContextStatus.ACTIVE
))

# HFT Loop READS (every 0.5s):
params = HFTContext.get(market_id)
if params is None or params.is_stale():
    # Fallback to Scalp Mode
```

### Staleness Check
```python
MAX_CONTEXT_AGE_SECONDS = 600  # 10 minutes

def is_stale(self) -> bool:
    age = time.time() - self.timestamp
    return age > MAX_CONTEXT_AGE_SECONDS
```

### Fair Value Blending

```python
# The HFT doesn't use Alpha's fair value directly.
# It blends AI + smoothed market price:

ai_fair_value = params.fair_value           # From Alpha (e.g., 0.52)
smoothed_price = smoother.smooth_signal(market_id, yes_price)  # EMA'd market price

blended_fair_value = (ai_fair_value * 0.70) + (smoothed_price * 0.30)
# Example: (0.52 * 0.7) + (0.50 * 0.3) = 0.514
```

**Why blend?**
- Alpha's fair value might be 30+ seconds old
- Market may have moved since Alpha's analysis
- Blending anchors to Alpha but adapts to current market

### Market Regime Classification

```python
# From Alpha's analysis, market falls into one of these regimes:

if price < 0.10:
    regime = "CONVEXITY_OPPORTUNITY"  # Whale Zone → Route to GAMMA
elif spread > 2%:
    regime = "MAKER_WIDE"             # Wide spread → Post limit orders
elif spread <= 2%:
    regime = "TAKER_TIGHT"            # Tight spread → Taker orders
else:
    regime = "ZOMBIE"                 # Skip market
```

### MAKER_WIDE Strategy (Spread 2-12%)

```python
# When spread is wide, we POST LIMIT ORDERS inside the spread
# We're "making the market" - earning the spread

# EDGE CALCULATION:
edge = fair_value - yes_price
min_hft_edge = 0.005  # 0.5% minimum edge

if abs(edge) > min_hft_edge:
    side = 'YES' if edge > 0 else 'NO'
    
    # Safety: Only trade YES unless sports arbitrage
    if side == 'NO' and not (is_sports and sports_config.allow_no_bets):
        return None  # Block NO trades
    
    # Size calculation
    hft_size = min(
        available_capital * 0.02,     # 2% max
        max_position_size * 0.5,      # 50% of normal max
        50.0                          # $50 hard cap
    )
    
    return {
        'strategy': 'hft_maker',
        'side': side,
        'size': hft_size,
        'edge': abs(edge)
    }
```

### TAKER_TIGHT Strategy (Spread < 2%)

```python
# When spread is tight, we use TAKER ORDERS
# We "cross the spread" to get filled immediately

edge = fair_value - yes_price
min_hft_edge = 0.008  # 0.8% minimum edge (higher for taker)

if abs(edge) > min_hft_edge:
    side = 'YES' if edge > 0 else 'NO'
    
    # Safety: Only YES unless sports
    if side == 'NO' and not is_sports:
        return None
    
    hft_size = min(
        available_capital * 0.02,
        max_position_size * 0.5,
        50.0
    )
    
    return {
        'strategy': 'hft_taker',
        'side': side,
        'size': hft_size,
        'edge': abs(edge)
    }
```

---

## Scalp Mode (Microstructure Fallback)

### Overview
When Alpha cache is unavailable or stale, HFT falls back to **pure orderbook analysis**.

### 5-Step Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     SCALP MODE WORKFLOW                                         │
│                                                                                 │
│   STEP 1: Context Fetch (HFTContext)                                            │
│   STEP 2: Adaptive Signal Smoothing                                             │
│   STEP 3: Cubic Inventory Skew                                                  │
│   STEP 4: Cliff Protection Spread                                               │
│   STEP 5: Inventory Guard                                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### STEP 1: Non-Blocking Context Fetch

```python
hft_ctx = get_hft_context()
params = hft_ctx.get(market_id)

# SAFETY: HFT NEVER trades blind
if params is None:
    return None  # Skip - no blind trades

if params.status == ContextStatus.KILL:
    return None  # Emergency stop

if params.status == ContextStatus.PAUSED:
    return None  # Temporarily paused

if params.is_stale():
    return None  # Data > 10 minutes old
```

### STEP 2: Adaptive Signal Smoothing

**Algorithm: EMA with Jump Detection**

```python
class AdaptiveSignalSmoother:
    """
    Philosophy: SMOOTH noise, but REACT instantly to news shocks.
    
    - Small move (< 3 cents): Apply EMA smoothing
    - Large move (≥ 3 cents): Bypass smoothing, react instantly
    """
    
    EMA_ALPHA = 0.2           # 20% new, 80% old
    JUMP_THRESHOLD = 0.03     # 3 cent move = jump
    
    def smooth_signal(self, market_id: str, new_raw_signal: float):
        prev_smoothed = self._signal_memory.get(market_id)
        
        if prev_smoothed is None:
            # First signal - initialize
            self._signal_memory[market_id] = new_raw_signal
            return new_raw_signal, "INITIALIZED"
        
        diff = abs(new_raw_signal - prev_smoothed)
        
        if diff > JUMP_THRESHOLD:
            # JUMP DETECTED - bypass smoothing
            smoothed = new_raw_signal
            action = "JUMP_DETECTED"
        else:
            # Apply EMA: smoothed = α*new + (1-α)*prev
            smoothed = (EMA_ALPHA * new_raw_signal) + ((1 - EMA_ALPHA) * prev_smoothed)
            action = "EMA_SMOOTHED"
        
        self._signal_memory[market_id] = smoothed
        return smoothed, action
```

**Example:**
```
Tick 1: 0.50 → Smoothed: 0.50 (INITIALIZED)
Tick 2: 0.51 → Smoothed: 0.502 (EMA: 0.2*0.51 + 0.8*0.50)
Tick 3: 0.52 → Smoothed: 0.5056 (EMA: 0.2*0.52 + 0.8*0.502)
Tick 4: 0.58 → Smoothed: 0.58 (JUMP: |0.58-0.5056| > 0.03)
```

### STEP 3: Cubic Inventory Skew

**The "Hockey Stick" Curve**

```python
class CubicInventorySkew:
    """
    Philosophy: PASSIVE with small inventory, AGGRESSIVE with large inventory.
    
    The cubic function x³ has gentle slope near zero, explodes near ±1.
    This lets us hold small positions without aggressive pricing,
    but rapidly increases discount/premium as we approach risk limits.
    """
    
    MAX_POSITION_LIMIT = 1000.0  # Max inventory
    SKEW_INTENSITY = 0.05       # Max skew at 100% (5 cents)
    
    def calculate_skew(self, current_position: float, raw_fair_value: float):
        # Normalize position to [-1.0, 1.0]
        pos_ratio = current_position / MAX_POSITION_LIMIT
        pos_ratio = clamp(pos_ratio, -1.0, 1.0)
        
        # CUBIC FUNCTION: x³
        skew_adjustment = (pos_ratio ** 3) * SKEW_INTENSITY
        
        # LONG position → LOWER fair value (encourage selling)
        adjusted_fair = raw_fair_value - skew_adjustment
        
        return clamp(adjusted_fair, 0.01, 0.99)
```

**Example (Inventory Impact):**
```
Inventory    pos_ratio    pos_ratio³    Skew (cents)
─────────    ─────────    ──────────    ────────────
100 (10%)    0.10         0.001         0.005 (negligible)
500 (50%)    0.50         0.125         0.625 (0.6 cent)
900 (90%)    0.90         0.729         3.65 (3.6 cents!)
```

**Visualization:**
```
    Skew
    ▲
    │                          ╱
    │                       ╱
    │                    ╱
    │               ╱╱╱
    │        ─────
    └──────────────────────────► Inventory %
         10%    50%    90%
         
    "Hockey Stick" - flat at start, steep at end
```

### STEP 4: Cliff Protection Spread

**Algorithm: Zone-Based Spread Multiplier**

```python
class CliffProtection:
    """
    Philosophy: Volatility INCREASES relative to price near edges.
    
    At $0.50, a 1-cent move = 2% of price
    At $0.05, a 1-cent move = 20% of price!
    
    Solution: Widen spreads near the "cliffs" (0 or 1)
    """
    
    CLIFF_ZONE_THRESHOLD = 0.15     # Within 15 cents of edge
    CLIFF_SPREAD_MULT = 2.0         # Double spread
    
    EXTREME_ZONE_THRESHOLD = 0.05   # Within 5 cents of edge
    EXTREME_SPREAD_MULT = 3.0       # Triple spread
    
    def calculate_spread_multiplier(self, price: float):
        # Distance from nearest edge (0 or 1)
        dist_from_edge = min(price, 1.0 - price)
        
        if dist_from_edge < EXTREME_ZONE_THRESHOLD:
            return 3.0, "EXTREME"   # Price < $0.05 or > $0.95
        elif dist_from_edge < CLIFF_ZONE_THRESHOLD:
            return 2.0, "CLIFF"     # Price < $0.15 or > $0.85
        else:
            return 1.0, "SAFE"      # Price $0.15 to $0.85
```

**Example:**
```
Price    Zone      Base Spread    Multiplier    Final Spread
─────    ────      ───────────    ──────────    ────────────
$0.50    SAFE      50 bps         1.0×          50 bps
$0.12    CLIFF     50 bps         2.0×          100 bps
$0.03    EXTREME   50 bps         3.0×          150 bps
```

### STEP 5: Inventory Guard

**Prevents Over-Concentration**

```python
# Calculate current inventory skew
total_hft_value = sum(p['size'] for p in hft_positions)
hft_long_value = sum(p['size'] for p in hft_positions if p['side'] == 'YES')

current_skew_ratio = hft_long_value / total_hft_value  # 0.0 to 1.0

# max_inventory_skew comes from HFTContext (default 0.30 = 30%)

# If bullish and already heavily LONG → BLOCK further buys
if bias > 0 and side == 'YES' and current_skew_ratio > (0.5 + max_inventory_skew):
    return None  # "Already 80% long, blocking buy"

# If bearish and already heavily SHORT → BLOCK further sells
if bias < 0 and side == 'NO' and current_skew_ratio < (0.5 - max_inventory_skew):
    return None  # "Already 80% short, blocking sell"
```

---

## Quote Generation Formula

### Complete Flow

```python
# 1. Get AI guidance
ai_fair_value = params.fair_value

# 2. Smooth market price
smoothed_price = smoother.smooth_signal(market_id, yes_price)

# 3. Blend AI + Market
blended_fair_value = (ai_fair_value * 0.70) + (smoothed_price * 0.30)

# 4. Apply inventory skew (CUBIC)
skewed_fair_value = skew.calculate_skew(
    current_position=current_inventory,
    raw_fair_value=blended_fair_value,
    max_position=1000,
    intensity=0.05
)

# 5. Get base spread from AI
base_spread = params.base_spread_bps / 10000  # e.g., 50 bps = 0.005

# 6. Apply volatility multiplier
vol_multiplier = volatility_calculator.get_vol_multiplier(market_id, ref_vol)

# 7. Apply cliff protection
spread_multiplier = cliff.calculate_spread_multiplier(skewed_fair_value)

# 8. FINAL SPREAD
final_spread = base_spread * vol_multiplier * spread_multiplier

# 9. Calculate bid/ask around skewed fair value
half_spread = final_spread / 2
my_bid = skewed_fair_value - half_spread
my_ask = skewed_fair_value + half_spread

# 10. Polymarket compliance: round to tick grid ($0.01)
my_bid = round(my_bid, 2)
my_ask = round(my_ask, 2)

# 11. Clamp to kill zone bounds [$0.01, $0.99]
my_bid = clamp(my_bid, 0.01, 0.98)
my_ask = clamp(my_ask, 0.02, 0.99)
```

### Example Calculation

```
INPUTS:
  ai_fair_value = 0.52
  yes_price = 0.50
  current_inventory = 300 (long)
  base_spread_bps = 50
  vol_multiplier = 1.2 (elevated vol)
  
STEP 3 (Blend):
  blended = (0.52 × 0.7) + (0.50 × 0.3) = 0.514

STEP 4 (Skew):
  pos_ratio = 300 / 1000 = 0.30
  pos_ratio³ = 0.027
  skew = 0.027 × 0.05 = 0.00135
  skewed_fair = 0.514 - 0.00135 = 0.5127

STEP 5-7 (Spread):
  base = 0.005 (50 bps)
  vol_mult = 1.2
  cliff_mult = 1.0 (SAFE zone)
  final_spread = 0.005 × 1.2 × 1.0 = 0.006 (60 bps)

STEP 8-9 (Quote):
  half_spread = 0.003
  my_bid = 0.5127 - 0.003 = 0.5097 → $0.51 (rounded)
  my_ask = 0.5127 + 0.003 = 0.5157 → $0.52 (rounded)

FINAL QUOTE:
  BID: $0.51
  ASK: $0.52
  SPREAD: $0.01 (1%)
```

---

## Position Sizing

### Formula

```python
# Confidence and edge multipliers
confidence_mult = min(1.0, params.confidence * 1.5)  # 0.72 → 1.0 capped
edge_mult = min(1.0, edge * 20)                      # 5% edge → 100%

# Calculate size
scalp_size_usd = min(
    available_capital * 0.02 * confidence_mult * edge_mult,  # 2% max
    25.0,                                                     # Cap at $25 per scalp
    max_position_size * 0.4                                   # 40% of normal max
)

scalp_size_usd = max(scalp_size_usd, 5.0)  # Floor at $5
```

### Interaction with RiskManager

```python
# SSOT Risk Check (Chain of Command)
check_result = risk_manager.check_order(
    lane='HFT',
    amount=scalp_size_usd,
    capital=deployed_capital,
    current_utilization=utilization,
    sector=asset_class,
    market_price=yes_price
)

# HFT limits from risk_config.json:
# - max_pos_usd: $50
# - max_pos_pct: 2%

# Example:
# scalp_size_usd = $75
# After RiskManager: adjusted_amount = $50 (trimmed to max_pos_usd)
```

### 2% vs $50 Interaction

```
Capital = $10,000

2% of capital = $200
HFT max_pos_usd = $50

The LOWER of the two applies:
  min($200, $50) = $50

So HFT trades are capped at $50 regardless of capital.
```

---

## Inventory Risk Management

### Three Lines of Defense

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     INVENTORY RISK MANAGEMENT                                   │
│                                                                                 │
│   LINE 1: Cubic Inventory Skew                                                  │
│   ─────────────────────────────                                                │
│   As inventory grows, quotes skew against building more:                        │
│   - 10% inventory → 0.005 cent skew (negligible)                               │
│   - 50% inventory → 0.625 cent skew (slight)                                   │
│   - 90% inventory → 3.65 cent skew (aggressive pricing)                        │
│                                                                                 │
│   LINE 2: Inventory Guard                                                       │
│   ─────────────────────                                                        │
│   Hard block when inventory exceeds max_inventory_skew (default 30%):          │
│   - Current: 80% long → BLOCK new YES buys                                     │
│   - Current: 80% short → BLOCK new NO buys                                     │
│                                                                                 │
│   LINE 3: RiskManager (SSOT)                                                    │
│   ────────────────────────                                                     │
│   Final enforcement via check_order():                                          │
│   - Max position USD ($50)                                                      │
│   - Max position % (2%)                                                         │
│   - Sector caps                                                                 │
│   - Global utilization                                                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Position Concentration Tracking

```python
# HFT tracks inventory per-market and aggregate:

hft_positions = [p for p in positions if strategy_path == 'HFT']

# Per-market inventory
market_position = positions.get(market_id, {}).get('size', 0)

# Aggregate HFT inventory
total_hft_value = sum(p['size'] for p in hft_positions)
hft_long_value = sum(p['size'] for p in hft_positions if p['side'] == 'YES')
hft_short_value = total_hft_value - hft_long_value

# Net inventory: positive = net long
current_inventory = hft_long_value - hft_short_value

# Skew ratio: 0.0 = all short, 0.5 = balanced, 1.0 = all long
skew_ratio = hft_long_value / max(total_hft_value, 1)
```

---

## Order Lifecycle Management

### Anti-Churn Hysteresis

```python
HYSTERESIS_THRESHOLD = 0.01  # 1 cent
ORDER_STALE_SECONDS = 120    # 2 minutes

def _prune_stale_orders(self, market_id: str, current_ai_price: float):
    """
    Prevents "order churn" - expensive cancelling and re-placing.
    
    Queue priority is valuable; don't cancel for small price changes.
    """
    order = self.active_orders.get(market_id)
    order_price = order['price']
    
    drift = abs(current_ai_price - order_price)
    
    # CHECK 1: BOUNDS VIOLATION
    if order_price < 0.01 or order_price > 0.99:
        return CANCEL  # Safety
    
    # CHECK 2: STALENESS
    age = now - order['timestamp']
    if age > ORDER_STALE_SECONDS:
        return CANCEL  # Refresh liquidity
    
    # CHECK 3: DRIFT (with hysteresis)
    if drift <= HYSTERESIS_THRESHOLD:
        return KEEP  # Anti-churn: small drift OK
    
    if drift > HYSTERESIS_THRESHOLD:
        return CANCEL  # AI changed mind significantly
```

---

## Exit Strategy

### Mechanical Exits (Delta-Neutral)

```python
# From risk_config.json:
EXIT_STRATEGY_CONFIG['hft_scalp'] = {
    'type': 'mechanical',
    'tp_pct': 0.015,     # +1.5% Take Profit
    'sl_pct': 0.015,     # -1.5% Stop Loss
    'max_hours': 4       # 4 hour max hold
}
```

### Exit Calculation

```python
entry_price = position['entry_price']
current_pnl = (current_price - entry_price) / entry_price

if current_pnl >= 0.015:
    # TAKE PROFIT: +1.5% gain
    await close_position(market_id, reason='TP_HFT')

elif current_pnl <= -0.015:
    # STOP LOSS: -1.5% loss
    await close_position(market_id, reason='SL_HFT')

elif hold_time > timedelta(hours=4):
    # TIME EXIT: 4 hours max
    await close_position(market_id, reason='TIME_HFT')
```

---

## Summary: Key Formulas

| Component | Formula |
|-----------|---------|
| **Blended Fair Value** | `0.7 × ai_fair_value + 0.3 × smoothed_price` |
| **Cubic Skew** | `skew = (position / max_position)³ × intensity` |
| **EMA Smoothing** | `smoothed = α × new + (1-α) × prev` where α=0.2 |
| **Jump Detection** | `if |new - prev| > 0.03: bypass smoothing` |
| **Cliff Spread** | `spread × {1.0 if SAFE, 2.0 if CLIFF, 3.0 if EXTREME}` |
| **Final Spread** | `base_spread × vol_mult × cliff_mult` |
| **Bid/Ask** | `bid = skewed_fair - spread/2`, `ask = skewed_fair + spread/2` |
| **Size** | `min(capital × 2% × confidence × edge_mult, $25, max_pos × 40%)` |
| **Exit TP** | `+1.5%` |
| **Exit SL** | `-1.5%` |
| **Max Hold** | `4 hours` |

---

*Document Version: 1.0*
*Last Updated: February 2026*
