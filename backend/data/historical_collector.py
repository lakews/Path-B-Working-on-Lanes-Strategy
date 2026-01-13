import asyncio
import logging
from datetime import datetime, timezone, timedelta
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
        self.collection_interval = 60  # Collect every 60 seconds
        self.running = False
        self.snapshots_collected = 0
        self.last_collection_time = None
    
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
                
                stored_count = 0
                for market_data in markets:
                    success = await self.store_market_data(market_data)
                    if success:
                        stored_count += 1
                
                self.snapshots_collected += stored_count
                self.last_collection_time = datetime.now(timezone.utc)
                
                logger.info(f"Collected snapshot of {stored_count} markets")
                return stored_count
        except Exception as e:
            logger.error(f"Error collecting market snapshot: {e}")
            return 0
    
    async def store_market_data(self, market_data: Dict) -> bool:
        """Store market data in database"""
        try:
            # Extract prices safely
            yes_price = 0.5
            no_price = 0.5
            
            # Try different price fields - tokens array is the standard format
            tokens = market_data.get('tokens', [])
            if tokens and len(tokens) >= 2:
                for token in tokens:
                    outcome = token.get('outcome', '').lower()
                    price = token.get('price', 0)
                    if outcome in ['yes', 'true'] or 'yes' in outcome:
                        yes_price = float(price) if price else 0.5
                    elif outcome in ['no', 'false'] or 'no' in outcome:
                        no_price = float(price) if price else 0.5
                    # For other outcomes (sports teams, etc.), use first as yes, second as no
                    elif tokens.index(token) == 0:
                        yes_price = float(price) if price else 0.5
                    else:
                        no_price = float(price) if price else 0.5
            elif 'outcomePrices' in market_data:
                prices = market_data.get('outcomePrices', [])
                if len(prices) >= 2:
                    yes_price = float(prices[0]) if prices[0] else 0.5
                    no_price = float(prices[1]) if prices[1] else 0.5
            elif 'yes_price' in market_data:
                yes_price = float(market_data.get('yes_price', 0.5))
                no_price = float(market_data.get('no_price', 0.5))
            
            snapshot = {
                "id": str(uuid.uuid4()),
                "market_id": market_data.get('condition_id') or market_data.get('id'),
                "question": market_data.get('question', ''),
                "category": self._categorize_market(market_data.get('question', '')),
                "yes_price": yes_price,
                "no_price": no_price,
                "volume": float(market_data.get('volume', 0) or 0),
                "liquidity": float(market_data.get('liquidity', 0) or 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "end_date": market_data.get('end_date_iso') or market_data.get('endDate'),
                "raw_data": market_data
            }
            
            await self.db.historical_data.insert_one(snapshot)
            return True
        except Exception as e:
            logger.error(f"Error storing market data: {e}")
            return False
    
    def _categorize_market(self, question: str) -> str:
        """Categorize market based on question text"""
        question_lower = question.lower()
        
        crypto_keywords = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'coin', 'token', 'solana', 'sol']
        sports_keywords = ['nfl', 'nba', 'mlb', 'soccer', 'football', 'game', 'championship', 'super bowl', 'world series']
        politics_keywords = ['election', 'president', 'congress', 'senate', 'vote', 'political', 'trump', 'biden', 'governor']
        entertainment_keywords = ['oscar', 'grammy', 'emmy', 'movie', 'film', 'album', 'box office']
        
        if any(kw in question_lower for kw in crypto_keywords):
            return MarketCategory.CRYPTO
        elif any(kw in question_lower for kw in sports_keywords):
            return MarketCategory.SPORTS
        elif any(kw in question_lower for kw in politics_keywords):
            return MarketCategory.POLITICS
        elif any(kw in question_lower for kw in entertainment_keywords):
            return MarketCategory.ENTERTAINMENT
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
    
    async def get_historical_data_by_date_range(
        self, 
        start_date: str, 
        end_date: str, 
        category: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve historical data within a date range"""
        try:
            query = {
                "timestamp": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            if category:
                query["category"] = category
            
            cursor = self.db.historical_data.find(
                query,
                {"_id": 0, "raw_data": 0}  # Exclude large fields
            ).sort("timestamp", 1)
            
            return await cursor.to_list(length=50000)
        except Exception as e:
            logger.error(f"Error retrieving historical data by date range: {e}")
            return []
    
    async def get_collection_stats(self) -> Dict:
        """Get statistics about collected data"""
        try:
            total_snapshots = await self.db.historical_data.count_documents({})
            
            # Get unique markets
            unique_markets = await self.db.historical_data.distinct("market_id")
            
            # Get category distribution
            category_pipeline = [
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            category_cursor = self.db.historical_data.aggregate(category_pipeline)
            categories = await category_cursor.to_list(length=20)
            
            # Get date range
            oldest = await self.db.historical_data.find_one(
                {}, {"timestamp": 1, "_id": 0}, sort=[("timestamp", 1)]
            )
            newest = await self.db.historical_data.find_one(
                {}, {"timestamp": 1, "_id": 0}, sort=[("timestamp", -1)]
            )
            
            return {
                "total_snapshots": total_snapshots,
                "unique_markets": len(unique_markets),
                "category_distribution": {c["_id"]: c["count"] for c in categories},
                "oldest_snapshot": oldest.get("timestamp") if oldest else None,
                "newest_snapshot": newest.get("timestamp") if newest else None,
                "collector_running": self.running,
                "last_collection_time": self.last_collection_time.isoformat() if self.last_collection_time else None,
                "collection_interval_seconds": self.collection_interval
            }
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {
                "total_snapshots": 0,
                "unique_markets": 0,
                "category_distribution": {},
                "error": str(e)
            }
    
    async def cleanup_old_data(self, days_to_keep: int = 30) -> int:
        """Remove data older than specified days"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            result = await self.db.historical_data.delete_many({
                "timestamp": {"$lt": cutoff.isoformat()}
            })
            logger.info(f"Cleaned up {result.deleted_count} old snapshots")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0