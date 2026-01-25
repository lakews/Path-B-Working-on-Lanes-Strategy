# APEX TRADER - Trading System Architecture

## Complete Flow: Market → Trade Selection → Sizing → Entry → Exit

---

## 1. MARKET DATA FLOW

```
Polymarket API → WebSocket Service → Market Cache → Paper Trader
                      ↓
              Realtime Prices (yes_price, no_price)
              Order Book (bids, asks)
              Volume, Liquidity, End Date
```

**Key Files:**
- `/app/backend/data/polymarket_api.py` - REST API client
- `/app/backend/data/polymarket_websocket.py` - WebSocket price feeds
- `/app/backend/services/realtime_market_service.py` - Price cache manager

---

## 2. TRADE SELECTION (`_evaluate_entry`)

**File:** `/app/backend/paper_trading/paper_trader.py:906`

### Filter Chain (Sequential - First Failure Stops)

| Order | Filter | Threshold | Configurable? | Location |
|-------|--------|-----------|---------------|----------|
| 1 | Circuit Breaker | `max_drawdown_pct` | ✅ UI Config | paper_trader.py:922 |
| 2 | Max Positions | `max_open_positions` | ✅ UI Config | paper_trader.py:928 |
| 3 | Already Has Position | N/A | ❌ | paper_trader.py:933 |
| 4 | Available Capital | `min $5` | ❌ Hardcoded | paper_trader.py:942 |
| 5 | Min Volume | `min_volume_24h` | ✅ UI Config | paper_trader.py:961 |
| 6 | Min Liquidity | `min_liquidity` | ✅ UI Config | paper_trader.py:961 |
| 7 | Max Liquidity | `max_liquidity` | ✅ UI Config | paper_trader.py:966 |
| 8 | End Date Passed | N/A | ❌ | paper_trader.py:970-1010 |
| 9 | Expiry < 3 hours | `3 hours` | ❌ Hardcoded | paper_trader.py:1046 |
| 10 | Price Validation | `!= None, != 0` | ❌ | paper_trader.py:1055 |
| 11 | Extreme Prices | `!= 0.0, != 1.0` | ❌ Hardcoded | paper_trader.py:1063 |
| 12 | Stuck ~0.5 Price | `abs(p-0.5) < 0.02` | ❌ Hardcoded | paper_trader.py:1068 |
| 13 | RL Action | `!= WAIT, HOLD` | ❌ | paper_trader.py:1087 |
| 14 | RL Confidence | `>= 0.10` | ❌ Hardcoded | paper_trader.py:1087 |
| 15 | Expiry Rules | Strategy-specific | Partial | paper_trader.py:1127 |

### Signal Generation (`_get_signals`)

**File:** `/app/backend/paper_trading/paper_trader.py:2981`

```python
signals = {
    'sentiment': 0.0-1.0,        # From LLM/heuristic (0.5 = neutral)
    'volatility': 0.0-1.0,       # Price volatility estimate
    'sharp_alignment': 0.0-1.0,  # Sharp money indicator
    'price_uncertainty': 0.0-1.0, # Model uncertainty
    'whale_activity': -1.0-1.0,  # Whale tracker signal
    'fair_value': 0.0-1.0,       # Estimated fair value
}
```

**Signal Sources:**
- `/app/backend/ml/signal_fusion.py` - Main signal aggregator
- `/app/backend/ml/enhanced_sentiment.py` - LLM sentiment
- `/app/backend/ml/whale_tracker.py` - Whale detection
- `/app/backend/ml/volatility_predictor.py` - Volatility estimation

---

## 3. SIDE SELECTION (YES/NO)

**File:** `/app/backend/paper_trading/paper_trader.py:1096-1113`

| Condition | Side | Logic |
|-----------|------|-------|
| `sentiment > bullish_threshold` | YES | Bullish = Buy YES |
| `sentiment < bearish_threshold` | NO | Bearish = Buy NO |
| Neutral | RL-driven | BUY→YES, SELL→NO |

**Configurable Thresholds:**
- `bullish_sentiment_threshold` (default: 0.55) - UI Config
- `bearish_sentiment_threshold` (default: 0.45) - UI Config

---

## 4. STRATEGY SELECTION (`_determine_strategy`)

**File:** `/app/backend/paper_trading/paper_trader.py:2915`

### Strategy Priority Order

| Priority | Strategy | Trigger Condition | Config Threshold |
|----------|----------|-------------------|------------------|
| 1 | `alpha_directional` | `yes_price < 0.25` OR `> 0.75` | ❌ Hardcoded |
| 2 | `arbitrage` | `sharp_alignment > threshold` | `sharp_alignment_threshold` |
| 3 | `delta_neutral` | `price in [0.40, 0.60]` AND `vol < threshold` | `delta_neutral_price_min/max`, `volatility_threshold` |
| 4 | `alpha_directional` | `abs(sentiment - 0.5) > threshold` | `sentiment_strength_threshold` |
| 5 | `volatility_exploitation` | `volatility > threshold` OR `uncertainty > 0.7` | `volatility_threshold` |
| 6 | Default | Price-bucket rotation | ❌ |

