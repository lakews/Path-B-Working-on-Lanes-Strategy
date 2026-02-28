import logging
from typing import Dict, Tuple
from datetime import datetime, timezone
from database import get_db

# Import centralized spread constants
from execution.spread_policy import MAX_SPREAD_HFT, MIN_SPREAD_MAKER

logger = logging.getLogger(__name__)

class SpreadCalibrator:
    """Dynamic spread adjustment based on market conditions
    Adjusts spread size according to volatility and liquidity
    Target: Maximize profits during favorable conditions
    
    NOTE: Uses centralized spread policy constants from execution/spread_policy.py
    """
    
    def __init__(self):
        self.db = get_db()
        # Import RISK for centralized thresholds
        from risk_config import RISK
        self.base_spread = 0.02  # 2% base spread
        self.min_spread = MIN_SPREAD_MAKER  # Use centralized constant
        self.max_spread = MAX_SPREAD_HFT    # Use centralized constant (25%)
        self.volatility_threshold = 0.5
        self.liquidity_threshold = RISK.HFT_MIN_LIQUIDITY  # Task 27: Use SSOT
        
    async def calculate_optimal_spread(
        self,
        market_id: str,
        current_price: float,
        volatility: float,
        liquidity: float,
        volume: float
    ) -> Tuple[float, str]:
        """Calculate optimal spread based on market conditions
        Returns: (spread_percentage, reasoning)
        """
        try:
            # Start with base spread
            spread = self.base_spread
            reasoning_parts = []
            
            # Adjust for volatility
            volatility_adjustment = self._adjust_for_volatility(volatility)
            spread *= volatility_adjustment
            reasoning_parts.append(f"Volatility {volatility:.2f} → {volatility_adjustment:.2f}x")
            
            # Adjust for liquidity
            liquidity_adjustment = self._adjust_for_liquidity(liquidity)
            spread *= liquidity_adjustment
            reasoning_parts.append(f"Liquidity ${liquidity:.0f} → {liquidity_adjustment:.2f}x")
            
            # Adjust for volume
            volume_adjustment = self._adjust_for_volume(volume, liquidity)
            spread *= volume_adjustment
            reasoning_parts.append(f"Volume ratio → {volume_adjustment:.2f}x")
            
            # Adjust for price extremes
            price_adjustment = self._adjust_for_price_extremes(current_price)
            spread *= price_adjustment
            if price_adjustment != 1.0:
                reasoning_parts.append(f"Price extreme → {price_adjustment:.2f}x")
            
            # Adjust for market timing
            timing_adjustment = await self._adjust_for_timing(market_id)
            spread *= timing_adjustment
            if timing_adjustment != 1.0:
                reasoning_parts.append(f"Timing → {timing_adjustment:.2f}x")
            
            # Clamp to min/max
            spread = max(self.min_spread, min(self.max_spread, spread))
            
            reasoning = " | ".join(reasoning_parts)
            
            logger.info(f"Optimal spread for {market_id}: {spread:.3f} ({reasoning})")
            
            # Store calibration result
            await self._store_calibration(market_id, spread, reasoning)
            
            return spread, reasoning
            
        except Exception as e:
            logger.error(f"Error calculating optimal spread: {e}")
            return self.base_spread, "Error - using base spread"
    
    def _adjust_for_volatility(self, volatility: float) -> float:
        """Adjust spread based on volatility
        Higher volatility → Wider spread (more risk)
        """
        try:
            if volatility > 0.8:
                return 3.0  # Very high volatility - wide spread
            elif volatility > 0.6:
                return 2.0  # High volatility
            elif volatility > 0.4:
                return 1.5  # Moderate volatility
            elif volatility > 0.2:
                return 1.0  # Normal volatility
            else:
                return 0.7  # Low volatility - tighter spread
                
        except Exception as e:
            logger.error(f"Error adjusting for volatility: {e}")
            return 1.0
    
    def _adjust_for_liquidity(self, liquidity: float) -> float:
        """Adjust spread based on liquidity
        Lower liquidity → Wider spread (harder to fill)
        """
        try:
            if liquidity < 1000:
                return 2.5  # Very low liquidity
            elif liquidity < 5000:
                return 1.8  # Low liquidity
            elif liquidity < 20000:
                return 1.0  # Normal liquidity
            else:
                return 0.8  # High liquidity - tighter spread
                
        except Exception as e:
            logger.error(f"Error adjusting for liquidity: {e}")
            return 1.0
    
    def _adjust_for_volume(self, volume: float, liquidity: float) -> float:
        """Adjust spread based on volume/liquidity ratio
        High volume relative to liquidity → Wider spread
        """
        try:
            if liquidity == 0:
                return 1.5
            
            volume_ratio = volume / liquidity
            
            if volume_ratio > 2.0:
                return 1.5  # Very high volume - widen spread
            elif volume_ratio > 1.0:
                return 1.2  # High volume
            elif volume_ratio > 0.5:
                return 1.0  # Normal
            else:
                return 0.9  # Low volume - tighten spread
                
        except Exception as e:
            logger.error(f"Error adjusting for volume: {e}")
            return 1.0
    
    def _adjust_for_price_extremes(self, price: float) -> float:
        """Adjust spread for extreme prices
        Very low/high prices → Wider spread (more uncertainty)
        """
        try:
            if price < 0.10 or price > 0.90:
                return 1.5  # Extreme prices - wider spread
            elif price < 0.20 or price > 0.80:
                return 1.2  # Near extremes
            else:
                return 1.0  # Normal range
                
        except Exception as e:
            logger.error(f"Error adjusting for price extremes: {e}")
            return 1.0
    
    async def _adjust_for_timing(self, market_id: str) -> float:
        """Adjust spread based on time patterns
        Near market close → Wider spread (less time to capture)
        """
        try:
            market = await self.db.markets.find_one(
                {"id": market_id},
                {"end_date": 1, "_id": 0}
            )
            
            if not market or not market.get('end_date'):
                return 1.0
            
            end_date = market['end_date']
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            now = datetime.now(timezone.utc)
            time_remaining = (end_date - now).total_seconds()
            
            # Less than 1 hour remaining
            if time_remaining < 3600:
                return 2.0  # Very tight deadline
            # Less than 6 hours
            elif time_remaining < 21600:
                return 1.5  # Tight deadline
            # Less than 24 hours
            elif time_remaining < 86400:
                return 1.2  # Approaching deadline
            else:
                return 1.0  # Normal timing
                
        except Exception as e:
            logger.error(f"Error adjusting for timing: {e}")
            return 1.0
    
    async def get_spread_for_market(self, market_data: Dict) -> float:
        """Convenience method to get optimal spread for a market"""
        try:
            market_id = market_data.get('id')
            price = market_data.get('yes_price')
            
            # STRICT: Reject if no valid price
            if price is None or price == 0:
                logger.warning(f"[SPREAD] No valid price for {market_id} - using base spread")
                return self.base_spread
            
            price = float(price)
            liquidity = market_data.get('liquidity', 0)
            volume = market_data.get('volume', 0)
            
            # Get volatility prediction
            from ml.volatility_predictor import VolatilityPredictor
            volatility_predictor = VolatilityPredictor()
            volatility, _ = await volatility_predictor.predict_volatility(market_id)
            
            spread, reasoning = await self.calculate_optimal_spread(
                market_id,
                price,
                volatility,
                liquidity,
                volume
            )
            
            return spread
            
        except Exception as e:
            logger.error(f"Error getting spread for market: {e}")
            return self.base_spread
    
    async def _store_calibration(self, market_id: str, spread: float, reasoning: str):
        """Store spread calibration result"""
        try:
            await self.db.spread_calibrations.insert_one({
                "market_id": market_id,
                "spread": spread,
                "reasoning": reasoning,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing calibration: {e}")
    
    async def get_calibration_history(self, market_id: str, limit: int = 20) -> list:
        """Get historical spread calibrations for a market"""
        try:
            cursor = self.db.spread_calibrations.find(
                {"market_id": market_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting calibration history: {e}")
            return []
    
    async def get_average_spread_by_condition(self) -> Dict:
        """Get average spreads by market conditions"""
        try:
            # Aggregate by reasoning patterns
            pipeline = [
                {
                    "$group": {
                        "_id": "$reasoning",
                        "avg_spread": {"$avg": "$spread"},
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            cursor = self.db.spread_calibrations.aggregate(pipeline)
            results = await cursor.to_list(length=10)
            
            return {
                r['_id']: {
                    "avg_spread": r['avg_spread'],
                    "count": r['count']
                }
                for r in results
            }
            
        except Exception as e:
            logger.error(f"Error getting average spreads: {e}")
            return {}
