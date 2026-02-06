# APEX TRADER - Complete Lane Flow Documentation
## End-to-End Trade Lifecycle for All 5 Lanes

**Last Updated:** February 2026
**Document Type:** Technical Specification

---

# 🔵 LANE 1: HFT (High-Frequency Trading)

## Philosophy
> "Never wait. Speed over optimization."

---

### PHASE 1: ANALYSIS

```
┌─────────────────────────────────────────────────────────────┐
│                    HFT SIGNAL GENERATION                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  AsyncSignalCache (Pre-computed, Background Thread)         │
│       │                                                      │
│       ├── Order Flow Imbalance (OFI) ──────► REAL-TIME      │
│       │   OFI = (bid_vol - ask_vol) / total_vol             │
│       │                                                      │
│       ├── LLM Sentiment ───────────────────► CACHED (TTL)   │
│       │   Read from cache, never wait                        │
│       │                                                      │
│       └── Price Velocity ──────────────────► REAL-TIME      │
│           Δprice / Δtime over last N ticks                   │
│                                                              │
│  DECISION: Execute if OFI > threshold AND price in range    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Signal Sources:**
| Source | Weight | Latency | Update Frequency |
|--------|--------|---------|------------------|
| Order Flow (OFI) | 60% | 0ms | Real-time |
| Cached Sentiment | 25% | 0ms (cached) | Background refresh |
| Price Velocity | 15% | 0ms | Real-time |

**Entry Criteria:**
```python
# File: paper_trader.py, _determine_strategy()
if strategy in ['delta_neutral', 'hft_maker', 'hft_scalp']:
    # HFT criteria:
    - Price between 0.35-0.65 (mid-range)
    - Volatility < 0.15 (stable)
    - Liquidity > $10,000
    - Spread < 5 cents
```

---

### PHASE 2: SIZING

```python
# HFT uses FIXED UNIT sizing (no Kelly)
# File: risk_config.py

CORE_MAX_USD = 100.0      # Hard cap per trade
CORE_MAX_PCT = 0.03       # 3% of deployed capital
MIN_TRADE_AMOUNT = 2.0    # Floor

# Calculation:
position_size = min(
    CORE_MAX_USD,                              # $100
    deployed_capital * CORE_MAX_PCT,           # 3% of capital
    available_hft_allocation                   # 35% lane limit
)

# Example ($10k capital, $8k deployed):
# position_size = min($100, $240, $2800) = $100
```

**Sizing Parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max USD | $100 | Limit single-trade exposure |
| Max % | 3% | Portfolio concentration limit |
| Min Trade | $2 | Cover fees + slippage |
| Kelly | N/A | Speed > optimization |

---

### PHASE 3: TRADE CAPTURE

```python
# File: paper_trader.py, _execute_paper_trade()

trade_record = {
    "id": uuid4(),
    "market_id": market_id,
    "question": market_data['question'],
    "strategy": "delta_neutral",  # or hft_maker, hft_scalp
    "lane": "HFT",
    "side": "YES" or "NO",
    "size": position_size,
    "entry_price": yes_price,
    "yes_entry_price": yes_price,
    "entry_time": datetime.now(UTC),
    "asset_class": "finance",
    "signal_source": "order_flow",
    
    # HFT-specific metadata
    "ofi_at_entry": order_flow_imbalance,
    "spread_at_entry": spread,
    "latency_ms": execution_latency,
}

# Storage:
self.paper_positions[market_id] = trade_record
self.strategy_stats['delta_neutral']['trades'] += 1
```

---

### PHASE 4: RISK LIMITS

| Limit Type | Value | Enforcement Point |
|------------|-------|-------------------|
| Position Cap | $100 / 3% | Entry validation |
| Lane Allocation | 35% of capital | Pre-trade check |
| Spread Limit | 5 cents | Entry filter |
| Liquidity Min | $10,000 | Entry filter |
| Circuit Breaker | 5% drawdown | Portfolio monitor |
| Max Concurrent | Unlimited | N/A |

```python
# Risk checks before entry:
if spread > 0.05:
    reject("Spread too wide")
