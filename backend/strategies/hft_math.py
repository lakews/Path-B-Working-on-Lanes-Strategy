"""
Advanced HFT Strategy Mathematics
=================================

Professional-grade Risk Management and Signal Processing for Binary Markets.

Features:
1. Cubic Inventory Skew ("Hockey Stick" Curve)
2. Adaptive Signal Smoothing (Jump Detection)
3. Cliff Protection (Extreme Price Spread Widening)

Author: APEX TRADER Quantitative Research
Date: January 2026
"""

import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class HFTMathConfig:
    """Configuration for HFT mathematical models."""
    
    # Cubic Skew Parameters
    max_position_limit: float = 1000.0      # Max inventory before forced liquidation
    skew_intensity: float = 0.05            # Max skew at 100% inventory (5 cents)
    
    # Signal Smoothing Parameters
    ema_alpha: float = 0.2                  # EMA smoothing factor (0.2 = 20% new, 80% old)
    jump_threshold: float = 0.03            # 3 cent move = instant reaction (no smoothing)
    
    # Cliff Protection Parameters
    cliff_zone_threshold: float = 0.15      # Within 15 cents of 0 or 1 = danger zone
    cliff_spread_multiplier: float = 2.0    # Double spread in cliff zone
    extreme_zone_threshold: float = 0.05    # Within 5 cents = extreme danger
    extreme_spread_multiplier: float = 3.0  # Triple spread in extreme zone


# Global default config
DEFAULT_HFT_CONFIG = HFTMathConfig()


# =============================================================================
# TASK 1: CUBIC INVENTORY SKEW
# =============================================================================

class CubicInventorySkew:
    """
    Cubic Inventory Skew ("Hockey Stick" Curve)
    
    Philosophy: Be PASSIVE with small inventory, AGGRESSIVE with large inventory.
    
    The cubic function (x³) has a gentle slope near zero and explodes near ±1.
    This lets us hold small positions without aggressively pricing ourselves out,
    but rapidly increases the discount/premium as we approach risk limits.
    
    Example (max_pos=1000, intensity=0.05):
    - 10% inventory (100 shares): skew = 0.001³ × 0.05 = 0.00005 (negligible)
    - 50% inventory (500 shares): skew = 0.5³ × 0.05 = 0.00625 (0.6 cent)
    - 90% inventory (900 shares): skew = 0.9³ × 0.05 = 0.0365 (3.6 cents!)
    
    This is the "Hockey Stick" - flat at the start, steep at the end.
    """
    
    def __init__(self, config: HFTMathConfig = None):
        self.config = config or DEFAULT_HFT_CONFIG
        
    def calculate_skew(
        self, 
        current_position: float,
        raw_fair_value: float,
        max_position: float = None,
        intensity: float = None
    ) -> Tuple[float, float, Dict]:
        """
        Calculate cubic inventory skew adjustment.
        
        Args:
            current_position: Current inventory (+ve = long, -ve = short)
            raw_fair_value: AI's estimated fair value (0.0 to 1.0)
            max_position: Optional override for max position limit
            intensity: Optional override for skew intensity
            
        Returns:
            (adjusted_fair_value, skew_amount, debug_info)
        """
        max_pos = max_position or self.config.max_position_limit
        skew_int = intensity or self.config.skew_intensity
        
        # Normalize position to [-1.0, 1.0]
        if max_pos == 0:
            pos_ratio = 0.0
        else:
            pos_ratio = current_position / max_pos
            pos_ratio = max(-1.0, min(1.0, pos_ratio))
        
        # CUBIC FUNCTION: x³ keeps penalty low for small positions
        # Sign preserved: positive position = negative skew (encourage selling)
        skew_adjustment = (pos_ratio ** 3) * skew_int
        
        # Apply skew: LONG position -> LOWER fair value (encourage selling)
        adjusted_fair = raw_fair_value - skew_adjustment
        
        # Clamp to valid price range
        adjusted_fair = max(0.01, min(0.99, adjusted_fair))
        
        debug_info = {
            'current_position': current_position,
            'max_position': max_pos,
            'pos_ratio': round(pos_ratio, 4),
            'pos_ratio_cubed': round(pos_ratio ** 3, 6),
            'skew_intensity': skew_int,
            'skew_adjustment': round(skew_adjustment, 6),
            'raw_fair_value': round(raw_fair_value, 4),
            'adjusted_fair_value': round(adjusted_fair, 4),
        }
        
        return adjusted_fair, skew_adjustment, debug_info
    
    def calculate_skew_curve(
        self, 
        max_position: float = 1000,
        intensity: float = 0.05
    ) -> Dict[int, float]:
        """
        Generate the full skew curve for visualization/debugging.
        
        Returns: {inventory_pct: skew_amount}
        """
        curve = {}
        for pct in range(0, 101, 10):
            pos_ratio = pct / 100.0
            skew = (pos_ratio ** 3) * intensity
            curve[pct] = round(skew, 6)
        return curve


