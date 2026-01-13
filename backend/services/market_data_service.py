import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List
from database import get_db
from data.websocket_client import PolymarketWebSocket
from data.polymarket_api import PolymarketAPI
import uuid

logger = logging.getLogger(__name__)

class MarketDataService:
    """Manages real-time market data ingestion and normalization"""
    
    def __init__(self):
        self.db = get_db()
        self.ws_client = PolymarketWebSocket()
        self.running = False
        self.markets_cache = {}
        
    async def start(self):
        """Start market data service"""
        try:
            await self.ws_client.connect()
            
            self.ws_client.subscribe('price_update', self.handle_price_update)
            self.ws_client.subscribe('order_book', self.handle_order_book_update)
            self.ws_client.subscribe('trade', self.handle_trade)
            
            self.running = True
            
            await asyncio.gather(
                self.ws_client.listen(),
                self.update_markets_loop(),
                self.sync_time_loop()
            )
        except Exception as e:
            logger.error(f"Error starting market data service: {e}")
            raise
    
    async def stop(self):
        """Stop market data service"""
        self.running = False
        await self.ws_client.disconnect()
        logger.info("Market data service stopped")
    
    async def update_markets_loop(self):
        """Periodically update markets from API"""
        while self.running:
            try:
                await self.fetch_and_update_markets()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Error in markets update loop: {e}")
                await asyncio.sleep(5)
    
    async def fetch_and_update_markets(self):
        """Fetch active markets and update database"""
        try:
            async with PolymarketAPI() as api:
                markets = await api.get_markets(limit=500)
                
                for market_data in markets:
                    condition_id = market_data.get('condition_id')
                    if condition_id:
                        normalized = self.normalize_market_data(market_data)
                        await self.update_market(normalized)
                        await self.ws_client.subscribe_to_market(condition_id)
                
                logger.info(f"Updated {len(markets)} markets")
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
    
    def normalize_market_data(self, raw_data: Dict) -> Dict:
        """Normalize market data from API"""
        return {
            "id": raw_data.get('condition_id', str(uuid.uuid4())),
            "condition_id": raw_data.get('condition_id'),
            "question": raw_data.get('question', ''),
            "category": self._infer_category(raw_data.get('question', '')),
            "end_date": raw_data.get('end_date'),
            "yes_price": float(raw_data.get('yes_price', 0.5)),
            "no_price": float(raw_data.get('no_price', 0.5)),
            "volume": float(raw_data.get('volume', 0)),
            "liquidity": float(raw_data.get('liquidity', 0)),
            "order_book": {},
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    
    def _infer_category(self, question: str) -> str:
        """Infer market category from question"""
        q = question.lower()
        if any(w in q for w in ['bitcoin', 'eth', 'crypto', 'btc']):
            return 'crypto'
        elif any(w in q for w in ['nfl', 'nba', 'game', 'sport']):
            return 'sports'
        elif any(w in q for w in ['election', 'president', 'vote']):
            return 'politics'
        return 'finance'
    
    async def update_market(self, market_data: Dict):
        """Update market in database"""
        try:
            await self.db.markets.update_one(
                {"id": market_data['id']},
                {"$set": market_data},
                upsert=True
            )
            self.markets_cache[market_data['id']] = market_data
        except Exception as e:
            logger.error(f"Error updating market: {e}")
    
    async def handle_price_update(self, data: Dict):
        """Handle real-time price updates"""
        try:
            market_id = data.get('market_id')
            if market_id:
                update = {
                    "yes_price": float(data.get('yes_price', 0)),
                    "no_price": float(data.get('no_price', 0)),
                    "last_update": datetime.now(timezone.utc).isoformat()
                }
                await self.db.markets.update_one(
                    {"id": market_id},
                    {"$set": update}
                )
        except Exception as e:
            logger.error(f"Error handling price update: {e}")
    
    async def handle_order_book_update(self, data: Dict):
        """Handle order book updates"""
        try:
            market_id = data.get('market_id')
            if market_id:
                await self.db.markets.update_one(
                    {"id": market_id},
                    {"$set": {
                        "order_book": data.get('order_book', {}),
                        "last_update": datetime.now(timezone.utc).isoformat()
                    }}
                )
        except Exception as e:
            logger.error(f"Error handling order book update: {e}")
    
    async def handle_trade(self, data: Dict):
        """Handle trade events"""
        try:
            await self.db.market_trades.insert_one({
                "id": str(uuid.uuid4()),
                "market_id": data.get('market_id'),
                "price": float(data.get('price', 0)),
                "size": float(data.get('size', 0)),
                "side": data.get('side'),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error handling trade: {e}")
    
    async def sync_time_loop(self):
        """Maintain time synchronization"""
        while self.running:
            try:
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in time sync: {e}")