if liquidity < 10000:
    reject("Insufficient liquidity")
if drawdown >= max_drawdown_pct:
    reject("Circuit breaker active")
```

---

### PHASE 5: EXIT POINTS

```python
# File: paper_trader.py, DEFAULT_EXIT_PARAMS

'delta_neutral': {
    'take_profit': 0.02,    # +2% TP
    'stop_loss': -0.02,     # -2% SL
    'max_hours': 4          # 4 hour time limit
}

# Exit triggers (checked every loop iteration):
pnl_pct = (current_price - entry_price) / entry_price

if pnl_pct >= take_profit:      # +2%
    exit("TAKE_PROFIT")
    
if pnl_pct <= stop_loss:        # -2%
    exit("STOP_LOSS")
    
if hold_hours >= max_hours:     # 4 hours
    exit("TIME_LIMIT")
```

**Exit Parameters:**
| Strategy | Take Profit | Stop Loss | Max Hold | Force Exit |
|----------|-------------|-----------|----------|------------|
| delta_neutral | +2% | -2% | 4h | No |
| hft_maker | +2% | -2% | 4h | No |
| hft_scalp | +1.5% | -1.5% | 2h | No |

---

# 🟢 LANE 2: ALPHA (The Strategist)

## Philosophy
> "Wait for quality. Conviction over speed."

---

### PHASE 1: ANALYSIS

```
┌─────────────────────────────────────────────────────────────┐
│                   ALPHA SIGNAL GENERATION                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  BLOCKING CALLS (Waits for completion)                      │
│       │                                                      │
│       ├── LLM Sentiment Analysis ──────────► 200-2000ms     │
│       │   await sentiment_analyzer.analyze()                 │
│       │   Returns: 0.0-1.0 (bullish probability)            │
│       │                                                      │
│       ├── Bayesian Mispricing Detection ───► 50-200ms       │
│       │   await bayesian_outlier.detect()                    │
│       │   Returns: confidence, direction                     │
│       │                                                      │
│       ├── Sharp Alignment (Smart Money) ───► 10-50ms        │
│       │   await sharp_detector.get_alignment()               │
│       │   Returns: 0.0-1.0 (institutional flow)             │
│       │                                                      │
│       └── Cross-Market Correlation ────────► 10-50ms        │
│           Check related markets for divergence               │
│                                                              │
│  FUSION: AlphaBayesianFusion.fuse(signals)                  │
│       │                                                      │
│       └── Output: posterior, confidence, dominant_signal    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Signal Sources:**
| Source | Weight | Latency | Purpose |
|--------|--------|---------|---------|
| LLM Sentiment | 35% | 200-2000ms | Market narrative |
| Sharp Alignment | 40% | 10-50ms | Smart money flow |
| Mispricing | 25% | 50-200ms | Statistical edge |

**Entry Criteria:**
```python
# File: paper_trader.py, _determine_strategy()
if strategy in ['alpha_directional', 'arbitrage']:
    # Alpha criteria:
    - Price < 0.25 OR > 0.75 (directional conviction)
    - OR strong sentiment divergence from price
    - OR sharp_alignment > 0.7 (institutional buying)
    - Liquidity > $2,000
```

---

### PHASE 2: SIZING

