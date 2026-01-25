"""
Polymarket CLOB Client Wrapper

Provides a unified interface for interacting with Polymarket's Central Limit Order Book.
Handles authentication, order placement, monitoring, and cancellation.

SECURITY NOTE: Private key should NEVER be stored in code or committed to git.
Use environment variables: POLYMARKET_PRIVATE_KEY
"""

import os
import logging
import asyncio
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
import aiohttp

logger = logging.getLogger(__name__)

# Polymarket CLOB configuration
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    LIVE = "LIVE"
    MATCHED = "MATCHED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


@dataclass
class CLOBOrder:
    """Represents an order on the CLOB."""
    order_id: str
    token_id: str
    side: OrderSide
    price: float
    size: float
    size_matched: float
    status: OrderStatus
    created_at: datetime
    expiration: Optional[datetime] = None
    
    @property
    def is_filled(self) -> bool:
        return self.size_matched >= self.size * 0.99  # 99% filled = filled
    
    @property
    def is_partial(self) -> bool:
        return 0 < self.size_matched < self.size * 0.99
    
    @property
    def fill_pct(self) -> float:
        return (self.size_matched / self.size * 100) if self.size > 0 else 0


@dataclass
class OrderBook:
    """Represents the current order book state."""
    token_id: str
    bids: List[Dict]  # [{price, size}, ...]
    asks: List[Dict]
    timestamp: datetime
    
    @property
    def best_bid(self) -> Optional[float]:
        return float(self.bids[0]['price']) if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        return float(self.asks[0]['price']) if self.asks else None
    
    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None
    
    @property
    def is_stale(self) -> bool:
        """Check if orderbook data is more than 2 seconds old."""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > 2.0
    
    @property
    def bid_depth(self) -> float:
        """Total USD depth on bid side."""
        return sum(float(b.get('size', 0)) * float(b.get('price', 0)) for b in self.bids)
    
    @property
    def ask_depth(self) -> float:
        """Total USD depth on ask side."""
        return sum(float(a.get('size', 0)) * float(a.get('price', 0)) for a in self.asks)