**Strategy Files:**
- `/app/backend/strategies/alpha_directional.py` - Directional bets on extremes
- `/app/backend/strategies/arbitrage.py` - Cross-market arbitrage
- `/app/backend/strategies/delta_neutral.py` - Market making
- `/app/backend/strategies/volatility_exploitation.py` - Vol capture

---

## 5. POSITION SIZING (`_calculate_position_size`)

**File:** `/app/backend/paper_trading/paper_trader.py:2439`

### Two Sizing Modes

#### A. Polymarket Sizer (Default: `use_polymarket_sizer=True`)

**File:** `/app/backend/ml/polymarket_position_sizer.py:169`

```
Base Size = equity * kelly_adjusted * utilization_brake
         * liquidity_clamp * oracle_risk_mult * time_penalty
         * correlation_dampener * sector_cap
```

| Component | Formula | Effect |
|-----------|---------|--------|
| **Kelly Criterion** | `edge / odds` | Higher edge → larger size |
| **Utilization Brake** | `(1 - utilization)^1.5` | More deployed → smaller new trades |
| **Liquidity Clamp** | `min(size, ask_depth * 0.1)` | Can't exceed 10% of orderbook |
| **Oracle Risk** | `0.3-1.0 multiplier` | Ambiguous markets → smaller |
| **Time Penalty** | `1.0 - (hours_open / 168)` | Older → smaller |
| **Correlation Dampener** | `1 / sqrt(correlated_count)` | Similar positions → smaller |
| **Sector Cap** | `max 20% per sector` | Diversification limit |

#### B. Legacy Sizer (`use_polymarket_sizer=False`)

**File:** `/app/backend/paper_trading/paper_trader.py:2910`

```
size = base_size * rl_conf * vol_mult * liq_mult * kelly_mult
```

### Spread Impact on Sizing

**File:** `/app/backend/ml/adaptive_position_sizer.py:195`

```python
spread_mult = max(0.3, 1.0 - (spread * 2))
# 2% spread → 0.96 mult
# 10% spread → 0.80 mult
# 25% spread → 0.50 mult
```

---

## 6. ENTRY EXECUTION (`_execute_paper_entry`)

**File:** `/app/backend/paper_trading/paper_trader.py:1939`

### Entry Flow

```
1. Validate orderbook exists
2. Calculate spread from bids/asks
3. Check spread <= max_spread (configurable)
4. Check spread vs edge (maker_executor)
5. Simulate fill at best ask
6. Record trade in DB
7. Update paper_positions
```

### Spread Validation Chain

| Check | Location | Threshold |
|-------|----------|-----------|
| Max Spread Filter | paper_trader.py:1971 | `max_spread` (UI Config, default 25%) |
| Edge vs Spread | maker_executor.py:717 | `spread <= edge * 1.0` |
| Spread Calibrator | spread_calibrator.py:19 | `max_spread = 0.25` |

### Fill Price Calculation

```python
# For YES trades
fill_price = best_ask  # Pay the ask

# For NO trades  
entry_price = 1 - yes_price  # NO price = 1 - YES price
```

---

## 7. EXIT EVALUATION (`_evaluate_exit`)

**File:** `/app/backend/paper_trading/paper_trader.py:1747`

### Exit Triggers (Priority Order)

| Priority | Trigger | Condition | Configurable? |
|----------|---------|-----------|---------------|
| 1 | **Expiry Safety** | `hours_to_expiry <= 1.0` | ❌ Hardcoded |
| 2 | **Take Profit** | `pnl_pct >= tp_threshold` | ✅ Per-strategy config |
| 3 | **Stop Loss** | `pnl_pct <= sl_threshold` | ✅ Per-strategy config |
| 4 | **RL Reversal** | `opposite signal + conf > 0.7` | ❌ Hardcoded |
| 5 | **Time Limit** | `hours_open > max_hours` | ✅ Per-strategy config |

### Exit Modes

#### A. Dynamic Exit Mode (`use_dynamic_exit=True`)

**File:** `/app/backend/paper_trading/paper_trader.py:1575-1700`

Adjusts TP/SL based on:
- Max gain achieved during position
- Time to expiry
- Price zone (extremes vs mid)

```python
# Example: As position profits grow, raise TP threshold
if max_gain > 0.10:
    tp_threshold = max_gain * 0.7  # Lock in 70% of max gain
```

#### B. Simple Exit Mode (`use_dynamic_exit=False`)

Uses fixed thresholds from `exit_params_by_strategy`:

```python
DEFAULT_EXIT_PARAMS = {
    'delta_neutral': {'take_profit': 0.05, 'stop_loss': -0.08, 'max_hours': 8},
    'volatility_exploitation': {'take_profit': 0.08, 'stop_loss': -0.10, 'max_hours': 12},
    'alpha_directional': {'take_profit': 0.15, 'stop_loss': -0.10, 'max_hours': 24},
    'arbitrage': {'take_profit': 0.03, 'stop_loss': -0.03, 'max_hours': 6},
}
```

