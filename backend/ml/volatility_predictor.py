import numpy as np
import logging
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
from database import get_db
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib

logger = logging.getLogger(__name__)

MODEL_DIR = "/app/backend/ml/models"
os.makedirs(MODEL_DIR, exist_ok=True)

class VolatilityPredictor:
    """Trainable volatility prediction model using historical data"""
    
    def __init__(self):
        self.db = get_db()
        self.lookback_period = 60
        self.prediction_horizon = 15
        
        # ML models
        self.gb_model: Optional[GradientBoostingRegressor] = None
        self.rf_model: Optional[RandomForestRegressor] = None
        self.scaler = StandardScaler()
        self.is_trained = False
        
        # Load model if exists
        self._load_model()
    
    async def train_model(self, min_samples: int = 1000) -> Dict:
        """Train volatility prediction model on historical data"""
        try:
            logger.info("Starting volatility model training...")
            
            # Get historical data
            cursor = self.db.historical_data.find(
                {},
                {"market_id": 1, "yes_price": 1, "volume": 1, "liquidity": 1, "timestamp": 1, "_id": 0}
            ).sort("timestamp", 1).limit(100000)
            
            docs = await cursor.to_list(length=100000)
            
            if len(docs) < min_samples:
                return {"error": f"Not enough data. Need {min_samples}, have {len(docs)}"}
            
            # Group by market and create features
            X, y = self._prepare_training_data(docs)
            
            if len(X) < 100:
                return {"error": "Not enough valid training samples"}
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train Gradient Boosting model
            self.gb_model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            self.gb_model.fit(X_train_scaled, y_train)
            gb_score = self.gb_model.score(X_test_scaled, y_test)
            
            # Train Random Forest model
            self.rf_model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            self.rf_model.fit(X_train_scaled, y_train)
            rf_score = self.rf_model.score(X_test_scaled, y_test)
            
            self.is_trained = True
            self._save_model()
            
            # Store training metadata
            await self.db.ml_models.update_one(
                {"model_name": "volatility_predictor"},
                {"$set": {
                    "model_name": "volatility_predictor",
                    "gb_r2_score": float(gb_score),
                    "rf_r2_score": float(rf_score),
                    "training_samples": len(X_train),
                    "test_samples": len(X_test),
                    "features": ["price_std", "price_range", "volume_avg", "liquidity_avg", "price_momentum", "return_std"],
                    "trained_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            
            logger.info(f"Volatility model trained. GB R2: {gb_score:.4f}, RF R2: {rf_score:.4f}")
            
            return {
                "status": "trained",
                "gb_r2_score": float(gb_score),
                "rf_r2_score": float(rf_score),
                "training_samples": len(X_train),
                "test_samples": len(X_test)
            }
            
        except Exception as e:
            logger.error(f"Error training volatility model: {e}")
            return {"error": str(e)}
    
    def _prepare_training_data(self, docs: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features and labels from historical data"""
        # Group by market
        market_data = {}
        for doc in docs:
            market_id = doc.get('market_id')
            if market_id not in market_data:
                market_data[market_id] = []
            market_data[market_id].append(doc)
        
        X = []
        y = []
        
        for market_id, data in market_data.items():
            if len(data) < self.lookback_period + self.prediction_horizon:
                continue
            
            prices = [d.get('yes_price', 0.5) for d in data]
            volumes = [d.get('volume', 0) for d in data]
            liquidities = [d.get('liquidity', 0) for d in data]
            
            # Create sliding window samples
            for i in range(self.lookback_period, len(data) - self.prediction_horizon):
                # Features from lookback period
                window_prices = prices[i-self.lookback_period:i]
                window_volumes = volumes[i-self.lookback_period:i]
                window_liquidities = liquidities[i-self.lookback_period:i]
                
                # Calculate features
                features = self._extract_features(window_prices, window_volumes, window_liquidities)
                
                # Label: future volatility (std of returns in prediction horizon)
                future_prices = prices[i:i+self.prediction_horizon]
                if len(future_prices) > 1:
                    returns = np.diff(future_prices) / np.array(future_prices[:-1])
                    future_vol = np.std(returns) if len(returns) > 0 else 0
                else:
                    future_vol = 0
                
                X.append(features)
                y.append(future_vol)
        
        return np.array(X), np.array(y)
    
    def _extract_features(self, prices: List[float], volumes: List[float], liquidities: List[float]) -> List[float]:
        """Extract features from window data"""
        prices = np.array(prices)
        volumes = np.array(volumes)
        liquidities = np.array(liquidities)
        
        # Price features
        price_std = np.std(prices) if len(prices) > 1 else 0
        price_range = np.max(prices) - np.min(prices) if len(prices) > 0 else 0
        price_momentum = (prices[-1] - prices[0]) / prices[0] if prices[0] > 0 else 0
        
        # Volume features
        volume_avg = np.mean(volumes)
        
        # Liquidity features
        liquidity_avg = np.mean(liquidities)
        
        # Return features
        if len(prices) > 1:
            returns = np.diff(prices) / prices[:-1]
            return_std = np.std(returns) if len(returns) > 0 else 0
        else:
            return_std = 0
        
        return [price_std, price_range, volume_avg, liquidity_avg, price_momentum, return_std]
    
    async def predict_volatility(self, market_id: str) -> Tuple[float, float]:
        """Predict volatility for next 5-15 minutes"""
        try:
            if not self.is_trained:
                # Fallback to heuristic if not trained
                return await self._heuristic_predict(market_id)
            
            # Get recent data
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "volume": 1, "liquidity": 1, "_id": 0}
            ).sort("timestamp", -1).limit(self.lookback_period)
            
            docs = await cursor.to_list(length=self.lookback_period)
            
            if len(docs) < self.lookback_period // 2:
                return 0.5, 0.3
            
            # Reverse to chronological order
            docs = list(reversed(docs))
            
            prices = [d.get('yes_price', 0.5) for d in docs]
            volumes = [d.get('volume', 0) for d in docs]
            liquidities = [d.get('liquidity', 0) for d in docs]
            
            # Extract features
            features = self._extract_features(prices, volumes, liquidities)
            features_scaled = self.scaler.transform([features])
            
            # Ensemble prediction
            gb_pred = self.gb_model.predict(features_scaled)[0]
            rf_pred = self.rf_model.predict(features_scaled)[0]
            
            # Average predictions
            ensemble_pred = (gb_pred + rf_pred) / 2
            
            # Normalize to 0-1 range
            volatility_score = min(max(ensemble_pred * 10, 0.0), 1.0)
            
            # Confidence based on model agreement
            agreement = 1.0 - abs(gb_pred - rf_pred) / (max(gb_pred, rf_pred) + 1e-6)
            confidence = min(max(agreement, 0.0), 1.0)
            
            await self._store_prediction(market_id, volatility_score, confidence)
            
            return volatility_score, confidence
            
        except Exception as e:
            logger.error(f"Error predicting volatility: {e}")
            return 0.5, 0.0
    
    async def _heuristic_predict(self, market_id: str) -> Tuple[float, float]:
        """Fallback heuristic prediction"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "_id": 0}
            ).sort("timestamp", -1).limit(self.lookback_period)
            
            docs = await cursor.to_list(length=self.lookback_period)
            
            if len(docs) < 5:
                return 0.5, 0.3
            
            prices = [d.get('yes_price', 0.5) for d in docs]
            
            returns = np.diff(prices) / np.array(prices[:-1])
            volatility = np.std(returns) * np.sqrt(self.prediction_horizon)
            
            return min(max(volatility * 10, 0.0), 1.0), 0.5
            
        except Exception as e:
            logger.error(f"Error in heuristic prediction: {e}")
            return 0.5, 0.3
    
    def _save_model(self):
        """Save trained models to disk"""
        try:
            joblib.dump(self.gb_model, f"{MODEL_DIR}/volatility_gb.joblib")
            joblib.dump(self.rf_model, f"{MODEL_DIR}/volatility_rf.joblib")
            joblib.dump(self.scaler, f"{MODEL_DIR}/volatility_scaler.joblib")
            logger.info("Volatility models saved")
        except Exception as e:
            logger.error(f"Error saving volatility model: {e}")
    
    def _load_model(self):
        """Load trained models from disk"""
        try:
            gb_path = f"{MODEL_DIR}/volatility_gb.joblib"
            rf_path = f"{MODEL_DIR}/volatility_rf.joblib"
            scaler_path = f"{MODEL_DIR}/volatility_scaler.joblib"
            
            if os.path.exists(gb_path) and os.path.exists(rf_path):
                self.gb_model = joblib.load(gb_path)
                self.rf_model = joblib.load(rf_path)
                self.scaler = joblib.load(scaler_path)
                self.is_trained = True
                logger.info("Volatility models loaded from disk")
        except Exception as e:
            logger.error(f"Error loading volatility model: {e}")
    
    async def _store_prediction(self, market_id: str, prediction: float, confidence: float):
        """Store volatility prediction"""
        try:
            await self.db.signals.insert_one({
                "id": f"vol_{market_id}_{int(datetime.now(timezone.utc).timestamp())}",
                "market_id": market_id,
                "signal_type": "volatility",
                "confidence": confidence,
                "source": "ml_ensemble" if self.is_trained else "heuristic",
                "value": prediction,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing prediction: {e}")
    
    async def get_model_stats(self) -> Dict:
        """Get model training statistics"""
        try:
            stats = await self.db.ml_models.find_one(
                {"model_name": "volatility_predictor"},
                {"_id": 0}
            )
            return stats or {"status": "not_trained"}
        except Exception as e:
            logger.error(f"Error getting model stats: {e}")
            return {"error": str(e)}
