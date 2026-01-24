"""
Maker Order Execution Logic

Implements a "maker-first" execution strategy for prediction markets:
1. Try to post limit order at best bid/ask (maker - captures spread)
2. Wait for fill with timeout
3. Cross spread (taker) only if edge is high enough

In paper trading, this simulates the fill probability and spread capture.
For live trading, this would use actual CLOB API limit orders.
"""

import logging
import asyncio
import random
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OrderType(Enum):
    MAKER = "maker"  # Limit order, provides liquidity
    TAKER = "taker"  # Market order, takes liquidity


class FillStatus(Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    UNFILLED = "unfilled"
    CANCELLED = "cancelled"


@dataclass
class ExecutionResult:
    """Result of order execution attempt."""
    order_type: OrderType
    fill_status: FillStatus
    fill_price: float
    fill_size: float
    slippage: float
    spread_captured: float  # Positive = we captured spread, negative = we paid spread
    wait_time_ms: int
    attempts: int
    reason: str


# Configuration for maker execution
MAKER_CONFIG = {
    'maker_timeout_ms': 2000,           # Wait up to 2 seconds for maker fill
    'maker_fill_probability': 0.35,     # Base probability of maker fill (thin markets)
    'min_edge_for_taker': 0.02,         # 2% - minimum edge to cross spread as taker
    'min_edge_for_aggressive_taker': 0.03,  # 3% - edge for immediate taker execution
    'max_taker_slippage': 0.01,         # 1% max slippage for taker orders
    'spread_capture_pct': 0.5,          # Assume we capture 50% of spread as maker
}


class MakerOrderExecutor:
    """
    Simulates maker-first order execution strategy.
    
    In live trading, this would:
    1. POST a limit order at best bid (for buys) or best ask (for sells)
    2. Monitor order status via WebSocket
    3. After timeout, either cancel or cross spread
    
    In paper trading, we simulate fill probability based on:
    - Market volume (higher = better fill chance)
    - Spread width (tighter = better fill chance)
    - Order size relative to book depth
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = {**MAKER_CONFIG, **(config or {})}
        
        # Stats tracking
        self.stats = {
            'maker_attempts': 0,
            'maker_fills': 0,
            'taker_attempts': 0,
            'taker_fills': 0,
            'total_spread_captured': 0.0,
            'total_spread_paid': 0.0,
            'avg_wait_time_ms': 0,
        }
        
    async def execute_order(
        self,
        side: str,  # 'YES' or 'NO'
        size: float,
        market_data: Dict,
        edge: float,
    ) -> ExecutionResult:
        """
        Execute order with maker-first strategy.
        
        Args:
            side: 'YES' or 'NO'
            size: Order size in USD
            market_data: Market data including order book, prices, volume
            edge: Expected edge for this trade
            
        Returns:
            ExecutionResult with fill details
        """
        # Extract market data
        order_book = market_data.get('order_book', {})
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        volume_24h = market_data.get('volume_24h', 0)
        
        # Calculate spread
        best_bid = float(bids[0]['price']) if bids else 0.45
        best_ask = float(asks[0]['price']) if asks else 0.55
        spread = best_ask - best_bid
        spread_pct = spread / max(best_ask, 0.01)
        
        logger.info(f"[MAKER] Attempting {side} ${size:.2f} | Spread: {spread:.4f} ({spread_pct:.2%}) | Edge: {edge:.2%}")
        
        # Decision tree for execution strategy
        if edge >= self.config['min_edge_for_aggressive_taker']:
            # High edge - go directly as taker (speed matters more than spread)
            return await self._execute_as_taker(side, size, best_bid, best_ask, spread, edge, "high_edge")
        
        # Try maker first
        maker_result = await self._try_maker_fill(side, size, best_bid, best_ask, spread, volume_24h, edge)
        
        if maker_result.fill_status == FillStatus.FILLED:
            return maker_result
            
        # Maker unfilled - decide whether to cross spread
        if edge >= self.config['min_edge_for_taker']:
            # Edge still acceptable, cross spread as taker
            return await self._execute_as_taker(side, size, best_bid, best_ask, spread, edge, "maker_timeout")
        else:
            # Edge too small to justify paying spread - cancel
            logger.info(f"[MAKER] Cancelled - edge {edge:.2%} < min taker edge {self.config['min_edge_for_taker']:.2%}")
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.CANCELLED,
                fill_price=0,
                fill_size=0,
                slippage=0,
                spread_captured=0,
                wait_time_ms=self.config['maker_timeout_ms'],
                attempts=1,
                reason=f"edge_insufficient_for_taker"
            )
    
    async def _try_maker_fill(
        self,
        side: str,
        size: float,
        best_bid: float,
        best_ask: float,
        spread: float,
        volume_24h: float,
        edge: float,
    ) -> ExecutionResult:
        """Simulate maker order fill attempt."""
        self.stats['maker_attempts'] += 1
        
        # Calculate fill probability based on market conditions
        # Higher volume = better liquidity = higher fill chance
        volume_factor = min(1.0, volume_24h / 100000)  # Normalize to 100k volume
        
        # Tighter spread = more active market = higher fill chance
        spread_factor = max(0.3, 1.0 - (spread / 0.10))  # 10c spread = 0.3, 1c spread = 0.9
        
        # Smaller orders fill easier
        size_factor = max(0.5, 1.0 - (size / 1000))  # $1000 order = 0.5, $100 order = 0.9
        
        # Combined fill probability
        fill_prob = self.config['maker_fill_probability'] * volume_factor * spread_factor * size_factor
        fill_prob = min(0.8, fill_prob)  # Cap at 80%
        
        # Simulate wait time (random between 500ms and timeout)
        wait_time = random.randint(500, self.config['maker_timeout_ms'])
        
        # Simulate async wait (in paper trading, this is instant)
        # In live trading, this would actually wait and poll order status
        await asyncio.sleep(0.001)  # Minimal delay for paper trading
        
        # Determine if filled
        filled = random.random() < fill_prob
        
        if filled:
            self.stats['maker_fills'] += 1
            
            # Calculate fill price (we're at the front of the queue)
            # For YES buy: we bid at best_bid, fill at best_bid
            # For NO buy (YES sell): we ask at best_ask, fill at best_ask
            if side == 'YES':
                fill_price = best_bid
            else:
                fill_price = best_ask
            
            # Spread captured = we're providing liquidity, so we get the better price
            spread_captured = spread * self.config['spread_capture_pct']
            self.stats['total_spread_captured'] += spread_captured * size
            
            logger.info(f"[MAKER] ✅ FILLED as maker @ {fill_price:.4f} | Spread captured: ${spread_captured * size:.2f}")
            
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.FILLED,
                fill_price=fill_price,
                fill_size=size,
                slippage=0,  # No slippage as maker
                spread_captured=spread_captured * size,
                wait_time_ms=wait_time,
                attempts=1,
                reason="maker_fill"
            )
        else:
            logger.info(f"[MAKER] ⏳ Unfilled after {wait_time}ms (fill_prob: {fill_prob:.2%})")
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.UNFILLED,
                fill_price=0,
                fill_size=0,
                slippage=0,
                spread_captured=0,
                wait_time_ms=wait_time,
                attempts=1,
                reason="maker_unfilled"
            )
    
    async def _execute_as_taker(
        self,
        side: str,
        size: float,
        best_bid: float,
        best_ask: float,
        spread: float,
        edge: float,
        reason: str,
    ) -> ExecutionResult:
        """Execute as taker (cross the spread)."""
        self.stats['taker_attempts'] += 1
        self.stats['taker_fills'] += 1
        
        # For taker orders, we cross the spread
        # YES buy: we pay best_ask (higher price)
        # NO buy (YES sell): we pay best_bid (lower price)
        if side == 'YES':
            fill_price = best_ask
            # Simulate slippage based on size
            slippage = min(self.config['max_taker_slippage'], size / 50000)
            fill_price += slippage
        else:
            fill_price = best_bid
            slippage = min(self.config['max_taker_slippage'], size / 50000)
            fill_price -= slippage
        
        # Spread paid = we're taking liquidity, so we pay the spread
        spread_paid = spread * 0.5  # We pay half the spread
        self.stats['total_spread_paid'] += spread_paid * size
        
        logger.info(f"[MAKER] 💨 TAKER @ {fill_price:.4f} | Spread paid: ${spread_paid * size:.2f} | Reason: {reason}")
        
        return ExecutionResult(
            order_type=OrderType.TAKER,
            fill_status=FillStatus.FILLED,
            fill_price=fill_price,
            fill_size=size,
            slippage=slippage,
            spread_captured=-spread_paid * size,  # Negative = we paid
            wait_time_ms=0 if reason == "high_edge" else self.config['maker_timeout_ms'],
            attempts=1,
            reason=reason
        )
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        total_attempts = self.stats['maker_attempts'] + self.stats['taker_attempts']
        maker_rate = self.stats['maker_fills'] / max(1, self.stats['maker_attempts'])
        
        return {
            **self.stats,
            'maker_fill_rate': round(maker_rate, 3),
            'net_spread_pnl': round(
                self.stats['total_spread_captured'] - self.stats['total_spread_paid'], 2
            ),
            'total_executions': total_attempts,
        }
    
    def should_trade_given_spread(self, edge: float, spread: float) -> Tuple[bool, str]:
        """
        Pre-check if trade is worthwhile given the spread.
        
        Returns (should_trade, reason)
        """
        if edge <= 0:
            return False, "no_edge"
            
        # If spread eats more than 50% of edge, probably not worth it
        if spread > edge * 0.5:
            if edge < self.config['min_edge_for_aggressive_taker']:
                return False, f"spread_too_wide: spread={spread:.4f} > edge*0.5={edge*0.5:.4f}"
        
        return True, "ok"


# Singleton instance
_maker_executor: Optional[MakerOrderExecutor] = None


def get_maker_executor() -> MakerOrderExecutor:
    """Get singleton MakerOrderExecutor instance."""
    global _maker_executor
    if _maker_executor is None:
        _maker_executor = MakerOrderExecutor()
    return _maker_executor
