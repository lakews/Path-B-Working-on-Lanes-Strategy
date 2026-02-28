import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from database import get_db
from data.polymarket_api import PolymarketAPI
from models import MarketCategory
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
        self.price_history_running = False
        self.price_history_stats = {
            "markets_processed": 0,
            "price_points_collected": 0,
            "last_collection": None
        }
    
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
            # Extract prices safely - STRICT VALIDATION: None if no valid price
            yes_price = None
            no_price = None
            
            # Try different price fields - tokens array is the standard format
            tokens = market_data.get('tokens', [])
            if tokens and len(tokens) >= 2:
                for token in tokens:
                    outcome = token.get('outcome', '').lower()
                    price = token.get('price', 0)
                    if outcome in ['yes', 'true'] or 'yes' in outcome:
                        yes_price = float(price) if price else None
                    elif outcome in ['no', 'false'] or 'no' in outcome:
                        no_price = float(price) if price else None
                    # For other outcomes (sports teams, etc.), use first as yes, second as no
                    elif tokens.index(token) == 0:
                        yes_price = float(price) if price else None
                    else:
                        no_price = float(price) if price else None
            elif 'outcomePrices' in market_data:
                prices = market_data.get('outcomePrices', [])
                if len(prices) >= 2:
                    yes_price = float(prices[0]) if prices[0] else None
                    no_price = float(prices[1]) if prices[1] else None
            elif 'yes_price' in market_data:
                raw_yes = market_data.get('yes_price')
                raw_no = market_data.get('no_price')
                yes_price = float(raw_yes) if raw_yes is not None and raw_yes != 0 else None
                no_price = float(raw_no) if raw_no is not None and raw_no != 0 else None
            
            # STRICT VALIDATION: Skip storing if no valid price data
            if yes_price is None or yes_price == 0:
                logger.debug(f"[HISTORICAL] Skipping market with no valid price: {market_data.get('condition_id', 'unknown')[:16]}")
                return False
            
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
    
    # ==========================================
    # HIGH-FIDELITY PRICE HISTORY COLLECTION
    # ==========================================
    
    async def collect_price_history(self, market_limit: int = 50, interval: str = "1w", fidelity: int = 60) -> Dict:
        """
        Collect tick-level price history for active markets.
        This provides REAL price movements instead of static snapshots.
        
        Args:
            market_limit: Number of markets to collect (ordered by volume)
            interval: Time interval for history ("1h", "6h", "1d", "1w", "max")
            fidelity: Resolution in minutes
        
        Returns:
            Stats about collected data
        """
        self.price_history_running = True
        stats = {
            "markets_requested": market_limit,
            "markets_with_history": 0,
            "total_price_points": 0,
            "stored_snapshots": 0,
            "errors": []
        }
        
        try:
            async with PolymarketAPI() as api:
                # Get markets with CLOB token IDs
                markets = await api.get_markets_with_tokens(limit=market_limit)
                logger.info(f"Fetched {len(markets)} markets with token IDs")
                
                # Fetch price history for each market
                price_data = await api.get_market_price_history_batch(markets, interval, fidelity)
                
                stats["markets_with_history"] = len(price_data)
                
                # Store price history as time-series snapshots
                for condition_id, data in price_data.items():
                    history = data.get("history", [])
                    question = data.get("question", "")
                    
                    if not history:
                        continue
                    
                    stats["total_price_points"] += len(history)
                    
                    # Store each price point as a snapshot
                    for point in history:
                        timestamp_unix = point.get("t", 0)
                        price = float(point.get("p", 0.5))
                        
                        # Convert Unix timestamp to ISO
                        timestamp = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc).isoformat()
                        
                        snapshot = {
                            "id": str(uuid.uuid4()),
                            "market_id": condition_id,
                            "question": question,
                            "category": self._categorize_market(question),
                            "yes_price": price,
                            "no_price": round(1.0 - price, 4),
                            "volume": float(data.get("volume24hr", 0) or 0),
                            "liquidity": float(data.get("liquidity", 0) or 0),
                            "timestamp": timestamp,
                            "source": "price_history",  # Mark as real price data
                            "token_id": data.get("token_id"),
                            "raw_data": {"t": timestamp_unix, "p": price}
                        }
                        
                        # Upsert to avoid duplicates (same market + timestamp)
                        await self.db.historical_data.update_one(
                            {"market_id": condition_id, "timestamp": timestamp},
                            {"$set": snapshot},
                            upsert=True
                        )
                        stats["stored_snapshots"] += 1
                
                self.price_history_stats = {
                    "markets_processed": stats["markets_with_history"],
                    "price_points_collected": stats["total_price_points"],
                    "last_collection": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Price history collection complete: {stats['stored_snapshots']} snapshots from {stats['markets_with_history']} markets")
                
        except Exception as e:
            logger.error(f"Error collecting price history: {e}")
            stats["errors"].append(str(e))
        finally:
            self.price_history_running = False
        
        return stats
    
    async def start_price_history_collection(self, interval_minutes: int = 30, market_limit: int = 50):
        """Start continuous price history collection"""
        self.price_history_running = True
        logger.info(f"Starting continuous price history collection every {interval_minutes} minutes")
        
        while self.price_history_running:
            try:
                await self.collect_price_history(market_limit=market_limit)
                await asyncio.sleep(interval_minutes * 60)
            except Exception as e:
                logger.error(f"Error in continuous price history collection: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def stop_price_history_collection(self):
        """Stop continuous price history collection"""
        self.price_history_running = False
        logger.info("Stopped price history collection")
    
    async def get_price_history_stats(self) -> Dict:
        """Get statistics about collected price history data"""
        try:
            # Count snapshots with real price data vs simulated
            total_snapshots = await self.db.historical_data.count_documents({})
            real_price_snapshots = await self.db.historical_data.count_documents({"source": "price_history"})
            
            # Get unique markets with real price data
            real_markets = await self.db.historical_data.distinct("market_id", {"source": "price_history"})
            
            # Get date range for real price data
            oldest_real = await self.db.historical_data.find_one(
                {"source": "price_history"}, 
                {"timestamp": 1, "_id": 0}, 
                sort=[("timestamp", 1)]
            )
            newest_real = await self.db.historical_data.find_one(
                {"source": "price_history"}, 
                {"timestamp": 1, "_id": 0}, 
                sort=[("timestamp", -1)]
            )
            
            # Check price variation in real data
            price_variation_pipeline = [
                {"$match": {"source": "price_history"}},
                {"$group": {
                    "_id": "$market_id",
                    "min_price": {"$min": "$yes_price"},
                    "max_price": {"$max": "$yes_price"},
                    "count": {"$sum": 1}
                }},
                {"$addFields": {
                    "price_range": {"$subtract": ["$max_price", "$min_price"]}
                }},
                {"$match": {"price_range": {"$gt": 0.01}}},  # Markets with >1% price movement
                {"$count": "markets_with_movement"}
            ]
            movement_result = await self.db.historical_data.aggregate(price_variation_pipeline).to_list(length=1)
            markets_with_movement = movement_result[0]["markets_with_movement"] if movement_result else 0
            
            return {
                "total_snapshots": total_snapshots,
                "real_price_snapshots": real_price_snapshots,
                "real_price_percentage": round((real_price_snapshots / total_snapshots * 100) if total_snapshots > 0 else 0, 2),
                "unique_markets_with_real_data": len(real_markets),
                "markets_with_price_movement": markets_with_movement,
                "oldest_real_price_data": oldest_real.get("timestamp") if oldest_real else None,
                "newest_real_price_data": newest_real.get("timestamp") if newest_real else None,
                "collection_running": self.price_history_running,
                "last_collection_stats": self.price_history_stats
            }
        except Exception as e:
            logger.error(f"Error getting price history stats: {e}")
            return {"error": str(e)}