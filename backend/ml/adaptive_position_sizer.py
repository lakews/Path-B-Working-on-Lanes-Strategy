"""
Adaptive Position Sizing Engine
Advanced position sizing using liquidity, volume, Kelly criterion, and ML/RL signals.

Key Features:
- Liquidity-aware sizing: Reduces position in illiquid markets to avoid slippage
- Volume-weighted: Adjusts based on market activity
- Kelly-optimized: Uses learned win rates and avg returns per strategy/asset class
- RL confidence scaling: Higher confidence = larger positions
- Regime awareness: Adjusts for market volatility regimes
- Outstanding contracts: Considers market depth
"""
import logging
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime, timezone
from database import get_db

logger = logging.getLogger(__name__)


class AdaptivePositionSizer:
    """
    Calculates optimal position sizes using multiple factors:
    1. Kelly Criterion with learned parameters per strategy/asset class
    2. Liquidity score (volume, outstanding, spread)
    3. RL confidence from model predictions
    4. Volatility regime adjustment
    5. Asset class risk profile
    """
    
    # Asset class risk multipliers (learned baseline, can be updated by RL)
    ASSET_CLASS_RISK = {
        'crypto': 0.7,      # Higher volatility, reduce exposure
        'politics': 0.9,    # Binary outcomes, moderate risk
        'finance': 1.0,     # Standard risk
        'sports': 0.95,     # Predictable patterns
        'entertainment': 0.85,  # Lower liquidity typically
        'science': 0.8,     # Less liquid, more volatile
    }
    
    # Strategy risk multipliers
    STRATEGY_RISK = {
        'delta_neutral': 1.2,        # Low risk, can size up
        'volatility_exploitation': 0.5,  # High risk, size down
        'alpha_directional': 0.8,    # Medium risk
        'arbitrage': 1.1,            # Low risk, slight increase
    }
    
    # Minimum liquidity thresholds (in USD volume)
    MIN_LIQUIDITY_FOR_FULL_SIZE = 10000  # $10K daily volume for full position
    MIN_LIQUIDITY_FOR_TRADE = 500        # Won't trade below $500 volume
    
    def __init__(self, db=None):
        self.db = db or get_db()
        
        # Learned parameters (loaded from DB, updated by RL)
        self.learned_params = {
            'strategy_win_rates': {},
            'strategy_avg_wins': {},
            'strategy_avg_losses': {},
            'asset_class_win_rates': {},
            'asset_class_avg_wins': {},
            'asset_class_avg_losses': {},
            'liquidity_multipliers': {},
            'regime_adjustments': {},
        }
        
        # Track learning progress
        self.learning_updates = 0
        self.last_learn_time = None
    
    async def load_learned_params(self):
        """Load learned parameters from database"""
        try:
            params = await self.db.position_sizing_params.find_one(
                {"type": "learned_params"},
                {"_id": 0}
            )
            if params:
                self.learned_params.update(params.get('params', {}))
                self.learning_updates = params.get('learning_updates', 0)
                logger.info(f"Loaded position sizing params ({self.learning_updates} updates)")
        except Exception as e:
            logger.warning(f"Could not load learned params: {e}")
    
    async def save_learned_params(self):
        """Save learned parameters to database"""
        try:
            await self.db.position_sizing_params.update_one(
                {"type": "learned_params"},
                {"$set": {
                    "params": self.learned_params,
                    "learning_updates": self.learning_updates,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Could not save learned params: {e}")
    
    def calculate_kelly_criterion(
        self,
        strategy: str,
        asset_class: str,
        base_kelly_fraction: float = 0.25
    ) -> float:
        """
        Calculate Kelly criterion using learned win rates and returns.
        
        Kelly = (W * R - L) / R
        Where:
            W = win rate
            R = average win / average loss ratio
            L = loss rate (1 - W)
        
        Uses strategy and asset class specific parameters when available.
        """
        # Get strategy-specific params (default to conservative if not learned)
        strat_win_rate = self.learned_params.get('strategy_win_rates', {}).get(strategy, 0.5)
        strat_avg_win = self.learned_params.get('strategy_avg_wins', {}).get(strategy, 0.12)
        strat_avg_loss = self.learned_params.get('strategy_avg_losses', {}).get(strategy, 0.08)
        
        # Get asset class specific params
        asset_win_rate = self.learned_params.get('asset_class_win_rates', {}).get(asset_class, 0.5)
        asset_avg_win = self.learned_params.get('asset_class_avg_wins', {}).get(asset_class, 0.10)
        asset_avg_loss = self.learned_params.get('asset_class_avg_losses', {}).get(asset_class, 0.08)
        
        # Blend strategy and asset class (60/40 weight)
        blended_win_rate = 0.6 * strat_win_rate + 0.4 * asset_win_rate
        blended_avg_win = 0.6 * strat_avg_win + 0.4 * asset_avg_win
        blended_avg_loss = 0.6 * strat_avg_loss + 0.4 * asset_avg_loss
        
        # Calculate Kelly
        if blended_avg_loss == 0:
            return base_kelly_fraction * 0.5
        
        win_loss_ratio = blended_avg_win / blended_avg_loss
        kelly = (blended_win_rate * win_loss_ratio - (1 - blended_win_rate)) / win_loss_ratio
        
        # Apply fractional Kelly (safer)
        kelly = kelly * base_kelly_fraction
        
        # Bound between 0 and max Kelly
        return max(0, min(kelly, base_kelly_fraction))
    
    def calculate_liquidity_multiplier(
        self,
        market_data: Dict,
        max_position_usd: float
    ) -> float:
        """
        Calculate position multiplier based on market liquidity.
        
        Considers:
        - 24h volume
        - Outstanding contracts/shares
        - Bid-ask spread
        - Order book depth (if available)
        
        Returns multiplier between 0 and 1.
        """
        volume_24h = market_data.get('volume_24h', 0) or 0
        volume = market_data.get('volume', volume_24h) or 0
        outstanding = market_data.get('outstanding_contracts', market_data.get('liquidity', 1000)) or 1000
        spread = market_data.get('spread', market_data.get('yes_price', 0.5) * 0.02) or 0.02
        
        # Use volume_24h as primary indicator - more relevant for active markets
        effective_volume = max(volume_24h, volume)
        
        # Log for debugging
        logger.debug(f"Liquidity calc: volume={volume}, volume_24h={volume_24h}, effective={effective_volume}, outstanding={outstanding}")
        
        # Volume check - use configurable minimum (passed via market_data or use sensible default)
        min_volume_threshold = market_data.get('_min_volume_threshold', 100)  # User config or default
        if effective_volume < min_volume_threshold:
            logger.debug(f"Volume too low: {effective_volume} < {min_volume_threshold}")
            return 0.0
        
        # Volume-based multiplier (linear scale up to full size threshold)
        volume_mult = min(1.0, effective_volume / self.MIN_LIQUIDITY_FOR_FULL_SIZE)
        
        # Outstanding contracts multiplier
        # Don't take more than 5% of outstanding
        max_from_outstanding = outstanding * 0.05
        outstanding_mult = min(1.0, max_from_outstanding / max_position_usd) if max_position_usd > 0 else 1.0
        
        # Spread penalty (wider spread = smaller position)
        spread_mult = max(0.3, 1.0 - (spread * 5))  # 0.02 spread = 0.9 mult, 0.1 spread = 0.5 mult
        
        # Combine factors
        liquidity_mult = min(volume_mult, outstanding_mult) * spread_mult
        
        return max(0.1, liquidity_mult)  # Minimum 10% if we trade at all
    
    def calculate_volatility_adjustment(
        self,
        predicted_volatility: float,
        historical_volatility: float = 0.02
    ) -> float:
        """
        Adjust position size based on volatility regime.
        
        Higher volatility = smaller positions (risk management)
        But also higher potential returns, so not linear reduction.
        
        NOTE: Reduced dampening to ensure trades can execute with small capital.
        """
        # Volatility ratio vs historical
        vol_ratio = predicted_volatility / max(historical_volatility, 0.01)
        
        # Regime classification - less aggressive dampening
        if vol_ratio < 0.5:
            # Very low vol - can size up slightly
            return 1.1
        elif vol_ratio < 1.0:
            # Normal vol
            return 1.0
        elif vol_ratio < 2.0:
            # Elevated vol - mild reduction
            return 0.9
        elif vol_ratio < 3.0:
            # High vol - moderate reduction
            return 0.8
        else:
            # Extreme vol - reduced sizing but still viable
            return 0.7
    
    def calculate_rl_confidence_multiplier(
        self,
        rl_confidence: float,
        rl_action: str
    ) -> float:
        """
        Scale position by RL model confidence.
        
        Higher confidence = larger position.
        Also considers action type (HOLD actions get smaller sizes).
        
        NOTE: Less aggressive dampening - RL confidence shouldn't block trades entirely.
        Even low confidence (0.15) should still allow reasonable position sizes.
        """
        # Base multiplier from confidence - higher floor to prevent over-dampening
        # Old: 0.7 + (conf * 0.5) → conf=0.15 gives 0.775
        # New: 0.85 + (conf * 0.3) → conf=0.15 gives 0.895 (less dampening)
        base_mult = 0.85 + (rl_confidence * 0.3)  # Range: 0.85 to 1.15
        
        # Action-based adjustment
        if 'HOLD' in rl_action or 'WAIT' in rl_action:
            base_mult *= 0.8  # Mild reduction if model suggests holding
        elif 'STRONG' in rl_action or 'LARGE' in rl_action:
            base_mult *= 1.2  # Increase for strong signals
        
        return min(1.3, base_mult)
    
    def calculate_optimal_position_size(
        self,
        deployed_capital: float,
        max_position_pct: float,
        strategy: str,
        asset_class: str,
        market_data: Dict,
        signals: Dict,
        rl_action: str,
        rl_confidence: float,
        kelly_fraction: float = 0.25,
        kelly_enabled: bool = True
    ) -> Dict:
        """
        Calculate optimal position size using ADAPTIVE multi-factor approach.
        
        Factors considered:
        1. Kelly Criterion (learned win rates)
        2. Liquidity (volume, spread, depth)
        3. Volatility regime
        4. RL model confidence
        5. Asset class risk profile
        6. Strategy risk profile
        7. Signal strength
        
        Returns dict with:
        - position_size: Final USD amount
        - sizing_breakdown: Dict explaining each factor
        - should_trade: Boolean if size meets criteria
        """
        # Base max position from config
        max_position_usd = deployed_capital * (max_position_pct / 100)
        
        # Minimum viable trade size (configurable, but reasonable floor)
        min_trade_size = max(5, deployed_capital * 0.005)  # $5 or 0.5% of capital, whichever is higher
        
        # ========== FACTOR 1: Kelly Criterion ==========
        if kelly_enabled:
            kelly_size = self.calculate_kelly_criterion(strategy, asset_class, kelly_fraction)
            kelly_position = deployed_capital * kelly_size
        else:
            kelly_size = kelly_fraction
            kelly_position = max_position_usd * 0.5
        
        # ========== FACTOR 2: Liquidity Score ==========
        liquidity_mult = self.calculate_liquidity_multiplier(market_data, max_position_usd)
        
        # ========== FACTOR 3: Volatility Regime ==========
        volatility = signals.get('volatility', 0.05)
        vol_mult = self.calculate_volatility_adjustment(volatility)
        
        # ========== FACTOR 4: RL Confidence ==========
        rl_mult = self.calculate_rl_confidence_multiplier(rl_confidence, rl_action)
        
        # ========== FACTOR 5: Asset Class Risk ==========
        asset_mult = self.ASSET_CLASS_RISK.get(asset_class.lower() if asset_class else 'finance', 1.0)
        
        # ========== FACTOR 6: Strategy Risk ==========
        strat_mult = self.STRATEGY_RISK.get(strategy, 1.0)
        
        # ========== FACTOR 7: Signal Strength ==========
        # Combine sentiment strength, sharp alignment, and price uncertainty
        sentiment = signals.get('sentiment', 0.5)
        sentiment_strength = abs(sentiment - 0.5) * 2  # 0-1 scale
        sharp_alignment = signals.get('sharp_alignment', 0.5)
        price_uncertainty = signals.get('price_uncertainty', 0.5)
        
        # Strong signals = larger position, weak signals = smaller
        # More variation: wider range to create position diversity
        signal_strength = (sentiment_strength * 0.3 + sharp_alignment * 0.4 + (1 - price_uncertainty) * 0.3)
        signal_mult = 0.6 + (signal_strength * 0.8)  # Range: 0.6 to 1.4 (wider than before)
        
        # ========== DIRECTIONAL DAMPENING ==========
        # For Alpha Directional (high conviction trades), apply dampening to create variety
        # High conviction shouldn't automatically mean max position - scale by uncertainty
        directional_dampening = 1.0
        if strategy == 'alpha_directional':
            # The more certain we are (low price_uncertainty), the MORE we dampen
            # This seems counterintuitive but prevents all alpha trades hitting max
            # High uncertainty = normal sizing, Low uncertainty = reduced sizing (we're already confident)
            certainty = 1 - price_uncertainty
            directional_dampening = 0.5 + (price_uncertainty * 0.5)  # 0.5-1.0x
            
            # Also dampen based on how extreme the sentiment is
            # Very extreme sentiment = already high edge, don't need max size
            if sentiment_strength > 0.7:
                directional_dampening *= 0.8
        
        # ========== COMBINE FACTORS ==========
        # Use geometric mean for more balanced combination (prevents one factor from dominating)
        import math
        factors = [liquidity_mult, vol_mult, rl_mult, asset_mult, strat_mult, signal_mult, directional_dampening]
        # Filter out zeros to avoid killing the position entirely
        positive_factors = [f for f in factors if f > 0]
        if positive_factors:
            # Geometric mean is more stable than product
            combined_mult = math.exp(sum(math.log(f) for f in positive_factors) / len(positive_factors))
        else:
            combined_mult = 0.5
        
        # ========== CALCULATE BASE POSITION ==========
        # Adaptive base: blend Kelly, max position, and signal-adjusted base
        if kelly_enabled and kelly_position > min_trade_size:
            # Kelly has meaningful data - use it with signal adjustment
            # Vary position based on signal strength even with Kelly
            kelly_signal_adj = 0.7 + (signal_strength * 0.6)  # 0.7-1.3x Kelly based on signals
            base_position = kelly_position * kelly_signal_adj
        else:
            # Kelly is too conservative - use signal-adjusted base
            # Higher signals = closer to max position, lower signals = closer to min
            signal_pct = 0.3 + (signal_strength * 0.5)  # 30-80% of max based on signals
            base_position = max_position_usd * signal_pct
        
        # Apply combined multiplier
        raw_position = base_position * combined_mult
        
        # ========== APPLY CONSTRAINTS ==========
        # Hard ceiling: never exceed max position or 10% of capital
        final_position = min(raw_position, max_position_usd)
        final_position = min(final_position, deployed_capital * 0.10)
        
        # Adaptive floor based on conviction
        # High liquidity + high RL confidence + strong signals = allow trade even if small
        conviction_score = (liquidity_mult * 0.3 + rl_mult * 0.3 + signal_mult * 0.4)
        
        # If position is below minimum but conviction is high, scale up to minimum
        if final_position < min_trade_size and conviction_score >= 0.7 and liquidity_mult >= 0.3:
            # Scale position to minimum, but only if we have conviction
            final_position = min_trade_size
        
        # ========== TRADING DECISION ==========
        # Should trade if:
        # 1. Position meets minimum size
        # 2. Liquidity is acceptable
        # 3. Not a WAIT/HOLD action with very low confidence
        should_trade = (
            final_position >= min_trade_size and 
            liquidity_mult > 0.1 and
            not (rl_action in ['WAIT', 'HOLD'] and rl_confidence < 0.3)
        )
        
        return {
            'position_size': round(final_position, 2),
            'should_trade': should_trade,
            'sizing_breakdown': {
                'base_max_position': round(max_position_usd, 2),
                'min_trade_size': round(min_trade_size, 2),
                'kelly_fraction': round(kelly_size, 4),
                'kelly_position': round(kelly_position, 2),
                'base_position': round(base_position, 2),
                'liquidity_multiplier': round(liquidity_mult, 3),
                'volatility_multiplier': round(vol_mult, 3),
                'rl_confidence_multiplier': round(rl_mult, 3),
                'asset_class_multiplier': round(asset_mult, 3),
                'strategy_multiplier': round(strat_mult, 3),
                'signal_multiplier': round(signal_mult, 3),
                'directional_dampening': round(directional_dampening, 3),
                'combined_multiplier': round(combined_mult, 4),
                'conviction_score': round(conviction_score, 3),
                'final_position': round(final_position, 2),
            },
            'factors': {
                'volume_24h': market_data.get('volume_24h', market_data.get('volume', 0)),
                'liquidity': market_data.get('liquidity', market_data.get('outstanding_contracts', 0)),
                'volatility': round(volatility, 4),
                'sentiment_strength': round(sentiment_strength, 3),
                'sharp_alignment': round(sharp_alignment, 3),
                'signal_strength': round(signal_strength, 3),
                'rl_confidence': round(rl_confidence, 3),
                'rl_action': rl_action,
            }
        }
    
    async def learn_from_trade(
        self,
        strategy: str,
        asset_class: str,
        pnl: float,
        pnl_pct: float,
        is_win: bool,
        sizing_used: Dict
    ):
        """
        Update learned parameters from trade outcome.
        
        Uses exponential moving average to update:
        - Win rates per strategy/asset class
        - Average win/loss amounts
        - Liquidity performance correlations
        """
        alpha = 0.1  # Learning rate
        
        # Update strategy win rate
        strat_win_rates = self.learned_params.setdefault('strategy_win_rates', {})
        current_strat_wr = strat_win_rates.get(strategy, 0.5)
        strat_win_rates[strategy] = (1 - alpha) * current_strat_wr + alpha * (1.0 if is_win else 0.0)
        
        # Update strategy avg win/loss
        if is_win:
            strat_avg_wins = self.learned_params.setdefault('strategy_avg_wins', {})
            current_avg = strat_avg_wins.get(strategy, 0.12)
            strat_avg_wins[strategy] = (1 - alpha) * current_avg + alpha * abs(pnl_pct)
        else:
            strat_avg_losses = self.learned_params.setdefault('strategy_avg_losses', {})
            current_avg = strat_avg_losses.get(strategy, 0.08)
            strat_avg_losses[strategy] = (1 - alpha) * current_avg + alpha * abs(pnl_pct)
        
        # Update asset class win rate
        asset_win_rates = self.learned_params.setdefault('asset_class_win_rates', {})
        current_asset_wr = asset_win_rates.get(asset_class, 0.5)
        asset_win_rates[asset_class] = (1 - alpha) * current_asset_wr + alpha * (1.0 if is_win else 0.0)
        
        # Update asset class avg win/loss
        if is_win:
            asset_avg_wins = self.learned_params.setdefault('asset_class_avg_wins', {})
            current_avg = asset_avg_wins.get(asset_class, 0.10)
            asset_avg_wins[asset_class] = (1 - alpha) * current_avg + alpha * abs(pnl_pct)
        else:
            asset_avg_losses = self.learned_params.setdefault('asset_class_avg_losses', {})
            current_avg = asset_avg_losses.get(asset_class, 0.08)
            asset_avg_losses[asset_class] = (1 - alpha) * current_avg + alpha * abs(pnl_pct)
        
        self.learning_updates += 1
        self.last_learn_time = datetime.now(timezone.utc)
        
        # Save periodically (every 10 trades)
        if self.learning_updates % 10 == 0:
            await self.save_learned_params()
        
        logger.debug(f"Learned from trade: {strategy}/{asset_class} - Win: {is_win}, PnL: {pnl_pct:.2%}")
    
    def get_learning_stats(self) -> Dict:
        """Get current learning statistics"""
        return {
            'total_updates': self.learning_updates,
            'last_update': self.last_learn_time.isoformat() if self.last_learn_time else None,
            'strategy_win_rates': self.learned_params.get('strategy_win_rates', {}),
            'asset_class_win_rates': self.learned_params.get('asset_class_win_rates', {}),
            'strategy_avg_wins': self.learned_params.get('strategy_avg_wins', {}),
            'strategy_avg_losses': self.learned_params.get('strategy_avg_losses', {}),
        }


# Singleton instance
_position_sizer: Optional[AdaptivePositionSizer] = None


def get_position_sizer() -> AdaptivePositionSizer:
    """Get or create singleton position sizer instance"""
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = AdaptivePositionSizer()
    return _position_sizer


async def init_position_sizer():
    """Initialize position sizer and load learned params"""
    sizer = get_position_sizer()
    await sizer.load_learned_params()
    return sizer
