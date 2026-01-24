# HFT Architecture Improvement Analysis

**Created:** January 24, 2026  
**Status:** Analysis Complete - No Changes Made  
**Purpose:** Audit of suggested HFT improvements vs current implementation

---

## Summary Table

| Suggestion | Status | Notes |
|------------|--------|-------|
| 1. Decouple Fast/Slow Loops | ⚠️ PARTIAL | WebSocket exists but not integrated into trading loop |
| 2. WebSocket for Price Updates | ⚠️ PARTIAL | Infrastructure exists at `/data/polymarket_websocket.py` but paper trader uses REST polling |
| 3. Order Book Imbalance Feature | ✅ IMPLEMENTED | `polymarket_sentiment.py` calculates bid/ask depth imbalance |
| 4. LLM Caching | ✅ IMPLEMENTED | Smart cache with volume-based TTL in `sentiment_llm.py` |
| 5. Log-Odds Model | ✅ IMPLEMENTED | Bayesian Log-Odds fusion in `paper_trader.py` |
| 6. Probability Clamping | ✅ IMPLEMENTED | Values clamped to 0.001-0.999 range |
| 7. Spread Awareness | ✅ IMPLEMENTED | `adaptive_position_sizer.py` has spread adjustment |
| 8. Maker vs Taker Logic | ❌ NOT IMPLEMENTED | No Post-Only or Limit Order logic |
| 9. Correlated Event Exposure | ⚠️ PARTIAL | Sector caps exist but not per-event correlation |
| 10. Ensemble Kelly | ❌ NOT IMPLEMENTED | Standard Kelly, no ensemble for correlated outcomes |

---

## Detailed Analysis

### 1. Architectural Bottlenecks - Decouple Fast/Slow Loops

**Status:** ⚠️ PARTIALLY IMPLEMENTED

**What Exists:**
- WebSocket infrastructure at `/app/backend/data/polymarket_websocket.py`
- Multiple async loops in paper_trader.py:
  - `_trading_loop()` - main trading
  - `_position_monitoring_loop()` - position updates
  - `_learning_loop()` - RL learning
- LLM cache with TTL-based expiration

**What's Missing:**
- Paper trader's `_trading_loop()` still uses REST API polling for market data
- No true "Fast Loop" (ms) vs "Slow Loop" (mins) separation
- Sentiment analysis runs inline with trading decisions, not in background

**Current Flow:**
```
Trading Loop (every ~30s):
  1. REST API fetch 200 markets (blocking)
  2. For each market: get sentiment (may call LLM if cache miss)
  3. Calculate signals
  4. Execute trades
```

**Suggested Architecture:**
```
Fast Loop (WebSocket, <100ms):
  - Subscribe to top 200 markets
  - Receive real-time price/book updates
  - Execute on cached signals

Slow Loop (Background, every 5 mins):
  - Discover new markets via REST
  - Update sentiment cache
  - Retrain RL model
```

---

### 2. WebSocket for Price Updates

**Status:** ⚠️ PARTIALLY IMPLEMENTED

**What Exists:**
```python
# /app/backend/data/polymarket_websocket.py
class PolymarketWebSocket:
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    async def subscribe_to_market(self, condition_id: str)
    async def subscribe_to_orderbook(self, token_id: str)
    # Full implementation with reconnection logic
```

**What's Missing:**
- Paper trader does NOT use this WebSocket client
- `paper_trader.py` line ~1850 calls REST API:
  ```python
  markets = await self.fetch_markets()  # REST polling
  ```

**Suggestion:**
Integrate `PolymarketWebSocketManager` into paper trader:
1. Subscribe to top markets on startup
2. Use WebSocket callbacks for price updates
3. Keep REST API only for market discovery (every 5 mins)

---

### 3. Order Book Imbalance Feature

**Status:** ✅ IMPLEMENTED

**Location:** `/app/backend/ml/polymarket_sentiment.py`