```python
# Alpha uses FRACTIONAL KELLY
# File: risk_config.py, paper_trader.py

KELLY_SCALING_FACTOR = 0.25   # 25% Kelly
MIN_KELLY_FRACTION = 0.10     # Floor at 10%
MAX_KELLY_FRACTION = 0.50     # Cap at 50%

# Kelly Criterion: f* = (p*b - q) / b
# Where: p = win_prob, b = odds, q = 1-p

def calculate_kelly(win_prob, odds):
    q = 1 - win_prob
    raw_kelly = (win_prob * odds - q) / odds
    
    # Scale by fraction
    scaled = raw_kelly * KELLY_SCALING_FACTOR
    
    # Clamp to bounds
    return max(MIN_KELLY_FRACTION, min(scaled, MAX_KELLY_FRACTION))

# Position size:
kelly_fraction = calculate_kelly(confidence, odds)
position_size = min(
    deployed_capital * kelly_fraction,
    CORE_MAX_USD,                              # $100
    deployed_capital * max_position_size_pct   # 3%
)

# Example (confidence=0.7, odds=2.5):
# raw_kelly = (0.7 * 2.5 - 0.3) / 2.5 = 0.58
# scaled = 0.58 * 0.25 = 0.145 (14.5%)
# clamped = max(0.10, min(0.145, 0.50)) = 0.145
# size = min($8000 * 0.145, $100, $240) = $100
```

**Sizing Parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Kelly Fraction | 25% | Conservative scaling |
| Min Kelly | 10% | Minimum conviction |
| Max Kelly | 50% | Prevent over-betting |
| Max Position | $100 / 3% | Portfolio limit |

---

### PHASE 3: TRADE CAPTURE

```python
trade_record = {
    "id": uuid4(),
    "market_id": market_id,
    "question": market_data['question'],
    "strategy": "alpha_directional",  # or arbitrage
    "lane": "ALPHA",
    "side": "YES" or "NO",
    "size": position_size,
    "entry_price": yes_price,
    "entry_time": datetime.now(UTC),
    "asset_class": asset_class,
    "signal_source": "bayesian_fusion",
    
    # Alpha-specific metadata
    "sentiment_score": sentiment,
    "sharp_alignment": sharp_alignment,
    "mispricing_confidence": mispricing,
    "bayesian_posterior": posterior,
    "kelly_fraction_used": kelly_fraction,
    "dominant_signal": dominant_signal,
}
```

---

### PHASE 4: RISK LIMITS

| Limit Type | Value | Enforcement Point |
|------------|-------|-------------------|
| Position Cap | $100 / 3% | Entry validation |
| Lane Allocation | 55% of capital | Pre-trade check |
| Liquidity Min | $2,000 | Entry filter |
| Confidence Min | 0.55 | Signal threshold |
| Circuit Breaker | 5% drawdown | Portfolio monitor |
| Correlation Limit | Max 30% same direction | Position check |

---

### PHASE 5: EXIT POINTS

```python
'alpha_directional': {
    'take_profit': 0.08,    # +8% TP
    'stop_loss': -0.05,     # -5% SL
    'max_hours': 12         # 12 hour time limit
}

'arbitrage': {
    'take_profit': 0.03,    # +3% TP
    'stop_loss': -0.03,     # -3% SL
    'max_hours': 6          # 6 hour time limit
}

# Dynamic exit adjustments by asset class:
EXIT_ADJUSTMENTS_BY_ASSET = {
    'politics': {'tp_mult': 1.2, 'sl_mult': 0.8, 'time_mult': 2.0},
    'crypto': {'tp_mult': 1.5, 'sl_mult': 1.2, 'time_mult': 0.5},
    # ...
}
```

**Exit Parameters:**
| Strategy | Take Profit | Stop Loss | Max Hold |
|----------|-------------|-----------|----------|
| alpha_directional | +8% | -5% | 12h |
| arbitrage | +3% | -3% | 6h |

---

# 🟣 LANE 3: GAMMA (Whale Zone)

## Philosophy
> "Risk 1 to make 10. Asymmetric payoffs only."

---

### PHASE 1: ANALYSIS

