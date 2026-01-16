# APEX TRADER - Configuration Guide

## Overview

APEX TRADER is an AI-driven prediction market trading engine designed for high-frequency algorithmic trading on Polymarket. This guide explains all configurable parameters and how they affect trading behavior.

## Configuration Tabs

### 1. Trading Tab
Basic trading parameters that control trade frequency and execution.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Trades per 10 min | 500 | Maximum number of trades per 10-minute window |
| Trade Interval | Auto | Calculated as `600 / trades_per_10min` seconds |

**Recommendation:** Start with 100-200 trades/10min for testing, increase to 500+ for production.

---

### 2. Capital Tab
Controls how much capital is deployed and position sizing.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Initial Capital | $10,000 | Total paper trading capital |
| Capital Deployment | 80% | Percentage actively deployed for trading |
| Max Position Size | 3% | Maximum single position as % of deployed capital |

**Example:** With $10,000 capital and 80% deployment:
- Deployed Capital = $8,000
- Max Position = $8,000 × 3% = $240 per trade

---

### 3. Risk Tab
Risk management parameters including Kelly Criterion.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Kelly Fraction | 0.25 | Base Kelly multiplier (25% of optimal) |
| Kelly Enabled | Yes | Toggle Kelly-based position sizing |
| Max Drawdown | 5% | Circuit breaker triggers at this drawdown |

**Kelly Criterion Explained:**
Kelly calculates optimal bet size using: `Kelly = (W × R - L) / R`
- W = Win rate (probability of winning)
- R = Win/Loss ratio (avg win ÷ avg loss)
- L = Loss rate (1 - W)

We use "fractional Kelly" (25% of optimal) for safety.

---

### 4. Market Selection Tab
Filters for selecting which markets to trade.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Min Liquidity | $100 | Minimum market liquidity |
| Max Liquidity | $1,000,000 | Maximum market liquidity |
| Min 24h Volume | $1,000 | Minimum daily trading volume |
| Max Spread | 5% | Maximum bid-ask spread |
| Max Open Positions | 50 | Position limit across all markets |
| Stuck Price Multiplier | 2.0x | Volume multiplier for stuck price detection |

**Stuck Price Detection:** Markets where price hasn't moved but volume is low (< avg × multiplier) are filtered out to avoid stale markets.

---

### 5. Exit Parameters Tab
Configure Take Profit, Stop Loss, and Max Hold Time per strategy.

#### Default Values by Strategy

| Strategy | Take Profit | Stop Loss | Max Hours |
|----------|-------------|-----------|-----------|
| Delta-Neutral | 2% | -2% | 4h |
| Volatility Exploitation | 5% | -5% | 8h |
| Alpha-Directional | 8% | -5% | 12h |
| Arbitrage | 3% | -3% | 6h |

#### Presets
- **Conservative:** TP=2%, SL=-2%, 4h (quick exits)
- **Moderate:** TP=5%, SL=-5%, 8h (balanced)
- **Aggressive:** TP=10%, SL=-8%, 24h (let winners run)

---

### 6. Asset Multipliers Tab
Adjust exit parameters based on asset class volatility.

| Asset Class | TP Mult | SL Mult | Time Mult | Rationale |
|-------------|---------|---------|-----------|-----------|
| Crypto | 1.5x | 1.3x | 0.5x | High volatility, close faster |
| Politics | 1.2x | 1.0x | 1.5x | Events take time to resolve |
| Sports | 1.0x | 0.8x | 0.25x | Games end quickly |
| Finance | 0.8x | 0.8x | 1.0x | More predictable |
| Entertainment | 1.0x | 1.0x | 1.0x | Standard |
| Science | 1.0x | 1.0x | 2.0x | Research takes time |

**Example:** Delta-Neutral (TP=2%) on Crypto (TP Mult=1.5x):
- Effective Take Profit = 2% × 1.5 = 3%

---

### 7. Advanced Tab
Fine-tune position sizing algorithm.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Min Kelly Fraction | 10% | Floor for position sizing |
| Max Kelly Fraction | 50% | Cap for position sizing (safety) |
| Min Position Size | $5 | Smallest allowed trade |
| Full Size Liquidity | $10,000 | 24h volume needed for full position sizing |

**Position Sizing Formula:**
```
Final Position = Base Kelly × Liquidity Factor × Volatility Factor × RL Confidence × Asset Risk
```

Where:
- **Liquidity Factor:** Scales down for low-volume markets
- **Volatility Factor:** Reduces size in volatile conditions
- **RL Confidence:** ML model confidence in the trade
- **Asset Risk:** Per-asset-class risk multiplier

---

### 8. Alerts Tab
Real-time market alerts configuration.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Alerts Enabled | No | Toggle real-time alerts |
| Volume Threshold | 2.0x | Alert when volume > liquidity × threshold |

**Alert Types:**
- **Volume Spike:** Market trading volume increases significantly
- **Price Movement:** Large price swing detected (5%+ change)

---

### 9. Asset Class & Strategy Tab
Enable/disable specific asset classes and trading strategies.

#### Trading Strategies

| Strategy | Risk | Expected Return | Description |
|----------|------|-----------------|-------------|
| Delta-Neutral | Low | 5-15% | Market making with zero directional exposure |
| Volatility Exploitation | High | 30-100%+ | Buy at extreme prices during volatility |
| Alpha-Directional | Medium | 10-30% | Directional bets based on ML signals |
| Arbitrage | Low | 2-5% | Exploit price discrepancies across markets |

#### Asset Classes

| Class | Description |
|-------|-------------|
| Finance | Interest rates, economic indicators, market indices |
| Politics | Elections, policy decisions, government actions |
| Sports | Game outcomes, championships, player performance |
| Crypto | Bitcoin price, crypto events, blockchain milestones |
| Entertainment | Awards, box office, celebrity events |
| Science & Tech | Scientific discoveries, tech launches, AI developments |

---

## Best Practices

### For New Users
1. Start with paper trading (no real money)
2. Use conservative exit parameters
3. Enable only 2-3 strategies initially
4. Monitor for at least 24 hours before adjusting

### For Production
1. Increase trades/10min to 500+
2. Use moderate exit parameters
3. Enable all strategies for diversification
4. Set alerts for volume spikes

### Risk Management
1. Never disable Kelly Criterion
2. Keep Max Drawdown at 5% or less
3. Use Min Position Size of $5+ to avoid dust trades
4. Review closed trades daily for patterns

---

## API Reference

All configuration is stored in MongoDB and accessible via REST API:

- `GET /api/config` - Get current configuration
- `POST /api/config/update` - Update configuration
- `POST /api/config/reload-live` - Hot-reload during active session

See [API_REFERENCE.md](./API_REFERENCE.md) for detailed endpoint documentation.