```python
# Lines 193-210
bid_depth = sum(float(b.get('size', 0)) for b in bids[:10])
ask_depth = sum(float(a.get('size', 0)) for a in asks[:10])
total_depth = bid_depth + ask_depth

if total_depth > 0:
    depth_imbalance = bid_depth / total_depth  # 0.6 = bullish, 0.4 = bearish
```

**No Changes Needed** - Already feeding order book imbalance to DQN via sentiment signals.

---

### 4. LLM Caching (Async Sentiment)

**Status:** ✅ IMPLEMENTED

**Location:** `/app/backend/ml/sentiment_llm.py`

```python
DEFAULT_CONFIG = {
    'hot_market_ttl_seconds': 600,    # 10 minutes for high-volume
    'cold_market_ttl_seconds': 3600,  # 60 minutes for low-volume
    'volume_threshold_high': 50000,   # Above = hot market
}

def _get_ttl(self, volume_24h: float) -> int:
    if volume_24h >= self._config['volume_threshold_high']:
        return self._config['hot_market_ttl_seconds']
    return self._config['cold_market_ttl_seconds']
```

**Enhancement Suggestion:**
Add a "Breaking News" trigger that invalidates cache early. Could monitor:
- Sudden volume spikes (>3x average)
- Large price movements (>5% in 5 mins)
- External news API integration

---

### 5. Log-Odds Model (Avoid Multiplicative Math)

**Status:** ✅ IMPLEMENTED

**Location:** `/app/backend/paper_trading/paper_trader.py` - `_calculate_model_probability()`

```python
# Bayesian Log-Odds Fusion
def logit(p):
    return math.log(p / (1 - p))

def inv_logit(lo):
    return 1 / (1 + math.exp(-lo))

# Base: market price as prior
base_log_odds = logit(yes_price)

# Updates from signals
sentiment_delta = SENTIMENT_WEIGHT * logit(p_sentiment)
rl_delta = RL_WEIGHT * logit(rl_prob)

# Fusion
final_log_odds = base_log_odds + sentiment_delta + rl_delta
P_model = inv_logit(final_log_odds)
```

**No Changes Needed** - Already using proper Bayesian log-odds fusion.

---

### 6. Probability Clamping

**Status:** ✅ IMPLEMENTED

**Location:** `/app/backend/paper_trading/paper_trader.py`

```python
# Line 2726
sentiment = max(0.001, min(0.999, sentiment))
```

Also inherent in log-odds math (logit(0) and logit(1) are undefined, so clamping happens naturally).

---

### 7. Spread Awareness

**Status:** ✅ IMPLEMENTED

**Location:** `/app/backend/ml/adaptive_position_sizer.py`

```python
# Lines 219-246
def calculate_spread_adjustment(self, market_data: Dict, yes_price: float) -> float:
    spread = best_ask - best_bid
    spread_pct = spread / max(yes_price, 0.01)
    
    # Inverse relationship: tight spread = larger position
    base_spread = 0.02
    spread_mult = base_spread / max(spread_pct, 0.005)
    
    return max(0.4, min(1.3, spread_mult))
```

**Enhancement Suggestion:**
Add spread check BEFORE deciding to trade (not just for sizing):
```python
if spread > edge * 2:
    return None  # Don't trade if spread eats >50% of edge
```

---

### 8. Maker vs Taker Logic (Post-Only Orders)

**Status:** ❌ NOT IMPLEMENTED

**Current Behavior:**
Paper trader simulates market orders (taker). No concept of:
- Posting limit orders at bid
- Waiting for fill
- Crossing spread only if edge is high enough

**Suggestion:**
```python
async def execute_with_maker_priority(self, market_id, side, size, edge):
    """
    1. Post limit order at best bid/ask
    2. Wait up to 2 seconds for fill
    3. If unfilled and edge > 3%, cross spread (taker)
    4. If unfilled and edge < 3%, cancel
    """
    # Implementation would require:
    # - Limit order placement via CLOB API
    # - Order status tracking
    # - Timeout management
```