class PolymarketCLOBClient:
    """
    Client for interacting with Polymarket's CLOB.
    
    Supports two modes:
    1. Read-only (no private key): Can fetch orderbook, prices, trades
    2. Authenticated (with private key): Can place/cancel orders
    
    Usage:
        # Read-only
        client = PolymarketCLOBClient()
        await client.initialize()
        orderbook = await client.get_orderbook(token_id)
        
        # Authenticated (for live trading)
        client = PolymarketCLOBClient(private_key="0x...")
        await client.initialize()
        order = await client.place_limit_order(token_id, OrderSide.BUY, 0.65, 100)
    """
    
    def __init__(self, private_key: Optional[str] = None):
        """
        Initialize CLOB client.
        
        Args:
            private_key: Ethereum private key for signing orders.
                        If None, client operates in read-only mode.
        """
        self.host = CLOB_HOST
        self.chain_id = CHAIN_ID
        self._private_key = private_key or os.environ.get('POLYMARKET_PRIVATE_KEY')
        self._clob_client = None
        self._api_creds = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        self._is_authenticated = False
        
        # Stats
        self.stats = {
            'orders_placed': 0,
            'orders_filled': 0,
            'orders_cancelled': 0,
            'orders_failed': 0,
            'total_volume': 0.0,
        }
    
    async def initialize(self) -> bool:
        """
        Initialize the CLOB client.
        
        Returns:
            True if initialization successful, False otherwise.
        """
        try:
            # Always create HTTP session for read operations
            self._session = aiohttp.ClientSession(headers={
                "Content-Type": "application/json"
            })
            
            # If private key provided, initialize authenticated client
            if self._private_key:
                try:
                    from py_clob_client.client import ClobClient
                    from py_clob_client.clob_types import ApiCreds
                    
                    # Initialize CLOB client
                    self._clob_client = ClobClient(
                        host=self.host,
                        key=self._private_key,
                        chain_id=self.chain_id
                    )
                    
                    # Create or derive API credentials
                    self._api_creds = self._clob_client.create_or_derive_api_creds()
                    self._clob_client.set_api_creds(self._api_creds)
                    
                    self._is_authenticated = True
                    logger.info("CLOB client initialized with authentication (live trading enabled)")
                    
                except ImportError:
                    logger.warning("py-clob-client not installed - running in read-only mode")
                    self._is_authenticated = False
                except Exception as e:
                    logger.error(f"Failed to initialize authenticated CLOB client: {e}")
                    self._is_authenticated = False
            else:
                logger.info("CLOB client initialized in read-only mode (no private key)")
                self._is_authenticated = False
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            return False
    
    async def close(self):
        """Close the client and cleanup resources."""
        if self._session:
            await self._session.close()
            self._session = None
        self._initialized = False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if client can place orders."""
        return self._is_authenticated and self._clob_client is not None
    
    async def get_orderbook(self, token_id: str, retries: int = 3) -> Optional[OrderBook]:
        """
        Fetch current orderbook for a token.
        
        Args:
            token_id: The token ID to fetch orderbook for
            retries: Number of retry attempts
            
        Returns:
            OrderBook object or None if fetch failed
        """
        if not self._session:
            logger.error("Client not initialized")
            return None
        
        last_error = None
        for attempt in range(retries):
            try:
                url = f"{self.host}/book"
                params = {"token_id": token_id}
                
                async with self._session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        return OrderBook(
                            token_id=token_id,
                            bids=data.get('bids', []),
                            asks=data.get('asks', []),
                            timestamp=datetime.now(timezone.utc)
                        )
                    else:
                        last_error = f"HTTP {response.status}"
                        
            except asyncio.TimeoutError:
                last_error = "Timeout"
            except Exception as e:
                last_error = str(e)
            
            if attempt < retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        logger.warning(f"Failed to fetch orderbook for {token_id[:20]}... after {retries} attempts: {last_error}")
        return None
    
    async def get_mid_price(self, token_id: str) -> Optional[float]:
        """Get mid-price from orderbook."""
        orderbook = await self.get_orderbook(token_id)
        return orderbook.mid_price if orderbook else None
    
    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        time_in_force: str = "GTC"
    ) -> Optional[CLOBOrder]:
        """
        Place a limit order on the CLOB.
        
        Args:
            token_id: Token to trade
            side: BUY or SELL
            price: Limit price (0-1 for binary markets)
            size: Number of shares
            time_in_force: Order duration ("GTC" = Good Till Cancelled)
            
        Returns:
            CLOBOrder object if successful, None otherwise
        """
        if not self.is_authenticated:
            logger.error("Cannot place order: client not authenticated")
            return None
        
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            
            # Map side
            clob_side = BUY if side == OrderSide.BUY else SELL
            
            # Create order args
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=clob_side
            )
            
            # Create signed order
            signed_order = self._clob_client.create_order(order_args)
            
            # Post order
            order_type = OrderType.GTC if time_in_force == "GTC" else OrderType.FOK
            response = self._clob_client.post_order(signed_order, order_type)
            
            if response and response.get('orderID'):
                self.stats['orders_placed'] += 1
                self.stats['total_volume'] += size * price
                
                order = CLOBOrder(
                    order_id=response['orderID'],
                    token_id=token_id,
                    side=side,
                    price=price,
                    size=size,
                    size_matched=0,
                    status=OrderStatus.LIVE,
                    created_at=datetime.now(timezone.utc)
                )
                
                logger.info(f"Order placed: {order.order_id[:16]}... {side.value} {size}@{price:.4f}")
                return order
            else:
                self.stats['orders_failed'] += 1
                logger.error(f"Order placement failed: {response}")
                return None
                
        except Exception as e:
            self.stats['orders_failed'] += 1
            logger.error(f"Error placing order: {e}")
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: The order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        if not self.is_authenticated:
            logger.error("Cannot cancel order: client not authenticated")
            return False
        
        try:
            response = self._clob_client.cancel(order_id)
            if response:
                self.stats['orders_cancelled'] += 1
                logger.info(f"Order cancelled: {order_id[:16]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    async def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count of cancelled orders."""
        if not self.is_authenticated:
            return 0
        
        try:
            response = self._clob_client.cancel_all()
            cancelled = response.get('cancelled', 0) if response else 0
            self.stats['orders_cancelled'] += cancelled
            logger.info(f"Cancelled {cancelled} orders")
            return cancelled
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return 0
    
    async def get_order_status(self, order_id: str) -> Optional[CLOBOrder]:
        """
        Get current status of an order.
        
        Args:
            order_id: The order ID to check
            
        Returns:
            Updated CLOBOrder or None
        """
        if not self.is_authenticated:
            return None
        
        try:
            response = self._clob_client.get_order(order_id)
            if response:
                status_map = {
                    'LIVE': OrderStatus.LIVE,
                    'MATCHED': OrderStatus.MATCHED,
                    'CANCELLED': OrderStatus.CANCELLED,
                    'EXPIRED': OrderStatus.EXPIRED,
                }
                
                return CLOBOrder(
                    order_id=response.get('id', order_id),
                    token_id=response.get('asset_id', ''),
                    side=OrderSide.BUY if response.get('side') == 'BUY' else OrderSide.SELL,
                    price=float(response.get('price', 0)),
                    size=float(response.get('original_size', 0)),
                    size_matched=float(response.get('size_matched', 0)),
                    status=status_map.get(response.get('status', ''), OrderStatus.UNKNOWN),
                    created_at=datetime.fromisoformat(response.get('created_at', datetime.now(timezone.utc).isoformat()))
                )
            return None
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None
    
    async def wait_for_fill(
        self,
        order: CLOBOrder,
        timeout_ms: int = 5000,
        poll_interval_ms: int = 500
    ) -> CLOBOrder:
        """
        Wait for an order to be filled.
        
        Args:
            order: The order to monitor
            timeout_ms: Maximum wait time in milliseconds
            poll_interval_ms: How often to check order status
            
        Returns:
            Updated order with final status
        """
        start_time = datetime.now(timezone.utc)
        timeout_sec = timeout_ms / 1000
        poll_sec = poll_interval_ms / 1000
        
        while True:
            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed >= timeout_sec:
                logger.info(f"Order {order.order_id[:16]}... timed out after {elapsed:.1f}s")
                break
            
            # Get current status
            updated = await self.get_order_status(order.order_id)
            if updated:
                order = updated
                
                if order.status == OrderStatus.MATCHED:
                    self.stats['orders_filled'] += 1
                    logger.info(f"Order filled: {order.order_id[:16]}... {order.fill_pct:.1f}%")
                    break
                elif order.status in [OrderStatus.CANCELLED, OrderStatus.EXPIRED]:
                    logger.info(f"Order {order.status.value}: {order.order_id[:16]}...")
                    break
            
            await asyncio.sleep(poll_sec)
        
        return order
    
    async def get_positions(self) -> List[Dict]:
        """Get current positions (requires authentication)."""
        if not self.is_authenticated:
            return []
        
        try:
            return self._clob_client.get_positions() or []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Get client statistics."""
        return {
            **self.stats,
            'is_authenticated': self.is_authenticated,
            'is_initialized': self._initialized,
        }


# Singleton instance
_clob_client: Optional[PolymarketCLOBClient] = None


async def get_clob_client() -> PolymarketCLOBClient:
    """Get or create singleton CLOB client."""
    global _clob_client
    if _clob_client is None:
        _clob_client = PolymarketCLOBClient()
        await _clob_client.initialize()
    return _clob_client
