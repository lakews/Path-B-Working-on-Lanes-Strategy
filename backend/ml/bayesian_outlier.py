import numpy as np
import logging
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
from database import get_db
from sklearn.ensemble import IsolationForest, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib

logger = logging.getLogger(__name__)

MODEL_DIR = "/app/backend/ml/models"
os.makedirs(MODEL_DIR, exist_ok=True)

class BayesianOutlierDetector:
    """Trainable mispricing detection using Isolation Forest + Gradient Boosting"""
    
    def __init__(self):
        self.db = get_db()
        self.prior_mispricing = 0.15
        self.min_liquidity = 1000
        self.min_volume = 500
        
        # ML models
        self.isolation_forest: Optional[IsolationForest] = None
        self.gb_classifier: Optional[GradientBoostingClassifier] = None
        self.scaler = StandardScaler()
        self.is_trained = False
        
        self._load_model()
    
    async def train_model(self, min_samples: int = 500) -> Dict:
        """Train mispricing detection model on historical data"""
        try:
            logger.info("Starting mispricing detection model training...")
            
            # Get historical data
            cursor = self.db.historical_data.find(
                {},
                {"market_id": 1, "yes_price": 1, "no_price": 1, "volume": 1, "liquidity": 1, "timestamp": 1, "_id": 0}
            ).sort("timestamp", 1).limit(100000)
            
            docs = await cursor.to_list(length=100000)
            
            if len(docs) < min_samples:
                return {"error": f"Not enough data. Need {min_samples}, have {len(docs)}"}
            
            # Prepare features
            X, y = self._prepare_training_data(docs)
            
            if len(X) < 100:
                return {"error": "Not enough valid training samples"}
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train Isolation Forest for anomaly detection
            self.isolation_forest = IsolationForest(
                n_estimators=100,
                contamination=0.1,
                random_state=42,
                n_jobs=-1
            )
            self.isolation_forest.fit(X_scaled)
            
            # Train Gradient Boosting for classification (if we have labels)
            if len(y) > 0 and sum(y) > 10:
                X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
                
                self.gb_classifier = GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.1,
                    random_state=42
                )
                self.gb_classifier.fit(X_train, y_train)
                gb_score = self.gb_classifier.score(X_test, y_test)
            else:
                gb_score = 0.0
            
            self.is_trained = True
            self._save_model()
            
            # Store training metadata
            await self.db.ml_models.update_one(
                {"model_name": "bayesian_outlier"},
                {"$set": {
                    "model_name": "bayesian_outlier",
                    "isolation_forest_trained": True,
                    "gb_accuracy": float(gb_score),
                    "training_samples": len(X),
                    "features": ["price_deviation", "volume_zscore", "liquidity_zscore", "spread", "price_velocity"],
                    "trained_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            
            logger.info(f"Mispricing model trained. GB Accuracy: {gb_score:.4f}")
            
            return {
                "status": "trained",
                "isolation_forest": True,
                "gb_accuracy": float(gb_score),
                "training_samples": len(X)
            }
            
        except Exception as e:
            logger.error(f"Error training mispricing model: {e}")
            return {"error": str(e)}
    
    def _prepare_training_data(self, docs: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features for mispricing detection"""
        # Group by market
        market_data = {}
        for doc in docs:
            market_id = doc.get('market_id')
            if market_id not in market_data:
                market_data[market_id] = []
            market_data[market_id].append(doc)
        
        X = []
        y = []
        
        # Calculate global statistics for normalization
        all_volumes = [d.get('volume', 0) for d in docs]
        all_liquidities = [d.get('liquidity', 0) for d in docs]
        vol_mean, vol_std = np.mean(all_volumes), np.std(all_volumes) + 1e-6
        liq_mean, liq_std = np.mean(all_liquidities), np.std(all_liquidities) + 1e-6
        
        for market_id, data in market_data.items():
            if len(data) < 10:
                continue
            
            prices = [d.get('yes_price', 0.5) for d in data]
            no_prices = [d.get('no_price', 0.5) for d in data]
            volumes = [d.get('volume', 0) for d in data]
            liquidities = [d.get('liquidity', 0) for d in data]
            
            # Create samples
            for i in range(5, len(data)):
                window_prices = prices[i-5:i]
                current_price = prices[i]
                current_volume = volumes[i]
                current_liquidity = liquidities[i]
                current_no_price = no_prices[i]
                
                # Features
                avg_price = np.mean(window_prices)
                price_deviation = abs(current_price - avg_price) / (avg_price + 1e-6)
                volume_zscore = (current_volume - vol_mean) / vol_std
                liquidity_zscore = (current_liquidity - liq_mean) / liq_std
                spread = abs(current_price + current_no_price - 1.0)
                price_velocity = (current_price - window_prices[0]) / (len(window_prices) + 1e-6)
                
                features = [price_deviation, volume_zscore, liquidity_zscore, spread, price_velocity]
                X.append(features)
                
                # Label: 1 if price deviation is high AND market characteristics suggest mispricing
                is_mispriced = 1 if (price_deviation > 0.15 and spread > 0.02) else 0
                y.append(is_mispriced)
        
        return np.array(X), np.array(y)
    
    async def detect_mispricing(self, market_data: Dict) -> Tuple[bool, float, float]:
        """Detect if market is mispriced"""
        try:
            market_id = market_data.get('id')
            current_price = market_data.get('yes_price', 0.5)
            volume = market_data.get('volume', 0)
            liquidity = market_data.get('liquidity', 0)
            
            if liquidity < self.min_liquidity or volume < self.min_volume:
                return False, 0.0, current_price
            
            historical_prices = await self._get_price_history(market_id)
            
            if self.is_trained and len(historical_prices) >= 5:
                return await self._ml_detect(market_data, historical_prices)
            else:
                return await self._heuristic_detect(market_data, historical_prices)
            
        except Exception as e:
            logger.error(f"Error detecting mispricing: {e}")
            return False, 0.0, 0.5
    
    async def _ml_detect(self, market_data: Dict, historical_prices: List[float]) -> Tuple[bool, float, float]:
        """ML-based mispricing detection"""
        try:
            current_price = market_data.get('yes_price', 0.5)
            no_price = market_data.get('no_price', 0.5)
            volume = market_data.get('volume', 0)
            liquidity = market_data.get('liquidity', 0)
            
            # Calculate features
            avg_price = np.mean(historical_prices[-5:])
            price_deviation = abs(current_price - avg_price) / (avg_price + 1e-6)
            volume_zscore = (volume - 5000) / 10000  # Rough normalization
            liquidity_zscore = (liquidity - 25000) / 50000
            spread = abs(current_price + no_price - 1.0)
            price_velocity = (current_price - historical_prices[-5]) / 5 if len(historical_prices) >= 5 else 0
            
            features = np.array([[price_deviation, volume_zscore, liquidity_zscore, spread, price_velocity]])
            features_scaled = self.scaler.transform(features)
            
            # Isolation Forest anomaly score
            anomaly_score = -self.isolation_forest.decision_function(features_scaled)[0]
            is_anomaly = anomaly_score > 0.5
            
            # GB classifier probability
            if self.gb_classifier is not None:
                gb_prob = self.gb_classifier.predict_proba(features_scaled)[0][1]
            else:
                gb_prob = 0.5
            
            # Combine scores
            combined_confidence = (anomaly_score * 0.4 + gb_prob * 0.6)
            combined_confidence = min(max(combined_confidence, 0.0), 1.0)
            
            # Estimate fair value
            fair_value = self._estimate_fair_value(market_data, historical_prices)
            
            is_mispriced = combined_confidence > 0.7 and abs(current_price - fair_value) > 0.1
            
            if is_mispriced:
                await self._store_signal(market_data.get('id'), combined_confidence, fair_value)
            
            return is_mispriced, combined_confidence, fair_value
            
        except Exception as e:
            logger.error(f"Error in ML mispricing detection: {e}")
            return False, 0.0, market_data.get('yes_price', 0.5)
    
    async def _heuristic_detect(self, market_data: Dict, historical_prices: List[float]) -> Tuple[bool, float, float]:
        """Fallback heuristic detection"""
        current_price = market_data.get('yes_price', 0.5)
        volume = market_data.get('volume', 0)
        liquidity = market_data.get('liquidity', 0)
        
        fair_value = self._estimate_fair_value(market_data, historical_prices)
        price_deviation = abs(current_price - fair_value)
        
        likelihood = self._calculate_likelihood(price_deviation, volume, liquidity)
        posterior = self._bayesian_update(likelihood)
        
        is_mispriced = posterior > 0.7 and price_deviation > 0.1
        
        if is_mispriced:
            await self._store_signal(market_data.get('id'), posterior, fair_value)
        
        return is_mispriced, posterior, fair_value
    
    def _estimate_fair_value(self, market_data: Dict, historical_prices: list) -> float:
        """Estimate fair value using multiple methods"""
        current_price = market_data.get('yes_price', 0.5)
        
        if len(historical_prices) < 5:
            return current_price
        
        moving_avg = np.mean(historical_prices[-10:])
        volume = market_data.get('volume', 0)
        liquidity = market_data.get('liquidity', 1)
        volume_weight = min(volume / (liquidity + 1), 1.0)
        
        fair_value = (moving_avg * 0.6) + (current_price * 0.4 * volume_weight)
        return min(max(fair_value, 0.01), 0.99)
    
    def _calculate_likelihood(self, price_deviation: float, volume: float, liquidity: float) -> float:
        """Calculate likelihood of mispricing"""
        deviation_factor = min(price_deviation / 0.3, 1.0)
        volume_factor = min(volume / 10000, 1.0)
        liquidity_factor = min(liquidity / 50000, 1.0)
        
        likelihood = (deviation_factor * 0.6) + (1 - volume_factor) * 0.2 + (1 - liquidity_factor) * 0.2
        return min(max(likelihood, 0.0), 1.0)
    
    def _bayesian_update(self, likelihood: float) -> float:
        """Update posterior probability using Bayes theorem"""
        prior = self.prior_mispricing
        posterior = (likelihood * prior) / ((likelihood * prior) + ((1 - likelihood) * (1 - prior)))
        return min(max(posterior, 0.0), 1.0)
    
    async def _get_price_history(self, market_id: str) -> list:
        """Get recent price history"""
        try:
            cursor = self.db.historical_data.find(
                {"market_id": market_id},
                {"yes_price": 1, "_id": 0}
            ).sort("timestamp", -1).limit(50)
            
            docs = await cursor.to_list(length=50)
            return [doc['yes_price'] for doc in reversed(docs) if 'yes_price' in doc]
        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []
    
    async def _store_signal(self, market_id: str, confidence: float, fair_value: float):
        """Store mispricing signal"""
        try:
            import uuid
            await self.db.signals.insert_one({
                "id": str(uuid.uuid4()),
                "market_id": market_id,
                "signal_type": "mispricing",
                "confidence": confidence,
                "source": "ml_ensemble" if self.is_trained else "bayesian_heuristic",
                "value": fair_value,
                "metadata": {"detection_method": "ml" if self.is_trained else "bayesian"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing mispricing signal: {e}")
    
    def _save_model(self):
        """Save trained models to disk"""
        try:
            joblib.dump(self.isolation_forest, f"{MODEL_DIR}/mispricing_iso.joblib")
            if self.gb_classifier:
                joblib.dump(self.gb_classifier, f"{MODEL_DIR}/mispricing_gb.joblib")
            joblib.dump(self.scaler, f"{MODEL_DIR}/mispricing_scaler.joblib")
            logger.info("Mispricing models saved")
        except Exception as e:
            logger.error(f"Error saving mispricing model: {e}")
    
    def _load_model(self):
        """Load trained models from disk"""
        try:
            iso_path = f"{MODEL_DIR}/mispricing_iso.joblib"
            scaler_path = f"{MODEL_DIR}/mispricing_scaler.joblib"
            
            if os.path.exists(iso_path):
                self.isolation_forest = joblib.load(iso_path)
                self.scaler = joblib.load(scaler_path)
                
                gb_path = f"{MODEL_DIR}/mispricing_gb.joblib"
                if os.path.exists(gb_path):
                    self.gb_classifier = joblib.load(gb_path)
                
                self.is_trained = True
                logger.info("Mispricing models loaded from disk")
        except Exception as e:
            logger.error(f"Error loading mispricing model: {e}")
    
    async def get_model_stats(self) -> Dict:
        """Get model training statistics"""
        try:
            stats = await self.db.ml_models.find_one(
                {"model_name": "bayesian_outlier"},
                {"_id": 0}
            )
            return stats or {"status": "not_trained"}
        except Exception as e:
            return {"error": str(e)}