### P&L Calculation (Spread-Aware)

**File:** `/app/backend/paper_trading/paper_trader.py:1775-1808`

```python
# With orderbook
if side == 'YES':
    exit_price = best_bid  # Sell at bid
else:
    exit_price = best_ask  # Buy back at ask

# Without orderbook - conservative estimate
spread_estimate = 0.02
exit_price = current_price ± (spread_estimate / 2)
```

---

## 8. CONFIGURATION HIERARCHY

### UI-Configurable (Settings Page)

| Setting | Default | Location |
|---------|---------|----------|
| `initial_capital` | $10,000 | paper_trader.py |
| `kelly_fraction` | 0.25 | paper_trader.py |
| `max_drawdown_pct` | 5% | paper_trader.py |
| `min_liquidity` | $100 | paper_trader.py |
| `max_liquidity` | $1M | paper_trader.py |
| `min_volume_24h` | $1,000 | paper_trader.py |
| `max_spread` | 25% | paper_trader.py |
| `max_open_positions` | 50 | paper_trader.py |
| `enabled_strategies` | all 4 | paper_trader.py |
| `bullish_sentiment_threshold` | 0.55 | paper_trader.py |
| `bearish_sentiment_threshold` | 0.45 | paper_trader.py |

### Hardcoded (Require Code Change)

| Setting | Value | Location |
|---------|-------|----------|
| Min trade size | $5 | paper_trader.py:942 |
| Expiry block | 3 hours | paper_trader.py:1046 |
| Expiry safety exit | 1 hour | paper_trader.py:1885 |
| RL min confidence | 0.10 | paper_trader.py:1087 |
| RL reversal confidence | 0.70 | paper_trader.py:1904 |
| Edge vs Spread ratio | 1.0x | maker_executor.py:717 |
| Spread sizing penalty | `spread * 2` | adaptive_position_sizer.py:195 |
| Sector cap | 20% | polymarket_position_sizer.py |

---

## 9. COMPLETE FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────┐
│                        MARKET DATA                               │
│  Polymarket API → WebSocket → Cache → Paper Trader Loop          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENTRY EVALUATION                              │
│  1. Circuit Breaker Check                                        │
│  2. Max Positions Check                                          │
│  3. Capital Available Check                                      │
│  4. Liquidity/Volume Filters (UI Config)                         │
│  5. End Date & Expiry Checks                                     │
│  6. Price Validation (no 0, null, or ~0.5)                       │
│  7. Generate ML Signals                                          │
│  8. RL Action + Confidence                                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │ Pass All Filters
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SIDE SELECTION                                │
│  sentiment > 0.55 → YES                                          │
│  sentiment < 0.45 → NO                                           │
│  else → RL-driven                                                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  STRATEGY SELECTION                              │
│  Price extremes → alpha_directional                              │
│  High sharp alignment → arbitrage                                │
│  Mid price + low vol → delta_neutral                             │
│  High volatility → volatility_exploitation                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  POSITION SIZING                                 │
│  Kelly Criterion (fee-adjusted)                                  │
│  × Utilization Brake                                             │
│  × Liquidity Clamp (orderbook depth)                             │
│  × Oracle Risk Multiplier                                        │
│  × Spread Penalty                                                │
│  × Correlation Dampener                                          │
│  × Sector Cap (20%)                                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENTRY EXECUTION                               │
│  1. Fetch Orderbook                                              │
│  2. Validate spread <= max_spread (25%)                          │
│  3. Validate spread <= edge * 1.0                                │
│  4. Simulate fill at best ask                                    │
│  5. Record to DB + Update positions                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXIT MONITORING                               │
│  Every tick, evaluate:                                           │
│  1. Expiry Safety (< 1 hour) → EXIT                              │
│  2. Take Profit (P&L >= TP) → EXIT                               │
│  3. Stop Loss (P&L <= SL) → EXIT                                 │
│  4. RL Reversal (opposite signal) → EXIT                         │
│  5. Time Limit (hours > max) → EXIT                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. KEY CONFIGURATION FILES

| File | Purpose |
|------|---------|
| `/app/frontend/src/pages/Configuration.js` | UI Settings |
| `/app/backend/paper_trading/paper_trader.py` | Main Trading Logic |
| `/app/backend/trading/maker_executor.py` | Order Execution |
| `/app/backend/trading/spread_calibrator.py` | Spread Limits |
| `/app/backend/ml/polymarket_position_sizer.py` | Position Sizing |
| `/app/backend/ml/adaptive_position_sizer.py` | Spread Penalties |
| `/app/backend/ml/strategy_tuner.py` | Strategy Optimization |
| `/app/backend/ml/signal_fusion.py` | Signal Generation |

---

*Last Updated: January 25, 2026*
