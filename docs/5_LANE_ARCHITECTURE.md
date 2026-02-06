# 5-Lane Trading Highway Architecture

## Executive Summary

The APEX Trader implements a **5-Lane Highway Architecture** that routes different trading strategies through isolated execution paths. Each lane has its own:
- Signal generation logic
- Position sizing formula
- Risk limits
- Exit conditions

This separation ensures that:
1. Fast strategies never wait for slow analysis
2. Each lane operates with appropriate risk parameters
3. Failures in one lane don't cascade to others

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MARKET DATA FEED                                  │
│              (WebSocket + REST Polling from Polymarket)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY ROUTER                                  │
│    Routes markets to appropriate lane based on category + liquidity      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │              │           │           │              │
         ▼              ▼           ▼           ▼              ▼
    ┌─────────┐   ┌─────────┐ ┌─────────┐ ┌─────────┐   ┌─────────┐
    │ LANE 1  │   │ LANE 2  │ │ LANE 3  │ │ LANE 4  │   │ LANE 5  │
    │   HFT   │   │  ALPHA  │ │  GAMMA  │ │ SPORTS  │   │  NEWS   │
    │ (Fast)  │   │ (Slow)  │ │(Sniper) │ │(Bookie) │   │(Bridge) │
    └─────────┘   └─────────┘ └─────────┘ └─────────┘   └─────────┘
         │              │           │           │              │
         └──────────────┴───────────┴───────────┴──────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      UNIFIED EXIT ENGINE                                 │
│        State → Strategy → Asset Class → Zone hierarchy                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PERFORMANCE TRACKING                                │
│              P&L, Strategy Stats, Asset Class Stats                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Lane 1: HFT (The Market Maker)

### Purpose
High-frequency, low-latency market making and scalping. Never blocks for slow operations.

### Capital Allocation
- **Default:** 35% of deployed capital
- **Config:** `RISK.HFT_ALLOCATION_PCT`

### Signal Generation

**Source:** `AsyncSignalCache` (pre-computed by Alpha Loop)

The HFT loop does NOT compute signals itself. It reads from a shared cache that Alpha populates:

```
┌───────────────┐     writes     ┌─────────────────┐     reads     ┌───────────────┐
│  Alpha Loop   │ ────────────▶  │ StrategyContext │ ◀──────────── │   HFT Loop    │
│   (30s cycle) │                │   (Shared State)│               │  (0.5s cycle) │
└───────────────┘                └─────────────────┘               └───────────────┘
```

**HFT Cycle (0.5s):**
1. Read market orderbook snapshot
2. Check `StrategyContext.get_target(market_id)` for Alpha's fair value
3. If target exists and not stale:
   - **Smart Mode:** Quote around Alpha's fair value
4. If no target:
   - **Scalp Mode:** Pure microstructure (spread capture)

### Position Sizing

**Formula:** Fixed unit size, never Kelly (too slow)

```python
hft_size = min(
    available_capital * HFT_UNIT_PCT,    # 2% default
    max_position_size * 0.5,
    $50  # Hard cap
)
```

**Liquidity Constraints:**
- `HFT_MIN_LIQUIDITY`: $10,000
- `HFT_MIN_VOLUME_24H`: $5,000

### Trade Execution

**Strategies:**
- `hft_scalp`: Pure spread capture, no directional bias
- `hft_maker`: Post limit orders inside the spread

**Side Selection:**
- **YES only** in most cases (safeguard against stale fair values)
- NO allowed only for Sports markets if `allow_no_bets: true`

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Inventory | $1,000 | `hft_execution.max_inventory_usd` |
| Skew Factor | 5% | Bias quotes when inventory builds |
| Max Position % | 10% | Of HFT capital allocation |
| Spread Tolerance | 12% | `MAX_SPREAD_HFT` |

### Exit Strategy

**Type:** Mechanical

| Condition | Action |
|-----------|--------|
| +1.5% Gain | Close All |
| -1.5% Loss | Close All |
| 4 Hours | Time-based close |

**Config:** `EXIT_STRATEGY_CONFIG['delta_neutral']` (HFT uses delta_neutral exits)

---

## Lane 2: ALPHA (The Strategist)

