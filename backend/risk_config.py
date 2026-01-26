"""
APEX TRADER - Risk Configuration (Single Source of Truth)
=========================================================

Task 21: Dual-Zone Risk Architecture
Task 23: Unified Portfolio Manager - Consolidated ALL sizing constants here
Task 23b: Made all parameters configurable via Settings UI

This file defines ALL risk and sizing parameters for the trading system.
No other file should contain hardcoded spread/risk/sizing values.

Two Trading Zones with Different Physics:
1. CONVEXITY ZONE ($0.01-$0.09): Tick-based spreads for Gamma Scalping
2. CORE ZONE ($0.10+): Percentage-based spreads for Directional Alpha

Usage:
    from risk_config import RISK, MarketRegime, classify_market_regime
    
    # To reload from database:
    await RISK.load_from_db()
"""

import logging
from typing import Tuple, Dict, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# =============================================================================
# DEFAULT VALUES (Used when resetting or no DB config exists)
# =============================================================================

DEFAULTS = {
    # Capital Allocation
    'ALLOCATED_CAPITAL_PCT': 80.0,
    'CASH_BUFFER_PCT': 5.0,
    
    # Global Safety
    'STOP_LOSS_PCT': 0.15,
    'MAX_DRAWDOWN_PCT': 5.0,
    'KILL_SWITCH_LOW': 0.03,
    'KILL_SWITCH_HIGH': 0.97,
    
    # Zone Threshold
    'PRICE_ZONE_THRESHOLD': 0.10,
    
    # Whale Zone
    'WHALE_PRICE_CEILING': 0.10,
    'WHALE_MAX_SPREAD_CENTS': 0.03,
    'WHALE_MIN_LIQUIDITY': 500.0,
    'WHALE_MIN_VOLUME_24H': 500.0,
    'WHALE_MAX_USD': 15.0,
    'WHALE_MAX_PCT': 0.01,
    
    # Core Zone
    'CORE_TAKER_SPREAD_PCT': 0.02,
    'CORE_MAKER_SPREAD_PCT': 0.10,
    'CORE_ZOMBIE_SPREAD_PCT': 0.12,
    'CORE_MIN_LIQUIDITY': 1000.0,
    'CORE_MIN_VOLUME_24H': 1000.0,
    'CORE_MAX_USD': 100.0,
    'CORE_MAX_PCT': 0.03,
    
    # Strategy Math
    'KELLY_SCALING_FACTOR': 0.25,
    'MIN_KELLY_FRACTION': 0.10,
    'MAX_KELLY_FRACTION': 0.50,
    'HFT_UNIT_PCT': 0.02,
    
    # Liquidity
    'MAX_LIQUIDITY_CONSUMPTION': 0.10,
    
    # Exposure
    'MAX_EVENT_EXPOSURE_PCT': 0.15,
    
    # Sector Limits
    'SECTOR_LIMITS': {
        'politics': 0.25,
        'sports': 0.30,
        'crypto': 0.20,
        'finance': 0.20,
        'entertainment': 0.15,
        'science': 0.15,
        'conflict': 0.10,
        'social': 0.10,
        'unknown': 0.15,
    },
    
    # Trade Filters
    'MIN_TRADE_AMOUNT': 2.0,
    'MIN_BET_FLOOR': 5.0,
    
    # Fees
    'TAKER_FEE': 0.02,
    'MAKER_FEE': 0.00,
    'ADVERSE_SELECTION_COST': 0.005,
    'MAKER_SPREAD_CAPTURE': 0.50,
    
    # Quality Filters
    'MIN_PRICE_BAND': 0.03,
    'MAX_PRICE_BAND': 0.97,
    'TOP_N_MARKETS': 50,
    
    # Position Sizer
    'UTILIZATION_EXPONENT': 1.5,
    'UTILIZATION_HARD_STOP': 0.95,
    'EDGE_RETENTION_PCT': 0.20,
    'TIME_PENALTY_MAX_DAYS': 90,
    'TIME_PENALTY_FLOOR': 0.50,
    'EVENT_SIMILARITY_THRESHOLD': 0.60,
    
    # Concurrent Limits
    'MAX_OPEN_POSITIONS': 50,
}