```
┌─────────────────────────────────────────────────────────────┐
│                   GAMMA SIGNAL GENERATION                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ORDERBOOK MICROSTRUCTURE ONLY (No LLM, No Sentiment)       │
│       │                                                      │
│       ├── Gap Detection ───────────────────────────────────│
│       │   if spread > 2 cents:                              │
│       │       → Place limit bid inside the gap              │
│       │                                                      │
│       ├── Wall Analysis ───────────────────────────────────│
│       │   if ask_volume < bid_volume * 0.3:                 │
│       │       → Wall is crumbling, SNIPE                    │
│       │   else:                                              │
│       │       → Wall is strong, JOIN the bid                │
│       │                                                      │
│       └── Price Filter ────────────────────────────────────│
│           ONLY trade if price $0.01 - $0.10 (OTM options)   │
│                                                              │
│  NO BAYESIAN, NO SENTIMENT - Pure microstructure            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Signal Sources:**
| Source | Weight | Purpose |
|--------|--------|---------|
| Gap Width | 40% | Entry opportunity |
| Wall Strength | 40% | Timing signal |
| Price Level | 20% | Asymmetry filter |

**Entry Criteria:**
```python
# File: trading/gamma_strategy.py
def is_gamma_candidate(market_data):
    price = market_data['yes_price']
    spread = market_data['spread']
    
    # STRICT price range for moonshots
    if not (0.01 <= price <= 0.10):
        return False
    
    # Spread must be tradeable
    if spread > 0.03:  # 3 cents max
        return False
    
    # Looking for 10x+ potential
    potential_return = (1.0 - price) / price
    return potential_return >= 10  # 10x minimum
```

---

### PHASE 2: SIZING

```python
# Gamma uses FIXED UNIT sizing (lottery ticket approach)
# File: risk_config.py

WHALE_MAX_USD = 15.0      # Hard cap - small position
WHALE_MAX_PCT = 0.01      # 1% of deployed capital

# NO KELLY - fixed unit for asymmetric bets
position_size = min(
    WHALE_MAX_USD,                    # $15 max
    deployed_capital * WHALE_MAX_PCT  # 1% of capital
)

# Rationale: Risk $15 to potentially make $150+ (10x)
# If 10% of moonshots hit 10x, you break even
# If 20% hit, you double your gamma allocation
```

**Sizing Parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max USD | **$15** | Small lottery ticket |
| Max % | **1%** | Minimal portfolio impact |
| Kelly | N/A | Fixed unit for lottery |
| Min Trade | $2 | Cover fees |

---

### PHASE 3: TRADE CAPTURE

```python
trade_record = {
    "id": uuid4(),
    "market_id": market_id,
    "question": market_data['question'],
    "strategy": "gamma_scalp",
    "lane": "GAMMA",
    "side": "YES",  # Always buying cheap YES
    "size": position_size,
    "entry_price": yes_price,
    "entry_time": datetime.now(UTC),
    "asset_class": asset_class,
    "signal_source": "microstructure",
    
    # Gamma-specific metadata
    "entry_type": "GAP" or "WALL_SNIPE" or "WALL_JOIN",
    "potential_return": (1 - entry_price) / entry_price,
    "spread_at_entry": spread,
    "wall_strength": wall_ratio,
}
```

---

### PHASE 4: RISK LIMITS

| Limit Type | Value | Enforcement Point |
|------------|-------|-------------------|
| Position Cap | **$15 / 1%** | Entry validation |
| Lane Allocation | 10% of capital | Pre-trade check |
| Price Range | $0.01 - $0.10 | Entry filter |
| Spread Limit | 3 cents | Entry filter |
| Circuit Breaker | 5% drawdown | Portfolio monitor |
| Max Concurrent | ~50 positions | Allocation limit |

---

### PHASE 5: EXIT POINTS

```python
# Gamma has UNIQUE exit logic for asymmetric plays

# File: paper_trader.py, GAMMA EXIT SIGNALS

# FREE ROLL: At 2x, sell half and hold remainder "for free"
if current_price >= entry_price * 2:
    sell_half()
    # Remaining position has $0 cost basis

