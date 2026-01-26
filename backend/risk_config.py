"""
APEX TRADER - Risk Configuration (Single Source of Truth)
=========================================================

Task 21: Dual-Zone Risk Architecture
Task 23: Unified Portfolio Manager - Consolidated ALL sizing constants here

This file defines ALL risk and sizing parameters for the trading system.
No other file should contain hardcoded spread/risk/sizing values.

Two Trading Zones with Different Physics:
1. CONVEXITY ZONE ($0.01-$0.09): Tick-based spreads for Gamma Scalping
2. CORE ZONE ($0.10+): Percentage-based spreads for Directional Alpha

Usage:
    from risk_config import RISK, MarketRegime, classify_market_regime
"""

from typing import Tuple, Dict
from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    """
    Single Source of Truth for ALL risk and sizing parameters.
    
    Hierarchy of Safety:
    1. Allocated Capital (virtual sub-account)
    2. Price Zones (hard override based on price)
    3. Strategy Regime (Alpha/HFT/Gamma)
    4. Liquidity (never consume >10% of depth)
    5. Exposure (sector and event caps)
    
    Two distinct trading zones with different risk physics:
    - Whale Zone: Cheap assets where we accumulate convexity
    - Core Zone: Standard assets where we trade directionally
    """
    
    # =========================================================================
    # CAPITAL ALLOCATION (Task 23)
    # =========================================================================
    ALLOCATED_CAPITAL_PCT: float = 80.0    # 80% of wallet is "deployed"
    CASH_BUFFER_PCT: float = 5.0           # 5% reserve for gas/fees
    
    # =========================================================================
    # GLOBAL SAFETY PARAMETERS
    # =========================================================================
    STOP_LOSS_PCT: float = 0.15            # 15% stop loss per trade
    MAX_DRAWDOWN_PCT: float = 5.0          # 5% max portfolio drawdown
    KILL_SWITCH_LOW: float = 0.03          # Don't trade below 3 cents
    KILL_SWITCH_HIGH: float = 0.97         # Don't trade above 97 cents
    
    # =========================================================================
    # ZONE THRESHOLD
    # =========================================================================
    PRICE_ZONE_THRESHOLD: float = 0.10     # Below = Whale, Above = Core
    
    # =========================================================================
    # ZONE 1: CONVEXITY / WHALE ZONE ($0.03 - $0.09)
    # =========================================================================
    # Strategy: Volatility Accumulation / Gamma Scalping
    # Logic: Percentage spreads are IRRELEVANT here. We care about absolute ticks.
    # 
    # Example: Asset at $0.02 with Bid=$0.01, Ask=$0.04
    #   - Percentage spread = 100% (looks terrible!)
    #   - Tick spread = 3 cents (actually tradeable)
    #   - If this goes to $0.50, we make 25x on a 3 cent risk
    
    WHALE_PRICE_CEILING: float = 0.10      # Prices below this are "Whale Zone"
    WHALE_MAX_SPREAD_CENTS: float = 0.03   # Max 3 cent absolute spread allowed
    WHALE_MIN_LIQUIDITY: float = 500.0     # Lower liquidity threshold ($500)
    WHALE_MIN_VOLUME_24H: float = 500.0    # Lower volume threshold ($500)
    WHALE_MAX_USD: float = 15.0            # HARD CAP: $15 per whale trade
    WHALE_MAX_PCT: float = 0.01            # HARD CAP: 1% of deployed capital
    
    # Aliases for backward compatibility
    @property
    def WHALE_MAX_POSITION(self) -> float:
        return self.WHALE_MAX_USD
    
    @property
    def WHALE_MAX_POSITION_PCT(self) -> float:
        return self.WHALE_MAX_PCT * 100  # Return as percentage (1.0)
    
    # =========================================================================
    # ZONE 2: CORE ALPHA ZONE ($0.10+)
    # =========================================================================
    # Strategy: Directional Prediction & Market Making
    # Logic: We pay for probability. We demand tight PERCENTAGE spreads.
    #
    # Example: Asset at $0.50 with Bid=$0.49, Ask=$0.51
    #   - Tick spread = 2 cents
    #   - Percentage spread = 4% (acceptable for maker)
    
    CORE_TAKER_SPREAD_PCT: float = 0.02    # < 2%: Safe to Take Liquidity (Alpha)
    CORE_MAKER_SPREAD_PCT: float = 0.10    # 2% - 10%: Safe to Make Liquidity (HFT)
    CORE_ZOMBIE_SPREAD_PCT: float = 0.12   # > 12%: Market is dead
    CORE_MIN_LIQUIDITY: float = 1000.0     # Higher liquidity threshold ($1K)
    CORE_MIN_VOLUME_24H: float = 1000.0    # Higher volume threshold ($1K)
    CORE_MAX_USD: float = 100.0            # HARD CAP: $100 per core trade
    CORE_MAX_PCT: float = 0.03             # HARD CAP: 3% of deployed capital
    
    # Aliases for backward compatibility
    @property
    def CORE_MAX_POSITION(self) -> float:
        return self.CORE_MAX_USD
    
    @property
    def CORE_MAX_POSITION_PCT(self) -> float:
        return self.CORE_MAX_PCT * 100  # Return as percentage (3.0)
    
    # =========================================================================
    # STRATEGY MATH (Task 23)
    # =========================================================================
    KELLY_SCALING_FACTOR: float = 0.25     # Quarter Kelly (conservative)
    MIN_KELLY_FRACTION: float = 0.10       # Floor for Kelly
    MAX_KELLY_FRACTION: float = 0.50       # Ceiling for Kelly
    HFT_UNIT_PCT: float = 0.02             # Maker orders = 2% of deployed
    
    # Aliases for backward compatibility
    @property
    def KELLY_FRACTION(self) -> float:
        return self.KELLY_SCALING_FACTOR
    
    # =========================================================================
    # LIQUIDITY CONSTRAINTS (Task 23)
    # =========================================================================
    MAX_LIQUIDITY_CONSUMPTION: float = 0.10  # Never take >10% of order book depth
    
    # =========================================================================
    # EXPOSURE LIMITS (Task 23)
    # =========================================================================
    MAX_EVENT_EXPOSURE_PCT: float = 0.15   # Max 15% per correlated event
    
    # =========================================================================
    # SECTOR CAPS (Task 23 - Consolidated from polymarket_position_sizer.py)
    # =========================================================================
    SECTOR_LIMITS: Dict[str, float] = field(default_factory=lambda: {
        'politics': 0.25,       # 25% max in politics
        'sports': 0.30,         # 30% max in sports
        'crypto': 0.20,         # 20% max in crypto
        'finance': 0.20,        # 20% max in finance
        'entertainment': 0.15,  # 15% max in entertainment
        'science': 0.15,        # 15% max in science
        'conflict': 0.10,       # 10% max in war/conflict
        'social': 0.10,         # 10% max in social/tweets
        'unknown': 0.15,        # 15% default for uncategorized
    })
    
    # =========================================================================
    # TRADE FILTERS
    # =========================================================================
    MIN_TRADE_AMOUNT: float = 2.0          # Dust filter: minimum $2 trade
    MIN_BET_FLOOR: float = 5.0             # Practical minimum: $5
    
    # =========================================================================
    # FEE STRUCTURE (Polymarket)
    # =========================================================================
    TAKER_FEE: float = 0.02                # 2% taker fee
    MAKER_FEE: float = 0.00                # No maker fee
    ADVERSE_SELECTION_COST: float = 0.005  # 0.5% adverse selection
    MAKER_SPREAD_CAPTURE: float = 0.50     # Assume 50% spread capture as maker
    
    # =========================================================================
    # QUALITY FILTERS (Pre-Flight)
    # =========================================================================
    MIN_PRICE_BAND: float = 0.03           # Skip if price < 3% (kill switch)
    MAX_PRICE_BAND: float = 0.97           # Skip if price > 97% (kill switch)
    TOP_N_MARKETS: int = 50                # Process top 50 by volume
    
    # =========================================================================
    # POSITION SIZER CONFIG (from polymarket_position_sizer.py)
    # =========================================================================
    UTILIZATION_EXPONENT: float = 1.5      # Brake exponent
    UTILIZATION_HARD_STOP: float = 0.95    # Stop at 95% utilization
    EDGE_RETENTION_PCT: float = 0.20       # Allow 20% edge erosion from slippage
    TIME_PENALTY_MAX_DAYS: int = 90        # 90 days = max penalty
    TIME_PENALTY_FLOOR: float = 0.50       # Minimum 0.5x for long-dated bets
    EVENT_SIMILARITY_THRESHOLD: float = 0.60  # Word overlap for same event
    
    # =========================================================================
    # CONCURRENT POSITION LIMITS
    # =========================================================================
    MAX_OPEN_POSITIONS: int = 50           # Max concurrent positions


