import logging
from typing import Dict, Tuple
from datetime import datetime, timezone
import numpy as np
from database import get_db
from ml.volatility_predictor import VolatilityPredictor
from ml.sentiment_analyzer import SentimentAnalyzer
from ml.bayesian_outlier import BayesianOutlierDetector
from ml.sharp_detector import SharpDetector
import uuid

logger = logging.getLogger(__name__)

class SignalFusionEngine:
    """Fuses signals from all AI modules using Bayesian inference"""
    
    def __init__(self, backtest_mode: bool = False):
        self.db = get_db()
        self.backtest_mode = backtest_mode
        self.volatility_predictor = VolatilityPredictor()
        self.bayesian_outlier = BayesianOutlierDetector()
        self.sharp_detector = SharpDetector()
        
        # Only init sentiment analyzer if not in backtest mode (LLM calls are slow)
        if not backtest_mode:
            self.sentiment_analyzer = SentimentAnalyzer()
        else:
            self.sentiment_analyzer = None
        
        self.weights = {
            'sentiment': 0.30,
            'volatility': 0.25,
            'mispricing': 0.25,
            'sharp_alignment': 0.20
        }
    
    async def generate_trading_signal(
        self, 
        market_data: Dict,
        proposed_side: str = "BUY"
    ) -> Dict[str, float]:
        """Generate fused trading signal from all AI modules
        Returns: {
            'confidence': float,
            'recommended_action': str,
            'position_direction': str,
            'signals': dict
        }
        """
        try:
            market_id = market_data.get('id')
            
            volatility, vol_conf = await self.volatility_predictor.predict_volatility(market_id)
            
            # Skip LLM sentiment in backtest mode for speed
            if self.backtest_mode or self.sentiment_analyzer is None:
                sentiment, sent_conf = self._heuristic_sentiment(market_data)
            else:
                sentiment, sent_conf = await self.sentiment_analyzer.analyze_sentiment(market_data)
            
            is_mispriced, misp_conf, fair_value = await self.bayesian_outlier.detect_mispricing(market_data)
            
            sharp_alignment = await self.sharp_detector.get_sharp_alignment(market_id, proposed_side)
            
            signals = {
                'sentiment': sentiment,
                'sentiment_confidence': sent_conf,
                'volatility': volatility,
                'volatility_confidence': vol_conf,
                'mispricing': misp_conf,
                'fair_value': fair_value,
                'sharp_alignment': sharp_alignment
            }
            
            bayesian_posterior = self._calculate_bayesian_posterior(signals)
            
            fused_confidence = self._calculate_fused_confidence(signals)
            
            action, direction = self._determine_action(
                market_data, 
                signals, 
                bayesian_posterior,
                fused_confidence
            )
            
            result = {
                'confidence': fused_confidence,
                'bayesian_posterior': bayesian_posterior,
                'recommended_action': action,
                'position_direction': direction,
                'signals': signals,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            await self._store_fused_signal(market_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating trading signal: {e}")
            return {
                'confidence': 0.0,
                'recommended_action': 'WAIT',
                'position_direction': 'NONE',
                'signals': {}
            }
    
    def _calculate_bayesian_posterior(self, signals: Dict) -> float:
        """Calculate Bayesian posterior probability"""
        try:
            sentiment = signals.get('sentiment', 0.5)
            sharp_align = signals.get('sharp_alignment', 0.5)
            mispricing_conf = signals.get('mispricing', 0.0)
            
            posterior = sentiment * sharp_align
            
            if mispricing_conf > 0.7:
                posterior *= 1.3
            
            return min(max(posterior, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating Bayesian posterior: {e}")
            return 0.5
    
    def _calculate_fused_confidence(self, signals: Dict) -> float:
        """Calculate weighted confidence score"""
        try:
            sent_score = signals.get('sentiment', 0.5) * signals.get('sentiment_confidence', 0)
            vol_score = (1 - signals.get('volatility', 0.5)) * signals.get('volatility_confidence', 0)
            misp_score = signals.get('mispricing', 0)
            sharp_score = signals.get('sharp_alignment', 0.5)
            
            weighted_confidence = (
                sent_score * self.weights['sentiment'] +
                vol_score * self.weights['volatility'] +
                misp_score * self.weights['mispricing'] +
                sharp_score * self.weights['sharp_alignment']
            )
            
            return min(max(weighted_confidence, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating fused confidence: {e}")
            return 0.0
    
    def _determine_action(
        self, 
        market_data: Dict, 
        signals: Dict, 
        posterior: float,
        confidence: float
    ) -> Tuple[str, str]:
        """Determine trading action and direction"""
        try:
            # STRICT PRICE VALIDATION - Cannot determine action without price
            current_price = market_data.get('yes_price')
            if current_price is None or current_price == 0:
                logger.warning("[SIGNAL-FUSION-REJECT] Missing price for action determination")
                return 'WAIT', 'NONE'
            current_price = float(current_price)
            
            fair_value = signals.get('fair_value', 0.5)
            sentiment = signals.get('sentiment', 0.5)
            volatility = signals.get('volatility', 0.5)
            
            if confidence < 0.3:
                return 'WAIT', 'NONE'
            
            if confidence > 0.7 and posterior > 0.7:
                if current_price < fair_value - 0.1:
                    return 'BUY', 'YES'
                elif current_price > fair_value + 0.1:
                    return 'SELL', 'YES'
            
            if volatility > 0.7 and current_price < 0.10:
                return 'BUY', 'YES'
            
            if sentiment > 0.65 and current_price < 0.50:
                return 'BUY', 'YES'
            elif sentiment < 0.35 and current_price > 0.50:
                return 'SELL', 'YES'
            
            return 'WAIT', 'NONE'
            
        except Exception as e:
            logger.error(f"Error determining action: {e}")
            return 'WAIT', 'NONE'
    
    def _heuristic_sentiment(self, market_data: Dict) -> Tuple[float, float]:
        """Fast heuristic sentiment for backtesting (no LLM calls)"""
        try:
            # STRICT VALIDATION - Return low confidence if no price data
            yes_price = market_data.get('yes_price')
            if yes_price is None or yes_price == 0:
                return 0.5, 0.0  # Neutral sentiment, zero confidence
            
            yes_price = float(yes_price)
            no_price = market_data.get('no_price')
            no_price = float(no_price) if no_price is not None and no_price != 0 else (1 - yes_price)
            volume = market_data.get('volume', 0)
            
            # Price-based sentiment
            sentiment = yes_price  # Market's implied probability
            
            # Volume-adjusted confidence
            confidence = min(volume / 10000, 0.8) if volume > 0 else 0.3
            
            return sentiment, confidence
        except Exception as e:
            logger.error(f"Error in heuristic sentiment: {e}")
            return 0.5, 0.3
    
    async def _store_fused_signal(self, market_id: str, result: Dict):
        """Store fused signal in database"""
        try:
            await self.db.signals.insert_one({
                "id": str(uuid.uuid4()),
                "market_id": market_id,
                "signal_type": "fused",
                "confidence": result['confidence'],
                "source": "signal_fusion_engine",
                "value": result['bayesian_posterior'],
                "metadata": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing fused signal: {e}")