# MOONBAG: At 5x, take full profit
if current_price >= entry_price * 5:
    sell_all()
    log("🌙 MOONBAG EXIT: 5x return!")

# STOP LOSS: Cut at 50% down (unusual for gamma)
if current_price <= entry_price * 0.5:
    sell_all()
    log("Gamma stop loss triggered")

# NO TIME LIMIT - hold until resolution or exit trigger
```

**Exit Parameters:**
| Trigger | Price Level | Action |
|---------|-------------|--------|
| Free Roll | 2x entry | Sell 50%, hold free |
| Moonbag | 5x entry | Sell 100% |
| Stop Loss | 0.5x entry | Sell 100% |
| Time Limit | None | Hold to resolution |

---

# 🟠 LANE 4: SPORTS (The Bookie)

## Philosophy
> "Real odds from bookmakers. No LLM hallucination."

---

### PHASE 1: ANALYSIS

```
┌─────────────────────────────────────────────────────────────┐
│                  SPORTS SIGNAL GENERATION                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  EXTERNAL API: The Odds API (Real Bookmaker Odds)           │
│       │                                                      │
│       ├── Fetch odds from William Hill, FanDuel, DraftKings │
│       │                                                      │
│       ├── Devig calculation ───────────────────────────────│
│       │   Remove bookmaker margin to get "fair value"       │
│       │   fair_value = implied_prob / (1 + vig)             │
│       │                                                      │
│       └── Weight: 85% real odds, 15% order flow             │
│                                                              │
│  LLM DISABLED - Cannot predict live sports scores           │
│  GitHub DISABLED - Irrelevant for sports                    │
│                                                              │
│  EDGE CALCULATION:                                          │
│       yes_edge = fair_value - polymarket_yes_price          │
│       no_edge = (1 - fair_value) - polymarket_no_price      │
│                                                              │
│  SIGNAL: Buy side with positive edge > min_edge + fees      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Signal Sources:**
| Source | Weight | Purpose |
|--------|--------|---------|
| The Odds API | 85% | Real bookmaker fair value |
| Order Flow | 15% | Market sentiment adjustment |
| LLM | 0% | DISABLED |

**Entry Criteria:**
```python
# File: strategies/sports_strategy.py
def generate_signal(market_data, fair_value):
    yes_price = market_data['yes_price']
    no_price = 1 - yes_price
    
    taker_fee = 0.02  # 2% Polymarket fee
    min_edge = 0.02   # 2% minimum edge
    
    yes_edge = fair_value - yes_price
    no_edge = (1 - fair_value) - no_price
    
    # Only trade if edge covers fees + minimum
    if yes_edge > min_edge + taker_fee:
        return Signal.BUY_YES
    elif no_edge > min_edge + taker_fee:
        return Signal.BUY_NO
    else:
        return Signal.HOLD
```

---

### PHASE 2: SIZING

```python
# Sports uses BINARY KELLY (aggressive for high win rate)
# File: risk_config.py, SportsConfig

kelly_fraction = 0.25     # 25% Kelly
min_kelly = 0.05          # 5% floor
max_kelly = 0.20          # 20% cap (conservative for sports)
max_position_size = 100   # $100 hard cap

# Binary Kelly for sports:
# f* = edge / odds

def sports_kelly(edge, odds):
    raw_kelly = edge / odds
    scaled = raw_kelly * kelly_fraction
    return max(min_kelly, min(scaled, max_kelly))

# Position size:
position_size = min(
    total_capital * allocation_pct * kelly_clamped,
    max_position_size,  # $100
)

# Example (edge=0.10, odds=2.0):
# raw_kelly = 0.10 / 2.0 = 0.05
# scaled = 0.05 * 0.25 = 0.0125
# clamped = max(0.05, min(0.0125, 0.20)) = 0.05 (hit floor)
# size = min($1500 * 0.05, $100) = $75
```