### Purpose
Slower, conviction-driven directional trading based on deep analysis.

### Capital Allocation
- **Default:** 55% of deployed capital
- **Config:** `RISK.ALPHA_ALLOCATION_PCT`

### Signal Generation

**Sources:**
1. **Bayesian Model:** Prior probabilities from historical data
2. **LLM Sentiment:** Real-time analysis via `EnhancedSentimentAnalyzer`
3. **RL Confidence:** Learned market patterns via `RLAdaptiveEngine`
4. **Sharp Money Detection:** `SharpDetector` for institutional flow
5. **Cross-Market Correlation:** Related market movement

**Signal Fusion (`SignalFusionEngine`):**

```
┌────────────────────────────────────────────────────────────────────────┐
│                      BAYESIAN SIGNAL FUSION                            │
│                                                                        │
│   P(YES | data) = P(data | YES) × P(YES) / P(data)                    │
│                                                                        │
│   Where P(YES) is the prior from:                                      │
│   - Market price (baseline)                                            │
│   - LLM sentiment (weighted)                                           │
│   - RL confidence (weighted)                                           │
│   - Sharp money signal (weighted)                                      │
└────────────────────────────────────────────────────────────────────────┘
```

**Alpha Weights (configurable):**
```python
alpha_weights = {
    'sentiment_weight': 0.50,      # LLM sentiment influence
    'rl_weight': 0.60,             # RL model influence
    'sharp_weight': 0.30,          # Sharp money influence
    'min_rl_confidence': 0.15,     # Minimum RL confidence to act
}
```

**Alpha Loop Cycle (30s):**
1. Fetch market data with volume/liquidity
2. Run LLM sentiment analysis
3. Run RL prediction
4. Detect sharp money flow
5. Fuse signals via Bayesian model
6. Write `fair_value` to `StrategyContext` (for HFT)
7. Evaluate Alpha trades

### Position Sizing

**Formula:** Binary Kelly Criterion

```python
# Binary Kelly (for prediction markets)
edge = model_probability - market_price
kelly_raw = edge / (1 - market_price)

# Fractional Kelly with bounds
kelly_fraction = clamp(
    kelly_raw * KELLY_SCALING_FACTOR,
    MIN_KELLY_FRACTION,
    MAX_KELLY_FRACTION
)

# Apply utilization brake
utilization = deployed_capital / total_capital
brake = max(0, 1 - (utilization / UTILIZATION_HARD_STOP) ^ UTILIZATION_EXPONENT)

# Final size
position_size = deployed_capital * kelly_fraction * brake * liquidity_scalar
```

**Liquidity Constraints (Price-Dependent):**
| Price Zone | Min Liquidity | Min Volume |
|------------|---------------|------------|
| Core (≥$0.10) | $1,000 | $1,000 |
| Whale (<$0.10) | $500 | $500 |

### Trade Execution

**Strategies:**
- `alpha_directional`: Primary directional strategy
- `arbitrage`: Cross-market mispricing (routed to Alpha, not HFT)

**Side Selection:**
- Based on `edge` direction from Bayesian fusion
- Bullish sentiment (>0.55) → YES
- Bearish sentiment (<0.45) → NO
- Neutral band → No trade

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Position | $100 | `CORE_MAX_USD` |
| Max Position % | 3% | `CORE_MAX_PCT` of deployed |
| Event Exposure | 15% | `MAX_EVENT_EXPOSURE_PCT` |
| Sector Caps | Variable | e.g., Crypto 20%, Politics 25% |
| Spread Tolerance | 5% | `MAX_SPREAD_ALPHA` (tighter) |

### Exit Strategy

**Type:** Complex (Asset Class Modifiers)

**Base Parameters (`alpha_directional`):**
- Take Profit: 30%
- Stop Loss: 15%
- Max Hold: 72 hours

**Asset Class Modifiers:**

| Asset Class | TP Mult | SL Mult | Time Mult | Trailing | Notes |
|-------------|---------|---------|-----------|----------|-------|
| Politics | 1.2x | 1.0x | 3.0x | Yes | Momentum matters |
| Finance | 1.0x | 1.2x | 1.0x | Yes | Stable, macro noise |
| Crypto | 1.5x | 1.5x | 0.5x | Yes | High volatility |
| Sports | 1.0x | 1.5x | 0.25x | No | Fixed duration |
| Entertainment | 2.0x | 0.8x | 2.0x | No | Viral events |
| Science | 2.0x | 0.5x | 5.0x | No | Binary outcomes |