# =============================================================================
# EXIT ENGINE CONFIGURATION (Task 24: Alpha-State Exit Engine)
# =============================================================================
# Hierarchical Exit Engine respecting: State > Strategy > Asset Class > Zone
# Replaces legacy fixed TP/SL with state-dependent logic

# 1. Global Safety Defaults
EXIT_GLOBAL_SETTINGS = {
    'whale_threshold_price': 0.10,    # Entries below this are "Whales"
    'max_spread_pct': 0.10,           # 10% spread tolerance (Polymarket is illiquid)
    'expiry_guard_hours': 2.0,        # Force close losing trades 2h before expiry
    'min_trade_size_usd': 2.00,       # Minimum sell size to avoid API dust errors
    'free_ride_floor': 0.02,          # Free ride stop loss floor ($0.02)
    'free_ride_ceiling': 0.98,        # Free ride take profit ceiling ($0.98)
}

# 2. Strategy Baselines (The "Class" Logic)
EXIT_STRATEGY_CONFIG = {
    'arbitrage': {
        'type': 'mechanical',
        'action': 'CLOSE_ALL',        # Mechanical trades always exit fully
        'tp_pct': 0.02,               # +2% Gain
        'sl_pct': 0.02,               # -2% Loss
        'max_hours': 6,               # Time limit
    },
    'delta_neutral': {
        'type': 'mechanical',
        'action': 'CLOSE_ALL',
        'tp_pct': 0.015,              # +1.5% Gain
        'sl_pct': 0.015,              # -1.5% Loss
        'max_hours': 4,
    },
    'volatility_exploitation': {
        'type': 'mechanical',
        'action': 'CLOSE_ALL',
        'tp_pct': 0.05,               # +5% Gain
        'sl_pct': 0.05,               # -5% Loss
        'max_hours': 24,
    },
    'alpha_directional': {
        'type': 'complex',            # Uses Asset Modifiers
        'action': 'FREE_ROLL',        # Default action is to Sell Principal
        'profit_trigger_pct': 0.30,   # Base target to trigger Free Roll (30%)
        'base_sl_pct': 0.15,          # Base Hard Stop (15%)
        'base_max_hours': 72,         # Base Time Limit (3 days)
    },
    'gamma_scalp': {
        'type': 'whale',              # Special whale zone handling
        'action': 'GAMMA_EXIT',       # Uses whale exit logic
        'stop_multiple': 0.50,        # Exit at 50% of entry
        'free_roll_multiple': 2.0,    # Sell 50% at 2x
        'moonbag_multiple': 5.0,      # Sell 100% at 5x
        'max_hours': 168,             # 7 days
    },
}

