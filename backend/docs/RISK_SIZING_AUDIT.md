# APEX TRADER - Risk & Sizing Audit
## Five-Lane Highway Architecture

**Last Updated:** February 2026
**Document Type:** Risk Management Specification

---

## 📊 EXECUTIVE SUMMARY

| Lane | Capital Allocation | Max Position | Kelly Variant | Min Trade | Risk Profile |
|------|-------------------|--------------|---------------|-----------|--------------|
| **HFT** | 35% | 3% / $100 | N/A (Fixed) | $2 | Low risk, high frequency |
| **ALPHA** | 55% | 3% / $100 | Fractional (25%) | $2 | Medium risk, conviction |
| **GAMMA** | 10% | 1% / $15 | Fixed Unit | $2 | High risk, asymmetric |
| **SPORTS** | 15%* | $100 | Binary Kelly | $5 | Medium risk, real odds |
| **NEWS** | Shared | 5% | Fractional (25%) | $5 | Event-driven, time-sensitive |

*Sports allocation is configurable, default overlaps with Alpha

---

## 1️⃣ HFT LANE (Market Maker)

### Capital Allocation
```python
HFT_ALLOCATION_PCT = 35.0%  # of deployed capital
```

### Position Sizing
| Parameter | Value | Source |
|-----------|-------|--------|
| Max Position USD | $100 | `CORE_MAX_USD` |
| Max Position % | 3% | `CORE_MAX_PCT` × 100 |
| Min Trade Amount | $2 | `MIN_TRADE_AMOUNT` |
| Kelly | **NOT USED** | Fixed unit sizing |

### Sizing Logic
```python
# HFT uses fixed unit sizing, not Kelly
position_size = min(
    CORE_MAX_USD,  # $100 cap
    deployed_capital * CORE_MAX_PCT  # 3% cap
)
```

### Risk Controls
- ✅ Maximum spread check (5 cents)
- ✅ Minimum liquidity ($10,000)
- ✅ Inventory skew limits
- ✅ Circuit breaker at 5% drawdown
- ❌ No conviction-based sizing (speed > optimization)

---

## 2️⃣ ALPHA LANE (The Strategist)

### Capital Allocation
```python
ALPHA_ALLOCATION_PCT = 55.0%  # of deployed capital
```

### Position Sizing
| Parameter | Value | Source |
|-----------|-------|--------|
| Max Position USD | $100 | `CORE_MAX_USD` |
| Max Position % | 3% | `max_position_size_pct` |
| Min Trade Amount | $2 | `MIN_TRADE_AMOUNT` |
| Kelly Fraction | 25% | `KELLY_SCALING_FACTOR` |
| Min Kelly | 10% | `MIN_KELLY_FRACTION` |
| Max Kelly | 50% | `MAX_KELLY_FRACTION` |

### Sizing Logic (Fractional Kelly)
```python
# Kelly Criterion: f* = (p*b - q) / b
# Where p = win_prob, b = odds, q = 1-p

raw_kelly = (win_prob * odds - (1 - win_prob)) / odds
scaled_kelly = raw_kelly * KELLY_SCALING_FACTOR  # 25%

# Clamp to bounds
kelly_fraction = max(MIN_KELLY_FRACTION, min(scaled_kelly, MAX_KELLY_FRACTION))

position_size = min(
    deployed_capital * kelly_fraction,
    CORE_MAX_USD,  # $100 cap
    deployed_capital * max_position_size_pct  # 3% cap
)
```

### Risk Controls
- ✅ Bayesian confidence weighting
- ✅ Sentiment divergence threshold
- ✅ Asset class exposure limits
- ✅ Strategy correlation checks
- ✅ Circuit breaker at 5% drawdown

---

## 3️⃣ GAMMA LANE (Whale Zone)

### Capital Allocation
```python
GAMMA_ALLOCATION_PCT = 10.0%  # of deployed capital (moonshot reserve)
```

