import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from database import get_db
from data.polymarket_api import PolymarketAPI
from models import Market, MarketCategory
import uuid

logger = logging.getLogger(__name__)

class HistoricalDataCollector:
    """Collects and stores historical market data for backtesting"""
    
    def __init__(self):
        self.db = get_db()
        self.collection_interval = 60
        self.running = False
    
    async def start_collection(self):
        """Start collecting historical data"""
        self.running = True
        logger.info("Starting historical data collection")
        
        while self.running:
            try:
                await self.collect_market_snapshot()
                await asyncio.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Error in data collection: {e}")
                await asyncio.sleep(5)
    
    async def stop_collection(self):
        """Stop data collection"""
        self.running = False
        logger.info("Stopped historical data collection")
    
    async def collect_market_snapshot(self):
        """Collect current market snapshot"""
        try:
            async with PolymarketAPI() as api:
                markets = await api.get_markets(limit=200)
                
                for market_data in markets:
                    await self.store_market_data(market_data)
                
                logger.info(f"Collected snapshot of {len(markets)} markets")
        except Exception as e:
            logger.error(f"Error collecting market snapshot: {e}")
    
    async def store_market_data(self, market_data: Dict):
        """Store market data in database"""
        try:
            snapshot = {
                "id": str(uuid.uuid4()),
                "market_id": market_data.get('condition_id'),
                "question": market_data.get('question'),
                "category": self._categorize_market(market_data.get('question', '')),
                "yes_price": float(market_data.get('yes_price', 0)),
                "no_price": float(market_data.get('no_price', 0)),
                "volume": float(market_data.get('volume', 0)),
                "liquidity": float(market_data.get('liquidity', 0)),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_data": market_data
            }
            
            await self.db.historical_data.insert_one(snapshot)
        except Exception as e:
            logger.error(f"Error storing market data: {e}")
    
    def _categorize_market(self, question: str) -> str:
        """Categorize market based on question text"""
        question_lower = question.lower()
        
        crypto_keywords = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'coin', 'token']
        sports_keywords = ['nfl', 'nba', 'mlb', 'soccer', 'football', 'game', 'championship']
        politics_keywords = ['election', 'president', 'congress', 'senate', 'vote', 'political']
        
        if any(kw in question_lower for kw in crypto_keywords):
            return MarketCategory.CRYPTO
        elif any(kw in question_lower for kw in sports_keywords):
            return MarketCategory.SPORTS
        elif any(kw in question_lower for kw in politics_keywords):
            return MarketCategory.POLITICS
        else:
            return MarketCategory.FINANCE
    
    async def get_historical_data(self, market_id: str, limit: int = 1000) -> List[Dict]:
        """Retrieve historical data for a market"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error retrieving historical data: {e}")
            return []