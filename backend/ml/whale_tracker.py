"""
Enhanced Sharp/Whale Trader Detection Module
Tracks large traders and smart money movements on Polymarket
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from database import get_db
from config import config
import uuid
import aiohttp

logger = logging.getLogger(__name__)


class WhaleTracker:
    """
    Tracks whale activity and smart money movements.
    Uses volume spikes and price impact to identify large traders.
    """
    
    def __init__(self):
        self.db = get_db()
        self.whale_threshold_volume = 10000  # $10k+ is considered whale activity
        self.sharp_win_rate_threshold = 0.65  # 65%+ win rate = sharp
        self.tracking_window = timedelta(days=7)
        
        # Simulated whale profiles (in production, track real addresses)
        self.known_whales = {}
        self.whale_positions = {}
    
    async def detect_whale_activity(self, market_data: Dict) -> Dict:
        """
        Detect whale activity in a market based on volume patterns
        Returns: {
            'whale_activity_score': float (0-1),
            'volume_spike': bool,
            'large_orders_detected': int,
            'whale_direction': str ('bullish', 'bearish', 'neutral'),
            'confidence': float
        }
        """
        try:
            market_id = market_data.get('id', '')
            volume = market_data.get('volume', 0)
            volume_24h = market_data.get('volume24hr', 0)
            liquidity = market_data.get('liquidity', 0)
            yes_price = market_data.get('yes_price', 0.5)
            
            # Calculate volume metrics
            volume_spike = await self._detect_volume_spike(market_id, volume_24h)
            price_impact = self._calculate_price_impact(market_data)
            large_order_indicator = self._detect_large_orders(volume_24h, liquidity)
            
            # Analyze price movement for direction
            direction = await self._analyze_whale_direction(market_id, yes_price)
            
            # Calculate overall whale activity score
            whale_score = (
                (0.4 if volume_spike else 0) +
                (price_impact * 0.3) +
                (large_order_indicator * 0.3)
            )
            
            # Confidence based on data quality
            confidence = min(0.9, 0.5 + (volume_24h / 100000) * 0.4)
            
            result = {
                'whale_activity_score': round(whale_score, 4),
                'volume_spike': volume_spike,
                'large_orders_detected': int(large_order_indicator * 10),
                'whale_direction': direction,
                'price_impact_score': round(price_impact, 4),
                'confidence': round(confidence, 4),
                'volume_24h': volume_24h,
                'liquidity': liquidity,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Store whale signal
            await self._store_whale_signal(market_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting whale activity: {e}")
            return {
                'whale_activity_score': 0,
                'volume_spike': False,
                'whale_direction': 'neutral',
                'confidence': 0.1
            }
    
    async def _detect_volume_spike(self, market_id: str, current_volume: float) -> bool:
        """Detect if current volume is significantly above average"""
        try:
            # Get historical volume data
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"volume": 1, "_id": 0}
            ).sort("timestamp", -1).limit(100)
            
            historical = await cursor.to_list(length=100)
            
            if not historical:
                return current_volume > self.whale_threshold_volume
            
            volumes = [h.get('volume', 0) for h in historical if h.get('volume', 0) > 0]
            
            if not volumes:
                return current_volume > self.whale_threshold_volume
            
            avg_volume = np.mean(volumes)
            std_volume = np.std(volumes) if len(volumes) > 1 else avg_volume * 0.5
            
            # Volume spike if > 2 standard deviations above mean
            return current_volume > (avg_volume + 2 * std_volume)
            
        except Exception as e:
            logger.error(f"Error detecting volume spike: {e}")
            return False
    
    def _calculate_price_impact(self, market_data: Dict) -> float:
        """Calculate potential price impact score"""
        volume = market_data.get('volume24hr', 0)
        liquidity = market_data.get('liquidity', 1)
        
        if liquidity == 0:
            return 0
        
        # Volume to liquidity ratio indicates market impact
        ratio = volume / liquidity
        
        # Normalize to 0-1 scale
        # Ratio > 1 means volume exceeds liquidity (high impact)
        impact = min(ratio / 2, 1.0)
        
        return impact
    
    def _detect_large_orders(self, volume_24h: float, liquidity: float) -> float:
        """Estimate presence of large orders"""
        if liquidity == 0:
            return 0
        
        # Large order indicator based on volume relative to liquidity
        indicator = min(volume_24h / max(liquidity * 2, 1), 1.0)
        
        return indicator
    
    async def _analyze_whale_direction(self, market_id: str, current_price: float) -> str:
        """Analyze whale trading direction from price movement"""
        try:
            # Get recent price history
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "timestamp": 1, "_id": 0}
            ).sort("timestamp", -1).limit(20)
            
            history = await cursor.to_list(length=20)
            
            if len(history) < 5:
                return 'neutral'
            
            prices = [h.get('yes_price', 0.5) for h in history]
            
            # Calculate trend
            recent_avg = np.mean(prices[:5])
            older_avg = np.mean(prices[5:])
            
            price_change = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            if price_change > 0.02:  # >2% increase
                return 'bullish'
            elif price_change < -0.02:  # >2% decrease
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception as e:
            logger.error(f"Error analyzing whale direction: {e}")
            return 'neutral'
    
    async def track_sharp_traders(self) -> Dict:
        """
        Identify and track sharp (smart money) traders
        Returns statistics about sharp trader activity
        """
        try:
            # Get markets with high volume spikes
            cursor = self.db.historical_data.aggregate([
                {"$match": {"source": "price_history"}},
                {"$group": {
                    "_id": "$market_id",
                    "total_volume": {"$sum": "$volume"},
                    "avg_price": {"$avg": "$yes_price"},
                    "price_std": {"$stdDevPop": "$yes_price"},
                    "count": {"$sum": 1}
                }},
                {"$match": {"count": {"$gt": 10}}},
                {"$sort": {"total_volume": -1}},
                {"$limit": 50}
            ])
            
            markets = await cursor.to_list(length=50)
            
            # Analyze which markets show sharp money patterns
            sharp_markets = []
            for market in markets:
                if market.get('price_std', 0) > 0.02:  # Significant price movement
                    sharp_markets.append({
                        'market_id': market['_id'],
                        'volume': market['total_volume'],
                        'price_volatility': market['price_std'],
                        'data_points': market['count']
                    })
            
            # Store analysis
            await self.db.sharp_analysis.update_one(
                {"type": "daily_summary"},
                {"$set": {
                    "markets_analyzed": len(markets),
                    "sharp_markets": len(sharp_markets),
                    "top_sharp_markets": sharp_markets[:10],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            
            return {
                'markets_analyzed': len(markets),
                'sharp_markets_identified': len(sharp_markets),
                'top_markets': sharp_markets[:5]
            }
            
        except Exception as e:
            logger.error(f"Error tracking sharp traders: {e}")
            return {'markets_analyzed': 0, 'sharp_markets_identified': 0}
    
    async def get_whale_alignment(self, market_id: str, proposed_side: str) -> Tuple[float, float]:
        """
        Get alignment score with whale/smart money activity
        Returns: (alignment_score, confidence)
        """
        try:
            # Get recent whale signal for this market
            signal = await self.db.whale_signals.find_one(
                {"market_id": market_id},
                {"_id": 0},
                sort=[("timestamp", -1)]
            )
            
            if not signal:
                return 0.5, 0.1
            
            whale_direction = signal.get('whale_direction', 'neutral')
            whale_score = signal.get('whale_activity_score', 0)
            confidence = signal.get('confidence', 0.5)
            
            # Calculate alignment
            if whale_direction == 'neutral':
                alignment = 0.5
            elif (whale_direction == 'bullish' and proposed_side == 'BUY') or \
                 (whale_direction == 'bearish' and proposed_side == 'SELL'):
                alignment = 0.5 + (whale_score * 0.5)  # Aligned with whales
            else:
                alignment = 0.5 - (whale_score * 0.3)  # Against whales
            
            return alignment, confidence
            
        except Exception as e:
            logger.error(f"Error getting whale alignment: {e}")
            return 0.5, 0.1
    
    async def _store_whale_signal(self, market_id: str, result: Dict):
        """Store whale activity signal"""
        try:
            await self.db.whale_signals.update_one(
                {"market_id": market_id},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "market_id": market_id,
                    **result
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error storing whale signal: {e}")
    
    async def get_whale_statistics(self) -> Dict:
        """Get overall whale tracking statistics"""
        try:
            # Count whale signals
            total_signals = await self.db.whale_signals.count_documents({})
            bullish_signals = await self.db.whale_signals.count_documents({"whale_direction": "bullish"})
            bearish_signals = await self.db.whale_signals.count_documents({"whale_direction": "bearish"})
            
            # Get recent high-activity markets
            cursor = self.db.whale_signals.find(
                {"whale_activity_score": {"$gt": 0.5}},
                {"_id": 0}
            ).sort("timestamp", -1).limit(10)
            
            high_activity = await cursor.to_list(length=10)
            
            return {
                'total_markets_tracked': total_signals,
                'bullish_whale_markets': bullish_signals,
                'bearish_whale_markets': bearish_signals,
                'neutral_markets': total_signals - bullish_signals - bearish_signals,
                'high_activity_markets': len(high_activity),
                'recent_whale_activity': high_activity[:5]
            }
            
        except Exception as e:
            logger.error(f"Error getting whale statistics: {e}")
            return {'total_markets_tracked': 0}


# Singleton instance
whale_tracker = WhaleTracker()
