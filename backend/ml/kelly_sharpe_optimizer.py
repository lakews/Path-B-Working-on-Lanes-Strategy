import logging
from typing import Dict, Tuple
import numpy as np
from config import config
from database import get_db

logger = logging.getLogger(__name__)

class KellySharpeOptimizer:
    """Kelly Criterion position sizing with Sharpe Ratio optimization"""
    
    def __init__(self):
        self.db = get_db()
        self.kelly_fraction = config.KELLY_FRACTION
        self.max_position_pct = config.MAX_POSITION_SIZE_PCT / 100
        self.min_sharpe = 1.0
        
    async def calculate_position_size(
        self, 
        market_data: Dict, 
        confidence: float, 
        win_probability: float
    ) -> Tuple[float, float]:
        """Calculate optimal position size using Kelly Criterion
        Returns: (position_size, kelly_percentage)
        """
        try:
            current_capital = await self._get_current_capital()
            
            price = market_data.get('yes_price', 0.5)
            
            odds = self._calculate_odds(price)
            
            full_kelly = self._kelly_formula(win_probability, odds)
            
            fractional_kelly = full_kelly * self.kelly_fraction
            
            confidence_adjusted = fractional_kelly * confidence
            
            capped_kelly = min(confidence_adjusted, self.max_position_pct)
            
            position_size = current_capital * capped_kelly
            
            sharpe_adjusted = await self._sharpe_adjustment(market_data, position_size)
            
            logger.info(f"Kelly size: {capped_kelly:.2%}, Position: ${position_size:.2f}")
            
            return sharpe_adjusted, capped_kelly
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.0, 0.0
    
    def _kelly_formula(self, win_prob: float, odds: float) -> float:
        """Kelly Criterion formula: f* = (p*b - q) / b"""
        try:
            p = min(max(win_prob, 0.01), 0.99)
            q = 1 - p
            b = odds
            
            kelly = (p * b - q) / b if b > 0 else 0
            
            return max(kelly, 0.0)
            
        except Exception as e:
            logger.error(f"Error in Kelly formula: {e}")
            return 0.0
    
    def _calculate_odds(self, price: float) -> float:
        """Calculate betting odds from price"""
        try:
            if price >= 0.99:
                return 0.01
            if price <= 0.01:
                return 99.0
            
            odds = (1 - price) / price
            return odds
            
        except Exception as e:
            logger.error(f"Error calculating odds: {e}")
            return 1.0
    
    async def _sharpe_adjustment(self, market_data: Dict, base_position: float) -> float:
        """Adjust position based on Sharpe Ratio"""
        try:
            market_id = market_data.get('id')
            
            historical_returns = await self._get_market_returns(market_id)
            
            if len(historical_returns) < 10:
                return base_position
            
            sharpe = self._calculate_sharpe(historical_returns)
            
            if sharpe < self.min_sharpe:
                adjustment = 0.5
            elif sharpe > 2.0:
                adjustment = 1.2
            else:
                adjustment = 0.5 + (sharpe / 2.0) * 0.5
            
            adjusted_position = base_position * adjustment
            
            max_position = config.INITIAL_CAPITAL * self.max_position_pct
            return min(adjusted_position, max_position)
            
        except Exception as e:
            logger.error(f"Error in Sharpe adjustment: {e}")
            return base_position
    
    def _calculate_sharpe(self, returns: list) -> float:
        """Calculate Sharpe Ratio"""
        try:
            if len(returns) < 2:
                return 0.0
            
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            
            if std_return == 0:
                return 0.0
            
            sharpe = mean_return / std_return
            return sharpe
            
        except Exception as e:
            logger.error(f"Error calculating Sharpe: {e}")
            return 0.0
    
    async def _get_current_capital(self) -> float:
        """Get current available capital"""
        try:
            metrics = await self.db.performance_metrics.find_one(
                {},
                sort=[("timestamp", -1)]
            )
            
            if metrics:
                return metrics.get('total_capital', config.INITIAL_CAPITAL)
            return config.INITIAL_CAPITAL
            
        except Exception as e:
            logger.error(f"Error getting capital: {e}")
            return config.INITIAL_CAPITAL
    
    async def _get_market_returns(self, market_id: str) -> list:
        """Get historical returns for market"""
        try:
            cursor = self.db.trades.find(
                {"market_id": market_id},
                {"price": 1, "_id": 0}
            ).sort("timestamp", -1).limit(50)
            
            docs = await cursor.to_list(length=50)
            prices = [doc['price'] for doc in reversed(docs)]
            
            if len(prices) < 2:
                return []
            
            returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
            return returns
            
        except Exception as e:
            logger.error(f"Error getting market returns: {e}")
            return []