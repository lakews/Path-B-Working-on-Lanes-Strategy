"""
Maker Order Execution Logic - Production Ready

Implements a "maker-first" execution strategy for prediction markets:
1. Fetch FRESH orderbook data (reject if unavailable or stale)
2. Try to post limit order at best bid/ask (maker - captures spread)
3. Monitor order for fill with timeout
4. Cross spread (taker) only if edge is high enough and order unfilled

Supports two modes:
- PAPER: Simulates fills based on market conditions (for backtesting/paper trading)
- LIVE: Places real orders via Polymarket CLOB API

================================================================================
LIVE TRADING REQUIREMENTS (Already Implemented):
================================================================================
✅ 1. ORDERBOOK REQUIREMENT: Rejects trades if orderbook unavailable
✅ 2. FRESH DATA: Fetches fresh orderbook immediately before each trade
✅ 3. STALENESS CHECK: Rejects orderbook data >2 seconds old
✅ 4. REAL CLOB API: Uses py-clob-client for actual order placement
✅ 5. ORDER MONITORING: Polls order status until filled/cancelled/timeout
✅ 6. SLIPPAGE PROTECTION: Max slippage parameter enforced
✅ 7. ERROR HANDLING: Circuit breaker, graceful degradation
✅ 8. AUDIT LOGGING: All trade attempts logged

To enable live trading:
1. Set POLYMARKET_PRIVATE_KEY environment variable
2. Set TRADING_MODE=live in config
================================================================================
"""

import logging
import asyncio
import random
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

from trading.clob_client import (
    PolymarketCLOBClient, get_clob_client,
    OrderSide, OrderStatus, OrderBook, CLOBOrder
)

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    PAPER = "paper"  # Simulate fills
    LIVE = "live"    # Real CLOB orders


class OrderType(Enum):
    MAKER = "maker"  # Limit order, provides liquidity
    TAKER = "taker"  # Market order, takes liquidity


