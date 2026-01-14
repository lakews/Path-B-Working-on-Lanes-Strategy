"""
Enhanced Whale Tracker with Real Polymarket CLOB Data
Tracks large traders and smart money movements using actual trade data from Polymarket
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import uuid
import aiohttp
import asyncio
import os

logger = logging.getLogger(__name__)


class WhaleTracker:
    """
    Tracks whale activity and smart money movements using Polymarket CLOB API.
    Monitors large trades (>$1000) to identify whale positioning.
    """
    
    # Polymarket CLOB API endpoints
    CLOB_REST_URL = "https://clob.polymarket.com"
    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    
    def __init__(self):
        self._db = None
        self.whale_threshold_usd = 1000  # $1000+ trades considered whale activity
        self.large_whale_threshold = 5000  # $5000+ is major whale
        self.mega_whale_threshold = 25000  # $25000+ is mega whale
        self.sharp_win_rate_threshold = 0.65  # 65%+ win rate = sharp trader
        self.tracking_window = timedelta(hours=24)
        
        # Cache for recent trades
        self._trade_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        # API credentials (optional for public endpoints)
        self.api_key = os.environ.get('API_KEY', '')
        
    @property
    def db(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db
    
    async def fetch_recent_trades(self, market_id: str, limit: int = 100) -> List[Dict]:
        """
        Fetch recent trades from Polymarket CLOB API
        """
        try:
            # Try to get token ID for the market
            token_id = await self._get_token_id(market_id)
            if not token_id:
                logger.warning(f"Could not find token ID for market {market_id}")
                return []
            
            async with aiohttp.ClientSession() as session:
                # Fetch trades from CLOB API
                url = f"{self.CLOB_REST_URL}/trades"
                params = {
                    "asset_id": token_id,
                    "limit": limit
                }
                
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                async with session.get(url, params=params, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        trades = data if isinstance(data, list) else data.get('trades', [])
                        
                        # Process and enrich trade data
                        processed_trades = []
                        for trade in trades:
                            processed = {
                                'trade_id': trade.get('id', str(uuid.uuid4())),
                                'market_id': market_id,
                                'token_id': token_id,
                                'price': float(trade.get('price', 0)),
                                'size': float(trade.get('size', 0)),
                                'side': trade.get('side', 'unknown'),
                                'timestamp': trade.get('timestamp', datetime.now(timezone.utc).isoformat()),
                                'maker': trade.get('maker', ''),
                                'taker': trade.get('taker', ''),
                                'usd_value': float(trade.get('price', 0)) * float(trade.get('size', 0))
                            }
                            processed_trades.append(processed)
                        
                        return processed_trades
                    else:
                        logger.warning(f"Failed to fetch trades: {response.status}")
                        return []
                        
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching trades for {market_id}")
            return []
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []
    
    async def _get_token_id(self, market_id: str) -> Optional[str]:
        """Get token ID for a market from Gamma API"""
        try:
            # Check cache first
            cache_key = f"token_{market_id}"
            if cache_key in self._trade_cache:
                cached = self._trade_cache[cache_key]
                if datetime.now(timezone.utc).timestamp() - cached['time'] < self._cache_ttl:
                    return cached['value']
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.GAMMA_API_URL}/markets/{market_id}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Get YES token ID (typically the first one)
                        tokens = data.get('tokens', [])
                        if tokens:
                            token_id = tokens[0].get('token_id')
                            # Cache it
                            self._trade_cache[cache_key] = {
                                'value': token_id,
                                'time': datetime.now(timezone.utc).timestamp()
                            }
                            return token_id
            return None
        except Exception as e:
            logger.error(f"Error getting token ID: {e}")
            return None
    
    async def detect_whale_activity(self, market_data: Dict) -> Dict:
        """
        Detect whale activity using real trade data from Polymarket CLOB
        Returns comprehensive whale analysis
        """
        try:
            market_id = market_data.get('id', '')
            
            # Fetch recent trades from API
            trades = await self.fetch_recent_trades(market_id, limit=200)
            
            # If no trades from API, fall back to volume-based analysis
            if not trades:
                return await self._fallback_whale_detection(market_data)
            
            # Analyze trades for whale activity
            whale_trades = [t for t in trades if t['usd_value'] >= self.whale_threshold_usd]
            large_whale_trades = [t for t in trades if t['usd_value'] >= self.large_whale_threshold]
            mega_whale_trades = [t for t in trades if t['usd_value'] >= self.mega_whale_threshold]
            
            total_volume = sum(t['usd_value'] for t in trades)
            whale_volume = sum(t['usd_value'] for t in whale_trades)
            
            # Analyze direction
            buy_volume = sum(t['usd_value'] for t in whale_trades if t['side'].lower() == 'buy')
            sell_volume = sum(t['usd_value'] for t in whale_trades if t['side'].lower() == 'sell')
            
            if whale_volume > 0:
                buy_ratio = buy_volume / whale_volume
                if buy_ratio > 0.6:
                    direction = 'bullish'
                elif buy_ratio < 0.4:
                    direction = 'bearish'
                else:
                    direction = 'neutral'
            else:
                direction = 'neutral'
            
            # Calculate whale activity score (0-1)
            whale_score = min(1.0, len(whale_trades) / 10)  # Normalize: 10+ whale trades = max score
            
            # Volume spike detection
            volume_spike = whale_volume > (total_volume * 0.5) if total_volume > 0 else False
            
            # Confidence based on data quality
            confidence = min(0.95, 0.3 + (len(trades) / 200) * 0.65)
            
            # Track unique whale addresses
            whale_addresses = set()
            for t in whale_trades:
                if t.get('taker'):
                    whale_addresses.add(t['taker'])
                if t.get('maker'):
                    whale_addresses.add(t['maker'])
            
            result = {
                'whale_activity_score': round(whale_score, 4),
                'volume_spike': volume_spike,
                'large_orders_detected': len(whale_trades),
                'large_whale_orders': len(large_whale_trades),
                'mega_whale_orders': len(mega_whale_trades),
                'whale_direction': direction,
                'whale_buy_volume': round(buy_volume, 2),
                'whale_sell_volume': round(sell_volume, 2),
                'buy_sell_ratio': round(buy_ratio, 4) if whale_volume > 0 else 0.5,
                'total_whale_volume': round(whale_volume, 2),
                'total_market_volume': round(total_volume, 2),
                'whale_volume_pct': round((whale_volume / total_volume * 100) if total_volume > 0 else 0, 2),
                'unique_whales': len(whale_addresses),
                'confidence': round(confidence, 4),
                'data_source': 'polymarket_clob',
                'trades_analyzed': len(trades),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Store whale signal
            await self._store_whale_signal(market_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting whale activity: {e}")
            return await self._fallback_whale_detection(market_data)
    
    async def _fallback_whale_detection(self, market_data: Dict) -> Dict:
        """
        Fallback whale detection using volume heuristics when API is unavailable
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
            
            # Lower confidence for fallback method
            confidence = min(0.6, 0.3 + (volume_24h / 100000) * 0.3)
            
            result = {
                'whale_activity_score': round(whale_score, 4),
                'volume_spike': volume_spike,
                'large_orders_detected': int(large_order_indicator * 10),
                'whale_direction': direction,
                'price_impact_score': round(price_impact, 4),
                'confidence': round(confidence, 4),
                'volume_24h': volume_24h,
                'liquidity': liquidity,
                'data_source': 'volume_heuristics',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            await self._store_whale_signal(market_id, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in fallback whale detection: {e}")
            return {
                'whale_activity_score': 0,
                'volume_spike': False,
                'whale_direction': 'neutral',
                'confidence': 0.1,
                'data_source': 'error'
            }
    
    async def _detect_volume_spike(self, market_id: str, current_volume: float) -> bool:
        """Detect if current volume is significantly above average"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"volume": 1, "_id": 0}
            ).sort("timestamp", -1).limit(100)
            
            historical = await cursor.to_list(length=100)
            
            if not historical:
                return current_volume > self.whale_threshold_usd * 10
            
            volumes = [h.get('volume', 0) for h in historical if h.get('volume', 0) > 0]
            
            if not volumes:
                return current_volume > self.whale_threshold_usd * 10
            
            avg_volume = np.mean(volumes)
            std_volume = np.std(volumes) if len(volumes) > 1 else avg_volume * 0.5
            
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
        
        ratio = volume / liquidity
        impact = min(ratio / 2, 1.0)
        
        return impact
    
    def _detect_large_orders(self, volume_24h: float, liquidity: float) -> float:
        """Estimate presence of large orders"""
        if liquidity == 0:
            return 0
        
        indicator = min(volume_24h / max(liquidity * 2, 1), 1.0)
        return indicator
    
    async def _analyze_whale_direction(self, market_id: str, current_price: float) -> str:
        """Analyze whale trading direction from price movement"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "timestamp": 1, "_id": 0}
            ).sort("timestamp", -1).limit(20)
            
            history = await cursor.to_list(length=20)
            
            if len(history) < 5:
                return 'neutral'
            
            prices = [h.get('yes_price', 0.5) for h in history]
            
            recent_avg = np.mean(prices[:5])
            older_avg = np.mean(prices[5:])
            
            price_change = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            if price_change > 0.02:
                return 'bullish'
            elif price_change < -0.02:
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
            
            sharp_markets = []
            for market in markets:
                if market.get('price_std', 0) > 0.02:
                    sharp_markets.append({
                        'market_id': market['_id'],
                        'volume': market['total_volume'],
                        'price_volatility': market['price_std'],
                        'data_points': market['count']
                    })
            
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
            
            if whale_direction == 'neutral':
                alignment = 0.5
            elif (whale_direction == 'bullish' and proposed_side == 'BUY') or \
                 (whale_direction == 'bearish' and proposed_side == 'SELL'):
                alignment = 0.5 + (whale_score * 0.5)
            else:
                alignment = 0.5 - (whale_score * 0.3)
            
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
            total_signals = await self.db.whale_signals.count_documents({})
            bullish_signals = await self.db.whale_signals.count_documents({"whale_direction": "bullish"})
            bearish_signals = await self.db.whale_signals.count_documents({"whale_direction": "bearish"})
            
            # Get signals with real data
            real_data_signals = await self.db.whale_signals.count_documents({"data_source": "polymarket_clob"})
            
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
                'real_data_markets': real_data_signals,
                'fallback_data_markets': total_signals - real_data_signals,
                'recent_whale_activity': high_activity[:5],
                'data_quality': {
                    'real_data_pct': round((real_data_signals / total_signals * 100) if total_signals > 0 else 0, 1),
                    'description': 'Percentage of markets tracked using live Polymarket CLOB data'
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting whale statistics: {e}")
            return {'total_markets_tracked': 0}
    
    async def get_top_whale_markets(self, limit: int = 10) -> List[Dict]:
        """Get markets with highest whale activity"""
        try:
            cursor = self.db.whale_signals.find(
                {},
                {"_id": 0, "market_id": 1, "whale_activity_score": 1, "whale_direction": 1, 
                 "total_whale_volume": 1, "large_orders_detected": 1, "timestamp": 1}
            ).sort("whale_activity_score", -1).limit(limit)
            
            markets = await cursor.to_list(length=limit)
            return markets
            
        except Exception as e:
            logger.error(f"Error getting top whale markets: {e}")
            return []


# Singleton instance
whale_tracker = WhaleTracker()
