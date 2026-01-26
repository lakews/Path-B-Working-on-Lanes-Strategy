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
        
        # STRICT PRICE VALIDATION for spread calculation
        yes_price = market_data.get('yes_price')
        if yes_price is not None and yes_price != 0:
            spread = market_data.get('spread', float(yes_price) * 0.02) or 0.02
        else:
            spread = market_data.get('spread', 0.02) or 0.02  # Use fixed default if no price
        
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
        
        # Spread penalty (wider spread = smaller position) - reduced penalty for real-world spreads
        spread_mult = max(0.3, 1.0 - (spread * 2))  # 0.05 spread = 0.9 mult, 0.25 spread = 0.5 mult
        
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
        
        INVERTED: Higher volatility = SMALLER positions (risk management)
        Uses ATR-style inverse scaling.
        """
        # Clamp volatility to reasonable range
        vol = max(0.01, min(predicted_volatility, 0.30))
        
        # ATR-style inverse scaling: position inversely proportional to volatility
        # Base volatility of 0.05 (5%) gives multiplier of 1.0
        # Higher vol = lower multiplier, lower vol = higher multiplier
        base_vol = 0.05
        vol_multiplier = base_vol / vol
        
        # Clamp to reasonable range (0.3x to 1.5x)
        return max(0.3, min(1.5, vol_multiplier))
    
    def calculate_spread_adjustment(
        self,
        market_data: Dict
    ) -> float:
        """
        Adjust position size based on bid-ask spread.
        
        Wider spread = higher transaction cost = SMALLER position
        """
        # Get spread from market data
        best_bid = float(market_data.get('best_bid', 0) or 0)
        best_ask = float(market_data.get('best_ask', 0) or 0)
        
        # STRICT PRICE VALIDATION
        yes_price = market_data.get('yes_price')
        if yes_price is None or yes_price == 0:
            # Cannot calculate spread adjustment without price - return neutral multiplier
            return 1.0
        yes_price = float(yes_price)
        
        if best_bid > 0 and best_ask > 0:
            spread = best_ask - best_bid
            spread_pct = spread / max(yes_price, 0.01)
        else:
            # Estimate spread from price (tighter near 0.5)
            spread_pct = 0.02 + abs(yes_price - 0.5) * 0.04  # 2-4% estimated
        
        # Inverse relationship: tight spread (1%) = 1.2x, wide spread (5%) = 0.5x
        # Base: 2% spread = 1.0x
        base_spread = 0.02
        spread_mult = base_spread / max(spread_pct, 0.005)
        
        # Clamp to reasonable range (0.4x to 1.3x)
        return max(0.4, min(1.3, spread_mult))
    
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
    
    def calculate_variance_sizing(
        self,
        current_price: float,
        base_size: float
    ) -> Tuple[float, Dict]:
        """
        Calculate Tail Risk / Variance-based position sizing.
        
        Uses Bernoulli variance p * (1-p) to scale position size.
        Maximum variance (and maximum position) is at p=0.5.
        Minimum variance (and minimum position) is at p near 0 or 1.
        
        This protects against:
        - Extreme price markets (lottery tickets)
        - Large losses from binary outcomes
        
        Args:
            current_price: Current market price (0.0 to 1.0)
            base_size: Base position size before variance adjustment
            
        Returns:
            Tuple of (adjusted_size, debug_info)
        """
        # 1. Hard Kill Switch at extremes
        # Don't trade at extreme prices - too risky
        if current_price < 0.03 or current_price > 0.97:
            return 0.0, {
                'kill_switch': True,
                'reason': f'price_extreme_{current_price:.3f}',
                'variance': 0.0,
                'multiplier': 0.0,
                'base_size': base_size,
                'final_size': 0.0
            }
        
        # 2. Calculate Bernoulli variance: p * (1 - p)
        # Max at p=0.5 (variance = 0.25)
        # Min at p=0 or p=1 (variance = 0)
        variance = current_price * (1 - current_price)
        
        # 3. Calculate size multiplier
        # At 50c: 4 * 0.25 = 1.0 (full size)
        # At 95c: 4 * 0.0475 = 0.19 (~20% size)
        # At 90c: 4 * 0.09 = 0.36 (~36% size)
        # At 70c: 4 * 0.21 = 0.84 (~84% size)
        size_multiplier = 4 * variance
        
        # 4. Calculate final size
        final_size = base_size * size_multiplier
        
        debug_info = {
            'kill_switch': False,
            'price': current_price,
            'variance': variance,
            'multiplier': size_multiplier,
            'base_size': base_size,
            'final_size': final_size
        }
        
        logger.debug(
            f"[VARIANCE-SIZING] Price={current_price:.3f} | "
            f"Var={variance:.4f} | Mult={size_multiplier:.3f} | "
            f"Base=${base_size:.2f} → Final=${final_size:.2f}"
        )
        
        return final_size, debug_info
    
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
        
        # ========== FACTOR 3: Volatility/ATR Adjustment (INVERSE) ==========
        volatility = signals.get('volatility', 0.05)
        vol_mult = self.calculate_volatility_adjustment(volatility)
        
        # ========== FACTOR 4: Spread Adjustment (INVERSE) ==========
        spread_mult = self.calculate_spread_adjustment(market_data)
        
        # ========== FACTOR 5: RL Confidence ==========
        rl_mult = self.calculate_rl_confidence_multiplier(rl_confidence, rl_action)
        
        # ========== FACTOR 6: Asset Class Risk ==========
        asset_mult = self.ASSET_CLASS_RISK.get(asset_class.lower() if asset_class else 'finance', 1.0)
        
        # ========== FACTOR 7: Strategy Risk ==========
        strat_mult = self.STRATEGY_RISK.get(strategy, 1.0)
        
        # ========== FACTOR 8: Signal Strength ==========
        sentiment = signals.get('sentiment', 0.5)
        sentiment_strength = abs(sentiment - 0.5) * 2  # 0-1 scale
        sharp_alignment = signals.get('sharp_alignment', 0.5)
        price_uncertainty = signals.get('price_uncertainty', 0.5)
        
        # Signal strength drives position size variation
        signal_strength = (sentiment_strength * 0.3 + sharp_alignment * 0.4 + (1 - price_uncertainty) * 0.3)
        signal_mult = 0.5 + (signal_strength * 0.7)  # Range: 0.5 to 1.2
        
        # ========== ADAPTIVE BASE POSITION (Kelly + ATR + Fallback) ==========
        import math
        
        # Kelly gives us the edge-based fraction, ATR scales for risk
        kelly_atr_base = kelly_position * vol_mult
        
        # FALLBACK: If Kelly is too conservative (< min_trade_size), use signal-based sizing
        # This ensures we don't just hit minimum floor for all trades
        if kelly_atr_base < min_trade_size:
            # Use max_position scaled by signals and volatility as fallback
            # signal_strength 0.3-0.8 of max, vol_mult scales it further
            fallback_pct = 0.3 + (signal_strength * 0.5)  # 30-80% of max based on signals
            fallback_base = max_position_usd * fallback_pct * vol_mult
            kelly_atr_base = fallback_base
        
        # Apply signal strength to create variance within base
        signal_variance = 0.6 + (signal_strength * 0.8)  # 0.6x to 1.4x
        
        base_position = kelly_atr_base * signal_variance
        
        # ========== APPLY RISK MULTIPLIERS ==========
        # These reduce position for riskier conditions
        # USE GEOMETRIC MEAN instead of direct product to be less punitive
        # Direct product: 0.8 * 0.8 * 0.8 * 0.8 = 0.41 (too aggressive)
        # Geometric mean: (0.8 * 0.8 * 0.8 * 0.8)^(1/4) = 0.8 (fairer)
        risk_factors = [spread_mult, liquidity_mult, asset_mult, strat_mult]
        risk_product = 1.0
        for f in risk_factors:
            risk_product *= f
        risk_combined = risk_product ** (1 / len(risk_factors))  # Geometric mean
        
        # Apply RL confidence as a separate boost/reduction
        raw_position = base_position * risk_combined * rl_mult
        
        # ========== APPLY CONSTRAINTS ==========
        # Hard ceiling: never exceed max position or 10% of capital
        final_position = min(raw_position, max_position_usd)
        final_position = min(final_position, deployed_capital * 0.10)
        
        # Combined multiplier for logging (what we actually applied)
        if kelly_atr_base > 0:
            combined_mult = final_position / kelly_atr_base
        else:
            combined_mult = 1.0
        
        # Adaptive floor based on conviction
        # High liquidity + high RL confidence + strong signals = allow trade even if small
        conviction_score = (liquidity_mult * 0.3 + rl_mult * 0.3 + signal_mult * 0.4)
        
        # If position is below minimum but conviction is high, scale up to minimum
        if final_position < min_trade_size and conviction_score >= 0.7 and liquidity_mult >= 0.3:
            final_position = min_trade_size
        
        # ========== TRADING DECISION ==========
        should_trade = (
            final_position >= min_trade_size and 
            liquidity_mult > 0.1 and
            not (rl_action in ['WAIT', 'HOLD'] and rl_confidence < 0.3)
        )
        
        # Debug why trades are rejected
        if not should_trade:
            reject_reasons = []
            if final_position < min_trade_size:
                reject_reasons.append(f"size ${final_position:.2f} < ${min_trade_size}")
            if liquidity_mult <= 0.1:
                reject_reasons.append(f"liquidity_mult {liquidity_mult:.3f} <= 0.1")
            if rl_action in ['WAIT', 'HOLD'] and rl_confidence < 0.3:
                reject_reasons.append(f"RL {rl_action} with low conf {rl_confidence:.2f}")
            logger.info(f"[SIZING-REJECT] {', '.join(reject_reasons)}")
        
        return {
            'position_size': round(final_position, 2),
            'should_trade': should_trade,
            'sizing_breakdown': {
                'base_max_position': round(max_position_usd, 2),
                'min_trade_size': round(min_trade_size, 2),
                'kelly_fraction': round(kelly_size, 4),
                'kelly_position': round(kelly_position, 2),
                'kelly_atr_base': round(kelly_atr_base, 2),
                'base_position': round(base_position, 2),
                'raw_position': round(raw_position, 2),
                'liquidity_multiplier': round(liquidity_mult, 3),
                'volatility_multiplier': round(vol_mult, 3),
                'spread_multiplier': round(spread_mult, 3),
                'rl_confidence_multiplier': round(rl_mult, 3),
                'asset_class_multiplier': round(asset_mult, 3),
                'strategy_multiplier': round(strat_mult, 3),
                'signal_multiplier': round(signal_mult, 3),
                'signal_variance': round(signal_variance, 3),
                'risk_combined': round(risk_combined, 4),
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