# =============================================================================
# TASK 2: ADAPTIVE SIGNAL SMOOTHING
# =============================================================================

class AdaptiveSignalSmoother:
    """
    Adaptive Signal Smoothing with Jump Detection
    
    Philosophy: SMOOTH noise, but REACT instantly to news shocks.
    
    The challenge: EMA smoothing removes noise but also delays reaction to real events.
    Solution: Use a "jump detector" to bypass smoothing when we see large moves.
    
    - Small move (< 3 cents): Apply EMA smoothing to filter tick noise
    - Large move (≥ 3 cents): Bypass smoothing, assume news event, react instantly
    
    This gives us the best of both worlds:
    - We don't chase 1-tick noise
    - We catch 10-cent jumps immediately
    """
    
    def __init__(self, config: HFTMathConfig = None):
        self.config = config or DEFAULT_HFT_CONFIG
        
        # Signal memory: market_id -> (smoothed_signal, timestamp)
        self._signal_memory: Dict[str, Tuple[float, datetime]] = {}
        
    def smooth_signal(
        self, 
        market_id: str,
        new_raw_signal: float,
        ema_alpha: float = None,
        jump_threshold: float = None
    ) -> Tuple[float, str, Dict]:
        """
        Apply adaptive smoothing to a raw signal.
        
        Args:
            market_id: Market identifier
            new_raw_signal: New raw signal value
            ema_alpha: Optional override for EMA alpha (default 0.2)
            jump_threshold: Optional override for jump detection (default 0.03)
            
        Returns:
            (smoothed_signal, action_taken, debug_info)
            action_taken: "JUMP_DETECTED" or "EMA_SMOOTHED" or "INITIALIZED"
        """
        alpha = ema_alpha or self.config.ema_alpha
        threshold = jump_threshold or self.config.jump_threshold
        now = datetime.now(timezone.utc)
        
        prev = self._signal_memory.get(market_id)
        
        if prev is None:
            # First signal for this market - initialize
            self._signal_memory[market_id] = (new_raw_signal, now)
            return new_raw_signal, "INITIALIZED", {
                'new_raw': new_raw_signal,
                'smoothed': new_raw_signal,
                'is_first': True,
            }
        
        prev_smoothed, prev_time = prev
        
        # Calculate signal change magnitude
        diff = abs(new_raw_signal - prev_smoothed)
        
        # JUMP DETECTION: Large move bypasses smoothing
        if diff > threshold:
            # News event detected - react instantly
            smoothed = new_raw_signal
            action = "JUMP_DETECTED"
            
            logger.debug(
                f"[SIGNAL] Jump detected in {market_id[:16]}: "
                f"{prev_smoothed:.4f} -> {new_raw_signal:.4f} (diff={diff:.4f})"
            )
        else:
            # Small move - apply EMA smoothing
            # EMA formula: smoothed = α * new + (1-α) * prev
            smoothed = (alpha * new_raw_signal) + ((1 - alpha) * prev_smoothed)
            action = "EMA_SMOOTHED"
        
        # Update memory
        self._signal_memory[market_id] = (smoothed, now)
        
        debug_info = {
            'new_raw': round(new_raw_signal, 4),
            'prev_smoothed': round(prev_smoothed, 4),
            'diff': round(diff, 4),
            'threshold': threshold,
            'jump_detected': diff > threshold,
            'ema_alpha': alpha,
            'smoothed': round(smoothed, 4),
        }
        
        return smoothed, action, debug_info
    
    def get_signal(self, market_id: str) -> Optional[float]:
        """Get the current smoothed signal for a market."""
        if market_id in self._signal_memory:
            return self._signal_memory[market_id][0]
        return None
    
    def reset(self, market_id: str = None):
        """Reset signal memory (for testing or market close)."""
        if market_id:
            self._signal_memory.pop(market_id, None)
        else:
            self._signal_memory.clear()


