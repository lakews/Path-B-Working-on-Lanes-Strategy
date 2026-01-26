# APEX TRADER - Two-Speed Hybrid Architecture

## Overview

The system has been re-architected into a **Two-Speed Hybrid** design that separates execution into:

1. **Fast Path (HFT)**: Sub-second market making with inventory management
2. **Slow Path (Alpha)**: ML-driven directional trades with full signal generation

This ensures the execution loop **NEVER waits** for slow operations (LLM calls, complex ML).

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        TWO-SPEED HYBRID ARCHITECTURE                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                        CAPITAL ALLOCATION                            │  │
│   │   ┌───────────────────┐      ┌───────────────────┐                  │  │
│   │   │  HFT CAPITAL      │      │  ALPHA CAPITAL    │                  │  │
│   │   │  40% ($4,000)     │      │  60% ($6,000)     │                  │  │
│   │   │                   │      │                   │                  │  │
│   │   │  Max Pos: 10%     │      │  Max Pos: 25%     │                  │  │
│   │   │  ($400 each)      │      │  ($1,500 each)    │                  │  │
│   │   │  3 pos/market     │      │  1 pos/market     │                  │  │
│   │   └───────────────────┘      └───────────────────┘                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                           FAST PATH (HFT)                           │  │
│   │                        < 100ms latency target                        │  │
│   │   ┌─────────────────────────────────────────────────────────────┐   │  │
│   │   │                                                              │   │  │
│   │   │   Order Book ───► OFI Calculation ───► Inventory Skew       │   │  │
│   │   │       │                  │                    │              │   │  │
│   │   │       ▼                  ▼                    ▼              │   │  │
│   │   │   Spread Check    Quote Adjustment    Asymmetric Quotes     │   │  │
│   │   │       │                  │                    │              │   │  │
│   │   │       └──────────────────┴────────────────────┘              │   │  │
│   │   │                          │                                   │   │  │
│   │   │                          ▼                                   │   │  │
│   │   │                 MAKER ORDER PLACEMENT                        │   │  │
│   │   │                                                              │   │  │
│   │   └─────────────────────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                          SLOW PATH (ALPHA)                          │  │
│   │                        Background processing                         │  │
│   │   ┌─────────────────────────────────────────────────────────────┐   │  │
│   │   │                                                              │   │  │
│   │   │   LLM Sentiment ──┐                                         │   │  │
│   │   │                    │                                         │   │  │
│   │   │   Polymarket ─────┼───► Signal Fusion ───► Bayesian         │   │  │
│   │   │   Sentiment        │          │           Posterior          │   │  │
│   │   │                    │          │               │              │   │  │
│   │   │   GitHub ─────────┘          │               │              │   │  │
│   │   │   Activity                    │               │              │   │  │
│   │   │                               ▼               ▼              │   │  │
│   │   │                        ASYNC CACHE ◄───────────              │   │  │
│   │   │                           │                                  │   │  │
│   │   │                           ▼                                  │   │  │
│   │   │           DIRECTIONAL TRADE (when edge detected)            │   │  │
│   │   │                                                              │   │  │
│   │   └─────────────────────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## New Files Created

| File | Purpose |
|------|---------|
| `backend/trading/strategy_manager.py` | Capital allocation between HFT/Alpha strategies |
| `backend/execution/spread_policy.py` | Centralized spread constants and EV calculations |
| `backend/execution/async_signal_cache.py` | Background LLM updates, instant cache reads |

---

## Key Components

### 1. Strategy Manager (`strategy_manager.py`)

Manages capital allocation between HFT and Alpha paths.

```python
from trading.strategy_manager import StrategyManager, StrategyType

# Initialize with $10K capital
manager = StrategyManager(
    total_capital=10000,
    hft_allocation_pct=0.40,   # 40% to HFT
    alpha_allocation_pct=0.60  # 60% to Alpha
)

# Get allocation for a market
allocation = manager.allocate_funds(market_id="0x1234")
print(allocation.hft_allocation.max_position_usd)   # $400
print(allocation.alpha_allocation.max_position_usd) # $1,500
```

### 2. Spread Policy (`spread_policy.py`)

Centralized spread constants - single source of truth.

```python
from execution.spread_policy import (
    MAX_SPREAD_HFT,          # 25%
    MAX_SPREAD_ALPHA,        # 15%
    SPREAD_GRID_VALUES,      # [0.03, 0.05, 0.07]
    SpreadPolicy,
    quick_ev_check
)

# Quick EV check
is_profitable, reason = quick_ev_check(spread=0.04, edge=0.05)
print(reason)  # "MAKER only (EV: $1.47)"
```

### 3. Async Signal Cache (`async_signal_cache.py`)

**CRITICAL**: Execution loop NEVER waits for LLM.

```python
from execution.async_signal_cache import get_signal_cache

cache = get_signal_cache()

# Background updater runs LLM calls asynchronously
await cache.start_background_updater(sentiment_analyzer, update_interval_seconds=60)

# Execution loop reads instantly (never blocks)
sentiment, confidence = cache.get_sentiment(market_id)
```

---

## Microstructure Math

### 1. Inventory Skew (Maker Logic)

