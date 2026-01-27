import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

class Config:
    # MongoDB
    MONGO_URL = os.environ['MONGO_URL']
    DB_NAME = os.environ['DB_NAME']
    
    # Polymarket
    API_KEY = os.environ['API_KEY']
    API_SECRET = os.environ['API_SECRET']
    API_PASSPHRASE = os.environ['API_PASSPHRASE']
    POLYMARKET_ADDRESS = os.environ['POLYMARKET_ADDRESS']
    
    # Wallet
    PRIVATE_KEY = os.environ['PRIVATE_KEY']
    WALLET_ADDRESS = os.environ['WALLET_ADDRESS']
    POLYGON_RPC_URL = os.environ['POLYGON_RPC_URL']
    
    # LLM
    EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
    
    # =========================================================================
    # Trading Configuration
    # =========================================================================
    # NOTE: Primary source of truth is now risk_config.py (Task 23)
    # These remain for backward compatibility and MongoDB settings override
    
    INITIAL_CAPITAL = float(os.environ.get('INITIAL_CAPITAL', 10000))  # Default $10,000
    TRADES_PER_10MIN = int(os.environ.get('TRADES_PER_10MIN', 500))
    
    # System Performance
    EXECUTION_LATENCY_MS = int(os.environ.get('EXECUTION_LATENCY_MS', 100))
    ML_INFERENCE_LATENCY_MS = int(os.environ.get('ML_INFERENCE_LATENCY_MS', 50))
    
    # =========================================================================
    # DEPRECATED: Now in risk_config.py (Task 23 - Unified Portfolio Manager)
    # These properties delegate to risk_config.py for backward compatibility
    # =========================================================================
    
    @property
    def CAPITAL_DEPLOYMENT_PCT(self):
        """DEPRECATED: Use risk_config.RISK.ALLOCATED_CAPITAL_PCT instead."""
        from risk_config import RISK
        return RISK.ALLOCATED_CAPITAL_PCT
    
    @property
    def MAX_POSITION_SIZE_PCT(self):
        """DEPRECATED: Use risk_config.RISK.CORE_MAX_PCT instead."""
        from risk_config import RISK
        return RISK.CORE_MAX_PCT * 100  # Return as percentage
    
    @property
    def MAX_DRAWDOWN_PCT(self):
        """DEPRECATED: Use risk_config.RISK.MAX_DRAWDOWN_PCT instead."""
        from risk_config import RISK
        return RISK.MAX_DRAWDOWN_PCT
    
    @property
    def KELLY_FRACTION(self):
        """DEPRECATED: Use risk_config.RISK.KELLY_SCALING_FACTOR instead."""
        from risk_config import RISK
        return RISK.KELLY_SCALING_FACTOR
    
    @property
    def MIN_KELLY_FRACTION(self):
        """DEPRECATED: Use risk_config.RISK.MIN_KELLY_FRACTION instead."""
        from risk_config import RISK
        return RISK.MIN_KELLY_FRACTION
    
    @property
    def MAX_KELLY_FRACTION(self):
        """DEPRECATED: Use risk_config.RISK.MAX_KELLY_FRACTION instead."""
        from risk_config import RISK
        return RISK.MAX_KELLY_FRACTION
    
    @property
    def MIN_LIQUIDITY(self):
        """DEPRECATED: Use risk_config.RISK.CORE_MIN_LIQUIDITY instead."""
        from risk_config import RISK
        return RISK.CORE_MIN_LIQUIDITY
    
    @property
    def MIN_VOLUME_24H(self):
        """DEPRECATED: Use risk_config.RISK.CORE_MIN_VOLUME_24H instead."""
        from risk_config import RISK
        return RISK.CORE_MIN_VOLUME_24H
    
    @property
    def MAX_SPREAD(self):
        """DEPRECATED: Use risk_config.RISK.CORE_MAKER_SPREAD_PCT instead."""
        from risk_config import RISK
        return RISK.CORE_MAKER_SPREAD_PCT
    
    @property
    def MAX_OPEN_POSITIONS(self):
        """DEPRECATED: Use risk_config.RISK.MAX_OPEN_POSITIONS instead."""
        from risk_config import RISK
        return RISK.MAX_OPEN_POSITIONS
    
    # Calculated values
    @property
    def DEPLOYED_CAPITAL(self):
        from risk_config import RISK
        return self.INITIAL_CAPITAL * (RISK.ALLOCATED_CAPITAL_PCT / 100)
    
    @property
    def MAX_POSITION_SIZE(self):
        from risk_config import RISK
        return self.DEPLOYED_CAPITAL * RISK.CORE_MAX_PCT
    
    @property
    def TRADE_INTERVAL_SECONDS(self):
        return 600 / self.TRADES_PER_10MIN

config = Config()


# ============================================================================
# SPREAD RULES - Single Source of Truth (Task 21)
# ============================================================================
# Updated 2026-01-26: Tightened after fixing orderbook parsing bug.
# Real Polymarket spreads are 0.1% - 2%, not the 99% we were seeing before.

