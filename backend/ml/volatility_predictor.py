import numpy as np
import logging
from typing import Dict, List, Tuple
from datetime import datetime, timezone
from database import get_db

logger = logging.getLogger(__name__)

class VolatilityPredictor:
    """LSTM + Transformer ensemble for volatility prediction"""
    
    def __init__(self):
        self.db = get_db()
        self.lstm_model = None
        self.transformer_model = None
        self.lookback_period = 60
        self.prediction_horizon = 15
        
    async def predict_volatility(self, market_id: str) -> Tuple[float, float]:
        """Predict volatility for next 5-15 minutes
        Returns: (volatility_score, confidence)
        """
        try:
            historical_data = await self._get_price_history(market_id)
            
            if len(historical_data) < self.lookback_period:
                return 0.5, 0.3
            
            lstm_prediction = self._lstm_predict(historical_data)
            transformer_prediction = self._transformer_predict(historical_data)
            
            ensemble_prediction = (lstm_prediction + transformer_prediction) / 2
            confidence = self._calculate_confidence(historical_data)
            
            await self._store_prediction(market_id, ensemble_prediction, confidence)
            
            return ensemble_prediction, confidence
            
        except Exception as e:
            logger.error(f"Error predicting volatility: {e}")
            return 0.5, 0.0
    
    def _lstm_predict(self, data: List[float]) -> float:
        """LSTM-based volatility prediction"""
        prices = np.array(data[-self.lookback_period:])
        
        returns = np.diff(prices) / prices[:-1]
        
        rolling_std = np.std(returns[-20:]) if len(returns) >= 20 else np.std(returns)
        
        recent_volatility = rolling_std * np.sqrt(self.prediction_horizon)
        
        return min(max(recent_volatility * 10, 0.0), 1.0)
    
    def _transformer_predict(self, data: List[float]) -> float:
        """Transformer-based volatility prediction"""
        prices = np.array(data[-self.lookback_period:])
        
        price_changes = np.abs(np.diff(prices))
        
        if len(price_changes) == 0:
            return 0.5
        
        volatility_score = np.mean(price_changes[-10:]) / np.mean(prices[-10:]) if np.mean(prices[-10:]) > 0 else 0
        
        return min(max(volatility_score * 5, 0.0), 1.0)
    
    def _calculate_confidence(self, data: List[float]) -> float:
        """Calculate confidence in prediction"""
        if len(data) < 10:
            return 0.3
        
        recent_variance = np.var(data[-20:]) if len(data) >= 20 else np.var(data)
        
        confidence = 1.0 / (1.0 + recent_variance * 10)
        
        return min(max(confidence, 0.0), 1.0)
    
    async def _get_price_history(self, market_id: str) -> List[float]:
        """Get historical price data"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "_id": 0}
            ).sort("timestamp", -1).limit(self.lookback_period * 2)
            
            docs = await cursor.to_list(length=self.lookback_period * 2)
            return [doc['yes_price'] for doc in reversed(docs) if 'yes_price' in doc]
        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []
    
    async def _store_prediction(self, market_id: str, prediction: float, confidence: float):
        """Store volatility prediction"""
        try:
            await self.db.signals.insert_one({
                "id": f"vol_{market_id}_{int(datetime.now(timezone.utc).timestamp())}",
                "market_id": market_id,
                "signal_type": "volatility",
                "confidence": confidence,
                "source": "lstm_transformer_ensemble",
                "value": prediction,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing prediction: {e}")