```python
# Configuration
MAX_INVENTORY = 1000.0
SKEW_FACTOR = 0.05

# 1. Calculate Inventory Ratio (-1.0 to 1.0)
inventory_ratio = current_position_usdc / MAX_INVENTORY

# 2. Calculate Skew
price_skew = inventory_ratio * (spread * SKEW_FACTOR)

# 3. Adjusted Quotes (centered on THEORETICAL price, not market mid)
my_bid_price = theoretical_price - (spread / 2) - price_skew
my_ask_price = theoretical_price + (spread / 2) - price_skew
```

**Effect**:
- **Long inventory** (+$500): Skew = +0.001 → Lower quotes → More likely to sell
- **Short inventory** (-$500): Skew = -0.001 → Higher quotes → More likely to buy

### 2. Order Flow Imbalance (OFI)

```python
def get_imbalance_alpha(order_book):
    # Sum volume at top 3 levels
    bid_vol = sum([b.size for b in order_book.bids[:3]])
    ask_vol = sum([a.size for a in order_book.asks[:3]])
    
    # Calculate Imbalance (-1 to +1)
    imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-9)
    return imbalance

# In execution loop:
ofi = get_imbalance_alpha(book)

# Shift quotes based on pressure
if ofi > 0.6:
    my_ask_price += 0.01  # Raise sell price (don't sell cheap into buy wall)
if ofi < -0.6:
    my_bid_price -= 0.01  # Lower buy price (don't buy expensive into sell wall)
```

### 3. Tail Risk / Variance Sizing

```python
# Inside position sizing logic
price = current_market_price

# 1. Hard Kill Switch at extremes
if price < 0.03 or price > 0.97:
    return 0.0  # NO TRADE

# 2. Calculate Bernoulli variance p * (1-p)
variance = price * (1 - price)

# 3. Calculate Multiplier
# At 50c: 4 * 0.25 = 1.0 (full size)
# At 95c: 4 * 0.0475 = 0.19 (~20% size)
size_multiplier = 4 * variance

final_size = base_size * size_multiplier
```

**Size Table**:
| Price | Variance | Multiplier | $100 Base → Final |
|-------|----------|------------|-------------------|
| 0.02  | -        | KILL       | $0 (no trade)     |
| 0.10  | 0.090    | 0.360      | $36               |
| 0.25  | 0.188    | 0.750      | $75               |
| 0.35  | 0.228    | 0.910      | $91               |
| 0.50  | 0.250    | 1.000      | $100              |
| 0.70  | 0.210    | 0.840      | $84               |
| 0.90  | 0.090    | 0.360      | $36               |
| 0.95  | 0.048    | 0.190      | $19               |
| 0.98  | -        | KILL       | $0 (no trade)     |

---

## EV Calculations

### Maker EV Formula
```
EV_maker = (spread × spread_capture) - adverse_selection - fee
         = (0.04 × 0.50) - 0.005 - 0.00
         = 0.02 - 0.005
         = 0.015 (1.5% per dollar)
```

### Taker EV Formula
```
EV_taker = edge - spread - fee
         = 0.05 - 0.04 - 0.02
         = -0.01 (NEGATIVE - don't take)
```

---

## Configuration

All spread constants are centralized in `execution/spread_policy.py`:

```python
# Maximum spreads by strategy
MAX_SPREAD_HFT = 0.25       # 25% for HFT
MAX_SPREAD_ALPHA = 0.15     # 15% for Alpha
MAX_SPREAD_AGGRESSIVE = 0.06 # 6% for high-edge taker

# Grid search values
SPREAD_GRID_VALUES = [0.03, 0.05, 0.07]

# Fee structure
MAKER_FEE = 0.0             # No maker fee
TAKER_FEE = 0.02            # 2% taker fee

# Spread capture assumptions
MAKER_SPREAD_CAPTURE_PCT = 0.50
ADVERSE_SELECTION_COST = 0.005
```

---

## Usage in Paper Trader

The paper trader should be updated to use these new components:

```python
from trading.strategy_manager import StrategyManager
from execution.spread_policy import SpreadPolicy, EVContext
from execution.async_signal_cache import get_signal_cache

# Initialize
strategy_manager = StrategyManager(total_capital=10000)
spread_policy = SpreadPolicy()
signal_cache = get_signal_cache()

# In trading loop:
# 1. Get instant cached sentiment (never blocks)
sentiment, confidence = signal_cache.get_sentiment(market_id)

# 2. Determine strategy path
allocation = strategy_manager.allocate_funds(market_id, market_data)
strategy_type, reason = strategy_manager.get_strategy_for_signal(signals, market_data)

# 3. Validate EV before trading
ctx = EVContext(spread=spread, edge=edge, position_size=size)
is_valid, maker_ev, taker_ev = spread_policy.validate_ev(ctx)

# 4. Execute with appropriate limits
if strategy_type == StrategyType.HFT:
    max_position = allocation.hft_allocation.max_position_usd
else:
    max_position = allocation.alpha_allocation.max_position_usd
```

---

## Files Modified

| File | Changes |
|------|---------|
| `trading/maker_executor.py` | Added inventory skew, OFI calculation, adjusted quoting |
| `ml/adaptive_position_sizer.py` | Added variance-based tail risk sizing |
| `trading/spread_calibrator.py` | Uses centralized spread constants |
| `ml/strategy_tuner.py` | Uses centralized spread grid values |

---

*Last Updated: December 2025*