# 3. Asset Modifiers (APPLIED TO ALPHA STRATEGY ONLY)
EXIT_ALPHA_ASSET_MODIFIERS = {
    'politics': {
        'description': 'Trending markets. Momentum matters.',
        'profit_mult': 1.2,           # Trend requires room (Target 36%)
        'sl_mult': 1.0,               # Standard Stop (15%)
        'time_mult': 3.0,             # Long Hold (9 Days)
        'use_trailing': True,
        'use_thesis_fail': True,
        'allow_zombie': False,
    },
    'finance': {
        'description': 'Stable, predictable markets.',
        'profit_mult': 1.0,           # Standard Target (30%)
        'sl_mult': 1.2,               # Looser Stop (18%) for macro noise
        'time_mult': 1.0,             # Standard Hold
        'use_trailing': True,
        'use_thesis_fail': True,
        'allow_zombie': False,
    },
    'crypto': {
        'description': 'High correlation, volatile assets.',
        'profit_mult': 1.5,           # Higher Target (45%)
        'sl_mult': 1.5,               # Wide Stop (22.5%) for volatility
        'time_mult': 0.5,             # Fast moving (36h)
        'use_trailing': True,
        'use_thesis_fail': True,
        'allow_zombie': False,
    },
    'sports': {
        'description': 'High vol events. Fixed duration.',
        'profit_mult': 1.0,           # Standard Target (30%)
        'sl_mult': 1.5,               # Wide Stop (22.5%) for game swings
        'time_mult': 0.25,            # Short Hold (18h)
        'use_trailing': False,        # No trailing (Game scores oscillate)
        'use_thesis_fail': False,     # Halftime down != Failed Thesis
        'allow_zombie': True,
    },
    'entertainment': {
        'description': 'Pop culture, viral events.',
        'profit_mult': 2.0,           # High Target (60%) - Viral events
        'sl_mult': 0.8,               # Tight Stop (12%) - Fades fast
        'time_mult': 2.0,             # Medium Hold
        'use_trailing': False,
        'use_thesis_fail': False,
        'allow_zombie': True,
    },
    'science': {
        'description': 'Binary/Lotto outcomes. Long holds.',
        'profit_mult': 2.0,           # Lotto Target (60%)
        'sl_mult': 0.5,               # Tight Stop (7.5%) - News dependent
        'time_mult': 5.0,             # Very Long Hold
        'use_trailing': False,
        'use_thesis_fail': False,
        'allow_zombie': True,
    },
    'conflict': {
        'description': 'Geopolitical events.',
        'profit_mult': 1.0,           # Standard Target (30%)
        'sl_mult': 1.2,               # Looser Stop for uncertainty
        'time_mult': 2.0,             # Medium-Long Hold
        'use_trailing': False,
        'use_thesis_fail': False,
        'allow_zombie': True,
    },
    'social': {
        'description': 'Social media/tweets.',
        'profit_mult': 1.5,           # Higher Target (45%)
        'sl_mult': 1.0,               # Standard Stop
        'time_mult': 0.5,             # Fast moving
        'use_trailing': True,
        'use_thesis_fail': True,
        'allow_zombie': False,
    },
    'default': {
        'description': 'Default/Unknown category.',
        'profit_mult': 1.0,
        'sl_mult': 1.0,
        'time_mult': 1.0,
        'use_trailing': True,
        'use_thesis_fail': True,
        'allow_zombie': False,
    },
}

# 4. Whale Zone Exit Rules (Entry < $0.10)
EXIT_WHALE_ZONE = {
    'stop_loss_multiple': 0.50,       # Exit if price drops to 50% of entry
    'free_roll_multiple': 2.0,        # Sell 50% when price doubles
    'free_roll_sell_pct': 0.50,       # Sell 50% on free roll
    'moonbag_multiple': 5.0,          # Sell 100% when price 5x's
    'ignore_trailing_stop': True,     # No trailing in whale zone
    'ignore_thesis_fail': True,       # No thesis fail in whale zone
}


def get_exit_config():
    """Get the complete exit engine configuration (deep copy of defaults)."""
    import copy
    return {
        'global': copy.deepcopy(EXIT_GLOBAL_SETTINGS),
        'strategies': copy.deepcopy(EXIT_STRATEGY_CONFIG),
        'alpha_modifiers': copy.deepcopy(EXIT_ALPHA_ASSET_MODIFIERS),
        'whale_zone': copy.deepcopy(EXIT_WHALE_ZONE),
    }


def get_alpha_asset_modifier(asset_class: str) -> dict:
    """Get exit modifiers for a specific asset class (Alpha strategy only)."""
    # Normalize asset class name
    normalized = asset_class.lower().strip() if asset_class else 'default'
    
    # Handle compound names
    if 'crypto' in normalized or 'bitcoin' in normalized:
        normalized = 'crypto'
    elif 'politic' in normalized or 'election' in normalized:
        normalized = 'politics'
    elif 'sport' in normalized or 'game' in normalized:
        normalized = 'sports'
    elif 'science' in normalized or 'tech' in normalized:
        normalized = 'science'
    elif 'entertainment' in normalized or 'pop' in normalized:
        normalized = 'entertainment'
    elif 'finance' in normalized or 'econ' in normalized:
        normalized = 'finance'
    elif 'conflict' in normalized or 'war' in normalized:
        normalized = 'conflict'
    elif 'social' in normalized or 'tweet' in normalized:
        normalized = 'social'
    
    return EXIT_ALPHA_ASSET_MODIFIERS.get(normalized, EXIT_ALPHA_ASSET_MODIFIERS['default'])


