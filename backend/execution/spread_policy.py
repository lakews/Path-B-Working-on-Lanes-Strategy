"""
Centralized Spread Policy - Single Source of Truth for Spread Constants

This module centralizes all spread-related constants and EV calculations.
Used by both HFT and Alpha execution paths.

CRITICAL: All spread thresholds should be imported from here, not hardcoded.
NOTE: Default values can be overridden via Settings UI (spread_policy config).
"""
import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TradeType(Enum):
    MAKER = "maker"     # Provide liquidity, capture spread
    TAKER = "taker"     # Take liquidity, pay spread


# ============================================================================
# DEFAULT SPREAD CONSTANTS (can be overridden by config)
# ============================================================================
# Task 21: Import from centralized config for Single Source of Truth
try:
    from config import SPREAD_RULES, RISK_PARAMS
    DEFAULT_MAX_SPREAD_HFT = SPREAD_RULES['MAX_SPREAD_HFT']          # 12%
    DEFAULT_MAX_SPREAD_ALPHA = SPREAD_RULES['MAX_SPREAD_ALPHA']      # 5%
    DEFAULT_MAX_SPREAD_AGGRESSIVE = SPREAD_RULES['MAX_SPREAD_AGGRESSIVE']  # 3%
    DEFAULT_MIN_SPREAD_MAKER = SPREAD_RULES['MIN_SPREAD_MAKER']      # 0.5%
    DEFAULT_TAKER_FEE = RISK_PARAMS['TAKER_FEE']                     # 2%
    DEFAULT_MAKER_FEE = RISK_PARAMS['MAKER_FEE']                     # 0%
    DEFAULT_ADVERSE_SELECTION_COST = RISK_PARAMS['ADVERSE_SELECTION_COST']  # 0.5%
    DEFAULT_MAKER_SPREAD_CAPTURE_PCT = RISK_PARAMS['MAKER_SPREAD_CAPTURE']  # 50%
except ImportError:
    # Fallback to hardcoded values if config not available
    DEFAULT_MAX_SPREAD_HFT = 0.12           # 12% - Max for HFT maker orders
    DEFAULT_MAX_SPREAD_ALPHA = 0.05         # 5% - Max for Alpha directional trades
    DEFAULT_MAX_SPREAD_AGGRESSIVE = 0.03    # 3% - For aggressive taker entries
    DEFAULT_MIN_SPREAD_MAKER = 0.005        # 0.5% - Minimum for maker profitability
    DEFAULT_TAKER_FEE = 0.02                # 2% taker fee
    DEFAULT_MAKER_FEE = 0.0                 # No maker fee on Polymarket
    DEFAULT_ADVERSE_SELECTION_COST = 0.005  # 0.5% adverse selection cost
    DEFAULT_MAKER_SPREAD_CAPTURE_PCT = 0.50 # 50% spread capture

# Minimum spread thresholds (below this, market is too tight for profit)
MIN_SPREAD_FOR_EDGE = 0.01              # 1% - Minimum spread to have edge as maker

# Grid search bounds for strategy tuning
SPREAD_GRID_VALUES = [0.01, 0.02, 0.03, 0.05]  # Real-world Polymarket spread range


# Module-level variables that can be updated from config
MAX_SPREAD_HFT = DEFAULT_MAX_SPREAD_HFT
MAX_SPREAD_ALPHA = DEFAULT_MAX_SPREAD_ALPHA
MAX_SPREAD_AGGRESSIVE = DEFAULT_MAX_SPREAD_AGGRESSIVE
MIN_SPREAD_MAKER = DEFAULT_MIN_SPREAD_MAKER
MAKER_FEE = DEFAULT_MAKER_FEE
TAKER_FEE = DEFAULT_TAKER_FEE
MAKER_SPREAD_CAPTURE_PCT = DEFAULT_MAKER_SPREAD_CAPTURE_PCT
ADVERSE_SELECTION_COST = DEFAULT_ADVERSE_SELECTION_COST


def update_spread_policy_from_config(config: Dict):
    """Update module-level spread policy values from config."""
    global MAX_SPREAD_HFT, MAX_SPREAD_ALPHA, MAX_SPREAD_AGGRESSIVE
    global MIN_SPREAD_MAKER, TAKER_FEE, MAKER_SPREAD_CAPTURE_PCT, ADVERSE_SELECTION_COST
    
    spread_config = config.get('spread_policy', {})
    if spread_config:
        MAX_SPREAD_HFT = spread_config.get('max_spread_hft', DEFAULT_MAX_SPREAD_HFT)
        MAX_SPREAD_ALPHA = spread_config.get('max_spread_alpha', DEFAULT_MAX_SPREAD_ALPHA)
        MAX_SPREAD_AGGRESSIVE = spread_config.get('max_spread_aggressive', DEFAULT_MAX_SPREAD_AGGRESSIVE)
        MIN_SPREAD_MAKER = spread_config.get('min_spread_maker', DEFAULT_MIN_SPREAD_MAKER)
        MAKER_SPREAD_CAPTURE_PCT = spread_config.get('maker_spread_capture', DEFAULT_MAKER_SPREAD_CAPTURE_PCT)
        ADVERSE_SELECTION_COST = spread_config.get('adverse_selection_cost', DEFAULT_ADVERSE_SELECTION_COST)
        TAKER_FEE = spread_config.get('taker_fee', DEFAULT_TAKER_FEE)
        
        logger.info(
            f"Spread policy updated from config: "
            f"HFT={MAX_SPREAD_HFT:.0%}, Alpha={MAX_SPREAD_ALPHA:.0%}, "
            f"TakerFee={TAKER_FEE:.1%}"
        )


