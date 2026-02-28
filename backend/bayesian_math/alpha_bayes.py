"""
ALPHA BAYESIAN FUSION
=====================

QUARANTINE: This module is ONLY for the ALPHA lane.
DO NOT import into HFT, Sports, Gamma, or News lanes.

Purpose: Fuse multiple weak signals (sentiment, sharp alignment, mispricing)
into a single posterior probability using Bayesian inference.

Math: Log-Bayesian fusion with configurable priors.
"""

import logging
import math
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AlphaPosterior:
    """Result of Alpha Bayesian fusion"""
    posterior: float          # P(profitable | all signals)
    confidence: float         # How confident we are (0-1)
    signal_strength: str      # 'strong', 'moderate', 'weak', 'neutral'
    dominant_signal: str      # Which signal contributed most
    log_odds: float          # Log-odds for debugging
    
    def to_dict(self) -> Dict:
        return {
            'posterior': round(self.posterior, 4),
            'confidence': round(self.confidence, 4),
            'signal_strength': self.signal_strength,
            'dominant_signal': self.dominant_signal,
            'log_odds': round(self.log_odds, 4)
        }


class AlphaBayesianFusion:
    """
    Bayesian fusion for Alpha lane signals.
    
    Combines:
    - Sentiment (LLM-based)
    - Sharp alignment (Order flow)
    - Mispricing detection (Statistical)
    
    Uses log-odds space for numerical stability.
    """
    
    # Default priors (can be calibrated from historical performance)
    DEFAULT_PRIORS = {
        'base_profitable': 0.45,      # Base rate of profitable trades
        'sentiment_reliability': 0.60, # How often sentiment is correct
        'sharp_reliability': 0.65,     # How often sharp money is correct
        'mispricing_reliability': 0.70 # How often mispricing signals are correct
    }
    
    # Signal weights (sum to 1.0)
    DEFAULT_WEIGHTS = {
        'sentiment': 0.35,
        'sharp_alignment': 0.40,
        'mispricing': 0.25
    }
    
    def __init__(
        self,
        priors: Optional[Dict[str, float]] = None,
        weights: Optional[Dict[str, float]] = None
    ):
        self.priors = priors or self.DEFAULT_PRIORS.copy()
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        
        # Validate weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.01:
            logger.warning(f"Alpha Bayes weights sum to {weight_sum}, normalizing...")
            for k in self.weights:
                self.weights[k] /= weight_sum
    
    def _prob_to_log_odds(self, p: float) -> float:
        """Convert probability to log-odds (logit)"""
        p = max(0.001, min(0.999, p))  # Clamp to avoid log(0)
        return math.log(p / (1 - p))
    
    def _log_odds_to_prob(self, lo: float) -> float:
        """Convert log-odds back to probability (sigmoid)"""
        lo = max(-10, min(10, lo))  # Clamp to avoid overflow
        return 1 / (1 + math.exp(-lo))
    
    def _calculate_likelihood_ratio(
        self,
        signal_value: float,
        reliability: float
    ) -> float:
        """
        Calculate likelihood ratio for a signal.
        
        If signal > 0.5 (bullish): LR > 1 (supports YES)
        If signal < 0.5 (bearish): LR < 1 (supports NO)
        If signal = 0.5 (neutral): LR = 1 (no update)
        
        The reliability determines how strongly the signal updates our belief.
        """
        # Deviation from neutral (0.5)
        deviation = signal_value - 0.5
        
        if abs(deviation) < 0.01:
            return 1.0  # Neutral signal, no update
        
        # Scale deviation by reliability
        # Higher reliability = stronger update
        scaled_deviation = deviation * reliability * 2
        
        # Convert to likelihood ratio
        # LR = P(signal | profitable) / P(signal | not profitable)
        lr = math.exp(scaled_deviation * 2)
        
        return lr
    
    def fuse(
        self,
        sentiment: float = 0.5,
        sharp_alignment: float = 0.5,
        mispricing: float = 0.0,
        mispricing_direction: str = 'neutral'
    ) -> AlphaPosterior:
        """
        Fuse multiple signals into a single posterior.
        
        Args:
            sentiment: 0-1, where > 0.5 is bullish
            sharp_alignment: 0-1, where > 0.5 indicates smart money buying
            mispricing: 0-1, confidence that market is mispriced
            mispricing_direction: 'underpriced' (buy YES), 'overpriced' (buy NO), 'neutral'
        
        Returns:
            AlphaPosterior with fused result
        """
        # Start with prior in log-odds space
        prior_prob = self.priors['base_profitable']
        log_odds = self._prob_to_log_odds(prior_prob)
        
        # Track contributions for debugging
        contributions = {}
        
        # Update with sentiment
        lr_sentiment = self._calculate_likelihood_ratio(
            sentiment,
            self.priors['sentiment_reliability']
        )
        log_odds += math.log(lr_sentiment) * self.weights['sentiment']
        contributions['sentiment'] = math.log(lr_sentiment) * self.weights['sentiment']
        
        # Update with sharp alignment
        lr_sharp = self._calculate_likelihood_ratio(
            sharp_alignment,
            self.priors['sharp_reliability']
        )
        log_odds += math.log(lr_sharp) * self.weights['sharp_alignment']
        contributions['sharp_alignment'] = math.log(lr_sharp) * self.weights['sharp_alignment']
        
        # Update with mispricing (if detected)
        if mispricing > 0.1:
            # Convert mispricing to directional signal
            if mispricing_direction == 'underpriced':
                mispricing_signal = 0.5 + (mispricing * 0.5)  # > 0.5 = buy YES
            elif mispricing_direction == 'overpriced':
                mispricing_signal = 0.5 - (mispricing * 0.5)  # < 0.5 = buy NO
            else:
                mispricing_signal = 0.5
            
            lr_mispricing = self._calculate_likelihood_ratio(
                mispricing_signal,
                self.priors['mispricing_reliability']
            )
            log_odds += math.log(lr_mispricing) * self.weights['mispricing']
            contributions['mispricing'] = math.log(lr_mispricing) * self.weights['mispricing']
        else:
            contributions['mispricing'] = 0.0
        
        # Convert back to probability
        posterior = self._log_odds_to_prob(log_odds)
        
        # Calculate confidence (how far from 0.5)
        confidence = abs(posterior - 0.5) * 2
        
        # Determine signal strength
        if confidence > 0.6:
            signal_strength = 'strong'
        elif confidence > 0.3:
            signal_strength = 'moderate'
        elif confidence > 0.1:
            signal_strength = 'weak'
        else:
            signal_strength = 'neutral'
        
        # Find dominant signal
        dominant_signal = max(contributions, key=lambda k: abs(contributions[k]))
        
        return AlphaPosterior(
            posterior=posterior,
            confidence=confidence,
            signal_strength=signal_strength,
            dominant_signal=dominant_signal,
            log_odds=log_odds
        )
    
    def update_priors(self, trade_results: Dict[str, float]):
        """
        Update priors based on observed trade performance.
        Call this periodically with aggregated results.
        
        Args:
            trade_results: Dict with keys like 'win_rate', 'sentiment_accuracy', etc.
        """
        if 'win_rate' in trade_results:
            # Exponential moving average update
            alpha = 0.1  # Learning rate
            self.priors['base_profitable'] = (
                (1 - alpha) * self.priors['base_profitable'] +
                alpha * trade_results['win_rate']
            )
        
        # Similar updates for other priors can be added
        logger.info(f"[ALPHA BAYES] Updated priors: {self.priors}")


# Singleton instance
_alpha_bayes: Optional[AlphaBayesianFusion] = None


def get_alpha_bayes() -> AlphaBayesianFusion:
    """Get or create the Alpha Bayesian fusion instance"""
    global _alpha_bayes
    if _alpha_bayes is None:
        _alpha_bayes = AlphaBayesianFusion()
    return _alpha_bayes