**Example (Crypto Alpha Trade):**
- Base TP: 30% × 1.5 = **45%**
- Base SL: 15% × 1.5 = **22.5%**
- Base Time: 72h × 0.5 = **36 hours**

---

## Lane 3: GAMMA (The Sniper)

### Purpose
Opportunistic convexity hunting in low-liquidity, out-of-the-money markets.

### Capital Allocation
- **Default:** 10% of deployed capital
- **Config:** `RISK.GAMMA_ALLOCATION_PCT`

### Signal Generation

**Source:** `GammaTrader` (isolated module)

The Gamma strategy scans for **mispriced convexity**—cheap options that can pay off big.

**Entry Logic ("Gap vs. Wall"):**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        GAP VS. WALL DETECTION                            │
│                                                                          │
│   A "Gap" is an orderbook imbalance:                                     │
│   - Thin asks + strong bids = Upward pressure                            │
│   - Thin bids + strong asks = Downward pressure                          │
│                                                                          │
│   A "Wall" is a large order at a specific price level.                   │
│   - Buying before the wall = Riding the breakout                         │
│   - Selling into the wall = Fading the resistance                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Gamma Strategy Selection:**
- Price < $0.10 → Whale Zone → `CONVEXITY_OPPORTUNITY`
- Orderbook gap detected → Entry signal
- Wall detected → Position management signal

### Position Sizing

**Formula:** Fixed small size (lottery ticket)

```python
gamma_size = min(
    available_capital * WHALE_MAX_PCT,   # 1% default
    WHALE_MAX_USD,                       # $15 hard cap
    liquidity * MAX_LIQUIDITY_CONSUMPTION  # 10% of depth
)
```

**Liquidity Constraints:**
- `GAMMA_MIN_LIQUIDITY`: $250 (lowest floor)
- `GAMMA_MIN_VOLUME_24H`: $250

### Trade Execution

**Strategy:** `gamma_scalp`

**Entry Types:**
1. **Gap Buy:** Buy YES when asks are thin
2. **Wall Ride:** Buy before a support wall

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Position | $15 | `WHALE_MAX_USD` |
| Max Position % | 1% | `WHALE_MAX_PCT` |
| Max Spread (cents) | $0.03 | Absolute, not percentage |

### Exit Strategy

**Type:** Whale Zone (Unique Logic)

The Gamma exit is designed for asymmetric payoffs:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      GAMMA EXIT HIERARCHY                                │
│                                                                          │
│   1. Stop Loss: Price drops to 50% of entry                              │
│      → Exit ALL immediately                                              │
│                                                                          │
│   2. Free Roll: Price doubles (2x entry)                                 │
│      → Sell 50% to recover principal                                     │
│      → Let remaining 50% ride as "house money"                           │
│                                                                          │
│   3. Moonbag: Price hits 5x entry                                        │
│      → Sell 100% of remaining position                                   │
│                                                                          │
│   4. Time Limit: 168 hours (7 days)                                      │
│      → Close any remaining position                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Exit Parameters:**
```python
EXIT_STRATEGY_CONFIG['gamma_scalp'] = {
    'type': 'whale',
    'action': 'GAMMA_EXIT',
    'stop_multiple': 0.50,      # Exit at 50% of entry
    'free_roll_multiple': 2.0,  # Sell 50% at 2x
    'moonbag_multiple': 5.0,    # Sell 100% at 5x
    'max_hours': 168,           # 7 days
}
```

---

## Lane 4: SPORTS (The Bookie)

### Purpose
Isolated lane for sports arbitrage against real bookmaker odds.

### Capital Allocation
- **Default:** 15% of deployed capital
- **Config:** `SportsConfig.allocation_pct`

### Signal Generation

**Source:** External API ("The Odds API")

