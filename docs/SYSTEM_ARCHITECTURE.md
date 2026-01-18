# APEX TRADER - System Architecture & Trading Flow

## Table of Contents
1. [System Overview](#system-overview)
2. [Trading Strategies](#trading-strategies)
3. [Asset Classes](#asset-classes)
4. [Entry Methodology](#entry-methodology)
5. [Exit Methodology](#exit-methodology)
6. [Risk Management](#risk-management)
7. [RL (Reinforcement Learning) System](#rl-system)
8. [Sentiment Analysis](#sentiment-analysis)
9. [Position Sizing](#position-sizing)
10. [Configuration Parameters](#configuration-parameters)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    APEX TRADER SYSTEM                                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  POLYMARKET  │───▶│    SIGNAL    │───▶│   STRATEGY   │───▶│    ENTRY     │              │
│  │   GAMMA API  │    │  GENERATION  │    │  SELECTION   │    │   DECISION   │              │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                   │                   │                   │                       │
│         │            ┌──────┴──────┐     ┌──────┴──────┐     ┌──────┴──────┐               │
│         │            │  Volatility │     │ Alpha Dir.  │     │  RL Engine  │               │
│         │            │  Sentiment  │     │ Delta Neut. │     │  Confidence │               │
│         │            │  Sharp Align│     │ Volatility  │     │  Check      │               │
│         │            │  Momentum   │     │ Arbitrage   │     │             │               │
│         │            └─────────────┘     └─────────────┘     └─────────────┘               │
│         │                                                           │                       │
│         ▼                                                           ▼                       │
│  ┌──────────────┐                                          ┌──────────────┐                │
│  │   POSITION   │◀─────────────────────────────────────────│   POSITION   │                │
│  │   TRACKING   │                                          │    SIZING    │                │
│  └──────────────┘                                          └──────────────┘                │
│         │                                                           │                       │
│         │            ┌─────────────┐                        ┌───────┴───────┐              │
│         │            │  Kelly      │                        │  Liquidity    │              │
│         │            │  Criterion  │                        │  Volume       │              │
│         │            │  Risk Adj.  │                        │  Asset Class  │              │
│         │            └─────────────┘                        │  Strategy     │              │
│         │                                                   └───────────────┘              │
│         ▼                                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                                  │
│  │    EXIT      │───▶│   CIRCUIT    │───▶│   TRADE      │                                  │
│  │  EVALUATION  │    │   BREAKER    │    │   LOGGING    │                                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                                  │
│         │                                                                                   │
│  ┌──────┴──────┐                                                                           │
│  │ Dynamic Mode│                                                                           │
│  │ - Resolution│     ┌───────────────────────────────────────────────────────┐            │
│  │ - Hold+SL   │────▶│                 RL LEARNING LOOP                      │            │
│  │ - Active    │     │  Trade Result → Reward Calculation → DQN Update       │            │
│  │ - Quick     │     └───────────────────────────────────────────────────────┘            │
│  │ Simple Mode │                                                                           │
│  │ - Fixed TP  │                                                                           │
│  │ - Fixed SL  │                                                                           │
│  └─────────────┘                                                                           │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Trading Strategies

### Strategy Selection Flow

```
                         ┌─────────────────┐
                         │  Market Data    │
                         │  YES Price: $X  │
                         └────────┬────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │         STRATEGY SELECTION            │
              │         (Priority Order)              │
              └───────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ 1. ALPHA DIR.   │    │ 2. ARBITRAGE    │    │ 3. DELTA NEUT.  │
│                 │    │                 │    │                 │
│ YES < 25%       │    │ Sharp Align     │    │ 40% ≤ YES ≤ 70% │
│   OR            │    │ > threshold     │    │ AND             │
│ YES > 75%       │    │ (default: 0.6)  │    │ Volatility < 6% │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                       │                       │
          │              NOT MET  │              NOT MET  │
          │                       ▼                       ▼
          │            ┌─────────────────┐    ┌─────────────────┐
          │            │ 4. ALPHA DIR.   │    │ 5. VOLATILITY   │
          │            │ (Sentiment)     │    │                 │
          │            │                 │    │ Volatility > 6% │
          │            │ Sentiment       │    │   OR            │
          │            │ Strength > 0.15 │    │ Uncertainty     │
          │            │                 │    │ > 0.7           │
          │            └─────────────────┘    └─────────────────┘
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    6. DEFAULT FALLBACK                          │
│           Round-robin based on price bucket for variety         │
└─────────────────────────────────────────────────────────────────┘
```

### Strategy Descriptions

| Strategy | Trigger Condition | Risk Level | Typical Hold | Description |
|----------|-------------------|------------|--------------|-------------|
| **Alpha Directional** | YES < 25% or > 75% | Medium | 4-24h | Directional bets on clear outcomes |
| **Arbitrage** | Sharp alignment > 0.6 | Low | 6h | Exploit price inefficiencies |
| **Delta Neutral** | 40% ≤ YES ≤ 70%, Vol < 6% | Low | 4h | Market making in stable markets |
| **Volatility Exploitation** | Vol > 6% or Uncertainty > 70% | High | 2h | Profit from price swings |

### Strategy Risk Multipliers (Position Sizing)

```python
STRATEGY_RISK = {
    'delta_neutral': 1.2,        # Low risk → Can size UP
    'volatility_exploitation': 0.5,  # High risk → Size DOWN
    'alpha_directional': 0.8,    # Medium risk
    'arbitrage': 1.1,            # Low risk → Slight increase
}
```

---

## Asset Classes

### Supported Asset Classes

```
┌───────────────────────────────────────────────────────────────────┐
│                      ASSET CLASSES                                │
├───────────┬───────────┬───────────┬───────────┬───────────┬──────┤
│  FINANCE  │ POLITICS  │  CRYPTO   │   SPORTS  │ENTERTAIN. │SCIENCE│
│           │           │           │           │           │      │
│ Risk: 1.0 │ Risk: 0.9 │ Risk: 0.7 │ Risk: 0.95│ Risk: 0.85│ 0.8  │
│ Standard  │ Binary    │ High Vol  │ Predict.  │ Low Liq.  │ Vol. │
└───────────┴───────────┴───────────┴───────────┴───────────┴──────┘
```

### Asset Class Risk Multipliers

```python
ASSET_CLASS_RISK = {
    'crypto': 0.7,        # Higher volatility → Reduce exposure
    'politics': 0.9,      # Binary outcomes → Moderate risk
    'finance': 1.0,       # Standard risk (baseline)
    'sports': 0.95,       # Predictable patterns
    'entertainment': 0.85,# Lower liquidity typically
    'science': 0.8,       # Less liquid, more volatile
}
```

### Asset Class Exit Multipliers

Each asset class can have custom TP/SL/Time multipliers applied to base strategy params:

```python
EXIT_ADJUSTMENTS_BY_ASSET = {
    'finance': {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0},
    'politics': {'tp_mult': 1.2, 'sl_mult': 0.8, 'time_mult': 1.5},
    'crypto': {'tp_mult': 1.5, 'sl_mult': 0.7, 'time_mult': 0.5},
    'sports': {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 0.8},
    'entertainment': {'tp_mult': 1.1, 'sl_mult': 0.9, 'time_mult': 1.2},
    'science': {'tp_mult': 1.2, 'sl_mult': 0.8, 'time_mult': 1.3},
}
```

---

## Entry Methodology

### Entry Decision Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ENTRY DECISION FLOW                               │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────┐
                    │    MARKET DATA       │
                    │    from Polymarket   │
                    └──────────┬───────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     FILTER CHECKS              │
              │  • Min Liquidity: $20,800      │
              │  • Min Volume 24h: $10,000     │
              │  • Not expired                 │
              │  • Valid price data            │
              └────────────────┬───────────────┘
                               │ PASS
                               ▼
              ┌────────────────────────────────┐
              │     SIGNAL GENERATION          │
              │  • Volatility                  │
              │  • Sentiment (0-1)             │
              │  • Sharp Alignment             │
              │  • Price Uncertainty           │
              │  • Momentum                    │
              └────────────────┬───────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     RL ENGINE DECISION         │
              │  DQN/Q-Table → Action          │
              │                                │
              │  Actions: BUY_YES, BUY_NO,     │
              │           SELL_YES, SELL_NO,   │
              │           WAIT                 │
              │                                │
              │  + Confidence Score (0-1)      │
              └────────────────┬───────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
            ACTION: WAIT          ACTION: BUY/SELL
                    │                     │
                    ▼                     ▼
               ┌────────┐       ┌────────────────────┐
               │  SKIP  │       │ CONFIDENCE CHECK   │
               │        │       │ > min_confidence   │
               └────────┘       │ (default: 0.3)     │
                                └─────────┬──────────┘
                                          │ PASS
                                          ▼
                                ┌────────────────────┐
                                │ TIME-AWARE FILTER  │
                                │ (Dynamic Mode)     │
                                │                    │
                                │ NO @ extreme YES:  │
                                │ • ≤7d: ENTER       │
                                │ • 8-30d: gain>0.5% │
                                │ • 31-90d: gain>1%  │
                                │ • >90d: gain>2%    │
                                │   OR SKIP          │
                                └─────────┬──────────┘
                                          │ PASS
                                          ▼
                                ┌────────────────────┐
                                │ STRATEGY SELECTION │
                                │ → Alpha/Arb/DN/Vol │
                                └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ SIDE SELECTION     │
                                │                    │
                                │ Based on:          │
                                │ • RL Action        │
                                │ • Sentiment Score  │
                                │ • Strategy rules   │
                                │                    │
                                │ Sentiment > 0.55   │
                                │   → YES            │
                                │ Sentiment < 0.45   │
                                │   → NO             │
                                └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ POSITION SIZING    │
                                │ (Adaptive)         │
                                │                    │
                                │ See: Position      │
                                │ Sizing Section     │
                                └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ CAPITAL CHECK      │
                                │ Size ≤ Available   │
                                └─────────┬──────────┘
                                          │ PASS
                                          ▼
                                ┌────────────────────┐
                                │   EXECUTE ENTRY    │
                                │                    │
                                │ • Log trade        │
                                │ • Update positions │
                                │ • Update capital   │
                                │ • Broadcast event  │
                                └────────────────────┘
```

### Side Selection Logic

```python
# Side selection based on signals and thresholds
def determine_side(sentiment, rl_action, strategy):
    # RL action takes priority if explicit
    if 'YES' in rl_action:
        return 'YES'
    if 'NO' in rl_action:
        return 'NO'
    
    # Sentiment-based selection
    if sentiment > 0.55:  # Bullish threshold
        return 'YES'
    elif sentiment < 0.45:  # Bearish threshold
        return 'NO'
    
    # Default based on strategy
    return 'YES' if strategy in ['alpha_directional'] else 'NO'
```

---

## Exit Methodology

### Exit Mode: Dynamic vs Simple

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXIT MODE SELECTION                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌───────────────────────┐          ┌───────────────────────┐             │
│   │    DYNAMIC MODE       │          │    SIMPLE MODE        │             │
│   │    (Time-Aware)       │          │    (Fixed)            │             │
│   ├───────────────────────┤          ├───────────────────────┤             │
│   │ • TP/SL based on:     │          │ • Fixed TP per        │             │
│   │   - Max possible gain │          │   strategy            │             │
│   │   - Time to expiry    │          │ • Fixed SL per        │             │
│   │   - Price extremeness │          │   strategy            │             │
│   │                       │          │ • Fixed max hold time │             │
│   │ • 4 Exit Modes:       │          │                       │             │
│   │   - Resolution        │          │ Example:              │             │
│   │   - Hold Protected    │          │ • Delta: TP=2%,       │             │
│   │   - Active            │          │   SL=-2%, 4h          │             │
│   │   - Quick Trade       │          │ • Alpha: TP=3%,       │             │
│   │                       │          │   SL=-3%, 6h          │             │
│   └───────────────────────┘          └───────────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dynamic Exit: Time-Based Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               DYNAMIC EXIT MODES BY TIME TO EXPIRY                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Days to     Exit          Take        Stop        Max        Description  │
│  Expiry      Mode          Profit      Loss        Hold                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ≤3 days     RESOLUTION    None        None        Until      Hold to      │
│              (Purple)                              expiry     market       │
│                                                               resolution   │
│                                                                             │
│  4-7 days    HOLD+SL       None        -15%        Until      Hold with    │
│              (Blue)                                expiry     SL safety    │
│                                                               net          │
│                                                                             │
│  8-30 days   ACTIVE        50% of      Scaled*     12d or     Active       │
│              (Cyan)        max gain    (-10%→-30%) 1 week     management   │
│                                                                             │
│  >30 days    QUICK         30% of      -8%         24h        Quick        │
│              (Yellow)      max gain                           in/out       │
│                                                                             │
│  Unknown     STANDARD      10% of      Scaled*     Zone-      Default      │
│              (Gray)        max gain    (-10%→-30%) based      behavior     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

* Scaled SL: SL = sl_base + (extremeness × (sl_extreme - sl_base))
             Where extremeness = |price - 0.5| / 0.5
             Example: At price 0.05, extremeness = 0.9, SL = -10% + 0.9×(-30%-(-10%)) = -28%
```

### Maximum Possible Gain Calculation

```python
def calculate_max_gain(side, entry_price):
    """
    YES position: Price can go to $1.00
        Max gain = (1 - entry_price) / entry_price
        Example: Entry $0.10 → Max gain = 900%
    
    NO position: YES price can go to $0
        Max gain = entry_price / (1 - entry_price)
        Example: Entry at YES $0.95 → NO entry $0.05 → Max gain = 1900%
    """
    if side == 'YES':
        return (1.0 - entry_price) / entry_price
    else:  # NO
        return entry_price / (1 - entry_price)
```

### Exit Decision Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXIT EVALUATION                                   │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────┐
                    │   OPEN POSITION      │
                    │   with current P&L   │
                    └──────────┬───────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  1. EXPIRY SAFETY CHECK        │
              │  Hours to expiry ≤ 1?          │
              │  → EXIT: "expiry_safety"       │
              └────────────────┬───────────────┘
                               │ NO
                               ▼
              ┌────────────────────────────────┐
              │  2. TAKE PROFIT CHECK          │
              │  (Skip if TP = None)           │
              │                                │
              │  P&L% ≥ TP threshold?          │
              │  → EXIT: "tp_{mode}"           │
              └────────────────┬───────────────┘
                               │ NO
                               ▼
              ┌────────────────────────────────┐
              │  3. STOP LOSS CHECK            │
              │  (Skip if SL = None)           │
              │                                │
              │  P&L% ≤ SL threshold?          │
              │  → EXIT: "sl_{mode}"           │
              └────────────────┬───────────────┘
                               │ NO
                               ▼
              ┌────────────────────────────────┐
              │  4. RL REVERSAL CHECK          │
              │  (Skip in Resolution mode)     │
              │                                │
              │  RL confidence > 70%           │
              │  AND opposite signal?          │
              │  → EXIT: "rl_reversal"         │
              └────────────────┬───────────────┘
                               │ NO
                               ▼
              ┌────────────────────────────────┐
              │  5. TIME LIMIT CHECK           │
              │                                │
              │  Hours open > max_hours?       │
              │  → EXIT: "time_{mode}"         │
              └────────────────┬───────────────┘
                               │ NO
                               ▼
                    ┌──────────────────────┐
                    │   CONTINUE HOLDING   │
                    └──────────────────────┘
```

---

## Risk Management

### Circuit Breaker

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CIRCUIT BREAKER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Total Equity = Current Cash + Deployed Capital + Unrealized P&L            │
│                                                                             │
│  Drawdown% = (Initial Capital - Total Equity) / Initial Capital × 100      │
│                                                                             │
│  IF Drawdown% > Max Drawdown (default: 10%):                               │
│     → CIRCUIT BREAKER TRIGGERED                                             │
│     → No new positions opened                                               │
│     → Existing positions continue (no force close)                          │
│     → Red flashing indicator in UI                                          │
│                                                                             │
│  Example:                                                                   │
│    Initial: $10,000                                                         │
│    Cash: $2,000                                                             │
│    Deployed: $7,000                                                         │
│    Unrealized P&L: -$1,200                                                  │
│    Total Equity: $7,800                                                     │
│    Drawdown: ($10,000 - $7,800) / $10,000 = 22% → TRIGGERED                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Risk Limits

```python
RISK_PARAMETERS = {
    'max_drawdown_pct': 10,           # Circuit breaker at 10% drawdown
    'capital_deployment_pct': 80,      # Max 80% of capital deployed
    'max_position_size_pct': 5,        # Single position max 5% of capital
    'max_position_size_usd': 500,      # Hard cap per position
    'min_position_size_usd': 5,        # Minimum position size
    'max_positions_per_market': 1,     # One position per market
}
```

---

## RL System

### Deep Q-Network (DQN) Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DQN ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STATE VECTOR (8 dimensions):                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ [yes_price, volatility, sentiment, sharp_alignment,                  │   │
│  │  liquidity_norm, volume_norm, time_to_expiry, portfolio_exposure]   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    NEURAL NETWORK                                    │   │
│  │         Input(8) → Dense(128) → ReLU → Dense(64) → ReLU             │   │
│  │                              → Dense(5) [Q-values]                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ACTION SPACE (5 actions):                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  0: BUY_YES  │  1: BUY_NO  │  2: SELL_YES  │  3: SELL_NO  │  4: WAIT │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  LEARNING:                                                                  │
│  • Experience Replay Buffer: 50,000 transitions                            │
│  • Prioritized Experience Replay (PER)                                      │
│  • Target Network: Soft update every step (τ = 0.005)                      │
│  • Batch Size: 64                                                           │
│  • Learning Rate: 0.0003                                                    │
│  • Discount Factor (γ): 0.99                                               │
│  • Epsilon: 0.15 (exploration rate)                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### RL Learning Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RL LEARNING LOOP                                  │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌─────────────┐
     │   MARKET    │
     │    DATA     │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐      ┌─────────────┐
     │   BUILD     │      │   EPSILON   │
     │   STATE     │─────▶│   GREEDY    │
     └─────────────┘      │  SELECTION  │
                          └──────┬──────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
            Random (ε)              Best Q-value (1-ε)
                    │                         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                         ┌─────────────┐
                         │   ACTION    │
                         │ + CONFIDENCE│
                         └──────┬──────┘
                                │
                                ▼
                         ┌─────────────┐
                         │   EXECUTE   │
                         │    TRADE    │
                         └──────┬──────┘
                                │
                                ▼
                         ┌─────────────┐
                         │   OBSERVE   │
                         │   OUTCOME   │
                         │   (P&L)     │
                         └──────┬──────┘
                                │
                                ▼
     ┌─────────────────────────────────────────────────────┐
     │                 REWARD CALCULATION                   │
     │                                                      │
     │  Base Reward = P&L%                                  │
     │                                                      │
     │  Risk-Adjusted:                                      │
     │  • +bonus if P&L > 0 with low volatility entry      │
     │  • -penalty for max drawdown during hold            │
     │  • +bonus for following sentiment correctly         │
     │                                                      │
     │  Trade Efficiency:                                   │
     │  • +bonus for quick profitable exits                 │
     │  • -penalty for holding too long with negative P&L  │
     │                                                      │
     │  Final: reward = base × risk_adj × efficiency        │
     └─────────────────────────────────────────────────────┘
                                │
                                ▼
     ┌─────────────────────────────────────────────────────┐
     │              EXPERIENCE REPLAY                       │
     │                                                      │
     │  Store: (state, action, reward, next_state, done)   │
     │                                                      │
     │  Prioritized by TD-error:                           │
     │  Higher surprise = Higher replay probability        │
     │                                                      │
     │  Sample batch of 64 transitions                     │
     │  Update Q-network via gradient descent              │
     │  Soft-update target network                         │
     └─────────────────────────────────────────────────────┘
```

---

## Sentiment Analysis

### Multi-Layer Sentiment Fusion

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SENTIMENT ANALYSIS LAYERS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LAYER 1: MARKET MICROSTRUCTURE (40% weight)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Price Sentiment: Current YES price                                 │   │
│  │ • Momentum: Price change rate over time                              │   │
│  │ • Volume Intensity: Recent vs total volume ratio                     │   │
│  │ • Liquidity Conviction: Spread-based sentiment                       │   │
│  │ • Whale Activity: Large order flow direction                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  LAYER 2: ORDER BOOK ANALYSIS (20% weight)                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Bid/Ask Imbalance: Order book skew                                 │   │
│  │ • Depth Analysis: Support/resistance levels                          │   │
│  │ • Outstanding Contract Flow: Net contract changes                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  LAYER 3: LLM SENTIMENT ANALYSIS (40% weight)                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • GPT-4o-mini analysis of market question                            │   │
│  │ • Returns: sentiment (0-1), confidence, reasoning                    │   │
│  │ • Cached for 30 minutes per market                                   │   │
│  │ • Considers: market question, current price, volume, category        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  FINAL FUSION:                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ sentiment = (microstructure × 0.4) +                                 │   │
│  │             (order_book × 0.2) +                                     │   │
│  │             (llm_sentiment × 0.4)                                    │   │
│  │                                                                       │   │
│  │ Range: 0.0 (Very Bearish) → 0.5 (Neutral) → 1.0 (Very Bullish)      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Sentiment Thresholds

```python
SENTIMENT_THRESHOLDS = {
    'bullish': 0.55,    # Above this → Lean YES
    'bearish': 0.45,    # Below this → Lean NO
    'strength_threshold': 0.15,  # |sentiment - 0.5| for Alpha strategy
}
```

---

## Position Sizing

### Adaptive Position Sizing Formula

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSITION SIZING CALCULATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BASE SIZE = Available Capital × Max Position %                             │
│            = (Initial - Deployed) × 0.05                                    │
│                                                                             │
│  MULTIPLIERS:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │  Liquidity Multiplier (0.3 - 1.0):                                   │   │
│  │    Based on market liquidity vs threshold                            │   │
│  │    Low liquidity = smaller positions                                 │   │
│  │                                                                       │   │
│  │  Volume Multiplier (0.5 - 1.0):                                      │   │
│  │    Based on 24h volume activity                                      │   │
│  │    Low volume = smaller positions                                    │   │
│  │                                                                       │   │
│  │  RL Confidence Multiplier (0.5 - 1.2):                               │   │
│  │    Higher confidence = larger positions                              │   │
│  │                                                                       │   │
│  │  Volatility Multiplier (0.5 - 1.0):                                  │   │
│  │    High volatility = smaller positions                               │   │
│  │                                                                       │   │
│  │  Strategy Risk Multiplier:                                           │   │
│  │    Delta Neutral: 1.2, Arbitrage: 1.1                               │   │
│  │    Alpha: 0.8, Volatility: 0.5                                       │   │
│  │                                                                       │   │
│  │  Asset Class Risk Multiplier:                                        │   │
│  │    Finance: 1.0, Politics: 0.9, Crypto: 0.7                         │   │
│  │    Sports: 0.95, Entertainment: 0.85, Science: 0.8                   │   │
│  │                                                                       │   │
│  │  Expiry Multiplier (0.5 - 1.5):                                      │   │
│  │    Near expiry with high confidence = larger                         │   │
│  │    Far expiry = smaller                                              │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  RISK COMBINED = (all multipliers)^(1/n)   [Geometric Mean]                │
│                                                                             │
│  FINAL SIZE = BASE × RISK_COMBINED                                          │
│                                                                             │
│  CONSTRAINTS:                                                               │
│  • Min: $5                                                                  │
│  • Max: $500 or max_position_size_pct of capital                           │
│  • Cannot exceed available capital                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Kelly Criterion (Optional)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KELLY CRITERION                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Kelly % = (Win Rate × Avg Win - (1 - Win Rate) × Avg Loss) / Avg Win      │
│                                                                             │
│  OR simplified: Kelly % = Win Rate - (1 - Win Rate) / (Avg Win / Avg Loss) │
│                                                                             │
│  Applied as: Position Size = Base Size × Kelly Fraction (default: 35%)     │
│                                                                             │
│  Kelly is learned per:                                                      │
│  • Strategy (separate win rates for Alpha, Arb, etc.)                      │
│  • Asset Class (separate win rates for Finance, Politics, etc.)            │
│                                                                             │
│  Kelly Bounds: Min 15%, Max 50% (configurable)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration Parameters

### Trading Parameters (Configurable via UI)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `initial_capital` | $10,000 | Starting paper trading capital |
| `capital_deployment_pct` | 80% | Max % of capital to deploy |
| `max_position_size_pct` | 5% | Max single position as % of capital |
| `max_position_size_usd` | $500 | Hard cap per position |
| `min_position_size_usd` | $5 | Minimum position size |
| `kelly_fraction` | 35% | Kelly criterion fraction |
| `kelly_enabled` | true | Enable Kelly-based sizing |
| `max_drawdown_pct` | 10% | Circuit breaker threshold |
| `trades_per_10min` | 50 | Rate limit for trades |

### Strategy Thresholds (Configurable via UI)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `volatility_threshold` | 0.06 (6%) | Trigger for Volatility strategy |
| `sentiment_strength_threshold` | 0.15 | Min sentiment divergence for Alpha |
| `sharp_alignment_threshold` | 0.6 | Min alignment for Arbitrage |
| `delta_neutral_price_min` | 0.40 | Min YES price for Delta Neutral |
| `delta_neutral_price_max` | 0.70 | Max YES price for Delta Neutral |
| `bullish_sentiment_threshold` | 0.55 | Above this → YES |
| `bearish_sentiment_threshold` | 0.45 | Below this → NO |

### Exit Parameters (Simple Mode)

| Strategy | Take Profit | Stop Loss | Max Hours |
|----------|-------------|-----------|-----------|
| Delta Neutral | 2% | -2% | 4h |
| Volatility | 2% | -2% | 4h |
| Alpha Directional | 2% | -2% | 4h |
| Arbitrage | 2% | -2% | 4h |

### Dynamic Exit Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tp_capture_pct` | 10% | % of max gain to target |
| `tp_min` | 0.5% | Minimum TP threshold |
| `tp_max` | 50% | Maximum TP threshold |
| `sl_base` | -10% | SL at mid-range prices (50%) |
| `sl_extreme` | -30% | SL at extreme prices (0% or 100%) |

### Market Filters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_liquidity` | $20,800 | Minimum market liquidity |
| `min_volume_24h` | $10,000 | Minimum 24h volume |
| `max_liquidity` | $10M | Maximum liquidity (avoid manipulation) |

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE TRADE LIFECYCLE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. MARKET SCAN (every 3s)                                                  │
│     Polymarket API → Filter → 182 tradeable markets                        │
│                                                                             │
│  2. FOR EACH MARKET:                                                        │
│     a. Generate Signals (volatility, sentiment, etc.)                      │
│     b. RL Engine → Action + Confidence                                      │
│     c. Strategy Selection (Alpha/Arb/DN/Vol)                               │
│     d. Side Selection (YES/NO)                                              │
│     e. Position Sizing (adaptive, Kelly, risk-adjusted)                    │
│     f. Entry Decision (time filter, capital check)                         │
│                                                                             │
│  3. POSITION MONITORING (continuous)                                        │
│     a. Update current prices                                                │
│     b. Calculate unrealized P&L                                             │
│     c. Evaluate exit conditions (TP/SL/Time/RL reversal)                   │
│     d. Execute exits when triggered                                         │
│                                                                             │
│  4. LEARNING (on exit)                                                      │
│     a. Calculate reward from P&L                                            │
│     b. Store experience in replay buffer                                    │
│     c. Train DQN on batch of experiences                                    │
│     d. Update strategy/asset class statistics                               │
│                                                                             │
│  5. RISK MONITORING                                                         │
│     a. Track total equity                                                   │
│     b. Calculate drawdown                                                   │
│     c. Circuit breaker if threshold exceeded                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File References

| Component | File Path |
|-----------|-----------|
| Paper Trader Engine | `/app/backend/paper_trading/paper_trader.py` |
| RL Engine (DQN) | `/app/backend/ml/rl_engine.py` |
| DQN Model | `/app/backend/ml/dqn.py` |
| Position Sizer | `/app/backend/ml/adaptive_position_sizer.py` |
| Sentiment Service | `/app/backend/services/sentiment_service.py` |
| API Server | `/app/backend/server.py` |
| Frontend UI | `/app/frontend/src/pages/PaperTrading.js` |
| Configuration UI | `/app/frontend/src/pages/Configuration.js` |

---

*Last Updated: January 18, 2026*