# Global instance
RISK = RiskConfig()


# ============================================================================
# MARKET REGIME CLASSIFICATION
# ============================================================================

class MarketRegime:
    """Market regime enumeration for dual-zone trading."""
    # Zone 1: Convexity (Whale Zone)
    CONVEXITY_OPPORTUNITY = "CONVEXITY_OPPORTUNITY"  # Cheap asset, tight tick spread
    
    # Zone 2: Core (Standard Zone)
    TAKER_TIGHT = "TAKER_TIGHT"     # Tight % spread, safe for taker
    MAKER_WIDE = "MAKER_WIDE"       # Wide % spread, maker opportunity
    
    # Invalid
    ZOMBIE = "ZOMBIE"               # Dead/illiquid, skip


def classify_market_regime(
    best_bid: float,
    best_ask: float,
    volume_24h: float = 0,
    liquidity: float = 0
) -> Tuple[str, Dict]:
    """
    Classify market into trading regime based on DUAL-ZONE architecture.
    
    Zone 1 (Convexity/Whale): Price < $0.10
        - Uses ABSOLUTE TICK SPREAD (cents, not percentage)
        - 3 cent spread on a 2 cent asset = tradeable!
        - Strategy: Gamma scalping, volatility accumulation
        
    Zone 2 (Core/Alpha): Price >= $0.10
        - Uses PERCENTAGE SPREAD
        - 2% spread = tight (taker safe)
        - 10% spread = wide (maker only)
        - Strategy: Directional alpha, market making
    
    Args:
        best_bid: Best bid price (0-1)
        best_ask: Best ask price (0-1)
        volume_24h: 24-hour trading volume in USD
        liquidity: Current liquidity in USD
        
    Returns:
        (regime: str, diagnostics: Dict)
    """
    # Calculate spreads
    spread_cents = best_ask - best_bid  # Absolute spread in dollars/probability
    mid_price = (best_bid + best_ask) / 2
    spread_pct = spread_cents / max(mid_price, 0.001)  # Relative spread
    
    # Build diagnostics
    diagnostics = {
        'best_bid': round(best_bid, 4),
        'best_ask': round(best_ask, 4),
        'mid_price': round(mid_price, 4),
        'spread_cents': round(spread_cents, 4),
        'spread_pct': round(spread_pct, 4),
        'volume_24h': round(volume_24h, 2),
        'liquidity': round(liquidity, 2),
        'zone': None,
        'reject_reason': None,
    }
    
    # =========================================================================
    # KILL SWITCH: Extreme prices
    # =========================================================================
    if mid_price < RISK.KILL_SWITCH_LOW or mid_price > RISK.KILL_SWITCH_HIGH:
        diagnostics['reject_reason'] = f'price {mid_price:.4f} outside kill switch ({RISK.KILL_SWITCH_LOW}-{RISK.KILL_SWITCH_HIGH})'
        return MarketRegime.ZOMBIE, diagnostics
    
    # =========================================================================
    # ZONE 1: CONVEXITY / WHALE ZONE (Price < $0.10)
    # =========================================================================
    # In this zone, percentage spreads are meaningless.
    # A 100% spread on a $0.02 asset = 2 cents = totally tradeable!
    # We use ABSOLUTE TICK SPREAD instead.
    
    if mid_price < RISK.WHALE_PRICE_CEILING:
        diagnostics['zone'] = 'WHALE'
        diagnostics['thresholds'] = {
            'max_spread_cents': RISK.WHALE_MAX_SPREAD_CENTS,
            'min_liquidity': RISK.WHALE_MIN_LIQUIDITY,
            'min_volume': RISK.WHALE_MIN_VOLUME_24H,
        }
        
        # Check tick spread (absolute)
        if spread_cents > RISK.WHALE_MAX_SPREAD_CENTS:
            diagnostics['reject_reason'] = f'tick spread {spread_cents:.4f} > max {RISK.WHALE_MAX_SPREAD_CENTS:.4f}'
            return MarketRegime.ZOMBIE, diagnostics
        
        # Check volume (lower threshold for whale zone)
        if volume_24h < RISK.WHALE_MIN_VOLUME_24H:
            diagnostics['reject_reason'] = f'volume ${volume_24h:.0f} < min ${RISK.WHALE_MIN_VOLUME_24H:.0f}'
            return MarketRegime.ZOMBIE, diagnostics
        
        # CONVEXITY OPPORTUNITY: Cheap asset with tight tick spread
        diagnostics['strategy'] = 'gamma_scalp'
        diagnostics['max_position'] = RISK.WHALE_MAX_USD
        return MarketRegime.CONVEXITY_OPPORTUNITY, diagnostics
    
    # =========================================================================
    # ZONE 2: CORE ALPHA ZONE (Price >= $0.10)
    # =========================================================================
    # Standard percentage-based spread logic for directional trading.
    
    diagnostics['zone'] = 'CORE'
    diagnostics['thresholds'] = {
        'taker_spread': RISK.CORE_TAKER_SPREAD_PCT,
        'maker_spread': RISK.CORE_MAKER_SPREAD_PCT,
        'zombie_spread': RISK.CORE_ZOMBIE_SPREAD_PCT,
        'min_liquidity': RISK.CORE_MIN_LIQUIDITY,
        'min_volume': RISK.CORE_MIN_VOLUME_24H,
    }
    
    # Check volume (higher threshold for core zone)
    if volume_24h < RISK.CORE_MIN_VOLUME_24H:
        diagnostics['reject_reason'] = f'volume ${volume_24h:.0f} < min ${RISK.CORE_MIN_VOLUME_24H:.0f}'
        return MarketRegime.ZOMBIE, diagnostics
    
    # ZOMBIE: Spread too wide
    if spread_pct > RISK.CORE_ZOMBIE_SPREAD_PCT:
        diagnostics['reject_reason'] = f'spread {spread_pct:.2%} > zombie {RISK.CORE_ZOMBIE_SPREAD_PCT:.0%}'
        return MarketRegime.ZOMBIE, diagnostics
    
    # MAKER_WIDE: Wide spread (2-12%), maker opportunity
    if spread_pct > RISK.CORE_TAKER_SPREAD_PCT:
        diagnostics['strategy'] = 'maker_limit_order'
        diagnostics['max_position'] = RISK.CORE_MAX_USD
        return MarketRegime.MAKER_WIDE, diagnostics
    
    # TAKER_TIGHT: Tight spread (<2%), safe to cross
    diagnostics['strategy'] = 'taker_directional'
    diagnostics['max_position'] = RISK.CORE_MAX_USD
    return MarketRegime.TAKER_TIGHT, diagnostics