The Sports lane is unique—it **bypasses** all standard signal generation:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SPORTS SIGNAL GENERATION                             │
│                                                                          │
│   1. Fetch odds from The Odds API                                        │
│      - NBA, NFL, MLB, NHL, Soccer, MMA                                   │
│                                                                          │
│   2. Compare to Polymarket price                                         │
│      - Polymarket YES = 0.60                                             │
│      - Implied odds from books = 0.55                                    │
│      - Edge = 0.60 - 0.55 = 5%                                           │
│                                                                          │
│   3. If edge > min_edge (2%):                                            │
│      - Generate SportsTradeSignal                                        │
│      - Route to execution                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

**Sports Detection (`is_sports_market()`):**
- Keyword matching: "game", "match", "win", team names
- Category tag: `sports`
- Question pattern: "[Team A] vs [Team B]"

### Position Sizing

**Formula:** Sports-specific Kelly

```python
# Edge calculation
edge = polymarket_price - implied_odds_from_books - taker_fee

# Kelly sizing
kelly_raw = edge / (1 - implied_odds)

# Clamped Kelly
kelly_fraction = clamp(kelly_raw * 0.25, 0.05, 0.20)

# Final size
position_size = min(
    sports_capital * kelly_fraction,
    max_position_size,  # $100 default
    min_trade_size      # $5 floor
)
```

**Sports Config:**
```python
SportsConfig = {
    'kelly_fraction': 0.25,
    'min_kelly': 0.05,
    'max_kelly': 0.20,
    'min_trade_size': 5.0,
}
```

### Trade Execution

**Strategy:** `sports_arbitrage`

**Key Feature: NO-Side Betting Allowed**
- Unlike other lanes, sports allows betting on NO
- Required for proper arbitrage (hedging both sides)
- Config: `allow_no_bets: True`

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max Position | $100 | `SportsConfig.max_position_size` |
| Max Positions | 10 | Concurrent sports positions |
| Min Edge | 2% | After fees |
| Max Spread | 15% | Sports markets are often wide |
| Price Range | $0.01 - $0.99 | Allow heavy favorites |

### Exit Strategy

**Type:** Mechanical (Time-Bounded)

Sports events have fixed end times, so exits are simpler:

```python
EXIT_STRATEGY_CONFIG['sports_arbitrage'] = {
    'type': 'mechanical',
    'action': 'CLOSE_ALL',
    'tp_pct': 0.30,     # +30% Take Profit
    'sl_pct': 0.25,     # -25% Stop Loss (wide for volatility)
    'max_hours': 48,    # Close before event
}
```

**Exit Logic:**
1. **Take Profit:** +30% gain → Close all
2. **Stop Loss:** -25% loss → Close all
3. **Time Limit:** 48 hours → Close before event starts
4. **Event Resolution:** Market resolves → Automatic

---

## Lane 5: NEWS (The Injector)

### Purpose
Bridge between slow LLM analysis and fast HFT execution. Processes breaking news and injects actionable signals.

### Capital Allocation
- Uses existing HFT/Alpha allocations (no separate pool)
- Signals are executed via HFT loop

### Signal Generation

**The Async Injection Pattern:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NEWS LANE ARCHITECTURE                                │
│                                                                          │
│   ┌───────────────┐                                                      │
│   │  NEWS SOURCE  │ ──────┐                                              │
│   │ (Webhook/Exa) │       │                                              │
│   └───────────────┘       │                                              │
│                           ▼                                              │
│   ┌─────────────────────────────────────────┐                            │
│   │           NEWS INJECTOR                 │                            │
│   │                                         │                            │
│   │  1. Receive news headline               │                            │
│   │  2. Call LLM (Event Resolution          │                            │
│   │     Adjudicator prompt)                 │                            │
│   │  3. Calculate Bayesian posterior        │                            │
│   │  4. If BF > 3.0: Inject to cache        │                            │
│   └─────────────────────────────────────────┘                            │
│                           │                                              │
│                           ▼                                              │
│   ┌─────────────────────────────────────────┐                            │
│   │       EMERGENT SIGNAL CACHE             │                            │
│   │   (In-Memory, TTL-based)                │                            │
│   │                                         │                            │
│   │   Key: emergent_signal:{market_id}      │                            │
│   │   Value: {direction, posterior, BF}     │                            │
│   └─────────────────────────────────────────┘                            │
│                           │                                              │
│                           ▼                                              │
│   ┌─────────────────────────────────────────┐                            │
│   │           HFT LOOP                      │                            │
│   │                                         │                            │
│   │  Every 0.5s: Check cache for signals    │                            │
│   │  If signal found: Execute news_sniper   │                            │
│   └─────────────────────────────────────────┘                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**LLM Analysis (`EmergentLLMService`):**