@dataclass
class EVContext:
    """Context for EV calculation."""
    spread: float
    edge: float
    trade_type: TradeType
    volatility: float = 0.05
    liquidity: float = 10000.0
    position_size: float = 100.0
    
    # Optional overrides
    fee_override: Optional[float] = None
    adverse_selection_override: Optional[float] = None


@dataclass
class EVResult:
    """Result of EV calculation."""
    ev: float
    is_profitable: bool
    breakdown: Dict[str, float]
    recommendation: str


class SpreadPolicy:
    """
    Centralized spread policy and EV calculations.
    
    Maker EV Formula:
        EV = (spread × spread_capture) - adverse_selection - fee
        
    Taker EV Formula:
        EV = edge - spread - fee
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize with optional config overrides."""
        self.config = config or {}
        
        # Allow config overrides
        self.max_spread_hft = self.config.get('max_spread_hft', MAX_SPREAD_HFT)
        self.max_spread_alpha = self.config.get('max_spread_alpha', MAX_SPREAD_ALPHA)
        self.min_spread_maker = self.config.get('min_spread_maker', MIN_SPREAD_MAKER)
        self.maker_fee = self.config.get('maker_fee', MAKER_FEE)
        self.taker_fee = self.config.get('taker_fee', TAKER_FEE)
        self.spread_capture = self.config.get('spread_capture', MAKER_SPREAD_CAPTURE_PCT)
        self.adverse_selection = self.config.get('adverse_selection', ADVERSE_SELECTION_COST)
    
    def validate_spread(
        self,
        spread: float,
        is_hft: bool = True,
        is_aggressive: bool = False
    ) -> Tuple[bool, str]:
        """
        Validate if spread is acceptable for trading.
        
        Args:
            spread: Current spread as decimal (e.g., 0.05 for 5%)
            is_hft: True for HFT strategy, False for Alpha
            is_aggressive: True for aggressive (high edge) entries
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if spread <= 0:
            return False, "invalid_spread_zero_or_negative"
        
        # Check minimum spread (too tight = no edge)
        if spread < self.min_spread_maker:
            return True, "tight_spread_taker_preferred"  # Valid but should taker instead
        
        # Check maximum spread based on strategy
        if is_aggressive:
            max_spread = MAX_SPREAD_AGGRESSIVE
        elif is_hft:
            max_spread = self.max_spread_hft
        else:
            max_spread = self.max_spread_alpha
        
        if spread > max_spread:
            return False, f"spread_too_wide_{spread:.2%}_max_{max_spread:.2%}"
        
        return True, "spread_acceptable"
    
    def calculate_maker_ev(self, ctx: EVContext) -> EVResult:
        """
        Calculate Expected Value for maker (limit) order.
        
        Maker EV = (spread × capture_rate) - adverse_selection - fee
        
        Key insight: As maker, we capture part of the spread but face
        adverse selection (getting filled when price moves against us).
        """
        fee = ctx.fee_override if ctx.fee_override is not None else self.maker_fee
        adverse = ctx.adverse_selection_override if ctx.adverse_selection_override is not None else self.adverse_selection
        
        # Spread captured (revenue)
        spread_revenue = ctx.spread * self.spread_capture
        
        # Costs
        adverse_cost = adverse * (1 + ctx.volatility)  # Higher vol = more adverse selection
        fee_cost = fee
        
        # Net EV per dollar
        ev_per_dollar = spread_revenue - adverse_cost - fee_cost
        
        # Total EV for position
        total_ev = ev_per_dollar * ctx.position_size
        
        breakdown = {
            'spread_revenue': spread_revenue,
            'adverse_selection_cost': adverse_cost,
            'fee_cost': fee_cost,
            'ev_per_dollar': ev_per_dollar,
            'total_ev': total_ev
        }
        
        is_profitable = ev_per_dollar > 0
        
        if is_profitable:
            recommendation = f"MAKER_PROFITABLE: EV=${total_ev:.2f} ({ev_per_dollar:.2%}/dollar)"
        else:
            recommendation = f"MAKER_UNPROFITABLE: EV=${total_ev:.2f}, consider TAKER"
        
        return EVResult(
            ev=total_ev,
            is_profitable=is_profitable,
            breakdown=breakdown,
            recommendation=recommendation
        )
    
    def calculate_taker_ev(self, ctx: EVContext) -> EVResult:
        """
        Calculate Expected Value for taker (market) order.
        
        Taker EV = edge - spread - fee
        
        Key insight: As taker, we pay the spread but execute immediately.
        Only profitable if our edge exceeds the cost.
        """
        fee = ctx.fee_override if ctx.fee_override is not None else self.taker_fee
        
        # Revenue from edge
        edge_revenue = ctx.edge
        
        # Costs
        spread_cost = ctx.spread  # Full spread as taker
        fee_cost = fee
        
        # Net EV per dollar
        ev_per_dollar = edge_revenue - spread_cost - fee_cost
        
        # Total EV for position
        total_ev = ev_per_dollar * ctx.position_size
        
        breakdown = {
            'edge_revenue': edge_revenue,
            'spread_cost': spread_cost,
            'fee_cost': fee_cost,
            'ev_per_dollar': ev_per_dollar,
            'total_ev': total_ev
        }
        
        is_profitable = ev_per_dollar > 0
        
        if is_profitable:
            recommendation = f"TAKER_PROFITABLE: EV=${total_ev:.2f} ({ev_per_dollar:.2%}/dollar)"
        else:
            recommendation = f"TAKER_UNPROFITABLE: EV=${total_ev:.2f}, need more edge"
        
        return EVResult(
            ev=total_ev,
            is_profitable=is_profitable,
            breakdown=breakdown,
            recommendation=recommendation
        )
    
    def validate_ev(
        self,
        ctx: EVContext,
        min_ev_per_dollar: float = 0.005
    ) -> Tuple[bool, EVResult, EVResult]:
        """
        Validate if trade has positive EV, comparing maker vs taker.
        
        Args:
            ctx: EV calculation context
            min_ev_per_dollar: Minimum EV required (default 0.5%)
            
        Returns:
            Tuple of (is_valid, maker_result, taker_result)
        """
        maker_ev = self.calculate_maker_ev(ctx)
        taker_ev = self.calculate_taker_ev(ctx)
        
        # Check if either strategy is profitable
        maker_valid = maker_ev.ev > min_ev_per_dollar * ctx.position_size
        taker_valid = taker_ev.ev > min_ev_per_dollar * ctx.position_size
        
        is_valid = maker_valid or taker_valid
        
        return is_valid, maker_ev, taker_ev
    
    def get_optimal_trade_type(self, ctx: EVContext) -> Tuple[TradeType, EVResult]:
        """
        Determine optimal trade type (maker vs taker) for given context.
        
        Returns:
            Tuple of (optimal_type, result)
        """
        maker_ev = self.calculate_maker_ev(ctx)
        taker_ev = self.calculate_taker_ev(ctx)
        
        # Compare EVs
        if maker_ev.ev >= taker_ev.ev and maker_ev.is_profitable:
            return TradeType.MAKER, maker_ev
        elif taker_ev.is_profitable:
            return TradeType.TAKER, taker_ev
        elif maker_ev.ev >= taker_ev.ev:
            return TradeType.MAKER, maker_ev
        else:
            return TradeType.TAKER, taker_ev


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_max_spread(is_hft: bool = True) -> float:
    """Get maximum allowed spread for strategy type."""
    return MAX_SPREAD_HFT if is_hft else MAX_SPREAD_ALPHA


def get_spread_grid() -> list:
    """Get spread values for grid search optimization."""
    return SPREAD_GRID_VALUES.copy()


def quick_ev_check(
    spread: float,
    edge: float,
    position_size: float = 100.0
) -> Tuple[bool, str]:
    """
    Quick EV check without full calculation.
    
    Returns (is_profitable, recommendation)
    """
    policy = SpreadPolicy()
    ctx = EVContext(
        spread=spread,
        edge=edge,
        trade_type=TradeType.TAKER,
        position_size=position_size
    )
    
    _, maker_ev, taker_ev = policy.validate_ev(ctx)
    
    if maker_ev.is_profitable and taker_ev.is_profitable:
        if maker_ev.ev > taker_ev.ev:
            return True, f"MAKER preferred (EV: ${maker_ev.ev:.2f} vs ${taker_ev.ev:.2f})"
        else:
            return True, f"TAKER preferred (EV: ${taker_ev.ev:.2f} vs ${maker_ev.ev:.2f})"
    elif maker_ev.is_profitable:
        return True, f"MAKER only (EV: ${maker_ev.ev:.2f})"
    elif taker_ev.is_profitable:
        return True, f"TAKER only (EV: ${taker_ev.ev:.2f})"
    else:
        return False, f"NO_TRADE: Maker EV=${maker_ev.ev:.2f}, Taker EV=${taker_ev.ev:.2f}"
