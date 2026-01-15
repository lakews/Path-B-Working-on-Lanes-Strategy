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
        """
        # Volatility ratio vs historical
        vol_ratio = predicted_volatility / max(historical_volatility, 0.01)
        
        # Regime classification
        if vol_ratio < 0.5:
            # Very low vol - can size up slightly
            return 1.1
        elif vol_ratio < 1.0:
            # Normal vol
            return 1.0
        elif vol_ratio < 2.0:
            # Elevated vol - reduce moderately
            return 0.8
        elif vol_ratio < 3.0:
            # High vol - reduce significantly
            return 0.6
        else:
            # Extreme vol - minimum sizing
            return 0.4
    
    def calculate_rl_confidence_multiplier(
        self,
        rl_confidence: float,
        rl_action: str
    ) -> float:
        """
        Scale position by RL model confidence.
        
        Higher confidence = larger position.
        Also considers action type (HOLD actions get smaller sizes).
        """
        # Base multiplier from confidence
        base_mult = 0.5 + (rl_confidence * 0.5)  # 0.5 to 1.0
        
        # Action-based adjustment
        if 'HOLD' in rl_action:
            base_mult *= 0.5  # Reduce if model suggests holding
        elif 'STRONG' in rl_action or 'LARGE' in rl_action:
            base_mult *= 1.2  # Increase for strong signals
        
        return min(1.2, base_mult)
    
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
        Calculate optimal position size using all factors.
        
        Returns dict with:
        - position_size: Final USD amount
        - sizing_breakdown: Dict explaining each factor
        - should_trade: Boolean if size > minimum
        """
        # Base max position from config
        max_position_usd = deployed_capital * (max_position_pct / 100)
        
        # 1. Kelly-based sizing (only if enabled)
        if kelly_enabled:
            kelly_size = self.calculate_kelly_criterion(strategy, asset_class, kelly_fraction)
            kelly_position = deployed_capital * kelly_size
        else:
            # Kelly disabled - use fixed fraction
            kelly_size = kelly_fraction
            kelly_position = max_position_usd * 0.5  # Use 50% of max as base
        
        # 2. Liquidity multiplier
        liquidity_mult = self.calculate_liquidity_multiplier(market_data, max_position_usd)
        
        # 3. Volatility adjustment
        volatility = signals.get('volatility', 0.02)
        vol_mult = self.calculate_volatility_adjustment(volatility)
        
        # 4. RL confidence multiplier
        rl_mult = self.calculate_rl_confidence_multiplier(rl_confidence, rl_action)
        
        # 5. Asset class risk multiplier
        asset_mult = self.ASSET_CLASS_RISK.get(asset_class, 1.0)
        
        # 6. Strategy risk multiplier
        strat_mult = self.STRATEGY_RISK.get(strategy, 1.0)
        
        # Combine all factors
        combined_mult = liquidity_mult * vol_mult * rl_mult * asset_mult * strat_mult
        
        # Adaptive sizing: use Kelly when available, fall back to base position when Kelly is too conservative
        min_base_position = max_position_usd * 0.1  # Minimum 10% of max for HFT
        
        if kelly_enabled and kelly_position > min_base_position:
            # Kelly has sufficient data - use it as primary with multipliers
            raw_position = kelly_position * combined_mult
        else:
            # Kelly is too conservative (new strategy/no data) or disabled - use adaptive base
            # Start with 30% of max, scaled by multipliers
            base_position = max_position_usd * 0.3
            raw_position = base_position * combined_mult
            
            # If Kelly is positive but small (and enabled), blend it in for learning
            if kelly_enabled and kelly_position > 0:
                raw_position = raw_position * 0.7 + kelly_position * combined_mult * 0.3
        
        # Apply hard caps
        final_position = min(raw_position, max_position_usd)
        final_position = min(final_position, deployed_capital * 0.10)  # Never more than 10% in one trade
        
        # Minimum trade size check for HFT
        min_trade_size = 5  # $5 minimum
        should_trade = final_position >= min_trade_size and liquidity_mult > 0
        
        return {
            'position_size': round(final_position, 2),
            'should_trade': should_trade,
            'sizing_breakdown': {
                'base_max_position': max_position_usd,
                'kelly_fraction': round(kelly_size, 4),
                'kelly_position': round(kelly_position, 2),
                'liquidity_multiplier': round(liquidity_mult, 3),
                'volatility_multiplier': round(vol_mult, 3),
                'rl_confidence_multiplier': round(rl_mult, 3),
                'asset_class_multiplier': round(asset_mult, 3),
                'strategy_multiplier': round(strat_mult, 3),
                'combined_multiplier': round(combined_mult, 4),
                'final_position': round(final_position, 2),
            },
            'factors': {
                'volume_24h': market_data.get('volume_24h', market_data.get('volume', 0)),
                'outstanding': market_data.get('outstanding_contracts', market_data.get('liquidity', 0)),
                'volatility': round(volatility, 4),
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