### Position Sizing
| Parameter | Value | Source |
|-----------|-------|--------|
| Max Position USD | **$15** | `WHALE_MAX_USD` |
| Max Position % | **1%** | `WHALE_MAX_PCT` × 100 |
| Max Spread | 3 cents | `WHALE_MAX_SPREAD_CENTS` |
| Min Trade Amount | $2 | `MIN_TRADE_AMOUNT` |
| Kelly | **FIXED UNIT** | Risk 1 to make 10 |

### Sizing Logic (Fixed Unit - Asymmetric Payoff)
```python
# Gamma does NOT use Kelly - fixed unit for lottery tickets
# Philosophy: Risk $15 to potentially make $150+ (10x)

position_size = min(
    WHALE_MAX_USD,  # $15 hard cap
    deployed_capital * WHALE_MAX_PCT  # 1% of capital
)

# Entry criteria is strict:
# - Price must be $0.01-$0.10 (OTM options)
# - Spread must be < 3 cents
# - Looking for 10x+ asymmetric payoff
```

### Risk Controls
- ✅ Price range filter ($0.01-$0.10 only)
- ✅ Strict spread limit (3 cents)
- ✅ Small fixed position size ($15 max)
- ✅ Free Roll exit at 2x (sell half, hold free)
- ✅ Moonbag exit at 5x (full profit take)
- ✅ Stop loss at 0.5x (50% down)

---

## 4️⃣ SPORTS LANE (The Bookie)

### Capital Allocation
```python
# From SportsConfig
allocation_pct = 15.0%  # Dedicated sports allocation
total_capital = 10000   # Base capital
```

### Position Sizing
| Parameter | Value | Source |
|-----------|-------|--------|
| Max Position USD | $100 | `max_position_size` |
| Max Positions | 10 | `max_positions` |
| Min Trade Size | $5 | `min_trade_size` |
| Kelly Fraction | 25% | `kelly_fraction` |
| Min Kelly | 5% | `min_kelly` |
| Max Kelly | 20% | `max_kelly` |

### Sizing Logic (Binary Kelly - Sports Specific)
```python
# Sports uses real odds from The Odds API
# Edge = fair_value - market_price

# Kelly for binary outcomes
if edge > 0:
    kelly = edge / odds  # Simplified binary Kelly
    
scaled_kelly = kelly * kelly_fraction  # 25%

# Clamp to sports-specific bounds
kelly_clamped = max(min_kelly, min(scaled_kelly, max_kelly))

position_size = min(
    total_capital * allocation_pct * kelly_clamped,
    max_position_size,  # $100 cap
    min_trade_size if kelly_clamped > 0 else 0  # $5 minimum
)
```