**Impact:** This is a significant enhancement for live trading but less critical for paper trading (which doesn't have real execution).

---

### 9. Correlated Event Exposure Cap

**Status:** ⚠️ PARTIALLY IMPLEMENTED

**What Exists:**
- Sector caps (crypto: 20%, sports: 30%, politics: 25%, etc.)
- Correlation dampener in position sizer

```python
# /app/backend/ml/polymarket_position_sizer.py
'sector_caps': {
    'crypto': 0.20,
    'sports': 0.30,
    'politics': 0.25,
    ...
}
```

**What's Missing:**
Per-event correlation cap. Example:
- "Who wins 2026 Election?" has 10 candidate markets
- Each candidate is 0.03-0.97 correlated with others
- Betting YES on candidate A is essentially betting NO on candidates B-J

**Suggestion:**
```python
def get_event_exposure(self, market_id: str) -> float:
    """Sum exposure across all markets in same event/question group"""
    event_id = self._get_event_id(market_id)  # Group by parent event
    related_markets = self._get_markets_by_event(event_id)
    return sum(self.positions.get(m, {}).get('size', 0) for m in related_markets)

# In position sizing:
event_exposure = self.get_event_exposure(market_id)
event_cap = self.deployed_capital * 0.15  # Max 15% per event
if event_exposure + position_size > event_cap:
    position_size = max(0, event_cap - event_exposure)
```

---

### 10. Ensemble Kelly for Correlated Outcomes

**Status:** ❌ NOT IMPLEMENTED

**Current:** Standard Kelly criterion applied independently per market.

**Problem:** If you have 10% edge on "Candidate A wins" and "Candidate B loses" (same event), betting full Kelly on both is over-leveraged because they're ~100% correlated.

**Suggestion:**
```python
def ensemble_kelly(self, edges: List[float], correlations: np.array) -> List[float]:
    """
    Multi-asset Kelly with correlation adjustment.
    
    For highly correlated outcomes (>0.8), treat as single position
    and allocate Kelly fraction to the highest-edge one only.
    """
    # Simplified version:
    # 1. Cluster markets by event/correlation
    # 2. Within each cluster, pick highest edge
    # 3. Apply Kelly to cluster, not individual markets
```

---

## Priority Recommendations

### High Priority (Significant Impact)
1. **Integrate WebSocket into Trading Loop** - Reduce latency from 3s to <100ms
2. **Add Event-Level Exposure Cap** - Prevent over-betting on correlated outcomes
3. **Spread Check Before Trade Decision** - Avoid trades where spread > 50% of edge

### Medium Priority (Nice to Have)
4. **Breaking News Cache Invalidation** - React faster to sudden market changes
5. **Maker Order Priority for Live Trading** - Capture spread instead of paying it

### Low Priority (Future Optimization)
6. **Ensemble Kelly** - Complex implementation, marginal gains unless trading many correlated markets
7. **Full Fast/Slow Loop Decoupling** - Requires significant refactor

---

## Files to Modify (When Ready)

| Suggestion | Files |
|------------|-------|
| WebSocket Integration | `paper_trader.py`, `server.py` |
| Event Exposure Cap | `polymarket_position_sizer.py`, `portfolio_manager.py` |
| Spread Pre-Check | `paper_trader.py` (trade decision logic) |
| Breaking News Trigger | `sentiment_llm.py`, `polymarket_sentiment.py` |
| Maker Orders | `paper_trader.py` (execution layer) |

---

## Conclusion

The codebase already implements several sophisticated features:
- ✅ Bayesian Log-Odds probability fusion
- ✅ Order book imbalance for DQN
- ✅ Volume-based LLM caching
- ✅ Spread-aware position sizing
- ✅ Sector caps

The main gaps are:
- ❌ WebSocket not used for real-time trading (infrastructure exists but unused)
- ❌ No event-level correlation cap (only sector caps)
- ❌ No maker/taker order logic
