"""
Polymarket WebSocket Client for Real-Time Data

Connects to Polymarket's WebSocket API for:
- Real-time price updates
- Live order book changes
- Trade notifications

This enables instant reactions to market movements instead of polling.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Set
from collections import defaultdict
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

logger = logging.getLogger(__name__)


class PolymarketWebSocket:
    """
    WebSocket client for real-time Polymarket data.
    
    Connects to Polymarket's CLOB WebSocket for:
    - Price tick updates
    - Order book snapshots and deltas
    - Trade notifications
    """
    
    # Polymarket WebSocket endpoints
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.connected = False
        
        # Subscribed markets
        self._subscribed_markets: Set[str] = set()
        self._subscribed_tokens: Set[str] = set()
        
        # Callbacks for different event types
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # Latest data cache
        self._latest_prices: Dict[str, float] = {}
        self._latest_order_books: Dict[str, Dict] = {}
        self._trade_buffer: Dict[str, List[Dict]] = defaultdict(list)
        
        # Connection management
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._reconnect_task: Optional[asyncio.Task] = None
        
        # Stats
        self._messages_received = 0
        self._last_message_time: Optional[datetime] = None
        
        logger.info("PolymarketWebSocket initialized")
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        try:
            logger.info(f"Connecting to Polymarket WebSocket: {self.WS_URL}")
            
            self.ws = await websockets.connect(
                self.WS_URL,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            )
            
            self.connected = True
            self.running = True
            self._reconnect_delay = 1  # Reset delay on successful connect
            
            logger.info("Polymarket WebSocket connected successfully")
            
            # Notify connection callbacks
            await self._emit('connected', {'timestamp': datetime.now(timezone.utc).isoformat()})
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Close WebSocket connection."""
        self.running = False
        self.connected = False
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            self.ws = None
        
        logger.info("Polymarket WebSocket disconnected")
    
    async def subscribe_market(self, token_id: str):
        """Subscribe to real-time updates for a market token."""
        if token_id in self._subscribed_tokens:
            return
        
        if not self.connected or not self.ws:
            logger.warning(f"Cannot subscribe to {token_id} - not connected")
            return
        
        try:
            # Polymarket subscription message format
            subscribe_msg = {
                "type": "subscribe",
                "channel": "market",
                "market": token_id,
            }
            
            await self.ws.send(json.dumps(subscribe_msg))
            self._subscribed_tokens.add(token_id)
            
            logger.debug(f"Subscribed to market: {token_id[:16]}...")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to market {token_id}: {e}")
    
    async def subscribe_markets(self, token_ids: List[str]):
        """Subscribe to multiple markets."""
        for token_id in token_ids:
            await self.subscribe_market(token_id)
            await asyncio.sleep(0.1)  # Rate limit subscriptions
    
    async def unsubscribe_market(self, token_id: str):
        """Unsubscribe from a market."""
        if token_id not in self._subscribed_tokens:
            return
        
        if not self.connected or not self.ws:
            return
        
        try:
            unsubscribe_msg = {
                "type": "unsubscribe",
                "channel": "market",
                "market": token_id,
            }
            
            await self.ws.send(json.dumps(unsubscribe_msg))
            self._subscribed_tokens.discard(token_id)
            
            logger.debug(f"Unsubscribed from market: {token_id[:16]}...")
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from market {token_id}: {e}")
    
    def on(self, event: str, callback: Callable):
        """
        Register a callback for an event type.
        
        Event types:
        - 'connected': WebSocket connected
        - 'disconnected': WebSocket disconnected
        - 'price_update': Price changed for a market
        - 'trade': New trade occurred
        - 'order_book': Order book update
        - 'error': Error occurred
        """
        self._callbacks[event].append(callback)
    
    def off(self, event: str, callback: Callable = None):
        """Remove callback(s) for an event."""
        if callback:
            self._callbacks[event] = [cb for cb in self._callbacks[event] if cb != callback]
        else:
            self._callbacks[event] = []
    
    async def _emit(self, event: str, data: Dict):
        """Emit an event to all registered callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")
    
    async def listen(self):
        """Main loop to listen for WebSocket messages."""
        while self.running:
            if not self.connected:
                # Try to reconnect
                success = await self.connect()
                if not success:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay
                    )
                    continue
                
                # Resubscribe to markets
                for token_id in list(self._subscribed_tokens):
                    self._subscribed_tokens.discard(token_id)
                    await self.subscribe_market(token_id)
            
            try:
                if not self.ws:
                    await asyncio.sleep(1)
                    continue
                
                # Wait for message with timeout
                try:
                    message = await asyncio.wait_for(
                        self.ws.recv(),
                        timeout=60  # 60 second timeout
                    )
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    try:
                        pong = await self.ws.ping()
                        await asyncio.wait_for(pong, timeout=10)
                    except:
                        logger.warning("WebSocket ping failed, reconnecting...")
                        self.connected = False
                    continue
                
                self._messages_received += 1
                self._last_message_time = datetime.now(timezone.utc)
                
                await self._handle_message(message)
                
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                self.connected = False
                await self._emit('disconnected', {'reason': str(e)})
                
            except Exception as e:
                logger.error(f"Error in WebSocket listener: {e}")
                await asyncio.sleep(1)
    
    async def _handle_message(self, raw_message: str):
        """Process incoming WebSocket message."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get('type', data.get('event', 'unknown'))
            
            if msg_type in ['price_change', 'tick', 'price']:
                await self._handle_price_update(data)
                
            elif msg_type in ['trade', 'fill']:
                await self._handle_trade(data)
                
            elif msg_type in ['book', 'order_book', 'book_snapshot']:
                await self._handle_order_book(data)
                
            elif msg_type in ['book_delta', 'book_update']:
                await self._handle_order_book_delta(data)
                
            elif msg_type == 'subscribed':
                logger.debug(f"Subscription confirmed: {data}")
                
            elif msg_type == 'error':
                logger.error(f"WebSocket error: {data}")
                await self._emit('error', data)
                
            else:
                logger.debug(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_price_update(self, data: Dict):
        """Handle price update message."""
        try:
            market_id = data.get('market', data.get('asset_id', data.get('token_id', '')))
            price = float(data.get('price', data.get('yes_price', 0)))
            
            if market_id and price > 0:
                old_price = self._latest_prices.get(market_id)
                self._latest_prices[market_id] = price
                
                event_data = {
                    'market_id': market_id,
                    'price': price,
                    'old_price': old_price,
                    'change': price - old_price if old_price else 0,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'raw': data
                }
                
                await self._emit('price_update', event_data)
                
        except Exception as e:
            logger.debug(f"Error handling price update: {e}")
    
    async def _handle_trade(self, data: Dict):
        """Handle trade notification."""
        try:
            market_id = data.get('market', data.get('asset_id', ''))
            
            trade = {
                'market_id': market_id,
                'price': float(data.get('price', 0)),
                'size': float(data.get('size', data.get('amount', 0))),
                'side': data.get('side', ''),
                'timestamp': data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'raw': data
            }
            
            # Buffer trades
            self._trade_buffer[market_id].append(trade)
            if len(self._trade_buffer[market_id]) > 100:
                self._trade_buffer[market_id] = self._trade_buffer[market_id][-100:]
            
            await self._emit('trade', trade)
            
        except Exception as e:
            logger.debug(f"Error handling trade: {e}")
    
    async def _handle_order_book(self, data: Dict):
        """Handle full order book snapshot."""
        try:
            market_id = data.get('market', data.get('asset_id', ''))
            
            order_book = {
                'bids': data.get('bids', []),
                'asks': data.get('asks', []),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
            self._latest_order_books[market_id] = order_book
            
            await self._emit('order_book', {
                'market_id': market_id,
                'order_book': order_book,
                'is_snapshot': True
            })
            
        except Exception as e:
            logger.debug(f"Error handling order book: {e}")
    
    async def _handle_order_book_delta(self, data: Dict):
        """Handle order book delta update."""
        try:
            market_id = data.get('market', data.get('asset_id', ''))
            
            # Apply delta to cached order book
            if market_id in self._latest_order_books:
                book = self._latest_order_books[market_id]
                
                # Update bids
                for bid_update in data.get('bids', []):
                    price = bid_update.get('price')
                    size = bid_update.get('size', 0)
                    # Remove or update
                    book['bids'] = [b for b in book['bids'] if b.get('price') != price]
                    if size > 0:
                        book['bids'].append({'price': price, 'size': size})
                
                # Update asks
                for ask_update in data.get('asks', []):
                    price = ask_update.get('price')
                    size = ask_update.get('size', 0)
                    book['asks'] = [a for a in book['asks'] if a.get('price') != price]
                    if size > 0:
                        book['asks'].append({'price': price, 'size': size})
                
                # Sort
                book['bids'].sort(key=lambda x: x.get('price', 0), reverse=True)
                book['asks'].sort(key=lambda x: x.get('price', 0))
                book['timestamp'] = datetime.now(timezone.utc).isoformat()
                
                await self._emit('order_book', {
                    'market_id': market_id,
                    'order_book': book,
                    'is_snapshot': False
                })
                
        except Exception as e:
            logger.debug(f"Error handling order book delta: {e}")
    
    def get_latest_price(self, market_id: str) -> Optional[float]:
        """Get the latest cached price for a market."""
        return self._latest_prices.get(market_id)
    
    def get_latest_order_book(self, market_id: str) -> Optional[Dict]:
        """Get the latest cached order book for a market."""
        return self._latest_order_books.get(market_id)
    
    def get_recent_trades(self, market_id: str, limit: int = 50) -> List[Dict]:
        """Get recent buffered trades for a market."""
        trades = self._trade_buffer.get(market_id, [])
        return trades[-limit:]
    
    def get_stats(self) -> Dict:
        """Get WebSocket connection statistics."""
        return {
            'connected': self.connected,
            'running': self.running,
            'messages_received': self._messages_received,
            'last_message': self._last_message_time.isoformat() if self._last_message_time else None,
            'subscribed_tokens': len(self._subscribed_tokens),
            'cached_prices': len(self._latest_prices),
            'cached_order_books': len(self._latest_order_books),
        }


class PolymarketWebSocketManager:
    """
    Manager for Polymarket WebSocket connections.
    
    Handles:
    - Automatic connection management
    - Market subscription management
    - Event distribution to consumers
    """
    
    def __init__(self):
        self.ws_client = PolymarketWebSocket()
        self._listener_task: Optional[asyncio.Task] = None
        self._started = False
        
        # Event handlers
        self._price_handlers: List[Callable] = []
        self._trade_handlers: List[Callable] = []
        
    async def start(self):
        """Start the WebSocket manager."""
        if self._started:
            return
        
        self._started = True
        
        # Register internal handlers
        self.ws_client.on('price_update', self._on_price_update)
        self.ws_client.on('trade', self._on_trade)
        self.ws_client.on('connected', self._on_connected)
        self.ws_client.on('disconnected', self._on_disconnected)
        
        # Start listener in background
        self._listener_task = asyncio.create_task(self.ws_client.listen())
        
        # Wait for connection to be established (with timeout)
        max_wait = 10  # seconds
        waited = 0
        while not self.ws_client.connected and waited < max_wait:
            await asyncio.sleep(0.5)
            waited += 0.5
        
        if self.ws_client.connected:
            logger.info("PolymarketWebSocketManager started - WebSocket connected")
        else:
            logger.warning("PolymarketWebSocketManager started - WebSocket connection pending (will retry in background)")
    
    async def stop(self):
        """Stop the WebSocket manager."""
        self._started = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        await self.ws_client.disconnect()
        
        logger.info("PolymarketWebSocketManager stopped")
    
    async def subscribe_to_markets(self, token_ids: List[str]):
        """Subscribe to multiple markets."""
        await self.ws_client.subscribe_markets(token_ids)
    
    def register_price_handler(self, handler: Callable):
        """Register a handler for price updates."""
        self._price_handlers.append(handler)
    
    def register_trade_handler(self, handler: Callable):
        """Register a handler for trade updates."""
        self._trade_handlers.append(handler)
    
    async def _on_price_update(self, data: Dict):
        """Internal price update handler."""
        for handler in self._price_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in price handler: {e}")
    
    async def _on_trade(self, data: Dict):
        """Internal trade handler."""
        for handler in self._trade_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in trade handler: {e}")
    
    async def _on_connected(self, data: Dict):
        """Handle WebSocket connected event."""
        logger.info("WebSocket connected - ready for real-time data")
    
    async def _on_disconnected(self, data: Dict):
        """Handle WebSocket disconnected event."""
        logger.warning(f"WebSocket disconnected: {data.get('reason', 'unknown')}")
    
    def get_latest_price(self, market_id: str) -> Optional[float]:
        """Get latest price from cache."""
        return self.ws_client.get_latest_price(market_id)
    
    def get_latest_order_book(self, market_id: str) -> Optional[Dict]:
        """Get latest order book from cache."""
        return self.ws_client.get_latest_order_book(market_id)
    
    def get_recent_trades(self, market_id: str, limit: int = 50) -> List[Dict]:
        """Get recent trades from buffer."""
        return self.ws_client.get_recent_trades(market_id, limit)
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            'started': self._started,
            **self.ws_client.get_stats()
        }


# Singleton instance
_ws_manager: Optional[PolymarketWebSocketManager] = None


def get_websocket_manager() -> PolymarketWebSocketManager:
    """Get singleton WebSocket manager instance."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = PolymarketWebSocketManager()
    return _ws_manager


async def init_websocket_manager() -> PolymarketWebSocketManager:
    """Initialize and start the WebSocket manager."""
    manager = get_websocket_manager()
    await manager.start()
    return manager