**Sizing Parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Kelly Fraction | 25% | Conservative base |
| Min Kelly | 5% | Ensure minimum bet |
| Max Kelly | 20% | Prevent over-betting |
| Max Position | $100 | Hard cap |
| Min Trade | $5 | Higher minimum for sports |

---

### PHASE 3: TRADE CAPTURE

```python
trade_record = {
    "id": uuid4(),
    "market_id": market_id,
    "question": market_data['question'],
    "strategy": "sports_arbitrage",
    "lane": "SPORTS",
    "side": "YES" or "NO",  # Both sides allowed!
    "size": position_size,
    "entry_price": yes_price,
    "entry_time": datetime.now(UTC),
    "asset_class": "sports",
    "signal_source": "odds_api",
    
    # Sports-specific metadata
    "fair_value": fair_value,
    "edge": edge,
    "odds_source": "the_odds_api",
    "sport_key": "americanfootball_nfl",
    "teams_matched": ["Seattle Seahawks", "Arizona Cardinals"],
    "bookmaker_odds": {
        "william_hill": 0.65,
        "fanduel": 0.64,
        "draftkings": 0.66
    }
}
```

---

### PHASE 4: RISK LIMITS

| Limit Type | Value | Enforcement Point |
|------------|-------|-------------------|
| Position Cap | $100 | Entry validation |
| Max Positions | 10 concurrent | Position counter |
| Min Edge | 2% | Signal threshold |
| Min Volume | $250 | Entry filter |
| Spread Limit | 15% | Entry filter (wide for sports) |
| Price Cap | 0.99 | Allow heavy favorites |
| Circuit Breaker | 5% drawdown | Portfolio monitor |

**Sports-Specific Overrides:**
```python
# Sports bypasses standard Alpha filters:
- NO-side betting: ALLOWED (required for arb)
- High prices (>0.95): ALLOWED (favorites)
- Wide spreads (>5%): ALLOWED (up to 15%)
- Low volume: REDUCED ($250 vs $1000)
```

---

### PHASE 5: EXIT POINTS

```python
# File: paper_trader.py, DEFAULT_EXIT_PARAMS

'sports_arbitrage': {
    'take_profit': 0.30,       # +30% TP (if line moves massively)
    'stop_loss': -1.00,        # -100% SL (ride to binary outcome)
    'max_hours': 24,           # 24 hour time limit
    'force_exit_on_time': True # Force sell if game delayed
}

# CRITICAL: Sports is BINARY OUTCOME
# - Selling early GUARANTEES loss due to spread
# - Ride to settlement unless 30%+ profit available
# - Only force exit if game delayed/cancelled (24h limit)
```

**Exit Parameters:**
| Trigger | Value | Rationale |
|---------|-------|-----------|
| Take Profit | +30% | Rare - only if line moves massively |
| Stop Loss | -100% | Ride to binary outcome |
| Time Limit | 24h | Catch delayed/cancelled games |
| Force Exit | Yes | Sell at market if time exceeded |

---

# 🟡 LANE 5: NEWS/EMERGENT (The Bridge)

## Philosophy
> "Slow analysis in background, fast execution from cache."

---

### PHASE 1: ANALYSIS

