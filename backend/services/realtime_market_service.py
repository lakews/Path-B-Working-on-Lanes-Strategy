"""
Real-Time Market Data Service

Provides a unified interface for market data that:
1. Uses WebSocket for real-time price updates (Fast Loop)
2. Falls back to REST API for market discovery (Slow Loop)
3. Caches data with intelligent refresh strategies

This decouples the fast trading loop from slow data fetching.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from data.polymarket_websocket import get_websocket_manager, PolymarketWebSocketManager
from data.polymarket_api import PolymarketAPI

logger = logging.getLogger(__name__)


class RealTimeMarketService:
    """
    Unified market data service that combines:
    - WebSocket for real-time price/order book updates (sub-100ms latency)
    - REST API for market discovery (every 5 minutes)
    
    The trading loop reads from cache, while background tasks update it.
    """
    
    def __init__(self):
        self.ws_manager: Optional[PolymarketWebSocketManager] = None
        self.api = PolymarketAPI()
        
        # Market cache (updated by both WebSocket and REST)
        self._market_cache: Dict[str, Dict] = {}
        self._market_tokens: Dict[str, List[str]] = {}  # market_id -> token_ids
        self._token_to_market: Dict[str, str] = {}  # token_id -> market_id
        
        # NEW: Track which tokens are YES vs NO
        self._token_outcome: Dict[str, str] = {}  # token_id -> "Yes" or "No"
        self._market_yes_token: Dict[str, str] = {}  # market_id -> yes_token_id
        self._market_no_token: Dict[str, str] = {}  # market_id -> no_token_id
        
        # Price cache (updated by WebSocket in real-time)
        # Store both YES and NO prices separately
        self._yes_price_cache: Dict[str, float] = {}  # market_id -> yes_price
        self._no_price_cache: Dict[str, float] = {}  # market_id -> no_price
        self._price_cache: Dict[str, float] = {}  # token_id -> price (raw)
        self._order_book_cache: Dict[str, Dict] = {}
        
        # Discovery state
        self._last_discovery_time: Optional[datetime] = None
        self._discovery_interval = timedelta(minutes=5)
        self._subscribed_tokens: Set[str] = set()
        
        # Background tasks
        self._discovery_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Stats
        self._ws_updates = 0
        self._rest_fetches = 0
        
    async def start(self):
        """Start the real-time market service."""
        if self._running:
            return
            
        self._running = True
        logger.info("Starting RealTimeMarketService...")
        
        # Initialize WebSocket manager
        self.ws_manager = get_websocket_manager()
        await self.ws_manager.start()
        
        # Register price update handler
        self.ws_manager.register_price_handler(self._on_price_update)
        
        # Do initial market discovery
        await self._discover_markets()
        
        # Start background discovery loop
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        
        logger.info(f"RealTimeMarketService started - {len(self._market_cache)} markets cached")
        
    async def stop(self):
        """Stop the real-time market service."""
        self._running = False
        
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        
        if self.ws_manager:
            await self.ws_manager.stop()
            
        logger.info("RealTimeMarketService stopped")
        
    async def _on_price_update(self, data: Dict):
        """Handle real-time price update from WebSocket.
        
        Correctly identifies whether the price update is for a YES or NO token
        and updates the market's yes_price accordingly.
        """
        token_id = data.get('asset_id') or data.get('token_id')
        price = data.get('price')
        
        if not token_id or price is None:
            return
            
        price = float(price)
        self._price_cache[token_id] = price
        self._ws_updates += 1
        
        # Determine if this is a YES or NO token
        outcome = self._token_outcome.get(token_id)
        market_id = self._token_to_market.get(token_id)
        
        if not market_id or market_id not in self._market_cache:
            return
            
        market = self._market_cache[market_id]
        
        if outcome == 'Yes':
            # This is the YES token price - use directly
            self._yes_price_cache[market_id] = price
            market['yes_price'] = price
            market['no_price'] = 1 - price
            market['price_source'] = 'websocket_yes'
        elif outcome == 'No':
            # This is the NO token price - convert to YES price
            # NO price + YES price = 1, so YES price = 1 - NO price
            yes_price = 1 - price
            self._no_price_cache[market_id] = price
            self._yes_price_cache[market_id] = yes_price
            market['yes_price'] = yes_price
            market['no_price'] = price
            market['price_source'] = 'websocket_no'
        else:
            # Unknown token outcome - log warning and skip
            logger.warning(f"Unknown token outcome for {token_id[:20]}... in market {market_id[:16]}")
            return
            
        market['last_ws_update'] = datetime.now(timezone.utc).isoformat()
                
    async def _discover_markets(self):
        """Discover markets via REST API (slow operation)."""
        try:
            logger.info("Discovering markets via REST API...")
            self._rest_fetches += 1
            
            async with PolymarketAPI() as api:
                # Fetch top 200 markets by volume
                markets = await api.get_markets(limit=200)
                
                if not markets:
                    logger.warning("No markets returned from REST API")
                    return
                
                # Update market cache
                new_tokens = []
                for market in markets:
                    market_id = market.get('id') or market.get('condition_id')
                    if not market_id:
                        continue
                        
                    self._market_cache[market_id] = market
                    
                    # Track token mappings
                    tokens = market.get('tokens') or market.get('clobTokenIds', [])
                    if tokens:
                        self._market_tokens[market_id] = tokens
                        for token in tokens:
                            self._token_to_market[token] = market_id
                            if token not in self._subscribed_tokens:
                                new_tokens.append(token)
                
                self._last_discovery_time = datetime.now(timezone.utc)
                
                # Subscribe to new tokens via WebSocket
                if new_tokens and self.ws_manager:
                    await self.ws_manager.subscribe_to_markets(new_tokens[:100])  # Limit to top 100
                    self._subscribed_tokens.update(new_tokens[:100])
                    logger.info(f"Subscribed to {len(new_tokens[:100])} new market tokens via WebSocket")
                
                logger.info(f"Market discovery complete: {len(markets)} markets, {len(self._subscribed_tokens)} subscribed tokens")
                
        except Exception as e:
            logger.error(f"Error during market discovery: {e}")
            
    async def _discovery_loop(self):
        """Background loop for periodic market discovery."""
        while self._running:
            try:
                await asyncio.sleep(self._discovery_interval.total_seconds())
                await self._discover_markets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(60)  # Wait before retry
                
    def get_markets(self, limit: int = 100) -> List[Dict]:
        """
        Get markets from cache (fast operation).
        
        Returns cached market data enriched with latest WebSocket prices.
        """
        markets = list(self._market_cache.values())
        
        # Sort by volume (descending)
        markets.sort(key=lambda m: m.get('volume_24h', 0), reverse=True)
        
        # Enrich with latest WebSocket prices
        for market in markets[:limit]:
            tokens = self._market_tokens.get(market.get('id'), [])
            if tokens:
                ws_price = self._price_cache.get(tokens[0])
                if ws_price is not None:
                    market['yes_price'] = ws_price
                    market['no_price'] = 1 - ws_price
                    market['price_source'] = 'websocket'
                else:
                    market['price_source'] = 'rest_cache'
                    
            # Get order book from WebSocket cache
            ws_book = self.ws_manager.get_latest_order_book(market.get('id')) if self.ws_manager else None
            if ws_book:
                market['order_book'] = ws_book
                
        return markets[:limit]
    
    def get_market(self, market_id: str) -> Optional[Dict]:
        """Get single market from cache with latest prices."""
        market = self._market_cache.get(market_id)
        if not market:
            return None
            
        # Enrich with WebSocket data
        tokens = self._market_tokens.get(market_id, [])
        if tokens:
            ws_price = self._price_cache.get(tokens[0])
            if ws_price is not None:
                market['yes_price'] = ws_price
                market['no_price'] = 1 - ws_price
                
        return market
    
    def get_latest_price(self, market_id: str) -> Optional[float]:
        """Get latest price from WebSocket cache."""
        tokens = self._market_tokens.get(market_id, [])
        if tokens:
            return self._price_cache.get(tokens[0])
        return None
    
    def get_order_book(self, market_id: str) -> Optional[Dict]:
        """Get order book from WebSocket cache."""
        if self.ws_manager:
            return self.ws_manager.get_latest_order_book(market_id)
        return None
    
    def get_stats(self) -> Dict:
        """Get service statistics."""
        return {
            'running': self._running,
            'markets_cached': len(self._market_cache),
            'tokens_subscribed': len(self._subscribed_tokens),
            'prices_cached': len(self._price_cache),
            'ws_updates': self._ws_updates,
            'rest_fetches': self._rest_fetches,
            'last_discovery': self._last_discovery_time.isoformat() if self._last_discovery_time else None,
            'websocket': self.ws_manager.get_stats() if self.ws_manager else None,
        }


# Singleton instance
_rtm_service: Optional[RealTimeMarketService] = None


def get_realtime_market_service() -> RealTimeMarketService:
    """Get singleton RealTimeMarketService instance."""
    global _rtm_service
    if _rtm_service is None:
        _rtm_service = RealTimeMarketService()
    return _rtm_service


async def init_realtime_market_service() -> RealTimeMarketService:
    """Initialize and start the real-time market service."""
    service = get_realtime_market_service()
    await service.start()
    return service