SPREAD_RULES = {
    # --- REGIME BOUNDARIES ---
    # Defines which regime a market falls into based on spread
    'TAKER_THRESHOLD': 0.02,       # < 2%: Tight market. Safe for Alpha Taker orders.
    'MAKER_THRESHOLD': 0.10,       # 2% - 10%: Wide market. Opportunity for HFT/Maker.
    'ZOMBIE_THRESHOLD': 0.12,      # > 12%: Market is broken/dead. Ignore completely.
    
    # --- HARD SAFETY LIMITS (Never Exceed) ---
    # These are absolute maximums, regardless of edge or confidence
    'MAX_SPREAD_ALPHA': 0.05,      # 5%: Absolute max for Alpha directional trades
    'MAX_SPREAD_HFT': 0.12,        # 12%: Absolute max for HFT maker orders
    'MAX_SPREAD_AGGRESSIVE': 0.03, # 3%: Max for aggressive taker entries
    
    # --- MAKER PROFITABILITY ---
    'MIN_SPREAD_MAKER': 0.005,     # 0.5%: Minimum spread for maker to be profitable
    'MIN_SPREAD_FOR_EDGE': 0.01,   # 1%: Minimum spread to have any maker edge
    
    # --- REAL-WORLD SPREAD GRID ---
    # Common spread values observed on Polymarket (for simulation/testing)
    'TYPICAL_SPREADS': [0.005, 0.01, 0.02, 0.03, 0.05],
}


# ============================================================================
# RISK PARAMETERS - Single Source of Truth
# ============================================================================

RISK_PARAMS = {
    # --- FEES ---
    'TAKER_FEE': 0.02,               # 2% taker fee (embedded in spread)
    'MAKER_FEE': 0.00,               # No maker fee on Polymarket
    
    # --- ADVERSE SELECTION ---
    'ADVERSE_SELECTION_COST': 0.005,  # 0.5% assumed adverse selection per trade
    'MAKER_SPREAD_CAPTURE': 0.50,     # Assume we capture 50% of spread as maker
}


# ============================================================================
# QUALITY FILTERS - DEPRECATED (Task 27: Legacy Purge)
# ============================================================================
# WARNING: These values are DEPRECATED. Use risk_config.py instead.
# Kept temporarily for backward compatibility - will be removed in future version.
#
# NEW SSOT MAPPING:
#   QUALITY_FILTERS['MIN_LIQUIDITY']  -> RISK.get_thresholds(strategy, price)[0]
#   QUALITY_FILTERS['MIN_VOLUME_24H'] -> RISK.get_thresholds(strategy, price)[1]
#   QUALITY_FILTERS['MAX_LIQUIDITY']  -> RISK.MAX_LIQUIDITY_CAP
#
# DO NOT ADD NEW REFERENCES TO THIS DICT
# ============================================================================

# QUALITY_FILTERS = {
#     'MIN_VOLUME_24H': 1000.0,      # DEPRECATED: Use RISK.get_thresholds()
#     'MIN_LIQUIDITY': 100.0,        # DEPRECATED: Use RISK.get_thresholds()
#     'MAX_LIQUIDITY': 1000000.0,    # DEPRECATED: Use RISK.MAX_LIQUIDITY_CAP
#     'MIN_PRICE_BAND': 0.05,        # Still valid - not in risk_config
#     'MAX_PRICE_BAND': 0.95,        # Still valid - not in risk_config
#     'TOP_N_MARKETS': 50,           # Still valid - not in risk_config
# }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_max_spread_for_strategy(strategy_type: str) -> float:
    """Get the maximum allowed spread for a given strategy type."""
    strategy_map = {
        'alpha': SPREAD_RULES['MAX_SPREAD_ALPHA'],
        'hft': SPREAD_RULES['MAX_SPREAD_HFT'],
        'aggressive': SPREAD_RULES['MAX_SPREAD_AGGRESSIVE'],
        'taker': SPREAD_RULES['TAKER_THRESHOLD'],
    }
    return strategy_map.get(strategy_type.lower(), SPREAD_RULES['MAX_SPREAD_ALPHA'])


def classify_spread_regime(spread: float) -> str:
    """Classify a spread into a market regime."""
    if spread <= SPREAD_RULES['TAKER_THRESHOLD']:
        return 'TAKER_TIGHT'
    elif spread <= SPREAD_RULES['ZOMBIE_THRESHOLD']:
        return 'MAKER_WIDE'
    else:
        return 'ZOMBIE'


def is_spread_acceptable(spread: float, is_hft: bool = False) -> bool:
    """Check if a spread is acceptable for trading."""
    max_spread = SPREAD_RULES['MAX_SPREAD_HFT'] if is_hft else SPREAD_RULES['MAX_SPREAD_ALPHA']
    return spread <= max_spread