```
┌─────────────────────────────────────────────────────────────┐
│                   NEWS SIGNAL GENERATION                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  INPUT: Webhook (Push) OR Exa.ai (Pull)                     │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ STEP 1: LLM ANALYSIS (Event Resolution Adjudicator) │    │
│  │                                                      │    │
│  │ System Prompt enforces:                              │    │
│  │ - YES Literalism Rule (evaluate YES outcome only)   │    │
│  │ - Sector-specific evidence weighting                │    │
│  │ - Calibrated confidence (0.50-0.95 scale)           │    │
│  │                                                      │    │
│  │ Output:                                              │    │
│  │   is_relevant: true                                  │    │
│  │   is_bullish_for_yes: true                           │    │
│  │   confidence: 0.75                                   │    │
│  │   rationale: "Official Fed statement confirms cut"  │    │
│  └─────────────────────────────────────────────────────┘    │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ STEP 2: BAYESIAN UPDATE (EventBayesianUpdater)      │    │
│  │                                                      │    │
│  │ Prior: current_market_price (e.g., 0.30)            │    │
│  │ Likelihood: from LLM confidence + source reliability│    │
│  │                                                      │    │
│  │ Bayes' Theorem:                                      │    │
│  │ P(YES|news) = P(news|YES) × P(YES) / P(news)        │    │
│  │                                                      │    │
│  │ Output:                                              │    │
│  │   prior: 0.30                                        │    │
│  │   posterior: 0.85                                    │    │
│  │   bayes_factor: 12.79                                │    │
│  └─────────────────────────────────────────────────────┘    │
│       │                                                      │
│       ▼ Only if bayes_factor > 3.0                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ STEP 3: CACHE INJECTION                              │    │
│  │                                                      │    │
│  │ Key: emergent_signal:{market_id}                    │    │
│  │ TTL: 300s (5 min) or 3600s (resolution)             │    │
│  │                                                      │    │
│  │ HFT loop reads from cache → executes immediately    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Signal Sources:**
| Source | Weight | Purpose |
|--------|--------|---------|
| LLM (Event Adjudicator) | 100% | News interpretation |
| Source Reliability | Modifier | Weight confidence |
| Bayes Factor | Gate | Only inject if BF > 3.0 |

**Confidence Calibration:**
| Level | Confidence | Evidence Type |
|-------|------------|---------------|
| Noise | 0.50 | Irrelevant, opinion |
| Weak | 0.60 | Rumors, "sources say" |
| Strong | 0.75 | Official quotes, Reuters/AP |
| Resolution | 0.95 | Event concluded, facts |

---

### PHASE 2: SIZING

```python
# News uses BAYESIAN KELLY (posterior as win probability)
# File: paper_trader.py, _execute_news_sniper()

kelly_fraction = 0.25
max_position_pct = 0.05  # 5% cap for news trades

# Bayesian Kelly:
# Use posterior (updated probability) as win_prob
# Scale by LLM confidence

posterior = bayes_result.posterior      # e.g., 0.85
confidence = bayes_result.confidence    # e.g., 0.52
edge = abs(posterior - current_price)   # e.g., 0.55

# Only trade if edge is significant
if edge < 0.02:  # 2% minimum
    return NO_TRADE

# Size calculation
base_size_pct = posterior * kelly_fraction * confidence

position_size = min(
    deployed_capital * base_size_pct,
    deployed_capital * max_position_pct,  # 5% cap
)

# Minimum check
if position_size < 5.0:
    return NO_TRADE