@dataclass
class RiskConfig:
    """
    Single Source of Truth for ALL risk and sizing parameters.
    
    All values are configurable via Settings UI. Use DEFAULTS for reset.
    
    Hierarchy of Safety:
    1. Allocated Capital (virtual sub-account)
    2. Price Zones (hard override based on price)
    3. Strategy Regime (Alpha/HFT/Gamma)
    4. Liquidity (never consume >10% of depth)
    5. Exposure (sector and event caps)
    """
    
    # =========================================================================
    # CAPITAL ALLOCATION
    # =========================================================================
    ALLOCATED_CAPITAL_PCT: float = DEFAULTS['ALLOCATED_CAPITAL_PCT']
    CASH_BUFFER_PCT: float = DEFAULTS['CASH_BUFFER_PCT']
    
    # =========================================================================
    # GLOBAL SAFETY PARAMETERS
    # =========================================================================
    STOP_LOSS_PCT: float = DEFAULTS['STOP_LOSS_PCT']
    MAX_DRAWDOWN_PCT: float = DEFAULTS['MAX_DRAWDOWN_PCT']
    KILL_SWITCH_LOW: float = DEFAULTS['KILL_SWITCH_LOW']
    KILL_SWITCH_HIGH: float = DEFAULTS['KILL_SWITCH_HIGH']
    
    # =========================================================================
    # ZONE THRESHOLD
    # =========================================================================
    PRICE_ZONE_THRESHOLD: float = DEFAULTS['PRICE_ZONE_THRESHOLD']
    
    # =========================================================================
    # ZONE 1: CONVEXITY / WHALE ZONE ($0.03 - $0.09)
    # =========================================================================
    WHALE_PRICE_CEILING: float = DEFAULTS['WHALE_PRICE_CEILING']
    WHALE_MAX_SPREAD_CENTS: float = DEFAULTS['WHALE_MAX_SPREAD_CENTS']
    WHALE_MIN_LIQUIDITY: float = DEFAULTS['WHALE_MIN_LIQUIDITY']
    WHALE_MIN_VOLUME_24H: float = DEFAULTS['WHALE_MIN_VOLUME_24H']
    WHALE_MAX_USD: float = DEFAULTS['WHALE_MAX_USD']
    WHALE_MAX_PCT: float = DEFAULTS['WHALE_MAX_PCT']
    
    @property
    def WHALE_MAX_POSITION(self) -> float:
        return self.WHALE_MAX_USD
    
    @property
    def WHALE_MAX_POSITION_PCT(self) -> float:
        return self.WHALE_MAX_PCT * 100
    
    # =========================================================================
    # ZONE 2: CORE ALPHA ZONE ($0.10+)
    # =========================================================================
    CORE_TAKER_SPREAD_PCT: float = DEFAULTS['CORE_TAKER_SPREAD_PCT']
    CORE_MAKER_SPREAD_PCT: float = DEFAULTS['CORE_MAKER_SPREAD_PCT']
    CORE_ZOMBIE_SPREAD_PCT: float = DEFAULTS['CORE_ZOMBIE_SPREAD_PCT']
    CORE_MIN_LIQUIDITY: float = DEFAULTS['CORE_MIN_LIQUIDITY']
    CORE_MIN_VOLUME_24H: float = DEFAULTS['CORE_MIN_VOLUME_24H']
    CORE_MAX_USD: float = DEFAULTS['CORE_MAX_USD']
    CORE_MAX_PCT: float = DEFAULTS['CORE_MAX_PCT']
    
    @property
    def CORE_MAX_POSITION(self) -> float:
        return self.CORE_MAX_USD
    
    @property
    def CORE_MAX_POSITION_PCT(self) -> float:
        return self.CORE_MAX_PCT * 100
    
    # =========================================================================
    # STRATEGY MATH
    # =========================================================================
    KELLY_SCALING_FACTOR: float = DEFAULTS['KELLY_SCALING_FACTOR']
    MIN_KELLY_FRACTION: float = DEFAULTS['MIN_KELLY_FRACTION']
    MAX_KELLY_FRACTION: float = DEFAULTS['MAX_KELLY_FRACTION']
    HFT_UNIT_PCT: float = DEFAULTS['HFT_UNIT_PCT']
    
    @property
    def KELLY_FRACTION(self) -> float:
        return self.KELLY_SCALING_FACTOR
    
    # =========================================================================
    # LIQUIDITY CONSTRAINTS
    # =========================================================================
    MAX_LIQUIDITY_CONSUMPTION: float = DEFAULTS['MAX_LIQUIDITY_CONSUMPTION']
    
    # =========================================================================
    # EXPOSURE LIMITS
    # =========================================================================
    MAX_EVENT_EXPOSURE_PCT: float = DEFAULTS['MAX_EVENT_EXPOSURE_PCT']
    
    # =========================================================================
    # SECTOR CAPS
    # =========================================================================
    SECTOR_LIMITS: Dict[str, float] = field(default_factory=lambda: dict(DEFAULTS['SECTOR_LIMITS']))
    
    # =========================================================================
    # TRADE FILTERS
    # =========================================================================
    MIN_TRADE_AMOUNT: float = DEFAULTS['MIN_TRADE_AMOUNT']
    MIN_BET_FLOOR: float = DEFAULTS['MIN_BET_FLOOR']
    
    # =========================================================================
    # FEE STRUCTURE
    # =========================================================================
    TAKER_FEE: float = DEFAULTS['TAKER_FEE']
    MAKER_FEE: float = DEFAULTS['MAKER_FEE']
    ADVERSE_SELECTION_COST: float = DEFAULTS['ADVERSE_SELECTION_COST']
    MAKER_SPREAD_CAPTURE: float = DEFAULTS['MAKER_SPREAD_CAPTURE']
    
    # =========================================================================
    # QUALITY FILTERS
    # =========================================================================
    MIN_PRICE_BAND: float = DEFAULTS['MIN_PRICE_BAND']
    MAX_PRICE_BAND: float = DEFAULTS['MAX_PRICE_BAND']
    TOP_N_MARKETS: int = DEFAULTS['TOP_N_MARKETS']
    
    # =========================================================================
    # POSITION SIZER CONFIG
    # =========================================================================
    UTILIZATION_EXPONENT: float = DEFAULTS['UTILIZATION_EXPONENT']
    UTILIZATION_HARD_STOP: float = DEFAULTS['UTILIZATION_HARD_STOP']
    EDGE_RETENTION_PCT: float = DEFAULTS['EDGE_RETENTION_PCT']
    TIME_PENALTY_MAX_DAYS: int = DEFAULTS['TIME_PENALTY_MAX_DAYS']
    TIME_PENALTY_FLOOR: float = DEFAULTS['TIME_PENALTY_FLOOR']
    EVENT_SIMILARITY_THRESHOLD: float = DEFAULTS['EVENT_SIMILARITY_THRESHOLD']
    
    # =========================================================================
    # CONCURRENT POSITION LIMITS
    # =========================================================================
    MAX_OPEN_POSITIONS: int = DEFAULTS['MAX_OPEN_POSITIONS']
    
    # =========================================================================
    # DATABASE PERSISTENCE
    # =========================================================================
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON/DB storage."""
        return {
            # Capital
            'allocated_capital_pct': self.ALLOCATED_CAPITAL_PCT,
            'cash_buffer_pct': self.CASH_BUFFER_PCT,
            
            # Safety
            'stop_loss_pct': self.STOP_LOSS_PCT,
            'max_drawdown_pct': self.MAX_DRAWDOWN_PCT,
            'kill_switch_low': self.KILL_SWITCH_LOW,
            'kill_switch_high': self.KILL_SWITCH_HIGH,
            
            # Zone
            'price_zone_threshold': self.PRICE_ZONE_THRESHOLD,
            
            # Whale
            'whale_price_ceiling': self.WHALE_PRICE_CEILING,
            'whale_max_spread_cents': self.WHALE_MAX_SPREAD_CENTS,
            'whale_min_liquidity': self.WHALE_MIN_LIQUIDITY,
            'whale_min_volume_24h': self.WHALE_MIN_VOLUME_24H,
            'whale_max_usd': self.WHALE_MAX_USD,
            'whale_max_pct': self.WHALE_MAX_PCT,
            
            # Core
            'core_taker_spread_pct': self.CORE_TAKER_SPREAD_PCT,
            'core_maker_spread_pct': self.CORE_MAKER_SPREAD_PCT,
            'core_zombie_spread_pct': self.CORE_ZOMBIE_SPREAD_PCT,
            'core_min_liquidity': self.CORE_MIN_LIQUIDITY,
            'core_min_volume_24h': self.CORE_MIN_VOLUME_24H,
            'core_max_usd': self.CORE_MAX_USD,
            'core_max_pct': self.CORE_MAX_PCT,
            
            # Strategy
            'kelly_scaling_factor': self.KELLY_SCALING_FACTOR,
            'min_kelly_fraction': self.MIN_KELLY_FRACTION,
            'max_kelly_fraction': self.MAX_KELLY_FRACTION,
            'hft_unit_pct': self.HFT_UNIT_PCT,
            
            # Liquidity
            'max_liquidity_consumption': self.MAX_LIQUIDITY_CONSUMPTION,
            
            # Exposure
            'max_event_exposure_pct': self.MAX_EVENT_EXPOSURE_PCT,
            'sector_limits': self.SECTOR_LIMITS,
            
            # Filters
            'min_trade_amount': self.MIN_TRADE_AMOUNT,
            'min_bet_floor': self.MIN_BET_FLOOR,
            
            # Fees
            'taker_fee': self.TAKER_FEE,
            'maker_fee': self.MAKER_FEE,
            
            # Positions
            'max_open_positions': self.MAX_OPEN_POSITIONS,
        }
    
    def load_from_dict(self, data: Dict):
        """Load values from dictionary (DB response)."""
        if not data:
            return
        
        # Capital
        if 'allocated_capital_pct' in data:
            self.ALLOCATED_CAPITAL_PCT = float(data['allocated_capital_pct'])
        if 'cash_buffer_pct' in data:
            self.CASH_BUFFER_PCT = float(data['cash_buffer_pct'])
        
        # Safety
        if 'stop_loss_pct' in data:
            self.STOP_LOSS_PCT = float(data['stop_loss_pct'])
        if 'max_drawdown_pct' in data:
            self.MAX_DRAWDOWN_PCT = float(data['max_drawdown_pct'])
        if 'kill_switch_low' in data:
            self.KILL_SWITCH_LOW = float(data['kill_switch_low'])
        if 'kill_switch_high' in data:
            self.KILL_SWITCH_HIGH = float(data['kill_switch_high'])
        
        # Zone
        if 'price_zone_threshold' in data:
            self.PRICE_ZONE_THRESHOLD = float(data['price_zone_threshold'])
            self.WHALE_PRICE_CEILING = float(data['price_zone_threshold'])
        
        # Whale
        if 'whale_max_spread_cents' in data:
            self.WHALE_MAX_SPREAD_CENTS = float(data['whale_max_spread_cents'])
        if 'whale_min_liquidity' in data:
            self.WHALE_MIN_LIQUIDITY = float(data['whale_min_liquidity'])
        if 'whale_min_volume_24h' in data:
            self.WHALE_MIN_VOLUME_24H = float(data['whale_min_volume_24h'])
        if 'whale_max_usd' in data:
            self.WHALE_MAX_USD = float(data['whale_max_usd'])
        if 'whale_max_pct' in data:
            self.WHALE_MAX_PCT = float(data['whale_max_pct'])
        
        # Core
        if 'core_taker_spread_pct' in data:
            self.CORE_TAKER_SPREAD_PCT = float(data['core_taker_spread_pct'])
        if 'core_maker_spread_pct' in data:
            self.CORE_MAKER_SPREAD_PCT = float(data['core_maker_spread_pct'])
        if 'core_zombie_spread_pct' in data:
            self.CORE_ZOMBIE_SPREAD_PCT = float(data['core_zombie_spread_pct'])
        if 'core_min_liquidity' in data:
            self.CORE_MIN_LIQUIDITY = float(data['core_min_liquidity'])
        if 'core_min_volume_24h' in data:
            self.CORE_MIN_VOLUME_24H = float(data['core_min_volume_24h'])
        if 'core_max_usd' in data:
            self.CORE_MAX_USD = float(data['core_max_usd'])
        if 'core_max_pct' in data:
            self.CORE_MAX_PCT = float(data['core_max_pct'])
        
        # Strategy
        if 'kelly_scaling_factor' in data:
            self.KELLY_SCALING_FACTOR = float(data['kelly_scaling_factor'])
        if 'min_kelly_fraction' in data:
            self.MIN_KELLY_FRACTION = float(data['min_kelly_fraction'])
        if 'max_kelly_fraction' in data:
            self.MAX_KELLY_FRACTION = float(data['max_kelly_fraction'])
        if 'hft_unit_pct' in data:
            self.HFT_UNIT_PCT = float(data['hft_unit_pct'])
        
        # Liquidity
        if 'max_liquidity_consumption' in data:
            self.MAX_LIQUIDITY_CONSUMPTION = float(data['max_liquidity_consumption'])
        
        # Exposure
        if 'max_event_exposure_pct' in data:
            self.MAX_EVENT_EXPOSURE_PCT = float(data['max_event_exposure_pct'])
        if 'sector_limits' in data and isinstance(data['sector_limits'], dict):
            self.SECTOR_LIMITS = data['sector_limits']
        
        # Filters
        if 'min_trade_amount' in data:
            self.MIN_TRADE_AMOUNT = float(data['min_trade_amount'])
        if 'min_bet_floor' in data:
            self.MIN_BET_FLOOR = float(data['min_bet_floor'])
        
        # Fees
        if 'taker_fee' in data:
            self.TAKER_FEE = float(data['taker_fee'])
        if 'maker_fee' in data:
            self.MAKER_FEE = float(data['maker_fee'])
        
        # Positions
        if 'max_open_positions' in data:
            self.MAX_OPEN_POSITIONS = int(data['max_open_positions'])
        
        logger.info(f"[RISK] Loaded config from DB: whale_max=${self.WHALE_MAX_USD}, core_max=${self.CORE_MAX_USD}")
    
    def reset_to_defaults(self):
        """Reset all values to defaults."""
        self.ALLOCATED_CAPITAL_PCT = DEFAULTS['ALLOCATED_CAPITAL_PCT']
        self.CASH_BUFFER_PCT = DEFAULTS['CASH_BUFFER_PCT']
        self.STOP_LOSS_PCT = DEFAULTS['STOP_LOSS_PCT']
        self.MAX_DRAWDOWN_PCT = DEFAULTS['MAX_DRAWDOWN_PCT']
        self.KILL_SWITCH_LOW = DEFAULTS['KILL_SWITCH_LOW']
        self.KILL_SWITCH_HIGH = DEFAULTS['KILL_SWITCH_HIGH']
        self.PRICE_ZONE_THRESHOLD = DEFAULTS['PRICE_ZONE_THRESHOLD']
        self.WHALE_PRICE_CEILING = DEFAULTS['WHALE_PRICE_CEILING']
        self.WHALE_MAX_SPREAD_CENTS = DEFAULTS['WHALE_MAX_SPREAD_CENTS']
        self.WHALE_MIN_LIQUIDITY = DEFAULTS['WHALE_MIN_LIQUIDITY']
        self.WHALE_MIN_VOLUME_24H = DEFAULTS['WHALE_MIN_VOLUME_24H']
        self.WHALE_MAX_USD = DEFAULTS['WHALE_MAX_USD']
        self.WHALE_MAX_PCT = DEFAULTS['WHALE_MAX_PCT']
        self.CORE_TAKER_SPREAD_PCT = DEFAULTS['CORE_TAKER_SPREAD_PCT']
        self.CORE_MAKER_SPREAD_PCT = DEFAULTS['CORE_MAKER_SPREAD_PCT']
        self.CORE_ZOMBIE_SPREAD_PCT = DEFAULTS['CORE_ZOMBIE_SPREAD_PCT']
        self.CORE_MIN_LIQUIDITY = DEFAULTS['CORE_MIN_LIQUIDITY']
        self.CORE_MIN_VOLUME_24H = DEFAULTS['CORE_MIN_VOLUME_24H']
        self.CORE_MAX_USD = DEFAULTS['CORE_MAX_USD']
        self.CORE_MAX_PCT = DEFAULTS['CORE_MAX_PCT']
        self.KELLY_SCALING_FACTOR = DEFAULTS['KELLY_SCALING_FACTOR']
        self.MIN_KELLY_FRACTION = DEFAULTS['MIN_KELLY_FRACTION']
        self.MAX_KELLY_FRACTION = DEFAULTS['MAX_KELLY_FRACTION']
        self.HFT_UNIT_PCT = DEFAULTS['HFT_UNIT_PCT']
        self.MAX_LIQUIDITY_CONSUMPTION = DEFAULTS['MAX_LIQUIDITY_CONSUMPTION']
        self.MAX_EVENT_EXPOSURE_PCT = DEFAULTS['MAX_EVENT_EXPOSURE_PCT']
        self.SECTOR_LIMITS = dict(DEFAULTS['SECTOR_LIMITS'])
        self.MIN_TRADE_AMOUNT = DEFAULTS['MIN_TRADE_AMOUNT']
        self.MIN_BET_FLOOR = DEFAULTS['MIN_BET_FLOOR']
        self.TAKER_FEE = DEFAULTS['TAKER_FEE']
        self.MAKER_FEE = DEFAULTS['MAKER_FEE']
        self.ADVERSE_SELECTION_COST = DEFAULTS['ADVERSE_SELECTION_COST']
        self.MAKER_SPREAD_CAPTURE = DEFAULTS['MAKER_SPREAD_CAPTURE']
        self.MAX_OPEN_POSITIONS = DEFAULTS['MAX_OPEN_POSITIONS']
        logger.info("[RISK] Reset all parameters to defaults")


# Global instance
RISK = RiskConfig()


def get_defaults() -> Dict:
    """Get default values for UI reset button."""
    return {
        'allocated_capital_pct': DEFAULTS['ALLOCATED_CAPITAL_PCT'],
        'cash_buffer_pct': DEFAULTS['CASH_BUFFER_PCT'],
        'stop_loss_pct': DEFAULTS['STOP_LOSS_PCT'],
        'max_drawdown_pct': DEFAULTS['MAX_DRAWDOWN_PCT'],
        'kill_switch_low': DEFAULTS['KILL_SWITCH_LOW'],
        'kill_switch_high': DEFAULTS['KILL_SWITCH_HIGH'],
        'price_zone_threshold': DEFAULTS['PRICE_ZONE_THRESHOLD'],
        'whale_max_spread_cents': DEFAULTS['WHALE_MAX_SPREAD_CENTS'],
        'whale_min_liquidity': DEFAULTS['WHALE_MIN_LIQUIDITY'],
        'whale_min_volume_24h': DEFAULTS['WHALE_MIN_VOLUME_24H'],
        'whale_max_usd': DEFAULTS['WHALE_MAX_USD'],
        'whale_max_pct': DEFAULTS['WHALE_MAX_PCT'],
        'core_taker_spread_pct': DEFAULTS['CORE_TAKER_SPREAD_PCT'],
        'core_maker_spread_pct': DEFAULTS['CORE_MAKER_SPREAD_PCT'],
        'core_zombie_spread_pct': DEFAULTS['CORE_ZOMBIE_SPREAD_PCT'],
        'core_min_liquidity': DEFAULTS['CORE_MIN_LIQUIDITY'],
        'core_min_volume_24h': DEFAULTS['CORE_MIN_VOLUME_24H'],
        'core_max_usd': DEFAULTS['CORE_MAX_USD'],
        'core_max_pct': DEFAULTS['CORE_MAX_PCT'],
        'kelly_scaling_factor': DEFAULTS['KELLY_SCALING_FACTOR'],
        'min_kelly_fraction': DEFAULTS['MIN_KELLY_FRACTION'],
        'max_kelly_fraction': DEFAULTS['MAX_KELLY_FRACTION'],
        'hft_unit_pct': DEFAULTS['HFT_UNIT_PCT'],
        'max_liquidity_consumption': DEFAULTS['MAX_LIQUIDITY_CONSUMPTION'],
        'max_event_exposure_pct': DEFAULTS['MAX_EVENT_EXPOSURE_PCT'],
        'sector_limits': DEFAULTS['SECTOR_LIMITS'],
        'min_trade_amount': DEFAULTS['MIN_TRADE_AMOUNT'],
        'min_bet_floor': DEFAULTS['MIN_BET_FLOOR'],
        'taker_fee': DEFAULTS['TAKER_FEE'],
        'maker_fee': DEFAULTS['MAKER_FEE'],
        'max_open_positions': DEFAULTS['MAX_OPEN_POSITIONS'],
    }


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