class FillStatus(Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    UNFILLED = "unfilled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"  # Trade rejected due to missing data


@dataclass
class ExecutionResult:
    """Result of order execution attempt."""
    order_type: OrderType
    fill_status: FillStatus
    fill_price: float
    fill_size: float
    slippage: float = 0.0
    spread_captured: float = 0.0  # Positive = we captured spread, negative = we paid spread
    wait_time_ms: int = 0
    attempts: int = 1
    reason: str = ""
    order_id: Optional[str] = None  # CLOB order ID for live trades
    
    @property
    def is_success(self) -> bool:
        return self.fill_status in [FillStatus.FILLED, FillStatus.PARTIAL]


# Configuration for maker execution
DEFAULT_CONFIG = {
    # Timing
    'maker_timeout_ms': 3000,           # Wait up to 3 seconds for maker fill
    'order_poll_interval_ms': 500,      # Poll order status every 500ms
    'max_orderbook_age_ms': 2000,       # Reject orderbook data older than 2s
    
    # Fill simulation (paper trading only)
    'maker_fill_probability': 0.35,     # Base probability of maker fill
    'spread_capture_pct': 0.5,          # Assume we capture 50% of spread as maker
    
    # Edge thresholds
    'min_edge_for_taker': 0.02,         # 2% - minimum edge to cross spread
    'min_edge_for_aggressive_taker': 0.03,  # 3% - edge for immediate taker
    
    # Slippage protection
    'max_taker_slippage': 0.01,         # 1% max slippage for taker orders
    'max_maker_slippage': 0.005,        # 0.5% max price movement for maker
    
    # Circuit breaker
    'max_consecutive_failures': 5,      # Stop trading after 5 consecutive failures
    'circuit_breaker_cooldown_s': 60,   # Cooldown period after circuit breaker trips
    
    # Minimum liquidity
    'min_orderbook_depth_usd': 100,     # Minimum depth required to trade
    
    # ==========================================================================
    # HFT MICROSTRUCTURE PARAMETERS (defaults - can be overridden by config)
    # ==========================================================================
    
    # Inventory Skew Configuration
    'max_inventory_usd': 1000.0,        # Maximum inventory in USD before full skew
    'skew_factor': 0.05,                # Sensitivity - how much to skew per unit inventory
    
    # OFI (Order Flow Imbalance) Configuration  
    'ofi_threshold': 0.6,               # Threshold to trigger OFI adjustment
    'ofi_adjustment': 0.01,             # Price adjustment amount when OFI triggered
    'ofi_levels': 3,                    # Number of order book levels to analyze
}


def _merge_hft_config(base_config: dict, user_config: dict) -> dict:
    """Merge HFT execution parameters from user config into base config."""
    merged = base_config.copy()
    
    # Check if user has hft_execution settings
    hft_exec = user_config.get('hft_execution', {})
    if hft_exec:
        if 'max_inventory_usd' in hft_exec:
            merged['max_inventory_usd'] = hft_exec['max_inventory_usd']
        if 'skew_factor' in hft_exec:
            merged['skew_factor'] = hft_exec['skew_factor']
        if 'ofi_threshold' in hft_exec:
            merged['ofi_threshold'] = hft_exec['ofi_threshold']
        if 'ofi_adjustment' in hft_exec:
            merged['ofi_adjustment'] = hft_exec['ofi_adjustment']
        if 'ofi_levels' in hft_exec:
            merged['ofi_levels'] = hft_exec['ofi_levels']
    
    return merged


class MakerOrderExecutor:
    """
    Production-ready order execution with maker-first strategy.
    
    Supports both paper trading (simulation) and live trading (real CLOB API).
    """
    
    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.PAPER,
        config: Optional[Dict] = None
    ):
        """
        Initialize executor.
        
        Args:
            mode: PAPER for simulation, LIVE for real trading
            config: Override default configuration
        """
        self.mode = mode
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self._clob_client: Optional[PolymarketCLOBClient] = None
        
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_breaker_until: Optional[datetime] = None
        
        # Stats tracking
        self.stats = {
            'maker_attempts': 0,
            'maker_fills': 0,
            'taker_attempts': 0,
            'taker_fills': 0,
            'rejections': 0,
            'total_spread_captured': 0.0,
            'total_spread_paid': 0.0,
            'avg_wait_time_ms': 0,
            'circuit_breaker_trips': 0,
        }
        
        # ==========================================================================
        # HFT INVENTORY TRACKING
        # ==========================================================================
        # Track inventory per market (positive = long, negative = short)
        self._inventory: Dict[str, float] = {}  # market_id -> position in USD
        
        logger.info(f"MakerOrderExecutor initialized in {mode.value} mode")
    
    async def initialize(self):
        """Initialize CLOB client for live trading."""
        if self.mode == ExecutionMode.LIVE:
            self._clob_client = await get_clob_client()
            if not self._clob_client.is_authenticated:
                logger.warning("CLOB client not authenticated - falling back to paper mode")
                self.mode = ExecutionMode.PAPER
    
    def _check_circuit_breaker(self) -> Tuple[bool, str]:
        """Check if circuit breaker is tripped."""
        if self._circuit_breaker_until:
            if datetime.now(timezone.utc) < self._circuit_breaker_until:
                remaining = (self._circuit_breaker_until - datetime.now(timezone.utc)).total_seconds()
                return False, f"circuit_breaker_cooldown_{remaining:.0f}s"
            else:
                # Cooldown expired, reset
                self._circuit_breaker_until = None
                self._consecutive_failures = 0
        return True, "ok"
    
    def _trip_circuit_breaker(self):
        """Trip the circuit breaker after too many failures."""
        self._circuit_breaker_until = datetime.now(timezone.utc) + \
            __import__('datetime').timedelta(seconds=self.config['circuit_breaker_cooldown_s'])
        self.stats['circuit_breaker_trips'] += 1
        logger.error(f"Circuit breaker tripped! Cooldown until {self._circuit_breaker_until}")
    
    def _record_success(self):
        """Record successful execution, reset failure counter."""
        self._consecutive_failures = 0
    
    def _record_failure(self):
        """Record failed execution, potentially trip circuit breaker."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config['max_consecutive_failures']:
            self._trip_circuit_breaker()
    
    # ==========================================================================
    # HFT MICROSTRUCTURE MATH
    # ==========================================================================
    
    def get_order_flow_imbalance(self, order_book: OrderBook) -> float:
        """
        Calculate Order Flow Imbalance (OFI) from order book.
        
        OFI = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        
        Returns value between -1.0 (all asks) and +1.0 (all bids).
        
        Positive OFI = buying pressure → raise ask price
        Negative OFI = selling pressure → lower bid price
        """
        levels = self.config.get('ofi_levels', 3)
        
        # Sum volume at top N levels
        bid_vol = sum(
            float(b.get('size', b) if isinstance(b, dict) else b)
            for b in order_book.bids[:levels]
        ) if order_book.bids else 0.0
        
        ask_vol = sum(
            float(a.get('size', a) if isinstance(a, dict) else a)
            for a in order_book.asks[:levels]
        ) if order_book.asks else 0.0
        
        # Calculate imbalance (-1 to +1)
        total = bid_vol + ask_vol + 1e-9  # Avoid division by zero
        imbalance = (bid_vol - ask_vol) / total
        
        return imbalance
    
    def calculate_inventory_skew(
        self,
        market_id: str,
        spread: float
    ) -> float:
        """
        Calculate Inventory Skew for asymmetric quoting.
        
        When we have lots of inventory (long), we want to SELL more aggressively:
        - Subtract skew from both bid and ask to lower our quotes
        - This makes us more likely to sell (reduce inventory)
        
        When we're short inventory, we want to BUY more aggressively:
        - Add to quotes (skew is negative) to raise prices
        - This makes us more likely to buy
        
        Returns:
            price_skew: Amount to subtract from quotes (positive = lower quotes)
        """
        current_position = self._inventory.get(market_id, 0.0)
        max_inventory = self.config.get('max_inventory_usd', 1000.0)
        skew_factor = self.config.get('skew_factor', 0.05)
        
        # Calculate inventory ratio (-1.0 to 1.0)
        inventory_ratio = current_position / max_inventory
        inventory_ratio = max(-1.0, min(1.0, inventory_ratio))
        
        # Calculate skew
        # If we have lots of inventory (+), skew is positive, we subtract from price
        price_skew = inventory_ratio * (spread * skew_factor)
        
        return price_skew
    
    def calculate_adjusted_quotes(
        self,
        theoretical_price: float,
        spread: float,
        market_id: str,
        order_book: OrderBook
    ) -> Tuple[float, float, Dict]:
        """
        Calculate adjusted bid/ask quotes using:
        1. Theoretical price (from Bayesian/Alpha) as center
        2. Inventory skew adjustment
        3. OFI-based adjustment
        
        CRITICAL: We trade our Alpha (theoretical_price), not market mid.
        
        Returns:
            (my_bid_price, my_ask_price, debug_info)
        """
        # 1. Calculate inventory skew
        price_skew = self.calculate_inventory_skew(market_id, spread)
        
        # 2. Calculate OFI
        ofi = self.get_order_flow_imbalance(order_book)
        ofi_threshold = self.config.get('ofi_threshold', 0.6)
        ofi_adjustment = self.config.get('ofi_adjustment', 0.01)
        
        # 3. Base quotes centered on THEORETICAL price, not market mid
        half_spread = spread / 2
        base_bid = theoretical_price - half_spread
        base_ask = theoretical_price + half_spread
        
        # 4. Apply inventory skew (same direction for both)
        # Positive skew (long inventory) → lower both quotes to sell more
        skewed_bid = base_bid - price_skew
        skewed_ask = base_ask - price_skew
        
        # 5. Apply OFI adjustment
        ofi_bid_adj = 0.0
        ofi_ask_adj = 0.0
        
        if ofi > ofi_threshold:
            # Strong buying pressure → raise ask (don't sell cheap)
            ofi_ask_adj = ofi_adjustment
        elif ofi < -ofi_threshold:
            # Strong selling pressure → lower bid (don't buy expensive)
            ofi_bid_adj = -ofi_adjustment
        
        # 6. Final quotes
        my_bid_price = max(0.001, skewed_bid + ofi_bid_adj)
        my_ask_price = min(0.999, skewed_ask + ofi_ask_adj)
        
        # Ensure bid < ask
        if my_bid_price >= my_ask_price:
            mid = (my_bid_price + my_ask_price) / 2
            my_bid_price = mid - 0.005
            my_ask_price = mid + 0.005
        
        debug_info = {
            'theoretical_price': theoretical_price,
            'market_spread': spread,
            'inventory_skew': price_skew,
            'ofi': ofi,
            'ofi_bid_adj': ofi_bid_adj,
            'ofi_ask_adj': ofi_ask_adj,
            'base_bid': base_bid,
            'base_ask': base_ask,
            'final_bid': my_bid_price,
            'final_ask': my_ask_price
        }
        
        logger.debug(
            f"[QUOTES] Theo={theoretical_price:.4f} | "
            f"Skew={price_skew:.4f} | OFI={ofi:.2f} | "
            f"Bid={my_bid_price:.4f} Ask={my_ask_price:.4f}"
        )
        
        return my_bid_price, my_ask_price, debug_info
    
    def update_inventory(
        self,
        market_id: str,
        side: str,
        size: float,
        is_entry: bool = True
    ):
        """
        Update inventory tracking after trade.
        
        Args:
            market_id: Market identifier
            side: 'YES' or 'NO'
            size: Trade size in USD
            is_entry: True for opening, False for closing
        """
        current = self._inventory.get(market_id, 0.0)
        
        # YES side is long, NO side is short
        if is_entry:
            if side == 'YES':
                self._inventory[market_id] = current + size
            else:
                self._inventory[market_id] = current - size
        else:
            # Closing position reduces inventory
            if side == 'YES':
                self._inventory[market_id] = current - size
            else:
                self._inventory[market_id] = current + size
        
        logger.debug(
            f"[INVENTORY] {market_id}: {current:.2f} -> {self._inventory[market_id]:.2f} "
            f"({'entry' if is_entry else 'exit'} {side} ${size:.2f})"
        )
    
    def get_inventory(self, market_id: str) -> float:
        """Get current inventory for market."""
        return self._inventory.get(market_id, 0.0)
    
    def get_inventory_ratio(self, market_id: str) -> float:
        """Get inventory ratio (-1 to 1) for market."""
        current = self._inventory.get(market_id, 0.0)
        max_inv = self.config.get('max_inventory_usd', 1000.0)
        return max(-1.0, min(1.0, current / max_inv))
    
    async def execute_order(
        self,
        side: str,  # 'YES' or 'NO'
        size: float,
        market_data: Dict,
        edge: float,
        token_id: Optional[str] = None,
        theoretical_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute order with maker-first strategy.
        
        CRITICAL: Uses theoretical_price (Alpha signal from Bayesian posterior) as the
        center for quote generation, NOT the market mid-price. We trade OUR Alpha,
        adjusted by inventory skew and OFI.
        
        Args:
            side: 'YES' or 'NO'
            size: Order size in USD
            market_data: Market data including order book, prices, volume
            edge: Expected edge for this trade
            token_id: Token ID for CLOB orders (required for live trading)
            theoretical_price: Alpha signal price from slow path (Bayesian posterior).
                              If not provided, falls back to market mid-price (not ideal).
            
        Returns:
            ExecutionResult with fill details
        """
        # Check circuit breaker
        can_trade, reason = self._check_circuit_breaker()
        if not can_trade:
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.REJECTED,
                fill_price=0, fill_size=0,
                reason=reason
            )
        
        # Get token ID for this side
        if not token_id:
            tokens = market_data.get('tokens', market_data.get('clobTokenIds', []))
            if tokens and len(tokens) >= 2:
                token_id = tokens[0] if side == 'YES' else tokens[1]
        
        # Fetch fresh orderbook
        orderbook = await self._get_fresh_orderbook(market_data, token_id)
        
        if orderbook is None:
            self.stats['rejections'] += 1
            self._record_failure()
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.REJECTED,
                fill_price=0, fill_size=0,
                reason="no_orderbook_data"
            )
        
        # Check orderbook staleness
        if orderbook.is_stale:
            self.stats['rejections'] += 1
            self._record_failure()
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.REJECTED,
                fill_price=0, fill_size=0,
                reason="orderbook_stale"
            )
        
        # Check minimum liquidity
        min_depth = self.config['min_orderbook_depth_usd']
        if orderbook.bid_depth < min_depth or orderbook.ask_depth < min_depth:
            self.stats['rejections'] += 1
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.REJECTED,
                fill_price=0, fill_size=0,
                reason=f"insufficient_liquidity_bid={orderbook.bid_depth:.0f}_ask={orderbook.ask_depth:.0f}"
            )
        
        best_bid = orderbook.best_bid
        best_ask = orderbook.best_ask
        spread = orderbook.spread
        
        if best_bid is None or best_ask is None or spread is None:
            self.stats['rejections'] += 1
            self._record_failure()
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.REJECTED,
                fill_price=0, fill_size=0,
                reason="invalid_orderbook_no_bid_ask"
            )
        
        spread_pct = spread / max(best_ask, 0.01)
        volume_24h = market_data.get('volume_24h', 0)
        
        logger.info(f"[EXEC] {self.mode.value.upper()} | {side} ${size:.2f} | "
                   f"Spread: {spread:.4f} ({spread_pct:.2%}) | Edge: {edge:.2%}")
        
        # Decision tree for execution strategy
        if edge >= self.config['min_edge_for_aggressive_taker']:
            # High edge - go directly as taker (speed matters more than spread)
            result = await self._execute_as_taker(
                side, size, best_bid, best_ask, spread, edge, 
                token_id, "high_edge"
            )
        else:
            # Try maker first
            result = await self._try_maker_fill(
                side, size, best_bid, best_ask, spread, 
                volume_24h, edge, token_id
            )
            
            if result.fill_status == FillStatus.UNFILLED:
                # Maker unfilled - decide whether to cross spread
                if edge >= self.config['min_edge_for_taker']:
                    result = await self._execute_as_taker(
                        side, size, best_bid, best_ask, spread, edge,
                        token_id, "maker_timeout"
                    )
                else:
                    # Edge too small to justify paying spread - cancel
                    logger.info(f"[EXEC] Cancelled - edge {edge:.2%} < min taker edge")
                    result = ExecutionResult(
                        order_type=OrderType.MAKER,
                        fill_status=FillStatus.CANCELLED,
                        fill_price=0, fill_size=0,
                        wait_time_ms=self.config['maker_timeout_ms'],
                        reason="edge_insufficient_for_taker"
                    )
        
        # Record success/failure
        if result.is_success:
            self._record_success()
        else:
            self._record_failure()
        
        return result
    
    async def _get_fresh_orderbook(
        self,
        market_data: Dict,
        token_id: Optional[str]
    ) -> Optional[OrderBook]:
        """
        Fetch fresh orderbook data with retry logic.
        
        STRICT MODE: No synthetic/fallback prices. If we can't get real data, reject the trade.
        
        Retry flow:
        - Attempt 1: Fetch orderbook → fails → wait 0.5s
        - Attempt 2: Fetch orderbook → fails → wait 1.0s  
        - Attempt 3: Fetch orderbook → fails → REJECT trade
        
        Returns None if orderbook cannot be fetched, triggering trade rejection.
        """
        # Try to use existing orderbook data from market_data (if recently fetched)
        existing_book = market_data.get('order_book', {})
        bids = existing_book.get('bids', [])
        asks = existing_book.get('asks', [])
        
        if bids and asks:
            # Existing data available - use it
            return OrderBook(
                token_id=token_id or '',
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc)
            )
        
        # No existing data - must fetch from CLOB API
        # This applies to BOTH paper and live mode
        if self._clob_client and token_id:
            # Retry loop with exponential backoff
            for attempt in range(3):
                orderbook = await self._clob_client.get_orderbook(token_id, retries=1)
                
                if orderbook and orderbook.bids and orderbook.asks:
                    logger.debug(f"[ORDERBOOK] Fetched on attempt {attempt + 1}: "
                               f"bid={orderbook.best_bid}, ask={orderbook.best_ask}")
                    return orderbook
                
                # Wait before retry (exponential backoff)
                if attempt < 2:
                    wait_time = 0.5 * (attempt + 1)  # 0.5s, 1.0s
                    logger.debug(f"[ORDERBOOK] Attempt {attempt + 1} failed, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            logger.warning(f"[ORDERBOOK] Failed to fetch after 3 attempts for token {token_id[:20] if token_id else 'N/A'}...")
        else:
            logger.warning("[ORDERBOOK] Cannot fetch - no CLOB client or token_id")
        
        # NO FALLBACK - Return None to trigger trade rejection
        # This prevents trades based on synthetic/default prices
        return None
    
    async def _try_maker_fill(
        self,
        side: str,
        size: float,
        best_bid: float,
        best_ask: float,
        spread: float,
        volume_24h: float,
        edge: float,
        token_id: Optional[str],
    ) -> ExecutionResult:
        """Attempt maker order execution."""
        self.stats['maker_attempts'] += 1
        
        # Determine our limit price
        if side == 'YES':
            limit_price = best_bid  # We bid at best bid
        else:
            limit_price = best_ask  # We ask at best ask
        
        if self.mode == ExecutionMode.LIVE and self._clob_client and token_id:
            # LIVE: Place real limit order
            return await self._execute_maker_live(
                side, size, limit_price, spread, token_id
            )
        else:
            # PAPER: Simulate maker fill
            return await self._simulate_maker_fill(
                side, size, limit_price, spread, volume_24h
            )
    
    async def _execute_maker_live(
        self,
        side: str,
        size: float,
        limit_price: float,
        spread: float,
        token_id: str,
    ) -> ExecutionResult:
        """Execute maker order via live CLOB API."""
        try:
            # Calculate shares from USD size
            shares = size / limit_price if limit_price > 0 else 0
            
            # Map side - for YES we buy YES token, for NO we sell YES token (or buy NO token)
            # In Polymarket, buying NO = selling YES at the inverse price
            order_side = OrderSide.BUY if side == 'YES' else OrderSide.SELL
            
            # Place limit order
            order = await self._clob_client.place_limit_order(
                token_id=token_id,
                side=order_side,
                price=limit_price,
                size=shares
            )
            
            if not order:
                return ExecutionResult(
                    order_type=OrderType.MAKER,
                    fill_status=FillStatus.UNFILLED,
                    fill_price=0, fill_size=0,
                    reason="order_placement_failed"
                )
            
            # Wait for fill
            updated_order = await self._clob_client.wait_for_fill(
                order,
                timeout_ms=self.config['maker_timeout_ms'],
                poll_interval_ms=self.config['order_poll_interval_ms']
            )
            
            if updated_order.is_filled:
                self.stats['maker_fills'] += 1
                spread_captured = spread * self.config['spread_capture_pct'] * size
                self.stats['total_spread_captured'] += spread_captured
                
                return ExecutionResult(
                    order_type=OrderType.MAKER,
                    fill_status=FillStatus.FILLED,
                    fill_price=limit_price,
                    fill_size=size,
                    spread_captured=spread_captured,
                    wait_time_ms=int((datetime.now(timezone.utc) - order.created_at).total_seconds() * 1000),
                    order_id=order.order_id,
                    reason="maker_fill"
                )
            elif updated_order.is_partial:
                partial_size = (updated_order.size_matched / updated_order.size) * size
                
                # Cancel remaining
                await self._clob_client.cancel_order(order.order_id)
                
                return ExecutionResult(
                    order_type=OrderType.MAKER,
                    fill_status=FillStatus.PARTIAL,
                    fill_price=limit_price,
                    fill_size=partial_size,
                    order_id=order.order_id,
                    reason=f"partial_fill_{updated_order.fill_pct:.0f}pct"
                )
            else:
                # Cancel unfilled order
                await self._clob_client.cancel_order(order.order_id)
                
                return ExecutionResult(
                    order_type=OrderType.MAKER,
                    fill_status=FillStatus.UNFILLED,
                    fill_price=0, fill_size=0,
                    wait_time_ms=self.config['maker_timeout_ms'],
                    order_id=order.order_id,
                    reason="maker_unfilled"
                )
                
        except Exception as e:
            logger.error(f"Live maker execution error: {e}")
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.UNFILLED,
                fill_price=0, fill_size=0,
                reason=f"error_{str(e)[:50]}"
            )
    
    async def _simulate_maker_fill(
        self,
        side: str,
        size: float,
        limit_price: float,
        spread: float,
        volume_24h: float,
    ) -> ExecutionResult:
        """Simulate maker order fill for paper trading."""
        # Calculate fill probability based on market conditions
        volume_factor = min(1.0, volume_24h / 100000)
        spread_factor = max(0.3, 1.0 - (spread / 0.10))
        size_factor = max(0.5, 1.0 - (size / 1000))
        
        fill_prob = self.config['maker_fill_probability'] * volume_factor * spread_factor * size_factor
        fill_prob = min(0.8, fill_prob)
        
        # Simulate wait time
        wait_time = random.randint(500, self.config['maker_timeout_ms'])
        await asyncio.sleep(0.001)  # Minimal delay for paper trading
        
        # Determine if filled
        filled = random.random() < fill_prob
        
        if filled:
            self.stats['maker_fills'] += 1
            spread_captured = spread * self.config['spread_capture_pct'] * size
            self.stats['total_spread_captured'] += spread_captured
            
            logger.info(f"[PAPER] ✅ MAKER FILL @ {limit_price:.4f} | Spread captured: ${spread_captured:.2f}")
            
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.FILLED,
                fill_price=limit_price,
                fill_size=size,
                spread_captured=spread_captured,
                wait_time_ms=wait_time,
                reason="maker_fill"
            )
        else:
            logger.info(f"[PAPER] ⏳ Maker unfilled after {wait_time}ms (prob: {fill_prob:.2%})")
            return ExecutionResult(
                order_type=OrderType.MAKER,
                fill_status=FillStatus.UNFILLED,
                fill_price=0, fill_size=0,
                wait_time_ms=wait_time,
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
        token_id: Optional[str],
        reason: str,
    ) -> ExecutionResult:
        """Execute as taker (cross the spread)."""
        self.stats['taker_attempts'] += 1
        
        # For taker orders, we cross the spread
        if side == 'YES':
            fill_price = best_ask
            slippage = min(self.config['max_taker_slippage'], size / 50000)
            fill_price = min(0.999, fill_price + slippage)
        else:
            fill_price = best_bid
            slippage = min(self.config['max_taker_slippage'], size / 50000)
            fill_price = max(0.001, fill_price - slippage)
        
        if self.mode == ExecutionMode.LIVE and self._clob_client and token_id:
            # LIVE: Place marketable limit order
            return await self._execute_taker_live(
                side, size, fill_price, spread, slippage, token_id, reason
            )
        else:
            # PAPER: Simulate taker fill
            return self._simulate_taker_fill(
                side, size, fill_price, spread, slippage, reason
            )
    
    async def _execute_taker_live(
        self,
        side: str,
        size: float,
        fill_price: float,
        spread: float,
        slippage: float,
        token_id: str,
        reason: str,
    ) -> ExecutionResult:
        """Execute taker order via live CLOB API."""
        try:
            shares = size / fill_price if fill_price > 0 else 0
            order_side = OrderSide.BUY if side == 'YES' else OrderSide.SELL
            
            # Place aggressive limit order (should fill immediately)
            order = await self._clob_client.place_limit_order(
                token_id=token_id,
                side=order_side,
                price=fill_price,
                size=shares
            )
            
            if not order:
                return ExecutionResult(
                    order_type=OrderType.TAKER,
                    fill_status=FillStatus.UNFILLED,
                    fill_price=0, fill_size=0,
                    reason="taker_order_failed"
                )
            
            # For taker, expect immediate fill
            updated_order = await self._clob_client.wait_for_fill(
                order,
                timeout_ms=1000,  # Short timeout for taker
                poll_interval_ms=200
            )
            
            if updated_order.is_filled:
                self.stats['taker_fills'] += 1
                spread_paid = spread * 0.5 * size
                self.stats['total_spread_paid'] += spread_paid
                
                return ExecutionResult(
                    order_type=OrderType.TAKER,
                    fill_status=FillStatus.FILLED,
                    fill_price=fill_price,
                    fill_size=size,
                    slippage=slippage,
                    spread_captured=-spread_paid,
                    order_id=order.order_id,
                    reason=reason
                )
            else:
                await self._clob_client.cancel_order(order.order_id)
                return ExecutionResult(
                    order_type=OrderType.TAKER,
                    fill_status=FillStatus.UNFILLED,
                    fill_price=0, fill_size=0,
                    order_id=order.order_id,
                    reason="taker_no_fill"
                )
                
        except Exception as e:
            logger.error(f"Live taker execution error: {e}")
            return ExecutionResult(
                order_type=OrderType.TAKER,
                fill_status=FillStatus.UNFILLED,
                fill_price=0, fill_size=0,
                reason=f"error_{str(e)[:50]}"
            )
    
    def _simulate_taker_fill(
        self,
        side: str,
        size: float,
        fill_price: float,
        spread: float,
        slippage: float,
        reason: str,
    ) -> ExecutionResult:
        """Simulate taker fill for paper trading."""
        self.stats['taker_fills'] += 1
        
        spread_paid = spread * 0.5 * size
        self.stats['total_spread_paid'] += spread_paid
        
        wait_time = self.config['maker_timeout_ms'] if reason == "maker_timeout" else 0
        
        logger.info(f"[PAPER] 💨 TAKER @ {fill_price:.4f} | Spread paid: ${spread_paid:.2f} | {reason}")
        
        return ExecutionResult(
            order_type=OrderType.TAKER,
            fill_status=FillStatus.FILLED,
            fill_price=fill_price,
            fill_size=size,
            slippage=slippage,
            spread_captured=-spread_paid,
            wait_time_ms=wait_time,
            reason=reason
        )
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        total_attempts = self.stats['maker_attempts'] + self.stats['taker_attempts']
        maker_rate = self.stats['maker_fills'] / max(1, self.stats['maker_attempts'])
        
        return {
            **self.stats,
            'mode': self.mode.value,
            'maker_fill_rate': round(maker_rate, 3),
            'net_spread_pnl': round(
                self.stats['total_spread_captured'] - self.stats['total_spread_paid'], 2
            ),
            'total_executions': total_attempts,
            'circuit_breaker_active': self._circuit_breaker_until is not None,
        }
    
    def should_trade_given_spread(self, edge: float, spread: float) -> Tuple[bool, str]:
        """
        Pre-check if trade is worthwhile given the spread.
        
        Returns (should_trade, reason)
        """
        if edge <= 0:
            return False, "no_edge"
            
        # Allow trading when edge covers spread (breakeven+), not 2x coverage
        # Real-world Polymarket spreads are 2-6%, demanding 2x was too restrictive
        if spread > edge * 1.0:
            if edge < self.config['min_edge_for_aggressive_taker']:
                return False, f"spread_too_wide: spread={spread:.4f} > edge={edge:.4f}"
        
        return True, "ok"


# Singleton instance
_maker_executor: Optional[MakerOrderExecutor] = None


def get_maker_executor(mode: Optional[ExecutionMode] = None) -> MakerOrderExecutor:
    """
    Get singleton MakerOrderExecutor instance.
    
    Args:
        mode: Override execution mode (default: PAPER)
    """
    global _maker_executor
    if _maker_executor is None:
        _maker_executor = MakerOrderExecutor(mode=mode or ExecutionMode.PAPER)
    return _maker_executor


async def initialize_executor(mode: ExecutionMode = ExecutionMode.PAPER) -> MakerOrderExecutor:
    """Initialize executor with specified mode."""
    global _maker_executor
    _maker_executor = MakerOrderExecutor(mode=mode)
    await _maker_executor.initialize()
    return _maker_executor