# Example (posterior=0.85, confidence=0.52, capital=$8000):
# base_size_pct = 0.85 * 0.25 * 0.52 = 0.11
# size = min($8000 * 0.11, $8000 * 0.05) = min($880, $400) = $400
```

**Sizing Parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Kelly Fraction | 25% | Conservative scaling |
| Max Position | 5% | Higher than other lanes (conviction) |
| Min Edge | 2% | Cover fees |
| Min Trade | $5 | Higher minimum |
| Bayes Threshold | 3.0 | Strong evidence required |

---

### PHASE 3: TRADE CAPTURE

```python
trade_record = {
    "id": uuid4(),
    "market_id": market_id,
    "question": market_data['question'],
    "strategy": "news_sniper",
    "lane": "NEWS",
    "side": "YES" or "NO",
    "size": position_size,
    "entry_price": yes_price,
    "entry_time": datetime.now(UTC),
    "asset_class": asset_class,
    "signal_source": "emergent_news",
    
    # News-specific metadata
    "news_headline": news_headline[:200],
    "news_source": source,
    "llm_confidence": llm_confidence,
    "bayes_prior": prior,
    "bayes_posterior": posterior,
    "bayes_factor": bayes_factor,
    "signal_ttl": ttl_seconds,
}
```

---

### PHASE 4: RISK LIMITS

| Limit Type | Value | Enforcement Point |
|------------|-------|-------------------|
| Position Cap | 5% of capital | Entry validation |
| Bayes Factor Min | 3.0 | Signal gate |
| Min Edge | 2% | Entry filter |
| Rate Limit | 20/minute | Injection throttle |
| Signal TTL | 5-60 min | Auto-expiry |
| Circuit Breaker | 5% drawdown | Portfolio monitor |

**Source Reliability Weights:**
| Source | Reliability |
|--------|-------------|
| apnews.com | 0.95 |
| reuters.com | 0.95 |
| bloomberg.com | 0.90 |
| bbc.com | 0.90 |
| coindesk.com | 0.85 |
| twitter.com/x.com | 0.60 |
| unknown | 0.50 |

---

### PHASE 5: EXIT POINTS

```python
# File: paper_trader.py, DEFAULT_EXIT_PARAMS

'news_sniper': {
    'take_profit': 0.15,       # +15% TP (news edge decays quickly)
    'stop_loss': -0.10,        # -10% SL (tighter - news can be wrong)
    'max_hours': 4,            # 4 hour time limit (news is time-sensitive)
    'force_exit_on_time': True # Force sell at market
}

# News trades have SHORT validity windows
# - Act fast on breaking news
# - Exit fast before edge decays
# - Tighter stop loss (LLM can misinterpret)
```

**Exit Parameters:**
| Trigger | Value | Rationale |
|---------|-------|-----------|
| Take Profit | +15% | Take profits before edge decays |
| Stop Loss | -10% | Tighter SL (news can be wrong) |
| Time Limit | 4h | News is time-sensitive |
| Force Exit | Yes | Sell at market if expired |

---

# 📊 CROSS-LANE COMPARISON

## Entry Criteria

| Lane | Analysis | Latency | Blocking? |
|------|----------|---------|-----------|
| HFT | Cache + Order Flow | 0-12ms | NO |
| Alpha | LLM + Bayes + Sharp | 200-2000ms | YES |
| Gamma | Orderbook Only | 50-100ms | NO |
| Sports | Odds API + Flow | 50-200ms | YES |
| News | LLM + Bayes | 500-2000ms | YES (background) |

## Position Sizing

| Lane | Method | Max Size | Min Size |
|------|--------|----------|----------|
| HFT | Fixed Unit | $100 / 3% | $2 |
| Alpha | Fractional Kelly (25%) | $100 / 3% | $2 |
| Gamma | Fixed Unit | $15 / 1% | $2 |
| Sports | Binary Kelly | $100 | $5 |
| News | Bayesian Kelly | 5% | $5 |

## Exit Parameters

| Lane | Take Profit | Stop Loss | Time Limit |
|------|-------------|-----------|------------|
| HFT | +2% | -2% | 4h |
| Alpha | +3% to +8% | -3% to -5% | 6-12h |
| Gamma | 2x (free roll), 5x (moon) | 0.5x | None |
| Sports | +30% | -100% (binary) | 24h |
| News | +15% | -10% | 4h |

---

# 🔒 GLOBAL RISK CONTROLS

## Circuit Breaker
```python
if portfolio_drawdown >= 5%:
    circuit_breaker = True
    # Stop ALL new entries
    # Allow exits only
    # Alert admin
```

## Portfolio Limits
- Max 80% capital deployed at any time
- Max 3% in any single position
- Max 30% correlation exposure

## Per-Lane Allocation
- HFT: 35%
- Alpha: 55%  
- Gamma: 10%
- Sports: 15% (configurable, overlaps)
- News: Shared (uses Alpha/HFT capital)