def get_zone_parameters(mid_price: float) -> Dict:
    """
    Get zone-specific parameters based on price.
    
    Args:
        mid_price: Current mid-price of the asset
        
    Returns:
        Dict with zone-specific thresholds
    """
    if mid_price < RISK.WHALE_PRICE_CEILING:
        return {
            'zone': 'WHALE',
            'min_liquidity': RISK.WHALE_MIN_LIQUIDITY,
            'min_volume': RISK.WHALE_MIN_VOLUME_24H,
            'max_position': RISK.WHALE_MAX_USD,
            'max_position_pct': RISK.WHALE_MAX_PCT,
            'spread_type': 'absolute_cents',
            'max_spread': RISK.WHALE_MAX_SPREAD_CENTS,
        }
    else:
        return {
            'zone': 'CORE',
            'min_liquidity': RISK.CORE_MIN_LIQUIDITY,
            'min_volume': RISK.CORE_MIN_VOLUME_24H,
            'max_position': RISK.CORE_MAX_USD,
            'max_position_pct': RISK.CORE_MAX_PCT,
            'spread_type': 'percentage',
            'max_spread': RISK.CORE_MAKER_SPREAD_PCT,
        }


def is_spread_acceptable(
    spread_cents: float,
    spread_pct: float,
    mid_price: float,
    is_hft: bool = False
) -> Tuple[bool, str]:
    """
    Check if spread is acceptable for trading.
    
    Args:
        spread_cents: Absolute spread (ask - bid)
        spread_pct: Percentage spread
        mid_price: Mid-price of asset
        is_hft: True if HFT strategy (wider tolerance)
        
    Returns:
        (acceptable: bool, reason: str)
    """
    # Whale zone: Check absolute spread
    if mid_price < RISK.WHALE_PRICE_CEILING:
        if spread_cents <= RISK.WHALE_MAX_SPREAD_CENTS:
            return True, f"whale_zone: tick_spread {spread_cents:.4f} <= {RISK.WHALE_MAX_SPREAD_CENTS}"
        return False, f"whale_zone: tick_spread {spread_cents:.4f} > {RISK.WHALE_MAX_SPREAD_CENTS}"
    
    # Core zone: Check percentage spread
    max_spread = RISK.CORE_ZOMBIE_SPREAD_PCT if is_hft else RISK.CORE_MAKER_SPREAD_PCT
    if spread_pct <= max_spread:
        return True, f"core_zone: pct_spread {spread_pct:.2%} <= {max_spread:.0%}"
    return False, f"core_zone: pct_spread {spread_pct:.2%} > {max_spread:.0%}"


def get_deployed_capital(wallet_balance: float) -> float:
    """Calculate deployed capital from wallet balance."""
    return wallet_balance * (RISK.ALLOCATED_CAPITAL_PCT / 100)
