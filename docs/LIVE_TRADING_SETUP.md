# Live Trading Setup Guide

This guide explains how to transition from paper trading to live trading with real CLOB orders.

## Prerequisites

1. **Polygon Wallet**: You need an Ethereum wallet with funds on Polygon network
2. **USDC Balance**: Your wallet must hold USDC on Polygon to place orders
3. **Private Key**: Export your wallet's private key (NEVER share this)

## Configuration

### 1. Set Environment Variable

Add your private key to `/app/backend/.env`:

```bash
# WARNING: Keep this secret! Never commit to git!
POLYMARKET_PRIVATE_KEY=0x...your_private_key_here...
```

### 2. Enable Live Trading Mode

In your code, initialize the executor in LIVE mode:

```python
from trading.maker_executor import MakerOrderExecutor, ExecutionMode, initialize_executor

# Option 1: Explicit initialization
executor = await initialize_executor(mode=ExecutionMode.LIVE)

# Option 2: Via singleton
from trading.maker_executor import get_maker_executor
executor = get_maker_executor(mode=ExecutionMode.LIVE)
await executor.initialize()
```

### 3. Verify Authentication

```python
# Check if CLOB client is authenticated
print(f"Authenticated: {executor._clob_client.is_authenticated}")
```

## How It Works

### Paper Mode (Default)
- Simulates order fills based on market conditions
- No real money at risk
- Uses historical fill probabilities
- Good for backtesting and strategy development

### Live Mode
1. **Fetches fresh orderbook** from Polymarket CLOB API
2. **Rejects trades** if orderbook is unavailable or stale (>2s old)
3. **Places real limit orders** via `py-clob-client`
4. **Monitors order status** until filled, cancelled, or timeout
5. **Handles partial fills** and cancellations

## Safety Features

### Circuit Breaker
- Trips after 5 consecutive failures
- 60-second cooldown before resuming
- Prevents runaway losses from API issues

### Orderbook Validation
- Rejects if no orderbook data available
- Rejects if data is more than 2 seconds old
- Requires minimum liquidity depth ($100)

### Slippage Protection
- Max 1% slippage for taker orders
- Max 0.5% price movement for maker orders

## Order Execution Flow

```
1. Check circuit breaker
   ↓
2. Get token ID for market
   ↓
3. Fetch FRESH orderbook from CLOB
   ↓
4. Validate orderbook (not stale, has liquidity)
   ↓
5. Decide strategy:
   - High edge (>3%): Go directly as TAKER
   - Normal: Try MAKER first, then TAKER if unfilled
   ↓
6. MAKER: Place limit order at best bid/ask
   - Wait up to 3 seconds for fill
   - Cancel if unfilled
   ↓
7. TAKER (if maker unfilled and edge >2%):
   - Place aggressive limit order
   - Should fill immediately
   ↓
8. Record result, update stats
```

## Monitoring

### Execution Stats

```python
stats = executor.get_stats()
print(f"Mode: {stats['mode']}")
print(f"Maker Fill Rate: {stats['maker_fill_rate']:.1%}")
print(f"Net Spread P&L: ${stats['net_spread_pnl']:.2f}")
print(f"Circuit Breaker Active: {stats['circuit_breaker_active']}")
```

### CLOB Client Stats

```python
clob_stats = executor._clob_client.get_stats()
print(f"Orders Placed: {clob_stats['orders_placed']}")
print(f"Orders Filled: {clob_stats['orders_filled']}")
print(f"Total Volume: ${clob_stats['total_volume']:.2f}")
```

## API Reference

### ExecutionResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `order_type` | OrderType | MAKER or TAKER |
| `fill_status` | FillStatus | FILLED, PARTIAL, UNFILLED, CANCELLED, REJECTED |
| `fill_price` | float | Actual fill price |
| `fill_size` | float | Amount filled in USD |
| `slippage` | float | Price slippage from expected |
| `spread_captured` | float | +ve = captured spread, -ve = paid spread |
| `wait_time_ms` | int | Time waited for fill |
| `order_id` | str | CLOB order ID (live only) |
| `reason` | str | Human-readable reason |

### FillStatus Values

- `FILLED`: Order completely filled
- `PARTIAL`: Order partially filled (remaining cancelled)
- `UNFILLED`: Order not filled within timeout
- `CANCELLED`: Order cancelled by user/system
- `REJECTED`: Trade rejected due to validation failure

## Testing Checklist

Before going live:

- [ ] Test paper trading thoroughly
- [ ] Verify wallet has sufficient USDC balance
- [ ] Test with small position sizes first ($10-50)
- [ ] Monitor execution stats for anomalies
- [ ] Set up alerts for circuit breaker trips
- [ ] Have manual cancel-all capability ready

## Troubleshooting

### "Client not authenticated"
- Check POLYMARKET_PRIVATE_KEY is set correctly
- Ensure py-clob-client is installed: `pip install py-clob-client`

### "Orderbook stale"
- WebSocket connection may be lagging
- Try reducing trade frequency

### "Circuit breaker tripped"
- Check API connectivity
- Review recent error logs
- Wait for cooldown (60s) or manually reset

### "Insufficient liquidity"
- Market may be illiquid
- Increase min_orderbook_depth_usd threshold