The LLM uses a specialized prompt called "Event Resolution Adjudicator":

```
Key Concept: The "YES" Literalism Rule

You must evaluate the impact strictly on the YES outcome of the specific 
contract, not the general sentiment of the subject.

Example:
- Question: "Will Bitcoin DROP below $60k?"
- News: "Bitcoin rallies to $72k on ETF approval."
- Analysis: Good for Bitcoin, but FATAL for the YES share.
- Output: is_bullish_for_yes: false
```

**Bayesian Update (`EventBayesianUpdater`):**

```python
# Bayes Factor calculation
BF = P(news | YES true) / P(news | NO true)

# Actionable thresholds
BF > 3.0  = Strong evidence (inject signal)
BF > 10.0 = Very strong evidence (high priority)
BF < 3.0  = Insufficient evidence (skip)
```

**Source Reliability Weights:**
```python
SOURCE_RELIABILITY = {
    'apnews.com': 0.95,
    'reuters.com': 0.95,
    'bloomberg.com': 0.90,
    'coindesk.com': 0.85,
    'twitter.com': 0.60,
    'unknown': 0.50
}
```

### Position Sizing

**Formula:** Kelly based on posterior probability

```python
# Calculate edge from news analysis
posterior = bayes_update(prior=market_price, news=news_item)
edge = abs(posterior - market_price)

# Kelly sizing with news confidence
kelly_raw = edge / (1 - posterior)
kelly_fraction = kelly_raw * news_config.kelly_fraction * llm_confidence

# Final size
position_size = min(
    deployed_capital * kelly_fraction,
    deployed_capital * MAX_POSITION_PCT,  # 5% cap
)
```

### Trade Execution

**Strategy:** `news_sniper`

The HFT loop checks for news signals on every cycle:

```python
# In HFT loop
async def _check_news_signals(self, market_id):
    signal = await self._signal_cache.get(f"emergent_signal:{market_id}")
    if signal and not signal.get('expired'):
        # Execute news_sniper strategy
        await self._execute_news_sniper(market_id, signal)
```

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Min Bayes Factor | 3.0 | Evidence threshold |
| Max Position % | 5% | Of deployed capital |
| Signal TTL | 300s | 5 minute default |
| Resolution TTL | 3600s | 1 hour for resolution news |
| Max Injections | 20/min | Rate limiting |

### Exit Strategy

**Type:** Time-Decay + Resolution

News signals have natural expiration:

1. **Signal TTL:** Signal expires after 5 minutes (default)
2. **Resolution News:** Longer TTL (1 hour) for market-resolving events
3. **Standard Exits:** Falls back to the underlying strategy's exit rules

---

## Cross-Lane Safeguards

### Category Isolation

```python
def route_to_lane(market_data):
    """Route market to appropriate lane"""
    
    # Sports detection (highest priority)
    if is_sports_market(market_data['question']):
        return 'SPORTS'
    
    # News signal check
    if has_emergent_signal(market_data['id']):
        return 'NEWS'
    
    # Price zone check
    price = market_data['yes_price']
    if price < WHALE_PRICE_CEILING:  # < $0.10
        return 'GAMMA'
    
    # Default to Alpha for analysis
    return 'ALPHA'
```

### Bayesian Quarantine

**Critical Rule:** Each lane has its own Bayesian model:
- **Alpha:** `SignalFusionEngine` with LLM + RL + Sharp
- **News:** `EventBayesianUpdater` (isolated, event-specific)

**Why?** Mixing them would contaminate priors. News events are discrete; Alpha is continuous.

### Emergency Stop Loss

All lanes share a global emergency stop:

```python
async def _emergency_stoploss_task(self):
    """Global circuit breaker"""
    while self.running:
        # Check drawdown
        current_drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        
        if current_drawdown > MAX_DRAWDOWN_PCT:
            logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")
            self.circuit_breaker_triggered = True
            await self._close_all_positions()
            break
        
        await asyncio.sleep(5)
```

---

## Summary Table

| Lane | Speed | Capital | Signal Source | Sizing | Exit Type | Unique Feature |
|------|-------|---------|---------------|--------|-----------|----------------|
| HFT | 0.5s | 35% | Cache (from Alpha) | Fixed 2% | Mechanical | Never blocks |
| ALPHA | 30s | 55% | LLM + RL + Bayes | Kelly | Asset-modified | Deep analysis |
| GAMMA | 30s | 10% | Orderbook gaps | Fixed 1% | Whale exits | 5x moonbag |
| SPORTS | 30s | 15%* | External odds API | Sports Kelly | Time-bounded | NO bets allowed |
| NEWS | Event | Shared | LLM + Event Bayes | News Kelly | TTL-based | Async injection |

*Sports allocation is separate from the HFT/Alpha/Gamma split.

---

## Configuration Reference

### File Locations

- **Risk Config:** `/app/backend/risk_config.py`
- **Paper Trader:** `/app/backend/paper_trading/paper_trader.py`
- **News Injector:** `/app/backend/services/news_injector.py`
- **Event Bayes:** `/app/backend/bayesian_math/event_bayes.py`
- **LLM Service:** `/app/backend/services/llm_service.py`
- **Signal Cache:** `/app/backend/services/signal_cache.py`

### Key Constants

```python
# Capital Allocation (risk_config.py)
HFT_ALLOCATION_PCT = 35.0
ALPHA_ALLOCATION_PCT = 55.0
GAMMA_ALLOCATION_PCT = 10.0

# Kelly Bounds
KELLY_SCALING_FACTOR = 0.25
MIN_KELLY_FRACTION = 0.10
MAX_KELLY_FRACTION = 0.50

# Liquidity Thresholds
HFT_MIN_LIQUIDITY = 10000.0
ALPHA_CORE_LIQUIDITY = 1000.0
GAMMA_MIN_LIQUIDITY = 250.0

# Exit Defaults
CORE_MAX_USD = 100.0
WHALE_MAX_USD = 15.0
```

---

## Appendix: Default Exit Parameters

### Strategy Defaults (`EXIT_STRATEGY_CONFIG`)

```python
EXIT_STRATEGY_CONFIG = {
    'arbitrage': {
        'type': 'mechanical',
        'tp_pct': 0.02,
        'sl_pct': 0.02,
        'max_hours': 6,
    },
    'delta_neutral': {
        'type': 'mechanical',
        'tp_pct': 0.015,
        'sl_pct': 0.015,
        'max_hours': 4,
    },
    'alpha_directional': {
        'type': 'complex',
        'profit_trigger_pct': 0.30,
        'base_sl_pct': 0.15,
        'base_max_hours': 72,
    },
    'gamma_scalp': {
        'type': 'whale',
        'stop_multiple': 0.50,
        'free_roll_multiple': 2.0,
        'moonbag_multiple': 5.0,
        'max_hours': 168,
    },
    'sports_arbitrage': {
        'type': 'mechanical',
        'tp_pct': 0.30,
        'sl_pct': 0.25,
        'max_hours': 48,
    },
}
```

### Alpha Asset Modifiers (`EXIT_ALPHA_ASSET_MODIFIERS`)

```python
EXIT_ALPHA_ASSET_MODIFIERS = {
    'politics': {'profit_mult': 1.2, 'sl_mult': 1.0, 'time_mult': 3.0},
    'finance': {'profit_mult': 1.0, 'sl_mult': 1.2, 'time_mult': 1.0},
    'crypto': {'profit_mult': 1.5, 'sl_mult': 1.5, 'time_mult': 0.5},
    'sports': {'profit_mult': 1.0, 'sl_mult': 1.5, 'time_mult': 0.25},
    'entertainment': {'profit_mult': 2.0, 'sl_mult': 0.8, 'time_mult': 2.0},
    'science': {'profit_mult': 2.0, 'sl_mult': 0.5, 'time_mult': 5.0},
}
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: APEX Trading Bot Development Team*