# =============================================================================
# TASK 3: CLIFF PROTECTION
# =============================================================================

class CliffProtection:
    """
    Cliff Protection (Extreme Price Spread Widening)
    
    Philosophy: Volatility INCREASES relative to price near the edges.
    
    At $0.50, a 1-cent move is 2% of price.
    At $0.05, a 1-cent move is 20% of price!
    
    Binary markets have higher relative volatility near 0 and 1 because:
    1. Small absolute moves are large percentage moves
    2. News events can cause instant resolution (0 or 1)
    3. Gamma (option-like convexity) increases at extremes
    
    Solution: Widen spreads as price approaches the "cliffs" (0 or 1).
    """
    
    def __init__(self, config: HFTMathConfig = None):
        self.config = config or DEFAULT_HFT_CONFIG
        
    def calculate_spread_multiplier(
        self, 
        price: float,
        cliff_threshold: float = None,
        cliff_multiplier: float = None,
        extreme_threshold: float = None,
        extreme_multiplier: float = None
    ) -> Tuple[float, str, Dict]:
        """
        Calculate spread multiplier based on price proximity to edges.
        
        Args:
            price: Current market price (0.0 to 1.0)
            cliff_threshold: Override for cliff zone threshold (default 0.15)
            cliff_multiplier: Override for cliff zone multiplier (default 2.0)
            extreme_threshold: Override for extreme zone threshold (default 0.05)
            extreme_multiplier: Override for extreme zone multiplier (default 3.0)
            
        Returns:
            (spread_multiplier, zone_name, debug_info)
        """
        cliff_th = cliff_threshold or self.config.cliff_zone_threshold
        cliff_mult = cliff_multiplier or self.config.cliff_spread_multiplier
        extreme_th = extreme_threshold or self.config.extreme_zone_threshold
        extreme_mult = extreme_multiplier or self.config.extreme_spread_multiplier
        
        # Distance from nearest edge (0 or 1)
        dist_from_edge = min(price, 1.0 - price)
        
        # Determine zone
        if dist_from_edge < extreme_th:
            # EXTREME ZONE: Price < $0.05 or > $0.95
            multiplier = extreme_mult
            zone = "EXTREME"
        elif dist_from_edge < cliff_th:
            # CLIFF ZONE: Price < $0.15 or > $0.85
            multiplier = cliff_mult
            zone = "CLIFF"
        else:
            # SAFE ZONE: $0.15 to $0.85
            multiplier = 1.0
            zone = "SAFE"
        
        debug_info = {
            'price': round(price, 4),
            'dist_from_edge': round(dist_from_edge, 4),
            'extreme_threshold': extreme_th,
            'cliff_threshold': cliff_th,
            'zone': zone,
            'multiplier': multiplier,
        }
        
        return multiplier, zone, debug_info
    
    def calculate_adjusted_spread(
        self,
        base_spread: float,
        price: float
    ) -> Tuple[float, Dict]:
        """
        Calculate the final spread after cliff protection adjustment.
        
        Args:
            base_spread: Normal spread (e.g., 0.02)
            price: Current market price
            
        Returns:
            (adjusted_spread, debug_info)
        """
        multiplier, zone, zone_info = self.calculate_spread_multiplier(price)
        adjusted_spread = base_spread * multiplier
        
        # Ensure spread doesn't exceed reasonable bounds
        adjusted_spread = min(adjusted_spread, 0.15)  # Cap at 15 cents
        
        return adjusted_spread, {
            **zone_info,
            'base_spread': round(base_spread, 4),
            'adjusted_spread': round(adjusted_spread, 4),
        }


