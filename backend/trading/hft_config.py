"""
HFT ENGINE V2 - CONFIGURATION
==============================

Configuration for the High-Frequency Trading Engine V2.
Defines all thresholds, multipliers, and allocations for the 5 HFT sub-strategies.

MongoDB-Only Architecture (NO Redis)
"""

from enum import Enum
from typing import Dict


class NewsStrength(Enum):
    """News strength classification based on Bayes Factor"""
    PAUSE = "PAUSE"       # BF >= 10.0 - Skip entire cycle
    EXTREME = "EXTREME"   # BF 5.0-10.0 - High impact news
    CAUTION = "CAUTION"   # BF 3.0-5.0 - Moderate impact
    NORMAL = "NORMAL"     # BF < 3.0 - No significant news


class HFTMode(Enum):
    """The 5 HFT sub-strategies"""
    DELTA_NEUTRAL = "delta_neutral"
    VOLATILITY_EXPLOIT = "volatility_exploit"
    EXTREME_SPREAD = "extreme_spread"
    SHARP_FOLLOWING = "sharp_following"
    LIQUIDITY_PROVISION = "liquidity_provision"


class HFTConfig:
    """
    HFT Engine V2 Configuration
    
    All thresholds, multipliers, and allocations for the 5 HFT sub-strategies.
    """
    
    # =========================================================================
    # NEWS STRENGTH THRESHOLDS (Based on Bayes Factor from PATH A signals)
    # =========================================================================
    PAUSE_BF = 10.0      # BF >= 10.0 → Skip entire cycle
    EXTREME_BF = 5.0     # BF 5.0-10.0 → EXTREME mode
    CAUTION_BF = 3.0     # BF 3.0-5.0 → CAUTION mode
    # BF < 3.0 → NORMAL mode
    
    # =========================================================================
    # SPREAD MULTIPLIERS (Applied based on news strength)
    # =========================================================================
    SPREAD_MULTIPLIERS: Dict[str, float] = {
        'NORMAL': 1.0,    # No adjustment
        'CAUTION': 1.3,   # Widen spreads 30%
        'EXTREME': 2.5,   # Widen spreads 150%
        'PAUSE': 0.0      # No trading
    }
    
    # =========================================================================
    # POSITION MULTIPLIERS (Applied based on news strength)
    # =========================================================================
    POSITION_MULTIPLIERS: Dict[str, float] = {
        'NORMAL': 1.0,    # No adjustment
        'CAUTION': 0.75,  # Reduce position 25%
        'EXTREME': 0.5,   # Reduce position 50%
        'PAUSE': 0.0      # No trading
    }
    
    # =========================================================================
    # CAPITAL ALLOCATION ACROSS 5 SUB-STRATEGIES (Must sum to 1.0)
    # =========================================================================
    SUB_STRATEGY_ALLOCATION: Dict[str, float] = {
        'delta_neutral': 0.35,        # 35% - Market making
        'volatility_exploit': 0.10,   # 10% - Mean reversion at extremes
        'extreme_spread': 0.15,       # 15% - Wide spreads at extremes
        'sharp_following': 0.20,      # 20% - Follow sharp traders
        'liquidity_provision': 0.20   # 20% - Standing quotes on high-volume
    }
    
    # =========================================================================
    # PRICE ZONES (Determines which strategy to use)
    # =========================================================================
    ZONES = {
        'extreme_low': (0.0, 0.10),    # Volatility exploit, extreme spread
        'standard': (0.10, 0.90),      # Delta neutral, sharp following, liquidity
        'extreme_high': (0.90, 1.0)    # Volatility exploit, extreme spread
    }
    
    # =========================================================================
    # STRATEGY-SPECIFIC PARAMETERS
    # =========================================================================
    
    # Delta-Neutral Market Making
    DELTA_NEUTRAL_BASE_SPREAD = 0.02   # 2% base spread
    DELTA_NEUTRAL_MIN_SPREAD = 0.005   # 0.5% minimum
    DELTA_NEUTRAL_CYCLE_MS = 500       # 500ms cycles
    
    # Volatility Exploitation
    VOLATILITY_MIN_SCORE = 0.70        # Minimum volatility score to enter
    VOLATILITY_BASE_POSITION = 50      # Base position size
    VOLATILITY_CYCLE_MS = 30000        # 30-second assessment
    
    # Extreme Spread Capture
    EXTREME_SPREAD_BASE = 0.01         # 1% base spread
    EXTREME_SPREAD_MULTIPLIER = 5.0    # 5x multiplier (up to 12.5x with news)
    EXTREME_SPREAD_MAX = 0.15          # 15% cap
    EXTREME_SPREAD_BASE_POSITION = 25  # Smaller position for risk
    
    # Sharp Trader Following
    SHARP_MIN_ZSCORE = 2.0             # Minimum z-score for significance
    SHARP_FOLLOW_SCALE = 0.5           # Follow 50% of sharp size
    SHARP_CYCLE_MS = 100               # 75-100ms (faster than normal)
    SHARP_LEAN_OFFSET = 0.002          # 0.2% lean toward sharp direction
    
    # Liquidity Provision
    LIQUIDITY_MIN_VOLUME = 50000       # $50k minimum daily volume
    LIQUIDITY_QUOTE_LEVELS = 5         # Quote at 5 price levels
    LIQUIDITY_BASE_SPREAD = 0.005      # 0.5% tight spread
    LIQUIDITY_SIZE_PER_LEVEL = 50      # $50 per level
    
    # =========================================================================
    # GLOBAL CONSTRAINTS (MUST RESPECT)
    # =========================================================================
    MAX_POSITION_PCT = 0.03            # 3% max position cap
    KELLY_FRACTION = 0.25              # 25% Kelly sizing
    TARGET_LATENCY_MS = 100            # Target < 100ms per cycle
    
    # =========================================================================
    # HFT LANE ALLOCATION (From total capital)
    # =========================================================================
    HFT_LANE_ALLOCATION = 0.35         # 35% of total capital to HFT lane
    
    # =========================================================================
    # EXECUTION MODE (Paper vs Live)
    # =========================================================================
    LIVE_MODE = False  # Switch to True for live two-sided market making
    
    # =========================================================================
    # DIRECTION DETERMINATION
    # =========================================================================
    EDGE_THRESHOLD = 0.02              # 2% minimum edge to take position
    PATH_A_OVERRIDE_BF = 5.0           # BF >= 5 allows PATH A to override HFT Math direction
    
    # =========================================================================
    # DRIFT DETECTION (PATH B staleness)
    # =========================================================================
    MAX_DRIFT_PCT = 0.05               # 5% max drift before PATH B price considered stale
    
    # =========================================================================
    # STRATEGY CLASSIFICATION
    # =========================================================================
    # Market making strategies: profit from spread (two-sided in live mode)
    MARKET_MAKING_STRATEGIES = ['delta_neutral', 'extreme_spread', 'liquidity_provision']
    
    # Directional strategies: profit from price movement (single-sided)
    DIRECTIONAL_STRATEGIES = ['volatility_exploit', 'sharp_following']
    
    # =========================================================================
    # MEAN REVERSION THRESHOLDS (for VOLATILITY_EXPLOIT)
    # =========================================================================
    MEAN_REVERSION_LOW = 0.15          # Below this, expect reversion up
    MEAN_REVERSION_HIGH = 0.85         # Above this, expect reversion down
    
    # =========================================================================
    # ORDER FLOW IMBALANCE (for LIQUIDITY_PROVISION)
    # =========================================================================
    ORDER_FLOW_IMBALANCE_RATIO = 1.2   # 20% imbalance triggers direction


