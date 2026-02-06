"""
POSITION SIZER UTILITIES
========================

Stateless math functions for position sizing across all 5 lanes.
These are pure functions with no state - all parameters are passed in.

Usage:
    from utils.position_sizer import PositionSizer
    
    size = PositionSizer.calculate_kelly_size(
        edge=0.05,
        odds=0.60,
        capital=10000,
        kelly_fraction=0.25
    )
"""

import math
import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SizingResult:
    """Result of a position sizing calculation"""
    size: float
    method: str
    raw_kelly: float
    adjusted_kelly: float
    confidence_factor: float
    liquidity_factor: float
    utilization_factor: float
    reason: str
    
    def to_dict(self) -> Dict:
        return {
            'size': round(self.size, 2),
            'method': self.method,
            'raw_kelly': round(self.raw_kelly, 4),
            'adjusted_kelly': round(self.adjusted_kelly, 4),
            'confidence_factor': round(self.confidence_factor, 4),
            'liquidity_factor': round(self.liquidity_factor, 4),
            'utilization_factor': round(self.utilization_factor, 4),
            'reason': self.reason
        }


class PositionSizer:
    """
    Stateless position sizing calculator.
    
    All methods are static - no instance state required.
    Configuration parameters are passed in from the RiskManager.
    """
    
    # ========================================
    # LANE 1: HFT - Fixed Unit Sizing
    # ========================================
    
    @staticmethod
    def calculate_hft_size(
        capital: float,
        max_pos_pct: float = 0.02,
        max_pos_usd: float = 50.0,
        min_size: float = 5.0
    ) -> SizingResult:
        """
        Calculate HFT position size using fixed unit method.
        
        HFT uses simple, fast sizing:
        - Fixed percentage of capital (default 2%)
        - Hard USD cap (default $50)
        - No Kelly, no complexity
        
        Args:
            capital: Deployed capital
            max_pos_pct: Max position as % of capital
            max_pos_usd: Hard USD cap
            min_size: Minimum position size
            
        Returns:
            SizingResult with calculated size
        """
        # Fixed unit: percentage of capital
        raw_size = capital * max_pos_pct
        
        # Apply USD cap
        size = min(raw_size, max_pos_usd)
        
        # Apply floor
        size = max(size, min_size)
        
        return SizingResult(
            size=size,
            method='fixed_unit',
            raw_kelly=0.0,
            adjusted_kelly=0.0,
            confidence_factor=1.0,
            liquidity_factor=1.0,
            utilization_factor=1.0,
            reason=f"HFT fixed: {max_pos_pct*100:.0f}% of capital, capped at ${max_pos_usd:.0f}"
        )
    
    # ========================================
    # LANE 2: ALPHA - Binary Kelly Criterion
    # ========================================
    
    @staticmethod
    def calculate_kelly_size(
        edge: float,
        market_price: float,
        capital: float,
        kelly_config: Dict,
        confidence: float = 1.0,
        liquidity: float = 100000.0,
        current_utilization: float = 0.0,
        max_pos_usd: float = 100.0,
        min_size: float = 5.0
    ) -> SizingResult:
        """
        Calculate position size using Binary Kelly Criterion.
        
        Kelly Formula (for binary outcomes):
            f* = (p - q) / q = edge / (1 - p)
            
        Where:
            p = model probability (fair value)
            q = 1 - p
            edge = p - market_price
            
        Adjustments:
            1. Fractional Kelly (default 25%)
            2. Kelly bounds (10%-50%)
            3. Utilization brake
            4. Liquidity scalar
            5. Confidence factor
        
        Args:
            edge: Model edge (model_prob - market_price)
            market_price: Current market price
            capital: Deployed capital
            kelly_config: Kelly configuration dict
            confidence: Model confidence (0-1)
            liquidity: Market liquidity in USD
            current_utilization: Current capital utilization (0-1)
            max_pos_usd: Hard USD cap
            min_size: Minimum position size
            
        Returns:
            SizingResult with calculated size
        """
        # Extract kelly params with defaults
        scaling_factor = kelly_config.get('scaling_factor', 0.25)
        min_fraction = kelly_config.get('min_fraction', 0.10)
        max_fraction = kelly_config.get('max_fraction', 0.50)
        util_exponent = kelly_config.get('utilization_exponent', 1.5)
        util_hard_stop = kelly_config.get('utilization_hard_stop', 0.95)
        
        # Calculate raw Kelly fraction
        # For binary markets: f* = edge / (1 - model_prob)
        # model_prob = market_price + edge
        model_prob = market_price + edge
        model_prob = max(0.01, min(0.99, model_prob))  # Clamp
        
        if model_prob >= 0.99:
            raw_kelly = 0.0  # No edge at extremes
        else:
            raw_kelly = edge / (1 - model_prob)
        
        # Handle negative edge (should have been caught earlier)
        if raw_kelly <= 0:
            return SizingResult(
                size=0.0,
                method='binary_kelly',
                raw_kelly=raw_kelly,
                adjusted_kelly=0.0,
                confidence_factor=confidence,
                liquidity_factor=1.0,
                utilization_factor=1.0,
                reason="No positive edge"
            )
        
        # Apply fractional Kelly and bounds
        adjusted_kelly = raw_kelly * scaling_factor
        adjusted_kelly = max(min_fraction, min(max_fraction, adjusted_kelly))
        
        # Utilization brake: reduce size as utilization increases
        util_factor = 1.0
        if current_utilization > 0:
            brake = max(0, 1 - pow(current_utilization / util_hard_stop, util_exponent))
            util_factor = brake
        
        # Liquidity factor: scale down if liquidity is low
        liquidity_threshold = 10000.0  # Full size at $10K liquidity
        liquidity_factor = min(1.0, liquidity / liquidity_threshold)
        
        # Confidence factor (from model)
        conf_factor = max(0.5, min(1.0, confidence))
        
        # Final Kelly fraction
        final_kelly = adjusted_kelly * util_factor * liquidity_factor * conf_factor
        
        # Calculate size
        raw_size = capital * final_kelly
        
        # Apply caps
        size = min(raw_size, max_pos_usd)
        size = max(size, min_size) if size > 0 else 0.0
        
        return SizingResult(
            size=size,
            method='binary_kelly',
            raw_kelly=raw_kelly,
            adjusted_kelly=final_kelly,
            confidence_factor=conf_factor,
            liquidity_factor=liquidity_factor,
            utilization_factor=util_factor,
            reason=f"Kelly: raw={raw_kelly:.3f}, adjusted={final_kelly:.3f}"
        )
    
    # ========================================
    # LANE 3: GAMMA - Fixed Unit (Lottery)
    # ========================================
    
    @staticmethod
    def calculate_gamma_size(
        capital: float,
        max_pos_pct: float = 0.01,
        max_pos_usd: float = 15.0,
        min_size: float = 2.0
    ) -> SizingResult:
        """
        Calculate GAMMA position size (lottery tickets).
        
        Gamma uses fixed small positions:
        - 1% of capital
        - Hard cap at $15
        - These are "moonshot" bets
        
        Args:
            capital: Deployed capital
            max_pos_pct: Max position as % of capital (1%)
            max_pos_usd: Hard USD cap ($15)
            min_size: Minimum position size
            
        Returns:
            SizingResult with calculated size
        """
        # Fixed unit: small percentage
        raw_size = capital * max_pos_pct
        
        # Apply USD cap (Gamma is capped low)
        size = min(raw_size, max_pos_usd)
        
        # Apply floor
        size = max(size, min_size)
        
        return SizingResult(
            size=size,
            method='fixed_unit_gamma',
            raw_kelly=0.0,
            adjusted_kelly=0.0,
            confidence_factor=1.0,
            liquidity_factor=1.0,
            utilization_factor=1.0,
            reason=f"Gamma lottery: {max_pos_pct*100:.0f}% of capital, max ${max_pos_usd:.0f}"
        )
    
    # ========================================
    # LANE 4: SPORTS - Sports Kelly
    # ========================================
    
    @staticmethod
    def calculate_sports_size(
        edge: float,
        implied_odds: float,
        capital: float,
        kelly_fraction: float = 0.25,
        min_kelly: float = 0.05,
        max_kelly: float = 0.20,
        max_pos_usd: float = 100.0,
        min_size: float = 5.0
    ) -> SizingResult:
        """
        Calculate sports arbitrage position size.
        
        Sports Kelly uses bookmaker-derived fair values:
        - Edge = polymarket_price - implied_odds_from_books - fees
        - More conservative Kelly bounds (5%-20%)
        
        Args:
            edge: Edge after fees (poly_price - fair_value - fees)
            implied_odds: True probability from devigged bookmaker odds
            capital: Sports capital allocation
            kelly_fraction: Fractional Kelly multiplier
            min_kelly: Minimum Kelly fraction (5%)
            max_kelly: Maximum Kelly fraction (20%)
            max_pos_usd: Hard USD cap
            min_size: Minimum position size
            
        Returns:
            SizingResult with calculated size
        """
        if edge <= 0:
            return SizingResult(
                size=0.0,
                method='sports_kelly',
                raw_kelly=0.0,
                adjusted_kelly=0.0,
                confidence_factor=1.0,
                liquidity_factor=1.0,
                utilization_factor=1.0,
                reason="No positive edge after fees"
            )
        
        # Kelly for sports: edge / (1 - implied_odds)
        if implied_odds >= 0.99:
            raw_kelly = 0.0
        else:
            raw_kelly = edge / (1 - implied_odds)
        
        if raw_kelly <= 0:
            return SizingResult(
                size=0.0,
                method='sports_kelly',
                raw_kelly=raw_kelly,
                adjusted_kelly=0.0,
                confidence_factor=1.0,
                liquidity_factor=1.0,
                utilization_factor=1.0,
                reason="Kelly suggests no bet"
            )
        
        # Apply fractional Kelly with sports-specific bounds
        adjusted_kelly = raw_kelly * kelly_fraction
        adjusted_kelly = max(min_kelly, min(max_kelly, adjusted_kelly))
        
        # Calculate size
        raw_size = capital * adjusted_kelly
        
        # Apply caps
        size = min(raw_size, max_pos_usd)
        size = max(size, min_size) if size > 0 else 0.0
        
        return SizingResult(
            size=size,
            method='sports_kelly',
            raw_kelly=raw_kelly,
            adjusted_kelly=adjusted_kelly,
            confidence_factor=1.0,
            liquidity_factor=1.0,
            utilization_factor=1.0,
            reason=f"Sports Kelly: raw={raw_kelly:.3f}, adjusted={adjusted_kelly:.3f}"
        )
    
    # ========================================
    # LANE 5: NEWS - News Kelly
    # ========================================
    
    @staticmethod
    def calculate_news_size(
        bayes_factor: float,
        posterior: float,
        prior: float,
        capital: float,
        kelly_fraction: float = 0.25,
        max_pos_pct: float = 0.05,
        max_pos_usd: float = 100.0,
        min_size: float = 5.0,
        confidence: float = 1.0
    ) -> SizingResult:
        """
        Calculate news sniper position size.
        
        News sizing uses Bayesian posterior probability:
        - Edge = |posterior - prior|
        - Scaled by Bayes Factor confidence
        
        Args:
            bayes_factor: Bayes Factor from news analysis
            posterior: P(YES) after news
            prior: P(YES) before news (market price)
            capital: Deployed capital
            kelly_fraction: Fractional Kelly multiplier
            max_pos_pct: Max position as % of capital (5%)
            max_pos_usd: Hard USD cap
            min_size: Minimum position size
            confidence: LLM confidence in analysis
            
        Returns:
            SizingResult with calculated size
        """
        # Edge from Bayesian update
        edge = abs(posterior - prior)
        
        if edge <= 0.01:  # Less than 1% edge
            return SizingResult(
                size=0.0,
                method='news_kelly',
                raw_kelly=0.0,
                adjusted_kelly=0.0,
                confidence_factor=confidence,
                liquidity_factor=1.0,
                utilization_factor=1.0,
                reason="Insufficient edge from news"
            )
        
        # Kelly with Bayes Factor scaling
        # Higher BF = higher confidence = larger size
        bf_confidence = min(1.0, math.log10(max(bayes_factor, 1)) / math.log10(10))  # BF=10 → 1.0
        
        # Raw Kelly
        model_prob = posterior if posterior > prior else (1 - posterior)
        raw_kelly = edge / (1 - model_prob) if model_prob < 0.99 else 0.0
        
        # Apply fractional Kelly with news scaling
        adjusted_kelly = raw_kelly * kelly_fraction * bf_confidence * confidence
        
        # Cap at max_pos_pct
        adjusted_kelly = min(adjusted_kelly, max_pos_pct)
        
        # Calculate size
        raw_size = capital * adjusted_kelly
        
        # Apply caps
        size = min(raw_size, max_pos_usd)
        size = max(size, min_size) if size > 0 else 0.0
        
        return SizingResult(
            size=size,
            method='news_kelly',
            raw_kelly=raw_kelly,
            adjusted_kelly=adjusted_kelly,
            confidence_factor=confidence * bf_confidence,
            liquidity_factor=1.0,
            utilization_factor=1.0,
            reason=f"News Kelly: BF={bayes_factor:.1f}, edge={edge:.3f}"
        )
    
    # ========================================
    # UTILITY FUNCTIONS
    # ========================================
    
    @staticmethod
    def apply_liquidity_constraint(
        size: float,
        liquidity: float,
        max_consumption: float = 0.10
    ) -> Tuple[float, str]:
        """
        Apply liquidity constraint to position size.
        
        Never consume more than 10% of available liquidity.
        
        Args:
            size: Proposed position size
            liquidity: Available market liquidity
            max_consumption: Max % of liquidity to consume
            
        Returns:
            (adjusted_size, reason)
        """
        max_by_liquidity = liquidity * max_consumption
        if size > max_by_liquidity:
            return max_by_liquidity, f"Liquidity cap: ${max_by_liquidity:.0f} (10% of ${liquidity:.0f})"
        return size, "Within liquidity"
    
    @staticmethod
    def calculate_utilization_brake(
        utilization: float,
        exponent: float = 1.5,
        hard_stop: float = 0.95
    ) -> float:
        """
        Calculate utilization brake factor.
        
        As utilization increases, the brake reduces position sizes:
        - 0% utilization → 1.0 (full size)
        - 95% utilization → 0.0 (no new trades)
        
        Args:
            utilization: Current utilization (0-1)
            exponent: Brake curve steepness
            hard_stop: Utilization level for full stop
            
        Returns:
            Brake factor (0-1)
        """
        if utilization >= hard_stop:
            return 0.0
        return max(0, 1 - pow(utilization / hard_stop, exponent))
    
    @staticmethod
    def calculate_time_penalty(
        days_to_expiry: float,
        max_days: float = 90,
        floor: float = 0.50
    ) -> float:
        """
        Calculate time penalty factor for position sizing.
        
        Longer time to expiry → smaller position (more uncertainty)
        
        Args:
            days_to_expiry: Days until market expires
            max_days: Days at which penalty is maximized
            floor: Minimum penalty factor
            
        Returns:
            Time penalty factor (floor to 1.0)
        """
        if days_to_expiry <= 0:
            return 1.0  # No penalty for expired/near-expired
        
        # Linear decay from 1.0 to floor over max_days
        penalty = 1.0 - ((1.0 - floor) * min(days_to_expiry, max_days) / max_days)
        return max(floor, penalty)