### Risk Controls
- ✅ Real odds validation (The Odds API)
- ✅ Minimum edge threshold (2%)
- ✅ Taker fee consideration (2%)
- ✅ Max 10 concurrent sports positions
- ✅ Binary outcome handling (ride to settlement)
- ✅ Stop loss at 100% (don't sell early - spread kills you)
- ✅ Take profit at 30% (if line moves massively)
- ✅ Time limit 24h (force exit if game delayed)

---

## 5️⃣ NEWS/EMERGENT LANE (The Bridge)

### Capital Allocation
```python
# News lane shares capital with other lanes
# Uses portfolio-level limits, not dedicated allocation
```

### Position Sizing
| Parameter | Value | Source |
|-----------|-------|--------|
| Max Position % | 5% | `max_position_pct` |
| Min Edge | 2% | `min_edge` |
| Min Trade Size | $5 | Hardcoded |
| Kelly Fraction | 25% | `kelly_fraction` |
| Bayes Factor Threshold | 3.0 | `min_bayes_factor` |

### Sizing Logic (Bayesian Kelly)
```python
# News lane uses Bayesian posterior as win probability
# Position size scales with confidence AND Bayes Factor

posterior = event_bayes.posterior  # From Bayesian update
confidence = event_bayes.confidence
edge = abs(posterior - current_price)

# Only trade if evidence is strong enough
if bayes_factor < 3.0:
    return 0  # Not actionable

# Bayesian Kelly
base_size_pct = posterior * kelly_fraction * confidence

position_size = min(
    deployed_capital * base_size_pct,
    deployed_capital * max_position_pct,  # 5% cap
)

# Minimum size check
if position_size < 5.0:
    return 0
```

### Risk Controls
- ✅ Bayes Factor threshold (BF > 3.0 required)
- ✅ Source reliability weighting
- ✅ TTL on signals (5 min default, 1 hour for resolution)
- ✅ Rate limiting (20 injections/minute)
- ✅ LLM confidence calibration (0.50-0.95 scale)
- ✅ Stop loss at 10% (news can be wrong)
- ✅ Take profit at 15% (edge decays quickly)
- ✅ Time limit 4h (news is time-sensitive)

---

## 🔒 GLOBAL RISK CONTROLS (All Lanes)

### Portfolio-Level Limits
| Parameter | Value | Effect |
|-----------|-------|--------|
| `max_position_size_pct` | 3% | No single position > 3% of deployed |
| `max_drawdown_pct` | 5% | Circuit breaker triggers at 5% loss |
| `capital_deployment_pct` | 80% | Only deploy 80% of initial capital |
| `MIN_TRADE_AMOUNT` | $2 | No trade smaller than $2 |

### Circuit Breaker Logic
```python
if drawdown_pct >= max_drawdown_pct:  # 5%
    circuit_breaker_triggered = True
    # Stop all new entries
    # Allow exits only
    # Log emergency alert
```

### Asset Class Exposure
```python
enabled_asset_classes = ['finance', 'politics', 'crypto', 
                         'entertainment', 'science', 'sports']

# Each asset class has multipliers for:
# - Take profit adjustment
# - Stop loss adjustment  
# - Time limit adjustment
```

---

## 📈 SIZING COMPARISON MATRIX

| Scenario | HFT | Alpha | Gamma | Sports | News |
|----------|-----|-------|-------|--------|------|
| **$10k Capital** | | | | | |
| Deployed (80%) | $8,000 | $8,000 | $8,000 | $8,000 | $8,000 |
| Lane Allocation | $2,800 | $4,400 | $800 | $1,200 | Shared |
| Max Single Trade | $100 | $100 | $15 | $100 | $400 |
| Typical Trade | $50 | $75 | $10 | $50 | $100 |
| Min Trade | $2 | $2 | $2 | $5 | $5 |
| **Risk per Trade** | 0.6% | 0.9% | 0.1% | 0.6% | 1.25% |

---

## ⚠️ KNOWN GAPS & RECOMMENDATIONS

### Current Issues
1. **News Lane**: Test endpoint doesn't apply global caps (fixed in production code)
2. **Sports Lane**: Exit params were missing (FIXED in this session)
3. **Gamma Lane**: May need price range expansion beyond $0.10

### Recommended Improvements
1. Add correlation-based position limits (don't overload one direction)
2. Implement time-of-day sizing adjustments (reduce size in low liquidity hours)
3. Add volatility-scaled sizing (reduce in high VIX environments)
4. Create real-time risk dashboard for all 5 lanes

---

## 📋 CONFIGURATION CHECKLIST

Before going live, verify:

- [ ] `EMERGENT_LLM_KEY` set in `.env`
- [ ] `ODDS_API_KEY` set for Sports lane
- [ ] `EXA_API_KEY` set for News polling (optional)
- [ ] `max_drawdown_pct` set appropriately (default 5%)
- [ ] `capital_deployment_pct` reviewed (default 80%)
- [ ] All lane allocations sum to 100% or less
- [ ] Circuit breaker tested
- [ ] Exit parameters verified for all strategies