def get_news_strength(bayes_factor: float) -> NewsStrength:
    """
    Classify news strength based on Bayes Factor.
    
    Args:
        bayes_factor: The Bayes Factor from PATH A signal
        
    Returns:
        NewsStrength enum value
    """
    if bayes_factor >= HFTConfig.PAUSE_BF:
        return NewsStrength.PAUSE
    elif bayes_factor >= HFTConfig.EXTREME_BF:
        return NewsStrength.EXTREME
    elif bayes_factor >= HFTConfig.CAUTION_BF:
        return NewsStrength.CAUTION
    else:
        return NewsStrength.NORMAL


def get_multipliers(news_strength: NewsStrength) -> Dict[str, float]:
    """
    Get spread and position multipliers for a given news strength.
    
    Args:
        news_strength: NewsStrength enum value
        
    Returns:
        Dict with 'spread_mult' and 'position_mult'
    """
    strength_name = news_strength.value
    return {
        'spread_mult': HFTConfig.SPREAD_MULTIPLIERS.get(strength_name, 1.0),
        'position_mult': HFTConfig.POSITION_MULTIPLIERS.get(strength_name, 1.0)
    }


def get_price_zone(price: float) -> str:
    """
    Determine price zone for strategy selection.
    
    Args:
        price: Current market price (0.0 to 1.0)
        
    Returns:
        Zone name: 'extreme_low', 'standard', or 'extreme_high'
    """
    if price <= HFTConfig.ZONES['extreme_low'][1]:
        return 'extreme_low'
    elif price >= HFTConfig.ZONES['extreme_high'][0]:
        return 'extreme_high'
    else:
        return 'standard'
