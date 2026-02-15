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
        
        # RACE CONDITION FIX: Event to signal when token mapping is ready
        # Price updates will be queued until this event is set
        self._token_mapping_ready = asyncio.Event()
        self._pending_price_updates: List[Dict] = []  # Queue for updates before mapping ready
        
        # Stats
        self._ws_updates = 0
        self._rest_fetches = 0
        self._dropped_updates = 0  # Updates received before mapping was ready
        
    async def start(self):
        """Start the real-time market service.
        
        RACE CONDITION FIX: We now ensure token mapping is populated BEFORE
        the WebSocket starts receiving price updates. The sequence is:
        1. Discover markets first (builds token -> YES/NO mapping)
        2. Signal that mapping is ready
        3. Connect WebSocket and subscribe to tokens
        4. Register price handler (now safe - mapping exists)
        """
        if self._running:
            return
            
        self._running = True
        logger.info("Starting RealTimeMarketService...")
        
        # STEP 1: Do initial market discovery FIRST (builds token mapping)
        # This MUST complete before WebSocket starts processing price updates
        await self._discover_markets()
        
        # STEP 2: Signal that token mapping is ready
        self._token_mapping_ready.set()
        logger.info(f"Token mapping ready: {len(self._token_outcome)} tokens mapped to YES/NO outcomes")
        
        # STEP 3: Initialize WebSocket manager (connects and starts listener)
        self.ws_manager = get_websocket_manager()
        await self.ws_manager.start()
        
        # STEP 4: Subscribe to tokens AFTER connection is established
        if self._subscribed_tokens:
            tokens_to_sub = list(self._subscribed_tokens)[:100]
            await self.ws_manager.subscribe_to_markets(tokens_to_sub)
            logger.info(f"Subscribed to {len(tokens_to_sub)} market tokens via WebSocket")
        
        # STEP 5: Register price handler AFTER mapping is ready
        # Now price updates can be processed correctly
        self.ws_manager.register_price_handler(self._on_price_update)
        
        # Process any queued updates that arrived during initialization
        if self._pending_price_updates:
            logger.info(f"Processing {len(self._pending_price_updates)} queued price updates")
            for update in self._pending_price_updates:
                await self._process_price_update(update)
            self._pending_price_updates.clear()
        
        # Start background discovery loop for periodic refresh
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        
        logger.info(f"RealTimeMarketService started - {len(self._market_cache)} markets cached, "
                   f"{len(self._token_outcome)} token mappings active")
        
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
        
        If token mapping isn't ready yet, queues the update for later processing.
        Otherwise, processes immediately with correct YES/NO token identification.
        """
        # Queue updates if mapping isn't ready yet
        if not self._token_mapping_ready.is_set():
            self._pending_price_updates.append(data)
            self._dropped_updates += 1
            return
        
        await self._process_price_update(data)
    
    async def _process_price_update(self, data: Dict):
        """Process a price update with token mapping.
        
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
        
        if not market_id:
            # Token not in our mapping - might be a new token or untracked market
            # Log at debug level to avoid spam
            logger.debug(f"Price update for unmapped token: {token_id[:20]}...")
            return
            
        if market_id not in self._market_cache:
            logger.debug(f"Market not in cache: {market_id[:16]}")
            return
            
        market = self._market_cache[market_id]
        
        # EXPIRATION CHECK - Ignore updates for expired markets and evict them
        end_date_str = market.get('end_date')
        if end_date_str:
            try:
                from dateutil.parser import parse
                end_date = parse(end_date_str)
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)
                if end_date < datetime.now(timezone.utc):
                    # Evict expired market from cache
                    del self._market_cache[market_id]
                    if market_id in self._yes_price_cache:
                        del self._yes_price_cache[market_id]
                    logger.debug(f"[WS-UPDATE] Ignoring and evicting expired market {market_id[:16]}")
                    return
            except:
                pass
        
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
            # Token exists in token_to_market but not in token_outcome
            # This shouldn't happen after proper initialization
            logger.warning(f"Token {token_id[:20]}... mapped to market but missing outcome. "
                          f"Token outcome map size: {len(self._token_outcome)}")
            return
            
        market['last_ws_update'] = datetime.now(timezone.utc).isoformat()
                
    async def _discover_markets(self):
        """Discover markets via REST API (slow operation).
        
        Builds the token -> market and token -> outcome mappings that are
        essential for correctly interpreting WebSocket price updates.
        """
        try:
            import json
            
            logger.info("Discovering markets via REST API...")
            self._rest_fetches += 1
            
            async with PolymarketAPI() as api:
                # Fetch top 200 markets by volume
                markets = await api.get_markets(limit=200)
                
                if not markets:
                    logger.warning("No markets returned from REST API")
                    return
                
                # Track new tokens for subscription
                new_tokens = []
                tokens_mapped = 0
                yes_tokens = 0
                no_tokens = 0
                
                # Update market cache and build token mappings
                for market in markets:
                    market_id = market.get('id') or market.get('condition_id')
                    if not market_id:
                        continue
                    
                    # EXPIRATION CHECK - Don't cache expired markets
                    end_date_str = market.get('end_date')
                    if end_date_str:
                        try:
                            from dateutil.parser import parse
                            end_date = parse(end_date_str)
                            if end_date.tzinfo is None:
                                end_date = end_date.replace(tzinfo=timezone.utc)
                            if end_date < datetime.now(timezone.utc):
                                # Remove from cache if it was previously cached
                                if market_id in self._market_cache:
                                    del self._market_cache[market_id]
                                    if market_id in self._yes_price_cache:
                                        del self._yes_price_cache[market_id]
                                    logger.debug(f"[WS-CACHE] Evicted expired market {market_id[:16]}")
                                continue
                        except:
                            pass
                        
                    self._market_cache[market_id] = market
                    
                    # Track token mappings with YES/NO outcomes
                    tokens = market.get('tokens') or market.get('clobTokenIds', [])
                    
                    # Parse outcomes - may be a JSON string or a list
                    outcomes_raw = market.get('outcomes', ['Yes', 'No'])
                    if isinstance(outcomes_raw, str):
                        try:
                            outcomes = json.loads(outcomes_raw)
                        except json.JSONDecodeError:
                            outcomes = ['Yes', 'No']  # Fallback
                    else:
                        outcomes = outcomes_raw
                    
                    if tokens:
                        self._market_tokens[market_id] = tokens
                        
                        # In Polymarket, tokens are ordered: [first_outcome_token, second_outcome_token]
                        # For binary markets: first = Yes, second = No
                        # For other markets: first = outcome1, second = outcome2
                        # We use positional mapping: index 0 = "Yes" equivalent, index 1 = "No" equivalent
                        
                        for i, token in enumerate(tokens):
                            self._token_to_market[token] = market_id
                            
                            if i < len(outcomes):
                                outcome_name = outcomes[i]
                                
                                # Normalize: index 0 is always treated as "Yes" for price calculations
                                # index 1 is always treated as "No"
                                if i == 0:
                                    self._token_outcome[token] = 'Yes'
                                    self._market_yes_token[market_id] = token
                                    yes_tokens += 1
                                else:
                                    self._token_outcome[token] = 'No'
                                    self._market_no_token[market_id] = token
                                    no_tokens += 1
                                
                                tokens_mapped += 1
                            
                            if token not in self._subscribed_tokens:
                                new_tokens.append(token)
                                self._subscribed_tokens.add(token)
                    
                    # Initialize YES price cache from REST data
                    yes_price = market.get('yes_price')
                    if yes_price is not None:
                        self._yes_price_cache[market_id] = float(yes_price)
                
                self._last_discovery_time = datetime.now(timezone.utc)
                
                # Only subscribe to WebSocket if already connected (not during initial startup)
                if self._token_mapping_ready.is_set() and new_tokens and self.ws_manager:
                    # This is a refresh discovery, safe to subscribe
                    tokens_to_sub = new_tokens[:100]
                    await self.ws_manager.subscribe_to_markets(tokens_to_sub)
                    logger.info(f"Subscribed to {len(tokens_to_sub)} new market tokens via WebSocket")
                
                logger.info(f"Market discovery complete: {len(markets)} markets, "
                           f"{tokens_mapped} tokens mapped ({yes_tokens} YES, {no_tokens} NO), "
                           f"{len(new_tokens)} new tokens found")
                
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
        Uses YES price cache which correctly handles both YES and NO token updates.
        """
        markets = list(self._market_cache.values())
        
        # Sort by volume (descending)
        markets.sort(key=lambda m: m.get('volume_24h', 0), reverse=True)
        
        # Enrich with latest prices from YES price cache
        for market in markets[:limit]:
            market_id = market.get('id')
            
            # Use YES price cache (correctly computed from YES or NO token updates)
            yes_price = self._yes_price_cache.get(market_id)
            
            if yes_price is not None:
                market['yes_price'] = yes_price
                market['no_price'] = 1 - yes_price
                
                # Check if this price came from WebSocket or REST
                if market.get('price_source', '').startswith('websocket'):
                    pass  # Keep existing source
                elif market_id in self._yes_price_cache and market.get('last_ws_update'):
                    market['price_source'] = 'websocket'
                else:
                    market['price_source'] = 'rest_cache'
            else:
                market['price_source'] = 'rest_cache'
                    
            # Get order book from WebSocket cache
            ws_book = self.ws_manager.get_latest_order_book(market_id) if self.ws_manager else None
            if ws_book:
                market['order_book'] = ws_book
                
        return markets[:limit]
    
    def get_market(self, market_id: str) -> Optional[Dict]:
        """Get single market from cache with latest prices."""
        market = self._market_cache.get(market_id)
        if not market:
            return None
            
        # Enrich with correct YES price from cache
        yes_price = self._yes_price_cache.get(market_id)
        if yes_price is not None:
            market['yes_price'] = yes_price
            market['no_price'] = 1 - yes_price
                
        return market
    
    def get_latest_price(self, market_id: str) -> Optional[float]:
        """Get latest YES price from cache (correctly computed from YES or NO token updates)."""
        return self._yes_price_cache.get(market_id)
    
    def get_order_book(self, market_id: str) -> Optional[Dict]:
        """Get order book from WebSocket cache."""
        if self.ws_manager:
            return self.ws_manager.get_latest_order_book(market_id)
        return None
    
    def get_stats(self) -> Dict:
        """Get service statistics."""
        return {
            'running': self._running,
            'token_mapping_ready': self._token_mapping_ready.is_set(),
            'markets_cached': len(self._market_cache),
            'tokens_subscribed': len(self._subscribed_tokens),
            'tokens_mapped': len(self._token_outcome),
            'yes_prices_cached': len(self._yes_price_cache),
            'prices_cached': len(self._price_cache),
            'ws_updates': self._ws_updates,
            'rest_fetches': self._rest_fetches,
            'dropped_updates': self._dropped_updates,
            'pending_updates': len(self._pending_price_updates),
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