# =============================================================================
# COMBINED HFT MATH ENGINE
# =============================================================================

class HFTMathEngine:
    """
    Combined HFT Mathematics Engine
    
    Integrates all three components:
    1. Cubic Inventory Skew
    2. Adaptive Signal Smoothing
    3. Cliff Protection
    
    Usage:
        engine = HFTMathEngine()
        result = engine.calculate_quote(
            market_id="market_123",
            raw_fair_value=0.50,
            raw_signal=0.55,
            current_position=500,
            base_spread=0.02
        )
    """
    
    def __init__(self, config: HFTMathConfig = None):
        self.config = config or DEFAULT_HFT_CONFIG
        self.skew = CubicInventorySkew(self.config)
        self.smoother = AdaptiveSignalSmoother(self.config)
        self.cliff = CliffProtection(self.config)
        
    def calculate_quote(
        self,
        market_id: str,
        raw_fair_value: float,
        raw_signal: float,
        current_position: float,
        base_spread: float,
        max_position: float = None
    ) -> Dict:
        """
        Calculate the full quote with all adjustments.
        
        Returns comprehensive quote data including:
        - Smoothed signal
        - Inventory-skewed fair value
        - Cliff-adjusted spread
        - Final bid/ask prices
        """
        # Step 1: Smooth the signal (with jump detection)
        smoothed_signal, signal_action, signal_debug = self.smoother.smooth_signal(
            market_id, raw_signal
        )
        
        # Step 2: Apply cubic inventory skew
        skewed_fair, skew_amount, skew_debug = self.skew.calculate_skew(
            current_position, raw_fair_value, max_position
        )
        
        # Step 3: Apply cliff protection to spread
        cliff_spread, cliff_debug = self.cliff.calculate_adjusted_spread(
            base_spread, skewed_fair
        )
        
        # Step 4: Calculate final bid/ask
        half_spread = cliff_spread / 2
        bid = round(skewed_fair - half_spread, 2)
        ask = round(skewed_fair + half_spread, 2)
        
        # Ensure bid/ask stay in valid range
        bid = max(0.01, min(0.98, bid))
        ask = max(0.02, min(0.99, ask))
        
        # Ensure ask > bid
        if ask <= bid:
            ask = bid + 0.01
        
        return {
            'bid': bid,
            'ask': ask,
            'spread': round(ask - bid, 2),
            'fair_value': round(skewed_fair, 4),
            'raw_fair_value': round(raw_fair_value, 4),
            'smoothed_signal': round(smoothed_signal, 4),
            'signal_action': signal_action,
            'skew_amount': round(skew_amount, 4),
            'cliff_zone': cliff_debug['zone'],
            'spread_multiplier': cliff_debug['multiplier'],
            'debug': {
                'signal': signal_debug,
                'skew': skew_debug,
                'cliff': cliff_debug,
            }
        }
    
    def reset_signal_memory(self, market_id: str = None):
        """Reset signal smoother memory."""
        self.smoother.reset(market_id)


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_hft_math_engine: Optional[HFTMathEngine] = None

def get_hft_math_engine() -> HFTMathEngine:
    """Get the global HFT Math Engine singleton."""
    global _hft_math_engine
    if _hft_math_engine is None:
        _hft_math_engine = HFTMathEngine()
    return _hft_math_engine
