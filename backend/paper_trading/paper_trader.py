"""
Paper Trading Engine with Full RL Integration
Simulates live trading, tracks positions, and feeds rewards to RL for continuous learning

Updated: Sports Strategy Injection (Task: Category Isolation)
- Sports markets routed to SportsArbitrageStrategy
- Dynamic filter overrides from SportsConfig
- NO-side betting allowed for sports arbitrage
"""
import asyncio
import logging
import os
import re
import uuid
from typing import Dict, List, Optional, Callable, Tuple
from datetime import datetime, timezone
from database import get_db
from ml.rl_engine import RLAdaptiveEngine
from services.market_data_service import MarketDataService
from services.realtime_market_service import get_realtime_market_service, RealTimeMarketService
from ml.sharp_detector import SharpDetector
from ml.volatility_predictor import VolatilityPredictor
from ml.signal_fusion import SignalFusionEngine
from ml.social_sentiment import SocialSentimentAnalyzer
from ml.enhanced_sentiment import get_enhanced_sentiment_analyzer
from trading.maker_executor import get_maker_executor, MakerOrderExecutor
from trading.gamma_strategy import get_gamma_trader, GammaTrader, GammaOrderType
from trading.exit_engine import get_exit_engine, ExitEngine, ExitAction, ExitReason
from services.hft_context import get_hft_context, get_volatility_calculator, HFTContext, VolatilityCalculator, ContextStatus
from services.telemetry import get_telemetry_service, create_decision_snapshot
from config import config, SPREAD_RULES, RISK_PARAMS
import numpy as np
from threading import Lock

# Sports Strategy imports
from risk_config import get_sports_config, is_sports_market, SportsConfig
from strategies.sports_strategy import get_sports_strategy, SportsArbitrageStrategy, SportsSignal, SportsTradeSignal

# =============================================================================
# SSOT RISK MANAGEMENT (5-Lane Architecture)
# =============================================================================
# Chain of Command: Strategy -> PositionSizer -> RiskManager -> Execution
from services.risk_manager import get_risk_manager, RiskManager, OrderCheckResult
from utils.position_sizer import PositionSizer, SizingResult
from services.news_service import get_news_poller, NewsPoller

logger = logging.getLogger(__name__)

# =============================================================================
# TWO-SPEED ARCHITECTURE: SHARED STATE MANAGEMENT
# =============================================================================
# The "Bridge" between HFT (Fast Path) and Alpha (Slow Path) loops
# - Alpha Loop WRITES theoretical prices and analysis
# - HFT Loop READS and uses them for quote generation

class StrategyContext:
    """
    Thread-safe shared state between HFT and Alpha loops.
    
    Alpha Loop writes:
        context.update_target(market_id, fair_value, regime, confidence)
    
    HFT Loop reads:
        target = context.get_target(market_id)
        if target:
            # Use Alpha's fair value for smart quoting
        else:
            # Pure scalp mode (market microstructure only)
    """
    
    def __init__(self):
        self._lock = Lock()
        self._targets: Dict[str, Dict] = {}  # market_id -> {fair_value, regime, confidence, timestamp}
        self._stats = {
            'alpha_updates': 0,
            'hft_reads': 0,
            'hft_hits': 0,  # Found Alpha target
            'hft_misses': 0,  # No Alpha target, pure scalp
        }
        self._last_alpha_cycle = None
        self._last_hft_cycle = None
    
    def update_target(self, market_id: str, fair_value: float, regime: str, 
                      confidence: float = 1.0, signals: Dict = None):
        """
        Alpha Loop: Write a new fair value target for a market.
        
        Args:
            market_id: Market identifier
            fair_value: Bayesian model probability (theoretical price)
            regime: Market regime (ZOMBIE, MAKER_WIDE, TAKER_TIGHT)
            confidence: Model confidence (0-1)
            signals: Additional signal data
        """
        with self._lock:
            self._targets[market_id] = {
                'fair_value': fair_value,
                'regime': regime,
                'confidence': confidence,
                'signals': signals or {},
                'timestamp': datetime.now(timezone.utc),
            }
            self._stats['alpha_updates'] += 1
    
    def get_target(self, market_id: str) -> Optional[Dict]:
        """
        HFT Loop: Read the current fair value target for a market.
        
        Returns:
            Target dict if available, None if no Alpha analysis yet
        """
        with self._lock:
            self._stats['hft_reads'] += 1
            target = self._targets.get(market_id)
            if target:
                self._stats['hft_hits'] += 1
                # Check staleness - Alpha targets older than 5 min are stale
                age = (datetime.now(timezone.utc) - target['timestamp']).total_seconds()
                if age > 300:  # 5 minutes
                    target['stale'] = True
                else:
                    target['stale'] = False
            else:
                self._stats['hft_misses'] += 1
            return target
    
    def clear_target(self, market_id: str):
        """Remove a market's target (e.g., after position closed)."""
        with self._lock:
            if market_id in self._targets:
                del self._targets[market_id]
    
    def get_all_targets(self) -> Dict[str, Dict]:
        """Get snapshot of all current targets."""
        with self._lock:
            return dict(self._targets)
    
    def get_stats(self) -> Dict:
        """Get bridge statistics."""
        with self._lock:
            hit_rate = self._stats['hft_hits'] / max(1, self._stats['hft_reads'])
            return {
                **self._stats,
                'hit_rate': round(hit_rate, 3),
                'active_targets': len(self._targets),
                'last_alpha_cycle': self._last_alpha_cycle,
                'last_hft_cycle': self._last_hft_cycle,
            }
    
    def record_alpha_cycle(self):
        """Record when Alpha loop completed a cycle."""
        with self._lock:
            self._last_alpha_cycle = datetime.now(timezone.utc)
    
    def record_hft_cycle(self):
        """Record when HFT loop completed a cycle."""
        with self._lock:
            self._last_hft_cycle = datetime.now(timezone.utc)


# Global strategy context (singleton)
_strategy_context: Optional[StrategyContext] = None

def get_strategy_context() -> StrategyContext:
    """Get or create the global strategy context."""
    global _strategy_context
    if _strategy_context is None:
        _strategy_context = StrategyContext()
    return _strategy_context


# =============================================================================
# MARKET REGIME CLASSIFICATION
# =============================================================================
# Categorize markets by liquidity profile to apply appropriate trading strategies

class MarketRegime:
    """Market regime enumeration for dual-zone trading (Task 21)."""
    # Zone 1: Convexity (Whale Zone - prices < $0.10)
    CONVEXITY_OPPORTUNITY = "CONVEXITY_OPPORTUNITY"  # Cheap asset, tight tick spread
    
    # Zone 2: Core (Standard Zone - prices >= $0.10)
    TAKER_TIGHT = "TAKER_TIGHT"     # Tight % spread (<2%), safe for taker
    MAKER_WIDE = "MAKER_WIDE"       # Wide % spread (2-12%), maker opportunity
    
    # Invalid
    ZOMBIE = "ZOMBIE"               # Dead/illiquid, skip

# Import from Single Source of Truth (Task 21: Dual-Zone Risk Architecture)
from risk_config import (
    RISK, 
    classify_market_regime,
    get_zone_parameters,
    is_spread_acceptable,
    MarketRegime as RiskMarketRegime
)

# Re-export for backwards compatibility
SPREAD_ZOMBIE_THRESHOLD = RISK.CORE_ZOMBIE_SPREAD_PCT
SPREAD_MAKER_THRESHOLD = RISK.CORE_MAKER_SPREAD_PCT
SPREAD_TAKER_THRESHOLD = RISK.CORE_TAKER_SPREAD_PCT
MIN_VOLUME_24H = RISK.CORE_MIN_VOLUME_24H

# Note: classify_market_regime is now imported from risk_config.py
# The function supports dual-zone architecture (Whale Zone + Core Zone)


# Callback for WebSocket broadcasting (set by server.py)
_broadcast_callback: Optional[Callable] = None

def set_broadcast_callback(callback: Callable):
    """Set the callback function for WebSocket broadcasting"""
    global _broadcast_callback
    _broadcast_callback = callback


def sanitize_for_json(obj):
    """
    Recursively convert numpy types to native Python types for JSON serialization.
    Handles numpy.bool_, numpy.int64, numpy.float64, etc.
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


async def broadcast_paper_event(event_type: str, data: dict):
    """Broadcast paper trading event to WebSocket clients"""
    global _broadcast_callback
    if _broadcast_callback:
        try:
            await _broadcast_callback({
                "type": event_type,
                **data
            })
        except Exception as e:
            logger.debug(f"Could not broadcast paper event: {e}")

class PaperTrader:
    """
    Paper Trading Engine - Simulates live trading without real money
    
    Key Features:
    - Tracks virtual positions and P&L
    - Feeds trade outcomes to RL for learning
    - Uses same signals as live trading
    - Records all decisions for analysis
    - Continuous mode with auto-restart
    - Graceful stop (lets positions close naturally)
    - ADAPTIVE POSITION SIZING: Uses liquidity, volume, Kelly, RL confidence
    """
    
    def __init__(self, continuous_mode: bool = False, use_config_capital: bool = True):
        self.db = get_db()
        self.rl_engine = RLAdaptiveEngine()
        self.market_data_service = MarketDataService()
        self.sharp_detector = SharpDetector()
        self.volatility_predictor = VolatilityPredictor()
        self.signal_fusion = SignalFusionEngine()
        
        # Initialize real-time market service for WebSocket data
        self.realtime_market_service: Optional[RealTimeMarketService] = None
        # WebSocket prices now correctly handle YES/NO token mapping
        self.use_websocket_data = True  # Toggle WebSocket vs REST polling
        
        # Initialize social sentiment analyzer for news/social data
        try:
            self.social_analyzer = SocialSentimentAnalyzer()
            logger.info("Social sentiment analyzer initialized")
        except Exception as e:
            logger.warning(f"Could not initialize social analyzer: {e}")
            self.social_analyzer = None
        
        # Initialize enhanced sentiment analyzer (LLM + Cross-Market Correlation)
        try:
            self.enhanced_sentiment = get_enhanced_sentiment_analyzer()
            logger.info("Enhanced sentiment analyzer (LLM + Correlation) initialized")
        except Exception as e:
            logger.warning(f"Could not initialize enhanced sentiment: {e}")
            self.enhanced_sentiment = None
        
        # Import position sizers - NEW polymarket-optimized sizer as primary
        from ml.polymarket_position_sizer import get_polymarket_position_sizer
        from ml.adaptive_position_sizer import get_position_sizer as get_legacy_position_sizer
        from ml.portfolio_manager import PortfolioManager
        
        # NEW: Polymarket-optimized position sizer (Binary Kelly, Utilization Brake, etc.)
        self.polymarket_sizer = get_polymarket_position_sizer()
        
        # Legacy sizer kept for fallback and RL learning
        self.position_sizer = get_legacy_position_sizer()
        
        # Portfolio manager tracks equity, utilization, sector exposure
        self.portfolio_manager = PortfolioManager()
        
        # =================================================================
        # SSOT RISK MANAGEMENT (5-Lane Architecture)
        # =================================================================
        # Inject RiskManager (SSOT Gatekeeper) and NewsPoller (Lane 5)
        self.risk_manager: RiskManager = get_risk_manager()
        self.news_poller: NewsPoller = get_news_poller()
        
        # Log SSOT config loaded
        logger.info("=" * 60)
        logger.info("🛡️ SSOT RISK MANAGER INITIALIZED")
        rm_status = self.risk_manager.get_status()
        logger.info(f"  Config Version: {rm_status.get('version', 'unknown')}")
        logger.info(f"  Lanes: {', '.join(rm_status.get('lanes', []))}")
        logger.info(f"  Max Drawdown: {rm_status.get('global_max_drawdown', 0)*100:.0f}%")
        logger.info(f"  Max Deployment: {rm_status.get('global_max_deployment', 0)*100:.0f}%")
        logger.info(f"  News Poller: {'✓ Enabled' if self.news_poller.is_enabled() else '✗ Disabled (no API key)'}")
        logger.info("=" * 60)
        
        self.running = False
        self.session_id = str(uuid.uuid4())[:8]
        
        # Continuous mode settings
        self.continuous_mode = continuous_mode
        self.graceful_stop = False  # When True, stop accepting new trades but close existing
        self.stop_requested = False
        
        # User configuration (loaded from DB) - FULL CONFIG PARAMETERS
        self.enabled_strategies = ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
        self.enabled_asset_classes = ['finance', 'politics', 'crypto', 'entertainment', 'science', 'sports']
        
        # Trading configuration - DEFAULTS only, will be overwritten by DB config in start()
        # These are fallbacks if DB has no config
        self.initial_capital = 10000.0  # Default $10K, DB overrides this
        self.capital_deployment_pct = 80.0
        self.max_position_size_pct = 3.0
        self.kelly_fraction = 0.25
        self.kelly_enabled = True  # NEW: Toggle Kelly Criterion
        self.max_drawdown_pct = 5.0
        self.trades_per_10min = 500
        
        # ================================================================
        # LEGACY PURGE (Task 27): Removed QUALITY_FILTERS dependency
        # All liquidity/volume checks now go through RISK.get_thresholds()
        # These remain only as fallback safety nets
        # ================================================================
        self.min_liquidity = RISK.GAMMA_MIN_LIQUIDITY  # System floor (lowest possible)
        self.max_liquidity = RISK.MAX_LIQUIDITY_CAP    # Wash trading filter
        self.min_volume_24h = RISK.GAMMA_MIN_VOLUME_24H  # System floor
        self.max_spread = SPREAD_RULES.get('MAX_SPREAD_ALPHA', 0.05)  # Tightened to 5% (was 35%)
        self.max_open_positions = 50
        self.stuck_price_multiplier = 2.0  # Volume multiplier for stuck prices (0.0, 0.5, 1.0)
        
        # ================================================================
        # ALPHA MODEL WEIGHTS (Task 19: Dynamic Alpha Tuning)
        # ================================================================
        # These control how much each signal source influences the final probability.
        # Can be updated at runtime via API endpoint POST /api/settings/alpha
        self.alpha_weights = {
            'sentiment_weight': 0.50,      # Weight for LLM sentiment signal
            'rl_weight': 0.60,             # Weight for RL model signal
            'sharp_weight': 0.30,          # Weight for sharp money signal (future use)
            'sentiment_neutral_low': 0.45, # Neutral band lower bound
            'sentiment_neutral_high': 0.55,# Neutral band upper bound
            'max_sentiment_delta': 2.0,    # Safety cap for sentiment swings
            'min_rl_confidence': 0.15,     # Minimum RL confidence to act
        }
        
        # Maker order executor for spread-aware execution
        self.maker_executor: MakerOrderExecutor = get_maker_executor()
        self.use_maker_execution = True  # Enable maker-first execution strategy
        
        # Gamma Strategy (Task 22) - Isolated whale zone execution
        self.gamma_trader: GammaTrader = get_gamma_trader()
        
        # Exit parameters per strategy - loaded from DB, defaults from DEFAULT_EXIT_PARAMS
        self.exit_params_by_strategy = dict(self.DEFAULT_EXIT_PARAMS)
        
        # Asset class exit multipliers - loaded from DB, defaults from EXIT_ADJUSTMENTS_BY_ASSET
        self.asset_class_exit_multipliers = dict(self.EXIT_ADJUSTMENTS_BY_ASSET)
        
        # Advanced position sizing parameters (configurable)
        self.min_kelly_fraction = 0.10
        self.max_kelly_fraction = 0.50
        self.min_position_size = 5.0  # Minimum position in USD
        self.min_liquidity_for_full_size = 10000.0  # Volume needed for full position
        
        # Strategy selection thresholds (configurable via UI)
        self.volatility_threshold = 0.06           # Threshold for volatility strategy (raised to 6% to capture more Delta Neutral)
        self.sentiment_strength_threshold = 0.25   # Threshold for alpha directional
        self.sharp_alignment_threshold = 0.8       # Threshold for arbitrage
        self.delta_neutral_price_min = 0.40        # Min price for delta neutral
        self.delta_neutral_price_max = 0.70        # Max price for delta neutral
        
        # Sentiment-based side selection thresholds (configurable via UI)
        self.bullish_sentiment_threshold = 0.55    # Above this → YES
        self.bearish_sentiment_threshold = 0.45    # Below this → NO
        
        # ============================================
        # DYNAMIC EXIT MODE CONFIGURATION
        # ============================================
        # When True: Use time-aware dynamic TP/SL based on max gain and expiry
        # When False: Use simple configurable TP/SL from exit_params_by_strategy
        self.use_dynamic_exit = True  # Toggle between dynamic and simple mode
        
        # Dynamic exit parameters (Option 4 Framework)
        self.dynamic_exit_config = {
            'tp_capture_pct': 0.10,      # Capture 10% of max possible gain
            'tp_min': 0.005,             # Minimum 0.5% TP
            'tp_max': 0.50,              # Maximum 50% TP
            'sl_base': -0.10,            # -10% SL at 50% price (center)
            'sl_extreme': -0.30,         # -30% SL at 0% or 100% price (edges)
        }
        
        # Time-aware entry filtering thresholds
        self.time_entry_config = {
            'min_gain_near_expiry': 0.001,      # 0.1% min gain if ≤7 days
            'min_gain_medium_term': 0.005,      # 0.5% min gain if 8-30 days
            'min_gain_longer_term': 0.01,       # 1% min gain if 31-90 days
            'min_gain_far_expiry': 0.02,        # 2% min gain if >90 days
            'skip_no_extreme_far_expiry': True, # Skip NO at extreme low YES if >90 days
        }
        
        # ============================================
        # EXIT ENGINE (Task 24: Alpha-State Exit Engine)
        # ============================================
        # Hierarchical exit logic: State → Strategy → Asset Class → Zone
        # Replaces legacy use_dynamic_exit toggle with sophisticated engine
        self.exit_engine: ExitEngine = get_exit_engine()
        self.use_exit_engine = True  # Toggle: True = new ExitEngine, False = legacy logic
        
        # ============================================
        # POSITION SIZING MODE CONFIGURATION
        # ============================================
        # When True: Use NEW Polymarket-optimized sizer (Binary Kelly, Utilization Brake, etc.)
        # When False: Use legacy adaptive sizer (for backwards compatibility)
        self.use_polymarket_sizer = True  # Toggle between new and legacy sizer
        
        # Polymarket fee (configurable)
        self.polymarket_fee_pct = 0.02  # 2% exit fee
        
        # Sector caps (configurable) - max portfolio allocation per category
        self.sector_caps = {
            'crypto': 0.20,       # 20% max in crypto
            'politics': 0.25,     # 25% max in politics
            'sports': 0.30,       # 30% max in sports
            'finance': 0.20,      # 20% max in finance
            'entertainment': 0.15,
            'science': 0.15,
            'conflict': 0.10,     # 10% max in war/conflict
            'social': 0.10,       # 10% max in social/tweets
            'unknown': 0.15,
        }
        
        # Event caps (configurable) - max exposure to correlated markets
        self.event_caps = {
            'max_event_exposure_pct': 0.15,  # 15% max per correlated event
            'similarity_threshold': 0.60,    # 60% question similarity = same event
        }
        
        # ==============================================================
        # TWO-SPEED ARCHITECTURE DEFAULTS (HFT/Alpha)
        # ==============================================================
        self.config = {}  # Full config storage
        self.hft_allocation_pct = 40.0      # % of deployed capital to HFT
        self.alpha_allocation_pct = 60.0    # % of deployed capital to Alpha
        self.hft_max_position_pct = 10.0    # Max position as % of HFT capital
        self.alpha_max_position_pct = 25.0  # Max position as % of Alpha capital
        self.hft_positions_pct = 5.0        # % of global max positions for HFT
        self.alpha_positions_pct = 2.0      # % of global max positions for Alpha
        
        # Strategy Risk Multipliers (position sizing)
        self.strategy_risk_multipliers = {
            'delta_neutral': 1.2,
            'volatility_exploitation': 0.5,
            'alpha_directional': 0.8,
            'arbitrage': 1.1
        }
        
        # Expiry thresholds (defaults)
        self.expiry_thresholds_config = {
            'no_entry_hours': 6,
            'high_urgency_hours': 24,
            'medium_urgency_days': 7,
            'normal_days': 30
        }
        
        # Expiry strategy adjustments (defaults)
        self.expiry_strategy_adjustments = {
            'delta_neutral': {'disable_within_hours': 48, 'size_mult_near_expiry': 0.5},
            'volatility_exploitation': {'boost_within_days': 7, 'boost_multiplier': 1.5, 'disable_within_hours': 6},
            'alpha_directional': {'min_confidence_near_expiry': 0.7, 'disable_within_hours': 6},
            'arbitrage': {'disable_within_hours': 6}
        }
        
        # HFT Execution parameters (defaults)
        self.hft_execution = {
            'max_inventory_usd': 1000,
            'skew_factor': 0.05,
            'ofi_threshold': 0.6,
            'ofi_adjustment': 0.01,
            'ofi_levels': 3
        }
        
        # Spread policy (from centralized config - Task 21)
        self.spread_policy_config = {
            'max_spread_hft': SPREAD_RULES.get('MAX_SPREAD_HFT', 0.12),
            'max_spread_alpha': SPREAD_RULES.get('MAX_SPREAD_ALPHA', 0.05),
            'max_spread_aggressive': SPREAD_RULES.get('MAX_SPREAD_AGGRESSIVE', 0.03),
            'min_spread_maker': SPREAD_RULES.get('MIN_SPREAD_MAKER', 0.005),
            'maker_spread_capture': RISK_PARAMS.get('MAKER_SPREAD_CAPTURE', 0.50),
            'adverse_selection_cost': RISK_PARAMS.get('ADVERSE_SELECTION_COST', 0.005),
            'taker_fee': RISK_PARAMS.get('TAKER_FEE', 0.02)
        }
        
        # Variance sizing (defaults)
        self.variance_sizing_config = {
            'kill_switch_low': 0.03,
            'kill_switch_high': 0.97
        }
        
        # Current capital starts at initial (will be set properly after config load)
        self.current_capital = self.initial_capital
        
        # Calculated values based on config (will be recalculated after config load)
        self.deployed_capital = self.initial_capital * (self.capital_deployment_pct / 100)
        self.max_position_size = self.deployed_capital * (self.max_position_size_pct / 100)
        
        # Session timing
        self.session_start_time = None  # Set when session starts
        
        # Lane 5: Signal cache for News/Emergent signals
        # This connects to the NewsInjector's cache writes
        self._signal_cache = None  # Will be set via set_signal_cache()
        
        # =================================================================
        # ZERO-AWAIT ATOMIC CACHES (Thread-Safe Local Memory)
        # =================================================================
        # These are updated by background pollers and read synchronously
        # by the HFT loop. NO AWAIT in the hot path.
        from threading import Lock
        self._news_atomic: Dict[str, Dict] = {}      # market_id -> {bf, direction, timestamp, ...}
        self._news_atomic_lock = Lock()
        self._alpha_atomic: Dict[str, Dict] = {}     # market_id -> {fair_value, bias, timestamp, ...}
        self._alpha_atomic_lock = Lock()
        
        # Paper positions tracking
        self.paper_positions: Dict[str, Dict] = {}
        self.closed_trades: List[Dict] = []
        self.trade_history: List[Dict] = []
        
        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0  # Realized P&L
        self.unrealized_pnl = 0.0  # Unrealized P&L from open positions
        self.max_drawdown = 0.0
        self.peak_capital = self.initial_capital
        self.circuit_breaker_triggered = False  # Circuit breaker flag
        
        # Strategy performance tracking (with full metrics like backtest)
        # Initialize ALL strategies upfront so they appear in results even with 0 trades
        self.strategy_stats = {
            'hft_scalp': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'hft_maker': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'delta_neutral': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'alpha_directional': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'gamma_scalp': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'sports_arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'news_sniper': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
        }
        
        # Asset class tracking (with full metrics like backtest)
        # Initialize ALL asset classes upfront
        self.asset_class_stats = {
            'finance': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'politics': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'crypto': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'entertainment': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'science': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
            'sports': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0},
        }
        
        # Returns distribution tracking
        self.trade_returns: List[float] = []
        
        # Equity curve tracking - now with strategy and asset class breakdowns
        self.equity_curve: List[Dict] = []
        self.strategy_equity: Dict[str, float] = {
            'hft_scalp': 0.0,
            'hft_maker': 0.0,
            'delta_neutral': 0.0,
            'alpha_directional': 0.0,
            'arbitrage': 0.0,
            'gamma_scalp': 0.0,
            'sports_arbitrage': 0.0,
            'news_sniper': 0.0,
        }
        
        # Three-Speed Lane Equity Tracking (Task 29)
        self.lane_equity: Dict[str, float] = {
            'HFT': 0.0,
            'ALPHA': 0.0,
            'GAMMA': 0.0
        }
        
        # =============================================================
        # HFT STATE ISOLATION (Jan 2026 - Market Memory Dicts)
        # =============================================================
        # Each market has isolated state to prevent data leaks between tickers
        # Key: market_id -> state_value
        self.smoothing_memory: Dict[str, float] = {}     # Smoothed signal per market
        self.volatility_memory: Dict[str, List[float]] = {}  # Price history per market
        self.last_signal_memory: Dict[str, Tuple[float, datetime]] = {}  # Last signal per market
        
        # HFT Math Engine (Cubic Skew, Jump Detection, Cliff Protection)
        from strategies.hft_math import HFTMathEngine, HFTMathConfig
        self.hft_math_config = HFTMathConfig(
            max_position_limit=1000,
            skew_intensity=0.05,
            ema_alpha=0.2,
            jump_threshold=0.03,
            cliff_zone_threshold=0.15,
            cliff_spread_multiplier=2.0,
            extreme_zone_threshold=0.05,
            extreme_spread_multiplier=3.0,
        )
        self.hft_math_engine = HFTMathEngine(self.hft_math_config)
        
        # =============================================================
        # HFT ACTIVE ORDER TRACKING (Polymarket Compliance - Jan 2026)
        # =============================================================
        # Track active orders for lifecycle management and hysteresis
        # Key: market_id -> {'price': float, 'size': float, 'side': str, 
        #                    'timestamp': datetime, 'order_id': str, 'ai_price': float}
        self.active_orders: Dict[str, Dict] = {}
        
        # Polymarket Microstructure Constants
        self.TICK_SIZE = 0.01           # $0.01 tick grid
        self.MIN_PRICE = 0.05           # Kill zone lower bound
        self.MAX_PRICE = 0.95           # Kill zone upper bound
        self.MIN_SPREAD_TICKS = 2       # Minimum 2 cents spread
        self.ORDER_STALE_SECONDS = 120  # Refresh orders after 2 minutes
        self.HYSTERESIS_THRESHOLD = 0.01  # 1 cent drift tolerance (anti-churn)
        
        # Quality Control Stats (Task 18)
        self._last_quality_stats: Dict = {
            'total_fetched': 0,
            'rejected_low_volume': 0,
            'rejected_extreme_price': 0,
            'rejected_low_liquidity': 0,
            'rejected_no_price': 0,
            'passed_quality': 0,
        }
        
        # Initialize asset class equity at 0 for all asset classes
        self.asset_class_equity: Dict[str, float] = {
            'finance': 0.0,
            'politics': 0.0,
            'crypto': 0.0,
            'entertainment': 0.0,
            'science': 0.0,
            'sports': 0.0
        }
        # Track equity curves over time for charts
        self.strategy_equity_history: Dict[str, List[Dict]] = {
            'delta_neutral': [],
            'volatility_exploitation': [],
            'alpha_directional': [],
            'arbitrage': []
        }
        self.asset_class_equity_history: Dict[str, List[Dict]] = {
            'finance': [],
            'politics': [],
            'crypto': [],
            'entertainment': [],
            'science': [],
            'sports': []
        }
        
        # Calculate trade interval from trades_per_10min
        self.trade_interval = max(1, 600 / self.trades_per_10min)  # Seconds between trade evaluations
        
        logger.info(f"Paper Trader initialized - Session: {self.session_id}")
        logger.info(f"  NOTE: Config will be loaded from DB when start() is called")
    
    async def _load_user_config(self):
        """Load ALL user trading configuration from database - DB IS THE SOURCE OF TRUTH"""
        try:
            user_config = await self.db.user_config.find_one({"type": "trading_preferences"})
            if user_config:
                # Load enabled strategies and asset classes
                if "enabled_strategies" in user_config:
                    self.enabled_strategies = user_config["enabled_strategies"]
                if "enabled_asset_classes" in user_config:
                    self.enabled_asset_classes = user_config["enabled_asset_classes"]
                
                # Load trading parameters - DB IS THE SOURCE OF TRUTH
                if "initial_capital" in user_config:
                    self.initial_capital = float(user_config["initial_capital"])
                    self.current_capital = self.initial_capital
                    self.peak_capital = self.initial_capital
                if "capital_deployment_pct" in user_config:
                    self.capital_deployment_pct = float(user_config["capital_deployment_pct"])
                if "max_position_size_pct" in user_config:
                    self.max_position_size_pct = float(user_config["max_position_size_pct"])
                if "kelly_fraction" in user_config:
                    self.kelly_fraction = float(user_config["kelly_fraction"])
                if "kelly_enabled" in user_config:
                    self.kelly_enabled = bool(user_config["kelly_enabled"])
                if "max_drawdown_pct" in user_config:
                    self.max_drawdown_pct = float(user_config["max_drawdown_pct"])
                if "trades_per_10min" in user_config:
                    self.trades_per_10min = int(user_config["trades_per_10min"])
                
                # Market selection thresholds
                if "min_liquidity" in user_config:
                    self.min_liquidity = float(user_config["min_liquidity"])
                if "max_liquidity" in user_config:
                    self.max_liquidity = float(user_config["max_liquidity"])
                if "min_volume_24h" in user_config:
                    self.min_volume_24h = float(user_config["min_volume_24h"])
                if "max_spread" in user_config:
                    self.max_spread = float(user_config["max_spread"])
                if "max_open_positions" in user_config:
                    self.max_open_positions = int(user_config["max_open_positions"])
                if "stuck_price_multiplier" in user_config:
                    self.stuck_price_multiplier = float(user_config["stuck_price_multiplier"])
                
                # Load exit parameters per strategy (configurable TP/SL/Max Hours)
                if "exit_params" in user_config:
                    db_exit_params = user_config["exit_params"]
                    for strategy in self.DEFAULT_EXIT_PARAMS.keys():
                        if strategy in db_exit_params:
                            ep = db_exit_params[strategy]
                            self.exit_params_by_strategy[strategy] = {
                                'take_profit': float(ep.get('take_profit', self.DEFAULT_EXIT_PARAMS[strategy]['take_profit'])),
                                'stop_loss': float(ep.get('stop_loss', self.DEFAULT_EXIT_PARAMS[strategy]['stop_loss'])),
                                'max_hours': float(ep.get('max_hours', self.DEFAULT_EXIT_PARAMS[strategy]['max_hours']))
                            }
                    logger.info(f"  Exit params loaded from DB for {len(db_exit_params)} strategies")
                
                # Load asset class exit multipliers from DB
                if "asset_class_exit_multipliers" in user_config:
                    db_asset_mult = user_config["asset_class_exit_multipliers"]
                    for asset_class in self.EXIT_ADJUSTMENTS_BY_ASSET.keys():
                        if asset_class in db_asset_mult:
                            am = db_asset_mult[asset_class]
                            self.asset_class_exit_multipliers[asset_class] = {
                                'tp_mult': float(am.get('tp_mult', self.EXIT_ADJUSTMENTS_BY_ASSET[asset_class]['tp_mult'])),
                                'sl_mult': float(am.get('sl_mult', self.EXIT_ADJUSTMENTS_BY_ASSET[asset_class]['sl_mult'])),
                                'time_mult': float(am.get('time_mult', self.EXIT_ADJUSTMENTS_BY_ASSET[asset_class]['time_mult']))
                            }
                    logger.info(f"  Asset class exit multipliers loaded for {len(db_asset_mult)} classes")
                
                # Load advanced position sizing parameters
                if "min_kelly_fraction" in user_config:
                    self.min_kelly_fraction = float(user_config["min_kelly_fraction"])
                if "max_kelly_fraction" in user_config:
                    self.max_kelly_fraction = float(user_config["max_kelly_fraction"])
                if "min_position_size" in user_config:
                    self.min_position_size = float(user_config["min_position_size"])
                if "min_liquidity_for_full_size" in user_config:
                    self.min_liquidity_for_full_size = float(user_config["min_liquidity_for_full_size"])
                
                # Load strategy selection thresholds (configurable via UI)
                if "volatility_threshold" in user_config:
                    self.volatility_threshold = float(user_config["volatility_threshold"])
                if "sentiment_strength_threshold" in user_config:
                    self.sentiment_strength_threshold = float(user_config["sentiment_strength_threshold"])
                if "sharp_alignment_threshold" in user_config:
                    self.sharp_alignment_threshold = float(user_config["sharp_alignment_threshold"])
                if "delta_neutral_price_min" in user_config:
                    self.delta_neutral_price_min = float(user_config["delta_neutral_price_min"])
                if "delta_neutral_price_max" in user_config:
                    self.delta_neutral_price_max = float(user_config["delta_neutral_price_max"])
                
                # Load sentiment-based side selection thresholds
                if "bullish_sentiment_threshold" in user_config:
                    self.bullish_sentiment_threshold = float(user_config["bullish_sentiment_threshold"])
                if "bearish_sentiment_threshold" in user_config:
                    self.bearish_sentiment_threshold = float(user_config["bearish_sentiment_threshold"])
                
                # Load NEW Polymarket sizer configuration
                if "use_polymarket_sizer" in user_config:
                    self.use_polymarket_sizer = bool(user_config["use_polymarket_sizer"])
                if "polymarket_fee_pct" in user_config:
                    self.polymarket_fee_pct = float(user_config["polymarket_fee_pct"])
                if "sector_caps" in user_config:
                    self.sector_caps.update(user_config["sector_caps"])
                
                # Load event caps configuration
                if "event_caps" in user_config:
                    self.event_caps = user_config["event_caps"]
                else:
                    self.event_caps = {
                        "max_event_exposure_pct": 0.15,
                        "similarity_threshold": 0.60,
                    }
                
                # Update polymarket sizer config if enabled
                if hasattr(self, 'polymarket_sizer') and self.polymarket_sizer:
                    self.polymarket_sizer.config['polymarket_fee_pct'] = self.polymarket_fee_pct
                    self.polymarket_sizer.config['sector_caps'].update(self.sector_caps)
                    self.polymarket_sizer.config['kelly_multiplier'] = self.kelly_fraction
                    self.polymarket_sizer.config['min_bet_floor'] = self.min_position_size
                    # Update event caps in sizer
                    self.polymarket_sizer.event_config.update(self.event_caps)
                
                # ==============================================================
                # TWO-SPEED ARCHITECTURE CONFIGURATION (HFT/Alpha)
                # ==============================================================
                
                # Store full config for components that need it
                self.config = user_config
                
                # HFT vs Alpha capital allocation
                if "hft_allocation_pct" in user_config:
                    self.hft_allocation_pct = float(user_config["hft_allocation_pct"])
                if "alpha_allocation_pct" in user_config:
                    self.alpha_allocation_pct = float(user_config["alpha_allocation_pct"])
                if "hft_max_position_pct" in user_config:
                    self.hft_max_position_pct = float(user_config["hft_max_position_pct"])
                if "alpha_max_position_pct" in user_config:
                    self.alpha_max_position_pct = float(user_config["alpha_max_position_pct"])
                if "hft_positions_pct" in user_config:
                    self.hft_positions_pct = float(user_config["hft_positions_pct"])
                if "alpha_positions_pct" in user_config:
                    self.alpha_positions_pct = float(user_config["alpha_positions_pct"])
                
                # Strategy Risk Multipliers - update position sizer
                if "strategy_risk_multipliers" in user_config:
                    self.strategy_risk_multipliers = user_config["strategy_risk_multipliers"]
                    # Update legacy position sizer with new strategy risk multipliers
                    if hasattr(self, 'position_sizer') and self.position_sizer:
                        self.position_sizer.update_config({'strategy_risk_multipliers': self.strategy_risk_multipliers})
                
                # Expiry thresholds
                if "expiry_thresholds" in user_config:
                    self.expiry_thresholds_config = user_config["expiry_thresholds"]
                if "expiry_strategy_adjustments" in user_config:
                    self.expiry_strategy_adjustments = user_config["expiry_strategy_adjustments"]
                
                # HFT Execution parameters - update maker executor
                if "hft_execution" in user_config:
                    self.hft_execution = user_config["hft_execution"]
                    # Update maker executor with HFT config
                    if hasattr(self, 'maker_executor') and self.maker_executor:
                        from trading.maker_executor import _merge_hft_config, DEFAULT_CONFIG
                        merged = _merge_hft_config(DEFAULT_CONFIG, user_config)
                        self.maker_executor.config.update(merged)
                        logger.info(f"  HFT Execution: inventory=${self.hft_execution.get('max_inventory_usd', 1000)}, skew={self.hft_execution.get('skew_factor', 0.05):.1%}")
                
                # Spread policy - update centralized spread constants
                if "spread_policy" in user_config:
                    self.spread_policy_config = user_config["spread_policy"]
                    from execution.spread_policy import update_spread_policy_from_config
                    update_spread_policy_from_config(user_config)
                    logger.info(f"  Spread Policy: HFT={self.spread_policy_config.get('max_spread_hft', 0.25):.0%}, Alpha={self.spread_policy_config.get('max_spread_alpha', 0.15):.0%}")
                
                # Variance sizing thresholds - store for use in position sizing
                if "variance_sizing" in user_config:
                    self.variance_sizing_config = user_config["variance_sizing"]
                    # Update legacy position sizer with variance sizing config
                    if hasattr(self, 'position_sizer') and self.position_sizer:
                        self.position_sizer.update_config({'variance_sizing': self.variance_sizing_config})
                    logger.info(f"  Variance Sizing: Kill switch {self.variance_sizing_config.get('kill_switch_low', 0.03):.0%}-{self.variance_sizing_config.get('kill_switch_high', 0.97):.0%}")
                
                # Recalculate derived values based on loaded config
                self.deployed_capital = self.initial_capital * (self.capital_deployment_pct / 100)
                self.max_position_size = self.deployed_capital * (self.max_position_size_pct / 100)
                self.trade_interval = max(0.1, 600 / self.trades_per_10min)  # Allow faster trading
                
                logger.info("=" * 60)
                logger.info("LOADED USER CONFIG FROM DATABASE:")
                logger.info(f"  Initial Capital: ${self.initial_capital:,.2f}")
                logger.info(f"  Capital Deployment: {self.capital_deployment_pct}% = ${self.deployed_capital:,.2f}")
                logger.info(f"  Max Position: {self.max_position_size_pct}% of deployed = ${self.max_position_size:,.2f}")
                logger.info(f"  Kelly: {self.kelly_fraction} (bounds: {self.min_kelly_fraction}-{self.max_kelly_fraction}) | Enabled: {self.kelly_enabled}")
                logger.info(f"  Event Caps: max={self.event_caps.get('max_event_exposure_pct', 0.15):.0%}, similarity={self.event_caps.get('similarity_threshold', 0.60):.0%}")
                logger.info(f"  Position Sizing: Min ${self.min_position_size:.0f}, Full Size @ ${self.min_liquidity_for_full_size:,.0f} vol")
                logger.info(f"  Max Drawdown: {self.max_drawdown_pct}%")
                logger.info(f"  Trades/10min: {self.trades_per_10min} | Interval: {self.trade_interval:.2f}s")
                logger.info(f"  Market Filters: Liq ${self.min_liquidity:,.0f}-${self.max_liquidity:,.0f}, Vol >= ${self.min_volume_24h:,.0f}, Spread <= {self.max_spread*100:.1f}%")
                logger.info(f"  Stuck Price Multiplier: {self.stuck_price_multiplier}x")
                logger.info(f"  Max Open Positions: {self.max_open_positions}")
                logger.info(f"  Strategies: {len(self.enabled_strategies)} | Asset Classes: {len(self.enabled_asset_classes)}")
                logger.info(f"  Strategy Thresholds: Vol={self.volatility_threshold}, Sentiment={self.sentiment_strength_threshold}, Sharp={self.sharp_alignment_threshold}")
                logger.info(f"  Delta-Neutral Price Range: {self.delta_neutral_price_min}-{self.delta_neutral_price_max}")
                logger.info(f"  Sentiment Side Thresholds: Bullish>{self.bullish_sentiment_threshold}, Bearish<{self.bearish_sentiment_threshold}")
                logger.info(f"  Exit Params: TP={self.exit_params_by_strategy.get('delta_neutral', {}).get('take_profit', 0):.0%} (Delta-Neutral)")
                logger.info(f"  Position Sizer: {'POLYMARKET (NEW)' if self.use_polymarket_sizer else 'LEGACY'}")
                logger.info(f"  Polymarket Fee: {self.polymarket_fee_pct*100:.1f}%")
                logger.info("=" * 60)
            else:
                logger.warning("No user config found in DB - using defaults")
                logger.info(f"  Using defaults: Capital=${self.initial_capital}, Kelly={self.kelly_fraction}")
        except Exception as e:
            logger.warning(f"Could not load user config: {e}")
    
    async def reload_config_live(self):
        """Reload configuration during a live session - hot reload"""
        old_kelly = self.kelly_fraction
        old_max_pos = self.max_position_size_pct
        
        await self._load_user_config()
        
        # Recalculate derived values
        self.deployed_capital = self.initial_capital * (self.capital_deployment_pct / 100)
        self.max_position_size = self.deployed_capital * (self.max_position_size_pct / 100)
        self.trade_interval = max(1, 600 / self.trades_per_10min)
        
        # Log what changed
        changes = []
        if old_kelly != self.kelly_fraction:
            changes.append(f"Kelly: {old_kelly} → {self.kelly_fraction}")
        if old_max_pos != self.max_position_size_pct:
            changes.append(f"Max Position: {old_max_pos}% → {self.max_position_size_pct}%")
        
        if changes:
            logger.info(f"Config hot-reloaded: {', '.join(changes)}")
        
        return {
            "reloaded": True,
            "changes": changes,
            "current_config": {
                "initial_capital": self.initial_capital,
                "deployed_capital": self.deployed_capital,
                "max_position_size": self.max_position_size,
                "kelly_fraction": self.kelly_fraction,
                "max_drawdown_pct": self.max_drawdown_pct,
            }
        }
    
    async def start(self):
        """Start paper trading session with TWO-SPEED ARCHITECTURE"""
        self.running = True
        logger.info(f"🚀 Starting Paper Trading Session: {self.session_id}")
        logger.info("=" * 60)
        logger.info("TWO-SPEED ARCHITECTURE ENABLED")
        logger.info("  HFT Loop:   Fast (0.5s) - Microstructure, Scalping")
        logger.info("  Alpha Loop: Slow (30s)  - Bayesian, LLM Analysis")
        logger.info("=" * 60)
        
        # Load user configuration
        await self._load_user_config()
        
        # Load RL model
        await self.rl_engine.load_model()
        
        # Initialize strategy context (shared state between loops)
        self.strategy_context = get_strategy_context()
        
        # Initialize real-time market service (WebSocket)
        if self.use_websocket_data:
            try:
                self.realtime_market_service = get_realtime_market_service()
                await self.realtime_market_service.start()
                logger.info("✅ WebSocket market service started - using real-time data")
            except Exception as e:
                logger.warning(f"⚠️ Could not start WebSocket service: {e} - falling back to REST polling")
                self.use_websocket_data = False
                self.realtime_market_service = None
        
        # Initialize session in DB
        await self._init_session()
        
        # =================================================================
        # TWO-SPEED ARCHITECTURE: Run HFT and Alpha loops CONCURRENTLY
        # =================================================================
        # - HFT Loop: Fast reactions, market microstructure, no LLM
        # - Alpha Loop: Slow analysis, Bayesian fusion, LLM sentiment
        # - Plus: monitoring, learning, emergency tasks
        await asyncio.gather(
            self._run_hft_loop(),              # Fast Path (0.5s cycle)
            self._run_alpha_loop(),            # Slow Path (30s cycle)
            self._position_monitoring_loop(),  # Exit monitoring
            self._learning_loop(),             # RL training
            self._continuous_mode_handler(),   # Session management
            self._emergency_stoploss_task(),   # Safety net
            self._run_news_loop(),             # Lane 5: NEWS (10s cycle)
            self._news_atomic_poller()         # Lane 5: Atomic cache updater (75ms)
        )
    
    # =================================================================
    # NEWS LOOP: THE INJECTOR (Lane 5)
    # =================================================================
    # Runs every 10 seconds
    # - Polls external news sources (Exa.ai)
    # - Analyzes news with LLM for market impact
    # - Injects signals into the trading system
    # =================================================================
    
    async def _run_news_loop(self):
        """
        News Injector Loop - Lane 5 of the 5-Lane Architecture.
        
        This loop:
        1. Polls Exa.ai for relevant news
        2. Matches news to active markets
        3. Analyzes with LLM (if available)
        4. Injects trade signals via execute_trade_cycle
        
        Runs every 10 seconds.
        """
        NEWS_CYCLE_INTERVAL = 10  # 10 seconds between cycles
        
        # Check if news polling is enabled
        if not self.news_poller.is_enabled():
            logger.warning("📰 [NEWS] News Loop DISABLED - EXA_API_KEY not configured")
            logger.warning("📰 [NEWS] To enable: export EXA_API_KEY='your-exa-api-key'")
            return
        
        logger.info("📰 NEWS Injector Loop Started")
        
        news_cycle_count = 0
        
        # Track recently processed headlines to avoid duplicates
        processed_headlines = set()
        
        while self.running:
            try:
                news_cycle_count += 1
                
                # Skip if in graceful stop mode
                if self.graceful_stop:
                    await asyncio.sleep(NEWS_CYCLE_INTERVAL)
                    continue
                
                # Get active markets to find relevant queries
                markets = await self._get_active_markets()
                if not markets:
                    await asyncio.sleep(NEWS_CYCLE_INTERVAL)
                    continue
                
                # Build search queries from market questions
                # Focus on markets with high volume or recent activity
                top_markets = sorted(
                    markets[:20],
                    key=lambda m: float(m.get('volume', 0) or 0),
                    reverse=True
                )[:5]
                
                for market_data in top_markets:
                    if not self.running:
                        break
                    
                    market_id = market_data.get('id', '')
                    question = market_data.get('question', '')
                    
                    # Skip if we already have a position
                    if market_id in self.paper_positions:
                        continue
                    
                    # Build search query from market question
                    # Extract key terms (simplified - could use NLP)
                    query = question[:100]  # Use first 100 chars
                    
                    # Poll for news
                    try:
                        events = await self.news_poller.poll_news(query, num_results=3)
                        
                        for event in events:
                            # Skip if already processed
                            headline_hash = hash(event.title[:50])
                            if headline_hash in processed_headlines:
                                continue
                            processed_headlines.add(headline_hash)
                            
                            # Log the news event
                            logger.info(f"📰 [NEWS] Found: {event.title[:60]}... ({event.source})")
                            
                            # TODO: Analyze with LLM (EmergentLLMService)
                            # For now, log and skip actual execution
                            # In production, this would:
                            # 1. Call EmergentLLMService for analysis
                            # 2. Calculate Bayesian posterior
                            # 3. If BF > 3.0, call execute_trade_cycle('NEWS', ...)
                            
                            source_reliability = self.news_poller.get_source_reliability(event.source)
                            
                            # Placeholder for future LLM integration
                            logger.info(
                                f"📰 [NEWS] Would analyze: '{event.title[:40]}...' "
                                f"(reliability={source_reliability:.0%})"
                            )
                        
                    except Exception as e:
                        logger.debug(f"[NEWS] Poll error for {market_id[:16]}: {e}")
                
                # Limit processed headlines cache size
                if len(processed_headlines) > 1000:
                    processed_headlines.clear()
                
                # Log cycle completion periodically
                if news_cycle_count % 30 == 0:
                    stats = self.news_poller.get_stats()
                    logger.info(
                        f"📰 [NEWS] Cycle {news_cycle_count}: "
                        f"{stats['total_events_found']} events found, "
                        f"{stats['successful_polls']}/{stats['total_polls']} polls succeeded"
                    )
                
                await asyncio.sleep(NEWS_CYCLE_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("📰 [NEWS] Loop cancelled")
                break
            except Exception as e:
                logger.error(f"📰 [NEWS] Loop error: {e}")
                await asyncio.sleep(NEWS_CYCLE_INTERVAL)
        
        logger.info("📰 NEWS Injector Loop Stopped")
    
    # =================================================================
    # NEWS ATOMIC POLLER (75ms Background Task)
    # =================================================================
    # Polls the signal cache and updates thread-safe local memory.
    # This enables ZERO-AWAIT reads in the HFT hot path.
    # =================================================================
    
    async def _news_atomic_poller(self):
        """
        Background task that polls the signal cache every 75ms.
        
        Updates self._news_atomic[market_id] with:
        - bayes_factor: Calculated BF from signal
        - direction: YES or NO
        - timestamp: When signal was created
        - expires_at: Signal expiration time
        - action: OVERRIDE, PAUSE, or IGNORE
        
        The HFT loop reads this atomically without await.
        """
        POLL_INTERVAL_MS = 75
        POLL_INTERVAL_S = POLL_INTERVAL_MS / 1000.0
        
        logger.info("🔄 [NEWS ATOMIC] Poller started (75ms interval)")
        
        while self.running:
            try:
                # Skip if no signal cache configured
                if not hasattr(self, '_signal_cache') or self._signal_cache is None:
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue
                
                # Get list of markets we're tracking
                markets_to_check = list(self.paper_positions.keys())
                
                # Also check markets from recent HFT activity
                if hasattr(self, '_recent_hft_markets'):
                    markets_to_check.extend(self._recent_hft_markets)
                
                markets_to_check = list(set(markets_to_check))[:50]  # Limit to 50 markets
                
                for market_id in markets_to_check:
                    try:
                        cache_key = f"emergent_signal:{market_id}"
                        signal = await self._signal_cache.get(cache_key)
                        
                        if signal:
                            # Calculate Bayes Factor
                            posterior = signal.get('posterior', 0.5)
                            prior = signal.get('prior', 0.5)
                            source_reliability = signal.get('source_reliability', 0.7)
                            
                            # Adjusted probability: shrink toward 0.5 by reliability
                            adj_prob = 0.5 + (posterior - 0.5) * source_reliability
                            adj_prob = max(0.01, min(0.99, adj_prob))
                            
                            # Bayes Factor: P(YES) / P(NO)
                            bayes_factor = adj_prob / (1 - adj_prob)
                            
                            # Determine action based on BF thresholds
                            action = self._determine_news_action(bayes_factor, signal)
                            
                            # Update atomic cache (thread-safe)
                            snapshot = {
                                'bayes_factor': bayes_factor,
                                'direction': signal.get('direction', 'NEUTRAL'),
                                'timestamp': signal.get('timestamp', datetime.now(timezone.utc).isoformat()),
                                'expires_at': signal.get('expires_at'),
                                'posterior': posterior,
                                'prior': prior,
                                'confidence': signal.get('confidence', 0.5),
                                'action': action,
                                'is_resolution': signal.get('is_resolution', False),
                                'spread_multiplier': 0.5 if action == 'OVERRIDE' else 1.0,
                                'size_multiplier': 2.0 if action == 'OVERRIDE' else 1.0,
                            }
                            
                            with self._news_atomic_lock:
                                self._news_atomic[market_id] = snapshot
                        else:
                            # No signal - remove from atomic cache
                            with self._news_atomic_lock:
                                if market_id in self._news_atomic:
                                    del self._news_atomic[market_id]
                    
                    except Exception as e:
                        logger.debug(f"[NEWS ATOMIC] Error polling {market_id[:8]}: {e}")
                
                await asyncio.sleep(POLL_INTERVAL_S)
                
            except asyncio.CancelledError:
                logger.info("🔄 [NEWS ATOMIC] Poller cancelled")
                break
            except Exception as e:
                logger.error(f"🔄 [NEWS ATOMIC] Poller error: {e}")
                await asyncio.sleep(1.0)  # Back off on error
        
        logger.info("🔄 [NEWS ATOMIC] Poller stopped")
    
    def _determine_news_action(self, bayes_factor: float, signal: Dict) -> str:
        """
        Determine action based on Bayes Factor thresholds.
        
        Returns:
            'OVERRIDE' - Strong signal, override Alpha, aggressive execution
            'PAUSE' - Extreme volatility, stop quoting
            'IGNORE' - Noise, continue with Alpha/Book
        """
        # Check for resolution signal (special case)
        if signal.get('is_resolution', False):
            return 'PAUSE'  # Market resolving - stop all activity
        
        # Extreme volatility: BF > 10.0
        if bayes_factor > 10.0:
            return 'PAUSE'
        
        # Actionable signal: BF >= 3.0
        if bayes_factor >= 3.0:
            return 'OVERRIDE'
        
        # Weak signal: 1.5 <= BF < 3.0
        if bayes_factor >= 1.5:
            return 'WEAK'  # May influence Alpha weight, but not override
        
        # Noise: BF < 1.5
        return 'IGNORE'
    
    def _check_for_news_signal(self, market_id: str) -> Dict:
        """
        SYNCHRONOUS check for news signal in atomic cache.
        
        This is the ZERO-AWAIT entry point for the HFT hot path.
        All data comes from local memory, updated by _news_atomic_poller().
        
        Args:
            market_id: Market to check
            
        Returns:
            Dict with:
            - action: 'OVERRIDE', 'PAUSE', 'IGNORE'
            - direction: 'YES', 'NO', 'NEUTRAL'
            - spread_multiplier: 0.5 (aggressive) to 1.5 (defensive)
            - size_multiplier: 0.5 to 2.0
            - reason: Human-readable explanation
        """
        result = {
            'action': 'IGNORE',
            'direction': 'NEUTRAL',
            'spread_multiplier': 1.0,
            'size_multiplier': 1.0,
            'bayes_factor': 1.0,
            'reason': 'No news signal'
        }
        
        try:
            # Thread-safe read from atomic cache
            with self._news_atomic_lock:
                snapshot = self._news_atomic.get(market_id)
            
            if not snapshot:
                return result
            
            # STALENESS CHECK: Signals older than 60s are ignored
            timestamp_str = snapshot.get('timestamp')
            if timestamp_str:
                try:
                    signal_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    age_seconds = (datetime.now(timezone.utc) - signal_time).total_seconds()
                    
                    if age_seconds > 60.0:
                        result['reason'] = f'Stale signal ({age_seconds:.0f}s old)'
                        return result
                except Exception:
                    pass  # Ignore timestamp parsing errors
            
            # EXPIRATION CHECK
            expires_at = snapshot.get('expires_at')
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > expiry:
                        result['reason'] = 'Signal expired'
                        return result
                except Exception:
                    pass
            
            # Get action from snapshot
            action = snapshot.get('action', 'IGNORE')
            bf = snapshot.get('bayes_factor', 1.0)
            direction = snapshot.get('direction', 'NEUTRAL')
            
            if action == 'PAUSE':
                # Extreme volatility or resolution - stop quoting
                result.update({
                    'action': 'PAUSE',
                    'direction': direction,
                    'spread_multiplier': 2.0,  # Widen spread if we do quote
                    'size_multiplier': 0.0,    # No new positions
                    'bayes_factor': bf,
                    'reason': f'PAUSE: BF={bf:.1f}, high volatility/resolution'
                })
            
            elif action == 'OVERRIDE':
                # Strong actionable signal - override Alpha
                result.update({
                    'action': 'OVERRIDE',
                    'direction': direction,
                    'spread_multiplier': 0.5,  # Aggressive - tighter spread
                    'size_multiplier': 2.0,    # Double size
                    'bayes_factor': bf,
                    'reason': f'OVERRIDE: BF={bf:.1f}, direction={direction}'
                })
            
            elif action == 'WEAK':
                # Weak signal - note but don't override
                result.update({
                    'action': 'WEAK',
                    'direction': direction,
                    'spread_multiplier': 0.9,  # Slightly tighter
                    'size_multiplier': 1.2,    # Slight size boost
                    'bayes_factor': bf,
                    'reason': f'WEAK: BF={bf:.1f}, direction={direction}'
                })
            
            else:
                # Noise
                result['reason'] = f'Noise: BF={bf:.1f}'
            
            return result
            
        except Exception as e:
            logger.debug(f"[NEWS CHECK] Error for {market_id[:8]}: {e}")
            return result
    
    # =================================================================
    # HFT LOOP: THE REFLEX (Fast Path)
    # =================================================================
    # Runs every 0.5-1.0s
    # - Checks orderbook spreads and microstructure
    # - Executes "reflex" trades (scalps, spread capture)
    # - Uses Alpha's theoretical prices if available
    # - NO LLM calls, NO heavy Bayesian computation
    # =================================================================
    
    async def _run_hft_loop(self):
        """
        HFT Reflex Loop - Fast, reactive trading based on market microstructure.
        
        This loop:
        1. Fetches orderbook snapshots (fast)
        2. Checks for scalping/arbitrage opportunities
        3. Uses Alpha's fair value targets if available
        4. Executes maker orders to capture spread
        
        Runs every 0.5 seconds.
        """
        HFT_CYCLE_INTERVAL = 0.5  # 500ms between cycles
        
        logger.info("🚀 HFT Reflex Loop Started")
        
        hft_cycle_count = 0
        
        while self.running:
            try:
                hft_cycle_count += 1
                cycle_start = datetime.now(timezone.utc)
                
                # Skip if in graceful stop mode
                if self.graceful_stop:
                    await asyncio.sleep(HFT_CYCLE_INTERVAL)
                    continue
                
                # 1. FAST FETCH: Get market snapshots (orderbook focused)
                markets = await self._get_active_markets()
                
                if not markets:
                    await asyncio.sleep(HFT_CYCLE_INTERVAL)
                    continue
                
                # 2. REFLEX CHECK: Process markets for HFT opportunities
                # Only process markets where we have Alpha targets OR good spreads
                hft_evaluated = 0
                hft_triggered = 0
                
                for market_data in markets[:50]:  # Process top 50 for speed
                    if not self.running:
                        break
                    
                    market_id = market_data.get('id')
                    
                    # Skip if we already have a position (let Alpha/monitoring handle exits)
                    if market_id in self.paper_positions:
                        continue
                    
                    # Check if Alpha has analyzed this market
                    alpha_target = self.strategy_context.get_target(market_id)
                    
                    if alpha_target and not alpha_target.get('stale'):
                        # SMART MODE: Use Alpha's fair value
                        opportunity = await self._evaluate_hft_opportunity(
                            market_data, 
                            fair_value=alpha_target['fair_value'],
                            regime=alpha_target['regime']
                        )
                    else:
                        # SCALP MODE: Pure market microstructure (autonomous)
                        # Fetch orderbook for scalp evaluation
                        try:
                            token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
                            if token_ids and isinstance(token_ids, list) and len(token_ids) > 0:
                                from data.polymarket_api import PolymarketAPI
                                async with PolymarketAPI() as api:
                                    order_book_data = await api.get_order_book(token_ids[0])
                                    if order_book_data.get('bids') and order_book_data.get('asks'):
                                        market_data['order_book'] = order_book_data
                                        bids = order_book_data['bids']
                                        asks = order_book_data['asks']
                                        market_data['best_bid'] = float(bids[0]['price']) if bids else 0
                                        market_data['best_ask'] = float(asks[0]['price']) if asks else 1
                        except Exception as e:
                            logger.debug(f"[HFT] Could not fetch orderbook: {e}")
                        
                        opportunity = await self._evaluate_hft_scalp(market_data)
                    
                    hft_evaluated += 1
                    
                    if opportunity and opportunity.get('should_trade'):
                        hft_triggered += 1
                        await self._execute_hft_trade(market_data, opportunity)
                
                # Record cycle completion
                self.strategy_context.record_hft_cycle()
                
                # Log every 20 cycles
                if hft_cycle_count % 20 == 0:
                    cycle_time = (datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000
                    bridge_stats = self.strategy_context.get_stats()
                    logger.info(
                        f"[HFT #{hft_cycle_count}] Evaluated: {hft_evaluated}, "
                        f"Triggered: {hft_triggered}, Cycle: {cycle_time:.0f}ms, "
                        f"Alpha Hits: {bridge_stats['hit_rate']:.1%}"
                    )
                
                # 3. SLEEP: Brief pause for next cycle
                await asyncio.sleep(HFT_CYCLE_INTERVAL)
                
            except Exception as e:
                logger.error(f"[HFT ERROR] {e}")
                await asyncio.sleep(1)
        
        logger.info("🛑 HFT Reflex Loop Stopped")
    
    async def _evaluate_hft_opportunity(self, market_data: Dict, fair_value: float, regime: str) -> Optional[Dict]:
        """
        Evaluate HFT opportunity using Alpha's theoretical price.
        
        This is "Smart HFT" - we know what Alpha thinks the fair value is,
        so we can post limit orders around that price to capture spread.
        
        Task 21: Simplified to ZOMBIE/MAKER_WIDE/TAKER_TIGHT regimes.
        """
        try:
            market_id = market_data.get('id', '')
            yes_price = market_data.get('yes_price')
            
            if yes_price is None or yes_price == 0:
                return None
            
            yes_price = float(yes_price)
            
            # Skip zombie markets
            if regime == MarketRegime.ZOMBIE:
                return None
            
            # Check capital availability
            current_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
            available_capital = self.deployed_capital - current_deployed
            if available_capital < 5:
                return None
            
            # Get orderbook data for spread-based strategies
            best_bid = market_data.get('best_bid', 0)
            best_ask = market_data.get('best_ask', 0)
            spread = best_ask - best_bid if (best_bid > 0 and best_ask > 0) else 0
            
            # =================================================================
            # REGIME-SPECIFIC STRATEGIES (Task 21: Dual-Zone Architecture)
            # =================================================================
            # Zone 1: CONVEXITY_OPPORTUNITY (Whale Zone - price < $0.10)
            # Zone 2: TAKER_TIGHT, MAKER_WIDE (Core Zone - price >= $0.10)
            # Skip: ZOMBIE
            
            # Log regime for debugging
            logger.info(f"[HFT-REGIME] {market_id[:16]}... regime={regime} yes_price={yes_price:.4f} FV={fair_value:.4f}")
            
            # Skip zombie markets
            if regime == MarketRegime.ZOMBIE:
                return None
            
            # CONVEXITY_OPPORTUNITY: Whale Zone - Delegate to GammaTrader (Task 22)
            # Uses isolated gamma_strategy.py for Gap vs. Wall logic
            if regime == MarketRegime.CONVEXITY_OPPORTUNITY:
                # Build market data with orderbook for GammaTrader
                gamma_market_data = {
                    'id': market_id,
                    'yes_price': yes_price,
                    'no_price': 1 - yes_price,
                    'clobTokenIds': market_data.get('clobTokenIds', []),
                    'order_book': {
                        'bids': [{'price': str(best_bid), 'size': str(market_data.get('bid_volume', 100))}] if best_bid > 0 else [],
                        'asks': [{'price': str(best_ask), 'size': str(market_data.get('ask_volume', 100))}] if best_ask > 0 else [],
                    }
                }
                
                # Generate orders using GammaTrader (isolated logic)
                gamma_orders = self.gamma_trader.calculate_orders(
                    market_data=gamma_market_data,
                    active_positions=self.paper_positions,
                    available_capital=available_capital
                )
                
                if gamma_orders:
                    order = gamma_orders[0]  # Take first order
                    return {
                        'should_trade': True,
                        'side': order.side,
                        'size': order.size,
                        'edge': abs(fair_value - yes_price),
                        'fair_value': fair_value,
                        'strategy': 'gamma_scalp',
                        'regime': regime,
                        'zone': 'WHALE',
                        'gamma_order_type': order.order_type.value,
                        'gamma_reason': order.reason.value,
                        'gamma_price': order.price,
                    }
                return None
            
            # MAKER_WIDE: Spread 2-12% - Maker opportunity
            # Strategy: Post limit orders inside the spread
            if regime == MarketRegime.MAKER_WIDE:
                if best_bid <= 0 or best_ask <= 0:
                    return None  # Need orderbook for maker strategy
                
                # Calculate edge from Alpha's fair value
                edge = fair_value - yes_price
                min_hft_edge = 0.005  # 0.5% edge for maker
                
                if abs(edge) > min_hft_edge:
                    side = 'YES' if edge > 0 else 'NO'
                    
                    # ==========================================================
                    # EDGE DIRECTION SAFEGUARD (Jan 2026)
                    # ==========================================================
                    # If price has moved significantly since Alpha analysis,
                    # the edge may have flipped direction. In this case, the
                    # original thesis is invalidated - DO NOT TRADE.
                    #
                    # EXCEPTION: Sports markets can trade NO side (for arbitrage)
                    # Sports config controls whether NO bets are allowed
                    #
                    # TEMPORARY FIX: Only trade YES side until model is validated
                    # This prevents systematic losses from stale fair value predictions
                    market_category = market_data.get('category', '').lower()
                    is_sports = market_data.get('_is_sports', False) or is_sports_market(market_data.get('question', ''))
                    sports_config = get_sports_config()
                    
                    if side == 'NO':
                        # Sports markets: Allow NO if enabled in config
                        if is_sports and sports_config.enabled and sports_config.allow_no_bets:
                            logger.debug(f"[HFT] Sports NO trade allowed: {market_id[:16]}...")
                            pass  # Allow the trade
                        else:
                            logger.debug(f"[HFT-SKIP] Skipping NO maker trade")
                            return None
                    
                    hft_size = min(
                        available_capital * 0.02,  # Max 2% per trade
                        self.max_position_size * 0.5,
                        50.0
                    )
                    
                    return {
                        'should_trade': True,
                        'side': side,
                        'size': hft_size,
                        'edge': abs(edge),
                        'fair_value': fair_value,
                        'strategy': 'hft_maker',
                        'regime': regime,
                    }
                return None
            
            # TAKER_TIGHT: Spread < 2% - Standard edge-based logic
            edge = fair_value - yes_price
            min_hft_edge = 0.008  # 0.8% edge for tight markets
            
            # DEBUG: Log the calculation (temp INFO for visibility)
            logger.info(
                f"[HFT-EDGE] {market_id[:16]}... FV={fair_value:.4f} yes_price={yes_price:.4f} "
                f"edge={edge:.4f} abs_edge={abs(edge):.4f} min={min_hft_edge}"
            )
            
            if abs(edge) > min_hft_edge:
                side = 'YES' if edge > 0 else 'NO'
                
                # ==========================================================
                # EDGE DIRECTION SAFEGUARD (Jan 2026)
                # ==========================================================
                # If price has moved significantly since Alpha analysis,
                # the edge may have flipped direction. In this case, the
                # original thesis is invalidated - DO NOT TRADE.
                #
                # EXCEPTION: Sports markets can trade NO side (for arbitrage)
                # We only trade if the current edge is POSITIVE (YES is underpriced)
                # or if we're confident in the model's fair value prediction.
                #
                # TEMPORARY FIX: Only trade YES side until model is validated
                # This prevents systematic losses from stale fair value predictions
                is_sports = market_data.get('_is_sports', False) or is_sports_market(market_data.get('question', ''))
                sports_config = get_sports_config()
                
                if side == 'NO':
                    # Sports markets: Allow NO if enabled in config
                    if is_sports and sports_config.enabled and sports_config.allow_no_bets:
                        logger.info(f"[HFT-SPORTS] Sports NO taker trade allowed")
                        pass  # Allow the trade
                    else:
                        logger.info(f"[HFT-SKIP] Skipping NO trade (edge flipped or FV < market)")
                        return None
                
                logger.info(f"[HFT-SIDE] edge={edge:.4f} > 0 is {edge > 0} → side={side}")
                
                hft_size = min(
                    available_capital * 0.02,  # Max 2% per HFT trade
                    self.max_position_size * 0.5,
                    50.0
                )
                
                return {
                    'should_trade': True,
                    'side': side,
                    'size': hft_size,
                    'edge': abs(edge),
                    'fair_value': fair_value,
                    'strategy': 'hft_taker',
                    'regime': regime,
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"[HFT] Error evaluating opportunity: {e}")
            return None
    
    # =============================================================================
    # POLYMARKET ORDER LIFECYCLE MANAGER (Jan 2026)
    # =============================================================================
    
    def _prune_stale_orders(self, market_id: str, current_ai_price: float) -> Dict:
        """
        Prune stale or drifted orders with hysteresis (anti-churn) logic.
        
        This prevents "order churn" - the expensive habit of cancelling and
        re-placing orders for small price changes. Queue priority is valuable.
        
        Logic:
        1. If drift <= HYSTERESIS_THRESHOLD (1 cent): KEEP order (anti-churn)
        2. If drift > HYSTERESIS_THRESHOLD: CANCEL (AI changed mind)
        3. If age > ORDER_STALE_SECONDS (120s): CANCEL (refresh liquidity)
        4. If price outside kill zones: CANCEL (safety)
        
        Returns:
            Dict with pruning statistics and actions taken
        """
        now = datetime.now(timezone.utc)
        stats = {
            'orders_checked': 0,
            'orders_kept_hysteresis': 0,
            'orders_cancelled_drift': 0,
            'orders_cancelled_stale': 0,
            'orders_cancelled_bounds': 0,
            'total_cancelled': 0,
        }
        
        # Get order for this market (if exists)
        order = self.active_orders.get(market_id)
        if not order:
            return stats
        
        stats['orders_checked'] = 1
        order_price = order.get('price', 0)
        order_time = order.get('timestamp')
        should_cancel = False
        cancel_reason = ""
        
        # =============================================================
        # CHECK 1: BOUNDS VIOLATION (Safety First)
        # =============================================================
        if order_price < self.MIN_PRICE or order_price > self.MAX_PRICE:
            should_cancel = True
            cancel_reason = f"BOUNDS_VIOLATION (price={order_price:.2f})"
            stats['orders_cancelled_bounds'] += 1
        
        # =============================================================
        # CHECK 2: STALENESS (Refresh Liquidity)
        # =============================================================
        elif order_time:
            age_seconds = (now - order_time).total_seconds()
            if age_seconds > self.ORDER_STALE_SECONDS:
                should_cancel = True
                cancel_reason = f"STALE ({age_seconds:.0f}s > {self.ORDER_STALE_SECONDS}s)"
                stats['orders_cancelled_stale'] += 1
        
        # =============================================================
        # CHECK 3: DRIFT vs HYSTERESIS (Anti-Churn)
        # =============================================================
        # Uses SEMANTIC ROUNDING for robust floating-point handling:
        # - Raw drift like 0.01000001 becomes 0.01 (KEEP)
        # - Raw drift like 0.01400000 becomes 0.014 (CANCEL)
        # This is cleaner than epsilon buffers - explicitly states precision tolerance
        if not should_cancel:
            raw_drift = abs(order_price - current_ai_price)
            
            # Round drift to 4 decimals (0.1 bps precision) to strip float noise
            clean_drift = round(raw_drift, 4)
            
            if clean_drift <= self.HYSTERESIS_THRESHOLD:
                # Small drift - KEEP the order to preserve queue priority
                stats['orders_kept_hysteresis'] += 1
                logger.debug(
                    f"[HFT-PRUNE] Keeping {market_id[:16]}... order "
                    f"(drift={clean_drift:.4f} <= {self.HYSTERESIS_THRESHOLD})"
                )
            else:
                # Large drift - AI has changed its mind significantly
                should_cancel = True
                cancel_reason = f"DRIFT ({clean_drift:.4f} > {self.HYSTERESIS_THRESHOLD})"
                stats['orders_cancelled_drift'] += 1
        
        # =============================================================
        # EXECUTE CANCELLATION
        # =============================================================
        if should_cancel:
            # Remove from active orders
            del self.active_orders[market_id]
            stats['total_cancelled'] += 1
            
            logger.info(
                f"[HFT-PRUNE] ❌ Cancelled {market_id[:16]}... | "
                f"Reason: {cancel_reason} | "
                f"Old Price: ${order_price:.2f} → AI Price: ${current_ai_price:.2f}"
            )
        
        return stats
    
    def _round_to_tick(self, price: float) -> float:
        """Round price to Polymarket tick grid ($0.01)."""
        return round(price, 2)
    
    def _clamp_to_bounds(self, price: float) -> float:
        """Clamp price to kill zone bounds [$0.05, $0.95]."""
        return max(self.MIN_PRICE, min(self.MAX_PRICE, price))
    
    def _enforce_min_spread(self, bid: float, ask: float) -> tuple:
        """
        Enforce minimum spread of 2 ticks ($0.02).
        
        If spread is too tight, widen symmetrically around mid-point.
        Returns (new_bid, new_ask) tuple.
        """
        min_spread = self.MIN_SPREAD_TICKS * self.TICK_SIZE
        current_spread = ask - bid
        
        if current_spread >= min_spread:
            return bid, ask
        
        # Widen symmetrically
        mid = (bid + ask) / 2
        half_spread = min_spread / 2
        
        new_bid = self._round_to_tick(mid - half_spread)
        new_ask = self._round_to_tick(mid + half_spread)
        
        # Re-apply bounds after widening
        new_bid = self._clamp_to_bounds(new_bid)
        new_ask = self._clamp_to_bounds(new_ask)
        
        # Final sanity check - ensure ask > bid
        if new_ask <= new_bid:
            new_ask = new_bid + min_spread
            new_ask = self._clamp_to_bounds(new_ask)
        
        return new_bid, new_ask
    
    def _calculate_order_qty(self, usd_size: float, limit_price: float) -> int:
        """
        Convert USD size to integer share quantity.
        
        Polymarket uses integer contracts. This is the "Dust Guard" -
        prevents placing orders for 0 shares.
        
        Returns: Integer quantity (0 if too small to trade)
        """
        if limit_price <= 0:
            return 0
        
        qty = int(usd_size // limit_price)
        return max(0, qty)  # Dust guard: minimum 0

    async def _evaluate_hft_scalp(self, market_data: Dict) -> Optional[Dict]:
        """
        Evaluate HFT scalping opportunity with SIGNAL HIERARCHY integration.
        
        SIGNAL HIERARCHY (Priority Order):
        1. NEWS (Highest) - Overrides everything if BF >= 3.0
        2. ALPHA (Medium) - AI fair value with age-decay weighting
        3. ORDER BOOK (Lowest) - Pure microstructure fallback
        
        ZERO-AWAIT HOT PATH:
        - News signals read from _news_atomic (local memory)
        - Alpha signals read from HFTContext (local cache)
        - No async calls in the decision logic
        
        GRACEFUL DEGRADATION:
        - If News unavailable → Use Alpha
        - If Alpha stale → Use Order Book with safety spread
        - If all fail → Return None (don't trade blind)
        
        Author: APEX TRADER Quantitative Architecture Team
        Date: February 2026 (Signal Hierarchy Integration)
        """
        try:
            market_id = market_data.get('id', '')
            yes_price = market_data.get('yes_price')
            volume_24h = market_data.get('volume_24h', 0) or 0
            
            if yes_price is None or yes_price == 0:
                return None
            
            yes_price = float(yes_price)
            
            # Track this market for news polling
            if not hasattr(self, '_recent_hft_markets'):
                self._recent_hft_markets = []
            if market_id not in self._recent_hft_markets:
                self._recent_hft_markets.append(market_id)
                self._recent_hft_markets = self._recent_hft_markets[-100:]  # Keep last 100
            
            # =============================================================
            # STEP 1: NEWS CHECK (Highest Priority) - ZERO AWAIT
            # =============================================================
            # Read from atomic cache - no async call
            news_signal = self._check_for_news_signal(market_id)
            
            # Initialize multipliers (will be overridden by signals)
            spread_multiplier = 1.0
            size_multiplier = 1.0
            target_price = None
            signal_source = 'NONE'
            forced_direction = None
            
            if news_signal['action'] == 'PAUSE':
                # Extreme volatility or resolution - STOP QUOTING
                logger.info(f"[HFT] 📰 PAUSE: {market_id[:16]}... - {news_signal['reason']}")
                return None
            
            elif news_signal['action'] == 'OVERRIDE':
                # Strong news signal - OVERRIDE Alpha
                signal_source = 'NEWS'
                spread_multiplier = news_signal['spread_multiplier']  # 0.5 (aggressive)
                size_multiplier = news_signal['size_multiplier']      # 2.0
                forced_direction = news_signal['direction']
                logger.info(f"[HFT] 📰 NEWS OVERRIDE: {market_id[:16]}... BF={news_signal['bayes_factor']:.1f} → {forced_direction}")
                # Skip Alpha checks - go directly to execution
            
            elif news_signal['action'] == 'WEAK':
                # Weak news signal - note but continue to Alpha
                signal_source = 'NEWS_WEAK'
                spread_multiplier = news_signal['spread_multiplier']  # 0.9
                size_multiplier = news_signal['size_multiplier']      # 1.2
                # Continue to Alpha for additional guidance
            
            # =============================================================
            # STEP 2: ALPHA CHECK (Medium Priority) - Only if no News Override
            # =============================================================
            if signal_source != 'NEWS':
                hft_ctx = get_hft_context()
                params = hft_ctx.get(market_id)
                
                if params is None:
                    # No Alpha context - check if we can fall back to Order Book
                    if signal_source != 'NEWS_WEAK':
                        logger.debug(f"[HFT] No context for {market_id[:16]}... - checking Order Book fallback")
                        signal_source = 'BOOK_ONLY'
                        spread_multiplier = 1.5  # Safety spread
                        size_multiplier = 0.5   # Half size
                    # If NEWS_WEAK, continue with that signal
                
                elif params.status == ContextStatus.KILL:
                    logger.debug(f"[HFT] KILL switch active for {market_id[:16]}...")
                    return None
                
                elif params.status == ContextStatus.PAUSED:
                    logger.debug(f"[HFT] PAUSED for {market_id[:16]}...")
                    return None
                
                else:
                    # Alpha context available - calculate weight based on age
                    alpha_age = params.get_age_seconds()
                    
                    if alpha_age < 2.0:
                        # FRESH Alpha (<2s): Full weight
                        alpha_weight = 1.0
                        signal_source = 'ALPHA_FRESH' if signal_source == 'NONE' else signal_source
                    elif alpha_age < 10.0:
                        # DECAYING Alpha (2-10s): Linear decay from 1.0 to 0.0
                        alpha_weight = 1.0 - ((alpha_age - 2.0) / 8.0)
                        signal_source = 'ALPHA_DECAY' if signal_source == 'NONE' else signal_source
                    else:
                        # STALE Alpha (>10s): No weight, use Order Book
                        alpha_weight = 0.0
                        signal_source = 'BOOK_ONLY' if signal_source == 'NONE' else signal_source
                        spread_multiplier = max(spread_multiplier, 1.5)  # Safety spread
                    
                    # Calculate target price: blend Alpha FV with Order Book Mid
                    if alpha_weight > 0 and params.fair_value:
                        alpha_fv = params.fair_value
                    else:
                        alpha_fv = yes_price
            else:
                # News OVERRIDE - skip Alpha entirely
                alpha_weight = 0.0
                params = None
                alpha_fv = yes_price
            
            # =============================================================
            # STEP 3: ORDER BOOK ANALYSIS (Lowest Priority / Fallback)
            # =============================================================
            best_bid = market_data.get('best_bid', 0)
            best_ask = market_data.get('best_ask', 0)
            
            if best_bid == 0 or best_ask == 0:
                order_book = market_data.get('order_book', {})
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
                if bids and asks:
                    best_bid = float(bids[0]['price'])
                    best_ask = float(asks[0]['price'])
                else:
                    return None  # No orderbook data
            
            book_mid = (best_bid + best_ask) / 2
            market_spread = best_ask - best_bid
            
            # Basic filters
            MIN_SCALP_VOLUME = 500
            if volume_24h < MIN_SCALP_VOLUME:
                return None
            
            if market_id in self.paper_positions:
                return None  # Already have position
            
            current_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
            available_capital = self.deployed_capital - current_deployed
            if available_capital < 10:
                return None
            
            # =============================================================
            # STEP 4: CALCULATE TARGET PRICE (Blended or Forced)
            # =============================================================
            if forced_direction:
                # News OVERRIDE - use forced direction
                if forced_direction == 'YES':
                    target_price = best_ask  # Buy YES at ask
                    side = 'YES'
                    edge = 0.05  # Assumed edge from news signal
                elif forced_direction == 'NO':
                    # Check if NO bets are allowed
                    is_sports = is_sports_market(market_data.get('question', ''))
                    sports_config = get_sports_config()
                    if is_sports and sports_config.allow_no_bets:
                        target_price = 1 - best_bid  # Buy NO
                        side = 'NO'
                        edge = 0.05
                    else:
                        return None  # NO bets not allowed
                else:
                    return None  # Invalid direction
            else:
                # Blend Alpha FV with Book Mid based on alpha_weight
                if signal_source == 'BOOK_ONLY':
                    target_price = book_mid
                    alpha_weight = 0.0
                else:
                    target_price = (alpha_fv * alpha_weight) + (book_mid * (1 - alpha_weight))
                
                # Calculate edge
                edge = target_price - yes_price
                
                # Determine side
                if abs(edge) < 0.005:  # Less than 0.5% edge
                    return None
                
                side = 'YES' if edge > 0 else 'NO'
                
                # Safety: Only YES unless sports
                if side == 'NO':
                    is_sports = is_sports_market(market_data.get('question', ''))
                    sports_config = get_sports_config()
                    if not (is_sports and sports_config.allow_no_bets):
                        return None
            
            # =============================================================
            # STEP 5: APPLY SPREAD & SIZE MULTIPLIERS
            # =============================================================
            # Get base spread from Alpha or default
            if params and hasattr(params, 'base_spread_bps'):
                base_spread = params.base_spread_bps / 10000
            else:
                base_spread = 0.005  # 50 bps default
            
            final_spread = base_spread * spread_multiplier
            
            # Cliff protection (near 0 or 1)
            dist_from_edge = min(yes_price, 1.0 - yes_price)
            if dist_from_edge < 0.05:
                final_spread *= 3.0  # Triple spread near extremes
            elif dist_from_edge < 0.15:
                final_spread *= 2.0  # Double spread in cliff zone
            
            # =============================================================
            # STEP 6: CALCULATE POSITION SIZE
            # =============================================================
            confidence = params.confidence if params else 0.5
            confidence_mult = min(1.0, confidence * 1.5)
            edge_mult = min(1.0, abs(edge) * 20)
            
            scalp_size_usd = min(
                available_capital * 0.02 * confidence_mult * edge_mult * size_multiplier,
                25.0 * size_multiplier,  # Cap scales with multiplier
                self.max_position_size * 0.4
            )
            scalp_size_usd = max(scalp_size_usd, 5.0)
            
            # Entry price
            entry_price = round(best_ask if side == 'YES' else (1 - best_bid), 2)
            
            # Integer share conversion
            order_qty = self._calculate_order_qty(scalp_size_usd, entry_price)
            if order_qty < 1:
                return None
            
            scalp_size = order_qty * entry_price
            
            # =============================================================
            # STEP 7: INVENTORY GUARD
            # =============================================================
            hft_positions = [p for p in self.paper_positions.values() 
                           if self._get_strategy_path(p.get('strategy', '')) == 'HFT']
            total_hft_value = sum(p.get('size', 0) for p in hft_positions)
            hft_long_value = sum(p.get('size', 0) for p in hft_positions if p.get('side') == 'YES')
            
            max_inventory_skew = params.max_inventory_skew if params else 0.30
            
            if total_hft_value > 0:
                current_skew_ratio = hft_long_value / total_hft_value
            else:
                current_skew_ratio = 0.5
            
            bias = params.bias if params else 0.0
            
            if bias > 0 and side == 'YES' and current_skew_ratio > (0.5 + max_inventory_skew):
                logger.debug(f"[HFT] Inventory guard: Already {current_skew_ratio:.0%} long")
                return None
            
            if bias < 0 and side == 'NO' and current_skew_ratio < (0.5 - max_inventory_skew):
                logger.debug(f"[HFT] Inventory guard: Already {(1-current_skew_ratio):.0%} short")
                return None
            
            # =============================================================
            # RETURN HFT PARAMS
            # =============================================================
            regime = params.regime if params else 'TAKER_TIGHT'
            strategy = 'hft_scalp' if regime == 'TAKER_TIGHT' else 'hft_maker'
            
            logger.info(
                f"[HFT] {signal_source}: {market_id[:16]}... | {side} ${scalp_size:.2f} | "
                f"edge={abs(edge):.2%} | spread_mult={spread_multiplier:.1f} | size_mult={size_multiplier:.1f}"
            )
            
            return {
                'market_id': market_id,
                'strategy': strategy,
                'side': side,
                'size': scalp_size,
                'entry_price': entry_price,
                'edge': abs(edge),
                'order_qty': order_qty,
                'tick_aligned': True,
                'fair_value': target_price,
                'regime': regime,
                'signal_source': signal_source,
                'spread_multiplier': spread_multiplier,
                'size_multiplier': size_multiplier,
                'alpha_weight': alpha_weight if 'alpha_weight' in dir() else 0.0,
                'news_bf': news_signal.get('bayes_factor', 1.0),
            }
            
        except Exception as e:
            logger.error(f"[HFT] Error evaluating scalp for {market_data.get('id', 'unknown')[:16]}: {e}")
            return None
            
            # =============================================================
            # STEP 2B: Real-Time Volatility Adaptation (STATE ISOLATED)
            # =============================================================
            # Store price tick in market-specific history for volatility calc
            if market_id not in self.volatility_memory:
                self.volatility_memory[market_id] = []
            
            # Keep last 20 ticks per market
            self.volatility_memory[market_id].append(yes_price)
            if len(self.volatility_memory[market_id]) > 20:
                self.volatility_memory[market_id] = self.volatility_memory[market_id][-20:]
            
            # Calculate volatility from stored price history
            vol_calc = get_volatility_calculator()
            vol_calc.add_tick(market_id, yes_price)  # Feed real-time service too
            vol_multiplier = vol_calc.get_vol_multiplier(market_id, params.reference_volatility)
            
            # =============================================================
            # STEP 3: Cubic Inventory Skew (STATE ISOLATED)
            # =============================================================
            # Calculate current inventory for this market type
            hft_positions = [
                p for p in self.paper_positions.values()
                if RISK.get_strategy_path(p.get('strategy', '')) == 'HFT'
            ]
            
            total_hft_value = sum(p.get('size', 0) for p in hft_positions)
            hft_long_value = sum(
                p.get('size', 0) for p in hft_positions
                if p.get('side', '').upper() in ['YES', 'BUY', 'LONG']
            )
            hft_short_value = total_hft_value - hft_long_value
            
            # Net inventory: positive = long, negative = short
            current_inventory = hft_long_value - hft_short_value
            
            # Apply CUBIC skew using HFT Math Engine
            # fair_value comes from smoothed price + AI context adjustment
            ai_fair_value = params.fair_value
            
            # Blend AI fair value with smoothed market price (70% AI, 30% smoothed)
            blended_fair_value = (ai_fair_value * 0.7) + (smoothed_price * 0.3)
            
            # Cubic skew: adjust fair value based on inventory
            skewed_fair_value, skew_amount, skew_debug = self.hft_math_engine.skew.calculate_skew(
                current_position=current_inventory,
                raw_fair_value=blended_fair_value,
                max_position=self.hft_math_config.max_position_limit,
                intensity=self.hft_math_config.skew_intensity,
            )
            
            # =============================================================
            # STEP 4: Cliff Protection Spread (Near 0/1 Boundaries)
            # =============================================================
            # Get base spread from AI context
            base_spread = params.base_spread_bps / 10000  # Convert bps to decimal
            
            # Apply cliff protection: widen spread near $0.00 or $1.00
            spread_multiplier, cliff_zone, cliff_debug = self.hft_math_engine.cliff.calculate_spread_multiplier(
                price=skewed_fair_value
            )
            
            # Final spread = base × volatility × cliff protection
            final_spread = base_spread * vol_multiplier * spread_multiplier
            
            # Calculate bid/ask around skewed fair value (KEEP AS FLOAT UNTIL END)
            half_spread = final_spread / 2
            my_bid = skewed_fair_value - half_spread
            my_ask = skewed_fair_value + half_spread
            
            # =============================================================
            # POLYMARKET COMPLIANCE: TICK GRID & BOUNDS ENFORCEMENT
            # =============================================================
            # 1. Round to tick grid ($0.01) - FINAL rounding step
            my_bid = round(my_bid, 2)
            my_ask = round(my_ask, 2)
            
            # 2. Clamp to kill zone bounds [$0.01, $0.99]
            my_bid = max(0.01, min(0.98, my_bid))
            my_ask = max(0.02, min(0.99, my_ask))
            
            # =============================================================
            # SAFETY GUARD: Ensure ask > bid with minimum spread
            # =============================================================
            if my_bid >= my_ask:
                # Force minimum spread of $0.01
                my_ask = my_bid + 0.01
            
            # Re-clamp after adjustment
            if my_ask > 0.99:
                my_ask = 0.99
                my_bid = min(my_bid, my_ask - 0.01)
            
            if my_bid < 0.01:
                my_bid = 0.01
                my_ask = max(my_ask, my_bid + 0.01)
            
            # =============================================================
            # PRUNE STALE ORDERS (Anti-Churn with Hysteresis)
            # =============================================================
            ai_price = skewed_fair_value  # Use skewed fair value for drift calculation
            prune_stats = self._prune_stale_orders(market_id, ai_price)
            if prune_stats['total_cancelled'] > 0:
                logger.debug(f"[HFT] Pruned {prune_stats['total_cancelled']} stale orders for {market_id[:16]}...")
            
            # Determine trade direction based on opportunity
            # If market best_ask < our_bid → We want to BUY (market is cheap)
            # If market best_bid > our_ask → We want to SELL (market is expensive)
            
            should_trade = False
            side = None
            edge = 0.0
            entry_price = 0.0
            
            # Check for BUY opportunity
            if best_ask < my_bid:
                # Market is cheaper than we're willing to pay
                should_trade = True
                side = 'YES'
                entry_price = round(best_ask, 2)  # Tick-aligned entry
                edge = (my_bid - best_ask) / max(best_ask, 0.01)
            
            # Check for SELL opportunity (if we have inventory)
            elif best_bid > my_ask:
                # Market is paying more than we want to sell at
                # For now, HFT scalp only does BUY entries (sell on exit)
                # This could be extended to short-selling in future
                pass
            
            # Also check if market mid is significantly below our fair value (bullish signal)
            market_mid = (best_bid + best_ask) / 2
            fv_edge = skewed_fair_value - market_mid
            bias = params.bias
            
            if not should_trade and fv_edge > 0.01 and bias > 0:
                # Fair value says market is underpriced and we're bullish
                should_trade = True
                side = 'YES'
                entry_price = round(best_ask, 2)  # Tick-aligned entry
                edge = fv_edge
            
            if not should_trade:
                return None
            
            # =============================================================
            # STEP 5: Inventory Guard (Using Cubic Skew State)
            # =============================================================
            # Check if we're already too concentrated in one direction
            max_inventory_skew = params.max_inventory_skew
            
            if total_hft_value > 0:
                current_skew_ratio = hft_long_value / total_hft_value
            else:
                current_skew_ratio = 0.5  # Neutral
            
            # If bullish bias (> 0) and already heavily LONG, block further buys
            if bias > 0 and side == 'YES' and current_skew_ratio > (0.5 + max_inventory_skew):
                logger.debug(f"[HFT] Inventory guard: Already {current_skew_ratio:.0%} long, blocking buy")
                return None
            
            # If bearish bias (< 0) and already heavily SHORT, block further sells
            if bias < 0 and side == 'NO' and current_skew_ratio < (0.5 - max_inventory_skew):
                logger.debug(f"[HFT] Inventory guard: Already {(1-current_skew_ratio):.0%} short, blocking sell")
                return None
            
            # =============================================================
            # CALCULATE POSITION SIZE (USD → Integer Shares)
            # =============================================================
            # Size based on confidence and edge
            confidence_mult = min(1.0, params.confidence * 1.5)  # Scale up with confidence
            edge_mult = min(1.0, edge * 20)  # Scale with edge (5% edge = 100%)
            
            scalp_size_usd = min(
                available_capital * 0.02 * confidence_mult * edge_mult,  # Max 2% * multipliers
                25.0,  # Cap at $25 per scalp
                self.max_position_size * 0.4  # 40% of normal max
            )
            scalp_size_usd = max(scalp_size_usd, 5.0)  # Minimum $5
            
            # =============================================================
            # POLYMARKET COMPLIANCE: INTEGER SHARE CONVERSION
            # =============================================================
            # Polymarket uses integer contracts - convert USD to shares
            order_qty = self._calculate_order_qty(scalp_size_usd, entry_price)
            
            # Dust Guard: Don't trade if quantity rounds to 0
            if order_qty < 1:
                logger.debug(f"[HFT] Dust guard: order_qty={order_qty} (size=${scalp_size_usd:.2f} @ ${entry_price:.2f})")
                return None
            
            # Recalculate actual USD size from integer quantity
            scalp_size = order_qty * entry_price
            
            # Determine regime
            if market_spread > SPREAD_TAKER_THRESHOLD:
                regime = MarketRegime.MAKER_WIDE
            else:
                regime = MarketRegime.TAKER_TIGHT
            
            # Calculate effective spread in bps for logging
            effective_spread_bps = int(final_spread * 10000)
            
            logger.info(
                f"🧠 [HFT MATH] {market_id[:16]}... | "
                f"Raw={yes_price:.4f} Smooth={smoothed_price:.4f} ({signal_action}) | "
                f"Skew={skew_amount:+.4f} (inv={current_inventory:.0f}) | "
                f"FV={skewed_fair_value:.4f} Zone={cliff_zone} (×{spread_multiplier:.1f}) | "
                f"Spread={effective_spread_bps}bps | Edge={edge:.2%} | "
                f"Qty={order_qty} @ ${entry_price:.2f} = ${scalp_size:.2f}"
            )
            
            # Build opportunity dict with enhanced diagnostics
            opportunity = {
                'should_trade': True,
                'side': side,
                'size': scalp_size,
                'edge': edge,
                'scalp_price': entry_price,
                'spread': market_spread,
                'strategy': 'hft_scalp_smart',
                'regime': regime,
                'fair_value': skewed_fair_value,
                'raw_fair_value': ai_fair_value,
                'smoothed_price': smoothed_price,
                'signal_action': signal_action,
                'bias': bias,
                'vol_multiplier': vol_multiplier,
                'effective_spread_bps': effective_spread_bps,
                'quoted_bid': my_bid,
                'quoted_ask': my_ask,
                # HFT Math Engine diagnostics
                'skew_amount': skew_amount,
                'current_inventory': current_inventory,
                'cliff_zone': cliff_zone,
                'spread_multiplier': spread_multiplier,
                # Polymarket compliance fields
                'order_qty': order_qty,
                'tick_aligned': True,
                'bounds_checked': True,
            }
            
            # =============================================================
            # TRACK ACTIVE ORDER (for Hysteresis/Lifecycle Management)
            # =============================================================
            self.active_orders[market_id] = {
                'price': entry_price,
                'size': scalp_size,
                'side': side,
                'timestamp': datetime.now(timezone.utc),
                'ai_price': skewed_fair_value,
                'order_qty': order_qty,
            }
            
            # =============================================================
            # ZERO-LATENCY TELEMETRY: Log decision snapshot
            # =============================================================
            try:
                telemetry = get_telemetry_service()
                snapshot = create_decision_snapshot(
                    market_id=market_id,
                    market_data=market_data,
                    hft_params=params.to_dict() if params else None,
                    opportunity=opportunity,
                    decision="TRADE",
                    reason=f"BUY_EDGE_{edge:.2%}",
                    hft_positions={
                        mid: pos for mid, pos in self.paper_positions.items()
                        if RISK.get_strategy_path(pos.get('strategy', '')) == 'HFT'
                    },
                )
                telemetry.log_decision(snapshot)  # Non-blocking
            except Exception as e:
                logger.debug(f"[HFT] Telemetry log error (ignored): {e}")
            
            return opportunity
            
        except Exception as e:
            logger.debug(f"[HFT] Error evaluating scalp: {e}")
            return None
    
    async def _execute_hft_trade(self, market_data: Dict, opportunity: Dict):
        """
        Execute an HFT trade.
        
        This handles both:
        1. Autonomous HFT scalps (pure market microstructure)
        2. Delegated Alpha trades (wide spread, need Maker execution)
        """
        try:
            market_id = market_data.get('id', '')
            
            # ==========================================================
            # LIVE EVENT FILTER (Jan 2026 - Critical Fix)
            # ==========================================================
            question = market_data.get('question', '').lower()
            
            # Skip live sports matchups (Team vs Team pattern)
            import re
            sports_pattern = re.compile(r'\bvs\.?\b|\bversus\b', re.IGNORECASE)
            is_sports_matchup = bool(sports_pattern.search(question))
            is_over_under = 'o/u' in question or 'over/under' in question
            
            if is_sports_matchup or is_over_under:
                logger.info(f"[HFT] BLOCKED live sports: {question[:40]}...")
                return
            
            side = opportunity['side']
            size = opportunity['size']
            strategy = opportunity.get('strategy', 'hft_scalp')
            regime = opportunity.get('regime', MarketRegime.TAKER_TIGHT)
            
            # Different logging for different modes (Task 21: Simplified)
            if regime == MarketRegime.MAKER_WIDE:
                logger.info(
                    f"📊 [HFT MAKER] {side} ${size:.2f} in {market_id[:16]}... | "
                    f"Edge: {opportunity['edge']:.2%} | Strategy: {strategy}"
                )
            else:
                logger.info(
                    f"⚡ [HFT TAKER] {side} ${size:.2f} in {market_id[:16]}... | "
                    f"Edge: {opportunity['edge']:.2%} | Strategy: {strategy}"
                )
            
            # Use the same entry execution as Alpha (but with HFT-specific sizing)
            # This reuses the maker executor infrastructure
            await self._execute_paper_entry(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=size,
                strategy='delta_neutral',  # HFT trades use delta_neutral exit params
                signals={'hft_mode': True, 'edge': opportunity['edge'], 'regime': regime},
                rl_action='HFT_ENTRY',
                rl_confidence=0.5,
                sizing_breakdown={
                    'hft_trade': True,
                    'edge': opportunity['edge'],
                    'fair_value': opportunity.get('fair_value'),
                    'regime': regime,
                    'delegated_from_alpha': strategy in ['hft_maker', 'hft_taker'],
                }
            )
            
        except Exception as e:
            logger.error(f"[HFT] Error executing trade: {e}")
    
    # =================================================================
    # CHAIN OF COMMAND: UNIFIED EXECUTION PIPELINE
    # =================================================================
    # All trades flow through this pipeline:
    # 1. Strategy -> 2. PositionSizer -> 3. RiskManager -> 4. Execution
    # This ensures SSOT risk limits are ALWAYS enforced.
    # =================================================================
    
    async def execute_trade_cycle(
        self, 
        lane: str, 
        market_data: Dict, 
        strategy: str,
        side: str,
        edge: float,
        raw_size_hint: float = None,
        signals: Dict = None,
        **kwargs
    ) -> Dict:
        """
        CHAIN OF COMMAND: Unified trade execution pipeline.
        
        All trades (HFT, ALPHA, GAMMA, SPORTS, NEWS) MUST flow through this method.
        
        Steps:
            1. MATH (PositionSizer): Calculate raw theoretical size
            2. ENFORCEMENT (RiskManager): Validate and trim/block
            3. ACTION: Execute if approved
            4. LOG: Record decision for audit
        
        Args:
            lane: Trading lane (HFT, ALPHA, GAMMA, SPORTS, NEWS)
            market_data: Market data dict
            strategy: Strategy name (hft_scalp, alpha_directional, etc.)
            side: Trade side (YES or NO)
            edge: Model edge (probability delta)
            raw_size_hint: Optional pre-calculated size hint
            signals: Additional signal data
            **kwargs: Additional strategy-specific params
        
        Returns:
            Dict with execution result
        """
        market_id = market_data.get('id', 'unknown')
        market_price = float(market_data.get('yes_price', 0.5))
        
        result = {
            'lane': lane,
            'strategy': strategy,
            'market_id': market_id,
            'side': side,
            'edge': edge,
            'executed': False,
            'blocked': False,
            'trimmed': False,
            'reason': '',
            'raw_size': 0.0,
            'approved_size': 0.0,
        }
        
        try:
            # ==========================================================
            # STEP 1: MATH (PositionSizer) - Calculate raw theoretical size
            # ==========================================================
            kelly_config = self.risk_manager.get_kelly_config()
            lane_config = self.risk_manager.get_lane_config(lane)
            
            # Get sizing based on lane
            if lane == 'HFT':
                sizing_result = PositionSizer.calculate_hft_size(
                    capital=self.deployed_capital,
                    max_pos_pct=lane_config.get('max_pos_pct', 0.02),
                    max_pos_usd=lane_config.get('max_pos_usd', 50.0),
                    min_size=self.min_position_size
                )
            elif lane == 'ALPHA':
                sizing_result = PositionSizer.calculate_kelly_size(
                    edge=edge,
                    market_price=market_price,
                    capital=self.deployed_capital,
                    kelly_config=kelly_config,
                    confidence=kwargs.get('confidence', 1.0),
                    liquidity=float(market_data.get('liquidity', 10000)),
                    current_utilization=self._get_utilization(),
                    max_pos_usd=lane_config.get('max_pos_usd', 100.0),
                    min_size=self.min_position_size
                )
            elif lane == 'GAMMA':
                sizing_result = PositionSizer.calculate_gamma_size(
                    capital=self.deployed_capital,
                    max_pos_pct=lane_config.get('max_pos_pct', 0.01),
                    max_pos_usd=lane_config.get('max_pos_usd', 15.0),
                    min_size=self.min_position_size
                )
            elif lane == 'SPORTS':
                implied_odds = kwargs.get('implied_odds', market_price)
                sizing_result = PositionSizer.calculate_sports_size(
                    edge=edge,
                    implied_odds=implied_odds,
                    capital=self.deployed_capital * lane_config.get('alloc_pct', 0.15),
                    kelly_fraction=kelly_config.get('scaling_factor', 0.25),
                    max_pos_usd=lane_config.get('max_pos_usd', 100.0),
                    min_size=self.min_position_size
                )
            elif lane == 'NEWS':
                bayes_factor = kwargs.get('bayes_factor', 1.0)
                posterior = kwargs.get('posterior', market_price)
                sizing_result = PositionSizer.calculate_news_size(
                    bayes_factor=bayes_factor,
                    posterior=posterior,
                    prior=market_price,
                    capital=self.deployed_capital,
                    kelly_fraction=kelly_config.get('scaling_factor', 0.25),
                    max_pos_pct=lane_config.get('max_pos_pct', 0.05),
                    max_pos_usd=lane_config.get('max_pos_usd', 100.0),
                    min_size=self.min_position_size,
                    confidence=kwargs.get('confidence', 1.0)
                )
            else:
                # Default to Kelly for unknown lanes
                sizing_result = PositionSizer.calculate_kelly_size(
                    edge=edge,
                    market_price=market_price,
                    capital=self.deployed_capital,
                    kelly_config=kelly_config,
                    max_pos_usd=100.0,
                    min_size=self.min_position_size
                )
            
            raw_size = raw_size_hint if raw_size_hint else sizing_result.size
            result['raw_size'] = raw_size
            result['sizing_method'] = sizing_result.method
            result['sizing_details'] = sizing_result.to_dict()
            
            if raw_size <= 0:
                result['blocked'] = True
                result['reason'] = f"PositionSizer returned zero size: {sizing_result.reason}"
                logger.info(f"🚫 [{lane}] BLOCKED (Sizer): ${raw_size:.2f} - {sizing_result.reason}")
                return result
            
            # ==========================================================
            # STEP 2: ENFORCEMENT (RiskManager) - Validate and trim/block
            # ==========================================================
            asset_class = market_data.get('asset_class', market_data.get('category', 'unknown'))
            
            check_result: OrderCheckResult = self.risk_manager.check_order(
                lane=lane,
                amount=raw_size,
                capital=self.deployed_capital,
                current_utilization=self._get_utilization(),
                sector=asset_class,
                sector_exposure=self._get_sector_exposure(asset_class),
                market_price=market_price
            )
            
            result['risk_check'] = check_result.to_dict()
            
            if not check_result.approved:
                result['blocked'] = True
                result['reason'] = check_result.reason
                logger.warning(f"🚫 [{lane}] TRADE BLOCKED by RiskManager: {check_result.reason}")
                return result
            
            if check_result.adjusted_amount < raw_size:
                result['trimmed'] = True
                logger.warning(
                    f"✂️ [{lane}] TRADE TRIMMED: ${raw_size:.2f} → ${check_result.adjusted_amount:.2f} "
                    f"({', '.join(check_result.warnings)})"
                )
            
            approved_size = check_result.adjusted_amount
            result['approved_size'] = approved_size
            
            # ==========================================================
            # STEP 3: ACTION - Execute the trade
            # ==========================================================
            logger.info(
                f"✅ [{lane}] TRADE APPROVED: {side} ${approved_size:.2f} in {market_id[:16]}... | "
                f"Strategy: {strategy} | Edge: {edge:.2%}"
            )
            
            # Execute via the existing _execute_paper_entry method
            await self._execute_paper_entry(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=approved_size,
                strategy=strategy,
                signals=signals or {},
                rl_action=f'{lane}_ENTRY',
                rl_confidence=kwargs.get('confidence', 0.5),
                sizing_breakdown={
                    'lane': lane,
                    'raw_size': raw_size,
                    'approved_size': approved_size,
                    'edge': edge,
                    'sizing_method': sizing_result.method,
                    'risk_warnings': check_result.warnings,
                }
            )
            
            result['executed'] = True
            result['reason'] = "Trade executed successfully"
            
            # ==========================================================
            # STEP 4: LOG - Record decision for audit trail
            # ==========================================================
            logger.info(
                f"📝 [{lane}] AUDIT: {strategy} {side} ${approved_size:.2f} | "
                f"Sizer: {sizing_result.method} → Risk: {'TRIMMED' if result['trimmed'] else 'PASS'}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[{lane}] Chain of Command error: {e}")
            result['blocked'] = True
            result['reason'] = f"Execution error: {str(e)}"
            return result
    
    def _get_utilization(self) -> float:
        """Get current capital utilization (0-1)"""
        try:
            total_invested = sum(
                pos.get('size', 0) 
                for pos in self.paper_positions.values()
            )
            return total_invested / max(1, self.deployed_capital)
        except Exception:
            return 0.0
    
    def _get_sector_exposure(self, sector: str) -> float:
        """Get current exposure to a specific sector"""
        try:
            sector_exposure = sum(
                pos.get('size', 0)
                for pos in self.paper_positions.values()
                if pos.get('asset_class', '').lower() == sector.lower()
            )
            return sector_exposure
        except Exception:
            return 0.0

    # =================================================================
    # ALPHA LOOP: THE BRAIN (Slow Path)
    # =================================================================
    # Runs every 30 seconds
    # - Runs full Bayesian probability fusion
    # - Calls LLM for sentiment analysis
    # - Updates StrategyContext with theoretical prices
    # - Executes high-conviction directional trades
    # =================================================================
    
    async def _run_alpha_loop(self):
        """
        Alpha Strategy Loop - Deep analysis for directional trades.
        
        This loop:
        1. Fetches full market details
        2. Runs Bayesian probability fusion (with LLM)
        3. Updates StrategyContext with fair values
        4. Executes high-conviction trades
        
        Runs every 30 seconds.
        """
        ALPHA_CYCLE_INTERVAL = 30  # 30 seconds between cycles
        MAX_MARKETS_PER_CYCLE = 20  # Limit markets to process per cycle (LLM is slow)
        
        logger.info("🧠 Alpha Strategy Loop Started")
        
        alpha_cycle_count = 0
        
        while self.running:
            try:
                alpha_cycle_count += 1
                cycle_start = datetime.now(timezone.utc)
                logger.info(f"[ALPHA #{alpha_cycle_count}] Starting cycle...")
                
                # Skip if in graceful stop mode (but still update targets for HFT)
                skip_new_entries = self.graceful_stop
                
                # 1. DEEP SCAN: Get full market details
                markets = await self._get_active_markets()
                
                if not markets:
                    logger.info(f"[ALPHA #{alpha_cycle_count}] No markets available")
                    await asyncio.sleep(ALPHA_CYCLE_INTERVAL)
                    continue
                
                # 2. RUN STRATEGY PIPELINE (The heavy lifting)
                # Limit markets per cycle to avoid LLM rate limits and long cycles
                alpha_evaluated = 0
                alpha_triggered = 0
                targets_updated = 0
                
                # Filter by asset class first
                filtered_markets = []
                asset_class_counts = {}
                for m in markets:
                    asset_class = m.get('asset_class', m.get('category', 'unknown')).lower()
                    asset_class_counts[asset_class] = asset_class_counts.get(asset_class, 0) + 1
                    if asset_class in [ac.lower() for ac in self.enabled_asset_classes]:
                        filtered_markets.append(m)
                
                logger.info(f"[ALPHA] Asset classes: {asset_class_counts}")
                logger.info(f"[ALPHA] Filtered to {len(filtered_markets)} from {len(markets)} markets")
                
                # Take top N markets by volume
                filtered_markets = sorted(
                    filtered_markets, 
                    key=lambda x: x.get('volume_24h', 0) or 0, 
                    reverse=True
                )[:MAX_MARKETS_PER_CYCLE]
                
                logger.info(f"[ALPHA #{alpha_cycle_count}] Processing {len(filtered_markets)} markets...")
                
                for market_data in filtered_markets:
                    if not self.running:
                        break
                    
                    market_id = market_data.get('id')
                    
                    # ==========================================================
                    # CATEGORY DETECTION (Task: Sports Strategy Injection)
                    # ==========================================================
                    # Detect if this is a sports market for category isolation
                    question = market_data.get('question', '').lower()
                    raw_category = market_data.get('category', 'unknown').lower()
                    
                    # Check if sports market using SSOT function
                    is_sports = is_sports_market(question)
                    
                    # ==========================================================
                    # SPORTS ROUTING (Green Lane)
                    # ==========================================================
                    # If sports market and sports strategy enabled, route to sports handler
                    # Do NOT skip/block - process through sports pipeline instead
                    if is_sports:
                        sports_config = get_sports_config()
                        
                        if sports_config.enabled:
                            # Route to Sports Strategy (bypass Alpha filters)
                            await self._process_sports_market(market_data, sports_config)
                            continue  # Skip Alpha processing for sports
                        else:
                            # Sports disabled - skip silently
                            logger.debug(f"[ALPHA] Sports market skipped (disabled): {question[:40]}...")
                            continue
                    
                    # ==========================================================
                    # LEGACY: Alpha Lane Processing (Non-Sports)
                    # ==========================================================
                    # FIX: Fetch fresh orderbook (The Brain needs eyes)
                    # ==========================================================
                    # Without orderbook data, regime classification defaults to
                    # TAKER_TIGHT and we miss liquidity information
                    try:
                        token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
                        if token_ids and isinstance(token_ids, list) and len(token_ids) > 0:
                            from data.polymarket_api import PolymarketAPI
                            async with PolymarketAPI() as api:
                                # Fetch YES token orderbook
                                order_book_data = await api.get_order_book(token_ids[0])
                                if order_book_data.get('bids') and order_book_data.get('asks'):
                                    market_data['order_book'] = order_book_data
                                    market_data['order_book_token'] = 'YES'
                                    
                                    # Extract best bid/ask for quick access
                                    bids = order_book_data['bids']
                                    asks = order_book_data['asks']
                                    market_data['best_bid'] = float(bids[0]['price']) if bids else 0
                                    market_data['best_ask'] = float(asks[0]['price']) if asks else 1
                                    
                                    logger.debug(f"[ALPHA] Fetched orderbook for {market_id[:16]}...")
                    except Exception as e:
                        logger.debug(f"[ALPHA] Could not fetch orderbook for {market_id[:16]}: {e}")
                    
                    # Run full Alpha analysis (Bayesian, signals, regime)
                    try:
                        analysis = await self._run_alpha_analysis(market_data)
                        if analysis:
                            logger.info(f"[ALPHA] {market_id[:16]}... FV={analysis['fair_value']:.4f} Edge={analysis['edge']:.4f} Should_trade={analysis.get('should_trade')}")
                        else:
                            logger.debug(f"[ALPHA] {market_id[:16]}... returned None")
                    except Exception as e:
                        logger.error(f"[ALPHA] Analysis failed for {market_id[:16]}: {e}")
                        analysis = None
                    
                    if analysis:
                        alpha_evaluated += 1
                        
                        # Update StrategyContext for HFT loop (legacy)
                        self.strategy_context.update_target(
                            market_id=market_id,
                            fair_value=analysis['fair_value'],
                            regime=analysis['regime'],
                            confidence=analysis.get('confidence', 1.0),
                            signals=analysis.get('signals', {})
                        )
                        targets_updated += 1
                        
                        # =============================================================
                        # NEW: Update HFT Context (Async-Skewed-Adaptive Architecture)
                        # =============================================================
                        # The HFT loop will read this non-blocking for smart execution
                        try:
                            hft_ctx = get_hft_context()
                            hft_ctx.update_from_analysis(market_id, analysis)
                        except Exception as e:
                            logger.debug(f"[ALPHA] Could not update HFT context: {e}")
                        
                        # =============================================================
                        # REGIME-SPECIFIC EXECUTION RULES (Task 17 Refined)
                        # =============================================================
                        # "Yellow Light" for Alpha on wide spreads:
                        # - Analyze the market ✓ (done above)
                        # - Update HFT targets ✓ (done above)
                        # - But DON'T execute Taker trade (spread would kill edge)
                        # - Instead, let HFT post Maker orders
                        
                        regime = analysis.get('regime', MarketRegime.TAKER_TIGHT)
                        
                        # ZOMBIE: Market is dead - skip entirely
                        if regime == MarketRegime.ZOMBIE:
                            logger.debug(f"🚫 [ALPHA SKIP] {market_id[:16]}... ZOMBIE market - no execution")
                            continue
                        
                        # MAKER_WIDE: Delegate to HFT for limit order posting
                        if regime == MarketRegime.MAKER_WIDE:
                            # GUARDRAIL: Spread 2-12% - delegate to HFT for maker strategy
                            if analysis.get('should_trade') and analysis.get('edge', 0) > 0.01:
                                alpha_triggered += 1  # Count as triggered for stats
                                logger.info(
                                    f"⚠️ [ALPHA DELEGATE] {market_id[:16]}... FV={analysis['fair_value']:.4f} "
                                    f"Edge={analysis['edge']:.2%} | Regime={regime} → Delegated to HFT"
                                )
                            # DO NOT execute directly - HFT will pick up the target
                            continue
                        
                        # CONVEXITY_OPPORTUNITY: Whale Zone - delegate to HFT for gamma scalping
                        # While Alpha CAN execute here, HFT's smaller, faster trades
                        # are better suited for the volatility accumulation strategy
                        if regime == MarketRegime.CONVEXITY_OPPORTUNITY:
                            if analysis.get('should_trade') and analysis.get('edge', 0) > 0.003:
                                alpha_triggered += 1  # Count for stats
                                logger.info(
                                    f"🐋 [ALPHA WHALE] {market_id[:16]}... FV={analysis['fair_value']:.4f} "
                                    f"Edge={analysis['edge']:.2%} | Regime={regime} → Delegated to HFT for gamma scalp"
                                )
                            # Delegate to HFT for whale zone trading
                            continue
                        
                        # TAKER_TIGHT: Execute Alpha trade directly (spread < 2%)
                        if not skip_new_entries and market_id not in self.paper_positions:
                            if analysis.get('should_trade') and analysis.get('edge', 0) > 0.01:
                                alpha_triggered += 1
                                await self._execute_alpha_trade(market_data, analysis)
                    
                    # Evaluate exits for existing positions
                    if market_id in self.paper_positions:
                        await self._evaluate_exit(market_id, market_data)
                
                # Record cycle completion
                self.strategy_context.record_alpha_cycle()
                
                # Log every cycle
                cycle_time = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                bridge_stats = self.strategy_context.get_stats()
                logger.info(
                    f"[ALPHA #{alpha_cycle_count}] COMPLETE | Evaluated: {alpha_evaluated}, "
                    f"Triggered: {alpha_triggered}, Targets: {targets_updated}, "
                    f"Cycle: {cycle_time:.1f}s, Positions: {len(self.paper_positions)}, "
                    f"Bridge: {bridge_stats['active_targets']} targets"
                )
                
                # Record equity curve with Three-Speed lane breakdowns
                self.equity_curve.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "capital": self.current_capital,
                    "pnl": self.total_pnl,
                    "open_positions": len(self.paper_positions),
                    "alpha_cycle": alpha_cycle_count,
                    # Strategy P&L breakdown (legacy)
                    "delta_neutral_pnl": self.strategy_equity.get('delta_neutral', 0),
                    "volatility_pnl": self.strategy_equity.get('volatility_exploitation', 0),
                    "alpha_pnl": self.strategy_equity.get('alpha_directional', 0),
                    "arbitrage_pnl": self.strategy_equity.get('arbitrage', 0),
                    # Three-Speed Lane P&L breakdown (Task 29)
                    "hft_pnl": self.lane_equity.get('HFT', 0),
                    "alpha_lane_pnl": self.lane_equity.get('ALPHA', 0),
                    "gamma_pnl": self.lane_equity.get('GAMMA', 0),
                    # Asset class P&L breakdown
                    "asset_class_equity": dict(self.asset_class_equity)
                })
                
                # Check graceful stop completion
                if self.graceful_stop and not self.paper_positions:
                    logger.info("Graceful stop complete - all positions closed")
                    self.running = False
                    break
                
                # 3. SLEEP: Wait for next cycle
                await asyncio.sleep(ALPHA_CYCLE_INTERVAL)
                
            except Exception as e:
                logger.error(f"[ALPHA ERROR] {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
        
        logger.info("🛑 Alpha Strategy Loop Stopped")
    
    async def _run_alpha_analysis(self, market_data: Dict) -> Optional[Dict]:
        """
        Run full Alpha analysis on a market.
        
        This is the "heavy" computation:
        - Signal generation (LLM, sentiment, etc.)
        - Bayesian probability fusion
        - Regime classification
        - Position sizing
        """
        try:
            market_id = market_data.get('id', '')
            yes_price = market_data.get('yes_price')
            
            if yes_price is None or yes_price == 0:
                logger.debug(f"[ALPHA] {market_id[:16]}... skipped - no yes_price")
                return None
            
            yes_price = float(yes_price)
            
            # Skip extreme prices
            if yes_price in [0.0, 1.0]:
                logger.debug(f"[ALPHA] {market_id[:16]}... skipped - extreme price {yes_price}")
                return None
            
            logger.debug(f"[ALPHA] Analyzing {market_id[:16]}... yes_price={yes_price:.4f}")
            
            # Get signals (includes LLM call - slow!)
            signals = await self._get_signals(market_data)
            
            # Get RL action using existing method
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Calculate model probability (Bayesian fusion)
            model_result = self._calculate_model_probability(
                sentiment=signals.get('sentiment', 0.5),
                sharp_alignment=signals.get('sharp_alignment', 0.5),
                rl_confidence=rl_confidence,
                yes_price=yes_price,
                rl_action=rl_action,
                return_diagnostics=True
            )
            
            if isinstance(model_result, dict):
                fair_value = model_result['final_probability']
                diagnostics = model_result
            else:
                fair_value = model_result
                diagnostics = {}
            
            # Classify regime (needs orderbook)
            order_book = market_data.get('order_book', {})
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            
            if bids and asks:
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                volume_24h = market_data.get('volume_24h', 0) or 0
                regime, regime_diagnostics = classify_market_regime(best_bid, best_ask, volume_24h)
                spread = best_ask - best_bid
                if regime == MarketRegime.ZOMBIE:
                    logger.info(f"[ALPHA-REGIME] {market_id[:16]}... spread={spread:.2%} → {regime}")
            else:
                regime = MarketRegime.TAKER_TIGHT
                regime_diagnostics = {}
                logger.debug(f"[ALPHA-REGIME] {market_id[:16]}... NO ORDERBOOK → defaulting to {regime}")
            
            # Log zombie markets but still return analysis for tracking
            if regime == MarketRegime.ZOMBIE:
                logger.debug(f"[ALPHA] Zombie market {market_id[:16]}... - no orderbook liquidity")
            
            # Calculate edge
            effective_price = yes_price + 0.02  # Fee-adjusted
            yes_edge = fair_value - effective_price
            no_edge = (1 - fair_value) - (1 - yes_price + 0.02)
            
            # Determine side and edge
            # ==========================================================
            # EDGE DIRECTION SAFEGUARD (Jan 2026)
            # ==========================================================
            # The model's fair value predictions have been systematically
            # wrong on NO bets. Until the model is recalibrated, only
            # trade YES positions where FV > market price.
            if yes_edge > no_edge and yes_edge > 0.01:
                side = 'YES'
                edge = yes_edge
            elif no_edge > yes_edge and no_edge > 0.01:
                # TEMPORARILY DISABLED: NO trades are losing systematically
                # side = 'NO'
                # edge = no_edge
                side = None  # Skip NO trades
                edge = no_edge
                logger.debug(f"[ALPHA] Skipping NO trade (model bias under review)")
            else:
                side = None
                edge = max(yes_edge, no_edge)
            
            return {
                'fair_value': fair_value,
                'regime': regime,
                'side': side,
                'edge': edge,
                'yes_edge': yes_edge,
                'no_edge': no_edge,
                'should_trade': side is not None,
                'signals': signals,
                'rl_action': rl_action,
                'rl_confidence': rl_confidence,
                'diagnostics': diagnostics,
                'confidence': rl_confidence,
            }
            
        except Exception as e:
            logger.debug(f"[ALPHA] Error analyzing market: {e}")
            return None
    
    # =============================================================================
    # NEWS/EMERGENT LANE (Lane 5) - Signal Cache Management
    # =============================================================================
    
    def set_signal_cache(self, cache):
        """
        Set the signal cache for Lane 5 news signals.
        
        This connects the PaperTrader to the NewsInjector's cache writes.
        """
        self._signal_cache = cache
        logger.info("[PAPER TRADER] Signal cache connected for Lane 5")
    
    def get_signal_cache(self):
        """Get the current signal cache instance"""
        return self._signal_cache
    
    # =============================================================================
    # NEWS/EMERGENT LANE (Lane 5) - News Signal Processing
    # =============================================================================
    
    async def _check_news_signal(self, market_id: str) -> Optional[Dict]:
        """
        Check AsyncSignalCache for an injected news signal.
        
        Key format: emergent_signal:{market_id}
        
        Returns:
            Dict with signal data if found and not expired, None otherwise
        """
        try:
            # Check if we have access to the signal cache
            if not hasattr(self, '_signal_cache') or self._signal_cache is None:
                return None
            
            cache_key = f"emergent_signal:{market_id}"
            signal = await self._signal_cache.get(cache_key)
            
            if signal:
                # Check if signal has expired
                expires_at = signal.get('expires_at')
                if expires_at:
                    from datetime import datetime
                    expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > expiry:
                        return None
                
                return signal
            
            return None
            
        except Exception as e:
            # CRITICAL: Never crash the trading loop for cache errors
            logger.debug(f"[NEWS CACHE] Error checking signal for {market_id[:16]}: {e}")
            return None
    
    async def _execute_news_sniper(self, market_data: Dict, news_signal: Dict):
        """
        Execute a trade based on an injected news signal.
        
        Lane 5: NEWS/EMERGENT - The Bridge
        
        This executes at HFT speed because:
        - The slow analysis (LLM + Bayesian) already happened in background
        - We're just reading from cache and executing
        """
        try:
            market_id = market_data.get('id', '')
            market_id_short = market_id[:16]
            question = market_data.get('question', '')
            
            direction = news_signal.get('direction', 'NEUTRAL')
            if direction == 'NEUTRAL':
                return
            
            bayes_factor = news_signal.get('bayes_factor', 0)
            posterior = news_signal.get('posterior', 0.5)
            confidence = news_signal.get('confidence', 0)
            news_headline = news_signal.get('news_headline', '')
            
            logger.info(
                f"[NEWS SNIPER] {market_id_short} | Direction: {direction} | "
                f"BF: {bayes_factor:.2f} | Posterior: {posterior:.2f} | "
                f"News: {news_headline[:50]}..."
            )
            
            # Determine side
            side = 'YES' if direction == 'YES' else 'NO'
            
            # Get prices
            yes_price = float(market_data.get('yes_price', 0.5))
            
            # Calculate position size using fractional Kelly with Bayesian posterior
            # f* = posterior * kelly_fraction
            kelly_fraction = 0.25
            base_size_pct = posterior * kelly_fraction * confidence
            
            # Apply minimum edge check
            if side == 'YES':
                edge = posterior - yes_price
            else:
                edge = (1 - posterior) - (1 - yes_price)
            
            if edge < 0.02:  # 2% minimum edge
                logger.debug(f"[NEWS SNIPER] {market_id_short} | Edge too small: {edge:.2%}")
                return
            
            # Calculate position size
            max_position_usd = self.deployed_capital * (self.portfolio_risk_config.get('max_position_pct', 5) / 100)
            position_size = min(
                self.deployed_capital * base_size_pct,
                max_position_usd
            )
            
            # Apply minimum trade size
            min_trade_size = 5.0
            if position_size < min_trade_size:
                logger.debug(f"[NEWS SNIPER] {market_id_short} | Size too small: ${position_size:.2f}")
                return
            
            # Execute the trade
            await self._execute_paper_trade(
                market_data=market_data,
                side=side,
                size=position_size,
                strategy='news_sniper',
                confidence=confidence,
                sentiment_score=posterior,
                signal_source='emergent_news'
            )
            
            logger.info(
                f"[NEWS SNIPER] EXECUTED {market_id_short} | "
                f"Side: {side} | Size: ${position_size:.2f} | "
                f"Edge: {edge:.2%} | BF: {bayes_factor:.2f}"
            )
            
        except Exception as e:
            # CRITICAL: Never crash the trading loop
            logger.error(f"[NEWS SNIPER] Error executing trade: {e}")
    
    # =============================================================================
    # SPORTS STRATEGY PROCESSING (Task: Sports Strategy Injection)
    # =============================================================================
    
    async def _process_sports_market(self, market_data: Dict, sports_config: SportsConfig):
        """
        Process a sports market using SportsArbitrageStrategy.
        
        This is the "Green Lane" for sports markets:
        - Uses real bookmaker odds from sports_odds.py
        - Lower volume/liquidity requirements
        - NO-side betting allowed
        - Bypasses Alpha's LLM sentiment (which hallucinates on sports)
        
        Args:
            market_data: Polymarket market data
            sports_config: SportsConfig from SSOT
        """
        try:
            market_id = market_data.get('id', '')
            question = market_data.get('question', '')
            yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
            
            # Skip if already have position
            if market_id in self.paper_positions:
                return
            
            logger.info(f"[SPORTS] Processing: {question[:50]}...")
            
            # ==========================================================
            # STEP 1: Get real odds from Sports Odds API
            # ==========================================================
            sentiment_analyzer = get_enhanced_sentiment_analyzer()
            
            # The enhanced sentiment analyzer handles sports routing internally
            # It will use 85% sports odds + 15% order flow for sports markets
            analysis = await sentiment_analyzer.analyze(market_data)
            
            # Extract fair value (from sports odds or fallback)
            fair_value = analysis.get('combined_sentiment', 0.5)
            sports_confidence = analysis.get('sports_confidence', 0)
            sports_matched_event = analysis.get('sports_matched_event')
            
            # ==========================================================
            # STEP 2: Generate signal using Sports Strategy
            # ==========================================================
            sports_strategy = get_sports_strategy(sports_config)
            
            signal = sports_strategy.generate_signal(
                market_data=market_data,
                fair_value=fair_value,
                sports_analysis=analysis
            )
            
            # ==========================================================
            # STEP 3: Execute if signal is valid
            # ==========================================================
            if signal.signal in [SportsSignal.BUY_YES, SportsSignal.BUY_NO]:
                # Validate side against config
                if signal.side == 'NO' and not sports_config.allow_no_bets:
                    logger.info(f"[SPORTS] NO-side blocked by config: {question[:40]}...")
                    return
                
                if signal.side == 'YES' and not sports_config.allow_yes_bets:
                    logger.info(f"[SPORTS] YES-side blocked by config: {question[:40]}...")
                    return
                
                # Check capital availability
                current_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
                available_capital = self.deployed_capital - current_deployed
                
                # Use sports allocation limit
                sports_allocation = sports_config.allocation_pct / 100 * self.deployed_capital
                sports_deployed = sum(
                    p.get('size', 0) for p in self.paper_positions.values()
                    if p.get('strategy') == 'sports_arbitrage'
                )
                sports_available = sports_allocation - sports_deployed
                
                if sports_available < sports_config.min_trade_size:
                    logger.debug(f"[SPORTS] Allocation exhausted: ${sports_available:.2f} available")
                    return
                
                # Cap size by sports allocation
                trade_size = min(signal.suggested_size, sports_available, available_capital)
                
                if trade_size < sports_config.min_trade_size:
                    return
                
                # Execute the trade
                await self._execute_sports_trade(
                    market_data=market_data,
                    signal=signal,
                    trade_size=trade_size,
                    analysis=analysis
                )
            else:
                logger.debug(f"[SPORTS] No signal: {signal.reason}")
                
        except Exception as e:
            logger.error(f"[SPORTS] Error processing market: {e}")
    
    async def _execute_sports_trade(
        self,
        market_data: Dict,
        signal: 'SportsTradeSignal',
        trade_size: float,
        analysis: Dict
    ):
        """
        Execute a sports arbitrage trade.
        
        Args:
            market_data: Polymarket market data
            signal: SportsTradeSignal from strategy
            trade_size: Trade size in USD
            analysis: Full sentiment analysis
        """
        try:
            market_id = market_data.get('id', '')
            question = market_data.get('question', '')
            
            # Calculate entry price - USE ACTUAL API PRICES (not computed)
            # The time difference between lookup vs compute is ~7 nanoseconds - negligible
            yes_price = float(market_data.get('yes_price', 0.5))
            no_price = float(market_data.get('no_price') or (1 - yes_price))  # Fallback only if API missing
            
            if signal.side == 'YES':
                entry_price = yes_price
            else:
                entry_price = no_price
            
            # Calculate shares
            shares = trade_size / entry_price if entry_price > 0 else 0
            
            # Create position
            position = {
                'market_id': market_id,
                'market_question': question[:100],  # Use consistent key name
                'question': question[:100],  # Keep for backwards compatibility
                'side': signal.side,
                'size': trade_size,
                'shares': shares,
                'entry_price': entry_price,
                'yes_entry_price': float(market_data.get('yes_price', 0.5)),  # Store YES price for P&L calc
                'entry_time': datetime.now(timezone.utc).isoformat(),
                'strategy': 'sports_arbitrage',
                'asset_class': 'sports',  # Add asset class
                'fair_value': signal.fair_value,
                'edge': signal.edge,
                'edge_pct': signal.edge_pct,
                'confidence': signal.confidence,
                'sports_matched_event': signal.matched_event,
                'bookmakers_used': signal.bookmakers_used,
                'lane': 'SPORTS',
            }
            
            # Add to positions
            self.paper_positions[market_id] = position
            
            # Track P&L by strategy
            if 'sports_arbitrage' not in self.strategy_equity:
                self.strategy_equity['sports_arbitrage'] = 0.0
            
            # Track in lane equity
            if 'SPORTS' not in self.lane_equity:
                self.lane_equity['SPORTS'] = 0.0
            
            # Log the trade
            logger.info(
                f"🏈 [SPORTS TRADE] {signal.side} ${trade_size:.2f} @ {entry_price:.4f} | "
                f"FV={signal.fair_value:.4f} Edge={signal.edge:.4f} ({signal.edge_pct:.2%}) | "
                f"Event: {signal.matched_event.get('home_team', 'N/A') if signal.matched_event else 'N/A'} vs "
                f"{signal.matched_event.get('away_team', 'N/A') if signal.matched_event else 'N/A'}"
            )
            
            # Record trade in DB
            self.db.paper_trades.insert_one({
                **position,
                'trade_type': 'ENTRY',
                'timestamp': datetime.now(timezone.utc),
            })
            
        except Exception as e:
            logger.error(f"[SPORTS] Error executing trade: {e}")
    
    async def _execute_alpha_trade(self, market_data: Dict, analysis: Dict):
        """Execute an Alpha (directional) trade."""
        try:
            market_id = market_data.get('id', '')
            
            # ==========================================================
            # SPORTS ROUTING CHECK (Skip - already processed)
            # ==========================================================
            # If this is a sports market, it should have been routed
            # to _process_sports_market already. Double-check here.
            question = market_data.get('question', '').lower()
            
            if is_sports_market(question):
                logger.debug(f"[ALPHA] Sports market should use sports handler: {question[:40]}...")
                return
            
            side = analysis['side']
            edge = analysis['edge']
            
            # Check capital
            current_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
            available_capital = self.deployed_capital - current_deployed
            if available_capital < 10:
                return
            
            # Calculate position size using Kelly
            size = min(
                available_capital * 0.05,  # Max 5% per Alpha trade
                self.max_position_size,
                100.0  # Cap at $100 for Alpha
            )
            
            # Determine strategy
            yes_price = float(market_data.get('yes_price', 0.5))
            if yes_price < 0.25 or yes_price > 0.75:
                strategy = 'alpha_directional'
            else:
                strategy = 'volatility_exploitation'
            
            logger.info(
                f"[ALPHA TRADE] {side} ${size:.2f} in {market_id[:16]}... | "
                f"Edge: {edge:.2%} | FV: {analysis['fair_value']:.4f} | Strategy: {strategy}"
            )
            
            await self._execute_paper_entry(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=size,
                strategy=strategy,
                signals=analysis.get('signals', {}),
                rl_action=analysis.get('rl_action', 'ALPHA_ENTRY'),
                rl_confidence=analysis.get('rl_confidence', 0.5),
                sizing_breakdown={
                    'alpha_trade': True,
                    'fair_value': analysis['fair_value'],
                    'edge': edge,
                    'regime': analysis['regime'],
                    'probability_diagnostics': analysis.get('diagnostics', {}),
                }
            )
            
        except Exception as e:
            logger.error(f"[ALPHA] Error executing trade: {e}")
    
    # =================================================================
    # LEGACY TRADING LOOP (Kept for compatibility, but replaced by above)
    # =================================================================
    
    async def _trading_loop(self):
        """
        Legacy trading loop - NOW DISABLED in favor of Two-Speed Architecture.
        
        The functionality is split into:
        - _run_hft_loop(): Fast microstructure trading
        - _run_alpha_loop(): Slow Bayesian analysis
        """
        logger.info("Legacy _trading_loop is disabled - using Two-Speed Architecture")
        # This loop is now effectively a no-op as HFT and Alpha loops handle everything
        while self.running:
            await asyncio.sleep(60)  # Sleep and let HFT/Alpha do the work
    
    async def stop(self, graceful: bool = False):
        """Stop paper trading and save final results
        
        Args:
            graceful: If True, stop accepting new trades but let existing positions
                     close naturally according to strategy rules (take profit/stop loss)
        """
        if graceful:
            self.graceful_stop = True
            self.stop_requested = True
            logger.info("Graceful stop initiated - waiting for positions to close naturally")
            
            # Wait for all positions to close (with timeout)
            max_wait = 300  # 5 minutes max
            waited = 0
            while self.paper_positions and waited < max_wait:
                await asyncio.sleep(5)
                waited += 5
                logger.info(f"Graceful stop: {len(self.paper_positions)} positions remaining")
            
            if self.paper_positions:
                logger.warning(f"Timeout waiting for graceful close - forcing close of {len(self.paper_positions)} positions")
                await self._close_all_positions()
        else:
            # Immediate stop - close all positions at current prices
            await self._close_all_positions()
        
        self.running = False
        
        # Stop WebSocket service
        if self.realtime_market_service:
            try:
                await self.realtime_market_service.stop()
                logger.info("WebSocket market service stopped")
            except Exception as e:
                logger.warning(f"Error stopping WebSocket service: {e}")
        
        # Clean up persisted positions (all should be closed now)
        await self._cleanup_persisted_positions()
        
        # Save session results
        await self._save_session_results()
        
        # Final RL learning from session
        await self._learn_from_session()
        
        logger.info(f"Paper Trading Stopped - Total PnL: ${self.total_pnl:.2f}")
    
    async def _cleanup_persisted_positions(self):
        """Remove all persisted positions for this session after clean close"""
        try:
            result = await self.db.paper_positions_live.delete_many({
                "session_id": self.session_id
            })
            if result.deleted_count > 0:
                logger.info(f"[PERSIST] Cleaned up {result.deleted_count} persisted positions")
        except Exception as e:
            logger.error(f"[PERSIST] Error cleaning up positions: {e}")
    
    async def _continuous_mode_handler(self):
        """Handle continuous mode - auto-restart sessions"""
        while self.running:
            try:
                if self.continuous_mode and not self.stop_requested:
                    # Check if session should auto-restart (e.g., after certain conditions)
                    # For now, continuous mode just keeps running indefinitely
                    pass
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in continuous mode handler: {e}")
                await asyncio.sleep(60)
    
    async def _init_session(self):
        """Initialize paper trading session in database"""
        self.session_start_time = datetime.now(timezone.utc)
        session_doc = {
            "session_id": self.session_id,
            "type": "paper_trading",
            "continuous_mode": self.continuous_mode,
            "initial_capital": self.initial_capital,
            "start_time": self.session_start_time.isoformat(),
            "status": "running",
            "trades": [],
            "positions": []
        }
        await self.db.paper_trading_sessions.insert_one(session_doc)
        
        # Load any existing open positions for this session (in case of restart)
        await self._load_positions_from_db()
    
    # =========================================================================
    # POSITION PERSISTENCE METHODS
    # =========================================================================
    
    async def _save_position_to_db(self, market_id: str, position: Dict):
        """Save position to database for persistence across restarts"""
        try:
            position_doc = {
                **position,
                "market_id": market_id,
                "session_id": self.session_id,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            await self.db.paper_positions_live.update_one(
                {"market_id": market_id, "session_id": self.session_id},
                {"$set": position_doc},
                upsert=True
            )
            logger.debug(f"[PERSIST] Saved position {market_id[:16]}... to DB")
        except Exception as e:
            logger.error(f"[PERSIST] Error saving position to DB: {e}")
    
    async def _delete_position_from_db(self, market_id: str):
        """Remove closed position from database"""
        try:
            result = await self.db.paper_positions_live.delete_one({
                "market_id": market_id,
                "session_id": self.session_id
            })
            if result.deleted_count > 0:
                logger.debug(f"[PERSIST] Deleted position {market_id[:16]}... from DB")
        except Exception as e:
            logger.error(f"[PERSIST] Error deleting position from DB: {e}")
    
    async def _load_positions_from_db(self):
        """Load open positions from database on startup/restart"""
        try:
            positions = await self.db.paper_positions_live.find({
                "session_id": self.session_id
            }).to_list(None)
            
            if positions:
                logger.info(f"[PERSIST] Loading {len(positions)} open positions from database")
                for pos in positions:
                    market_id = pos.get("market_id")
                    if market_id:
                        # Remove MongoDB _id field
                        pos.pop("_id", None)
                        self.paper_positions[market_id] = pos
                        logger.info(f"[PERSIST] Restored position: {pos.get('market_question', market_id)[:40]}... @ {pos.get('entry_price', 0):.4f}")
                
                logger.info(f"[PERSIST] Successfully restored {len(self.paper_positions)} positions")
            else:
                logger.info("[PERSIST] No existing positions to restore")
                
        except Exception as e:
            logger.error(f"[PERSIST] Error loading positions from DB: {e}")
    
    async def _reconstruct_positions_from_trades(self):
        """
        Fallback: Reconstruct positions from trade history if paper_positions_live is empty.
        Finds entry trades without matching exit trades.
        """
        try:
            # Get all entry trades for this session
            entries = await self.db.paper_trades.find({
                "session_id": self.session_id,
                "type": "entry"
            }).to_list(None)
            
            # Get all exit trades for this session
            exits = await self.db.paper_trades.find({
                "session_id": self.session_id,
                "type": "exit"
            }).to_list(None)
            
            # Find closed market IDs
            closed_markets = set(e.get("market_id") for e in exits)
            
            # Reconstruct open positions
            reconstructed = 0
            for entry in entries:
                market_id = entry.get("market_id")
                entry_price = entry.get("entry_price")
                
                # STRICT VALIDATION: Skip entries without valid entry_price
                if entry_price is None or entry_price == 0:
                    logger.warning(f"[RECONSTRUCT-SKIP] Entry {market_id[:16] if market_id else 'unknown'} has no valid entry_price - skipping")
                    continue
                
                if market_id and market_id not in closed_markets and market_id not in self.paper_positions:
                    position = {
                        "market_id": market_id,
                        "market_question": entry.get("market_question", "Unknown"),
                        "entry_price": float(entry_price),
                        "side": entry.get("side", "NO"),
                        "size": entry.get("size", 0),
                        "shares": entry.get("shares", 0),
                        "strategy": entry.get("strategy", "unknown"),
                        "asset_class": entry.get("asset_class", "other"),
                        "entry_timestamp": entry.get("timestamp"),
                        "reconstructed": True  # Flag to indicate this was reconstructed
                    }
                    self.paper_positions[market_id] = position
                    await self._save_position_to_db(market_id, position)
                    reconstructed += 1
                    logger.info(f"[RECONSTRUCT] Restored: {position.get('market_question', '')[:40]}...")
            
            if reconstructed > 0:
                logger.warning(f"[RECONSTRUCT] Reconstructed {reconstructed} positions from trade history")
            
            return reconstructed
            
        except Exception as e:
            logger.error(f"[RECONSTRUCT] Error reconstructing positions: {e}")
            return 0
    
    # =========================================================================
    # EMERGENCY STOP LOSS BACKGROUND TASK
    # =========================================================================
    
    async def _emergency_stoploss_task(self):
        """
        Background task that checks ALL positions for emergency stop loss.
        This is a safety net that runs independently of the main trading loop.
        Triggers at -50% loss regardless of strategy settings.
        """
        EMERGENCY_SL_THRESHOLD = -0.50  # -50% emergency stop
        CHECK_INTERVAL = 30  # Check every 30 seconds
        
        logger.info(f"[EMERGENCY SL] Background task started (threshold: {EMERGENCY_SL_THRESHOLD:.0%}, interval: {CHECK_INTERVAL}s)")
        
        while self.running:
            try:
                await asyncio.sleep(CHECK_INTERVAL)
                
                if not self.paper_positions:
                    continue
                
                # Get current prices for all positions
                markets = await self._get_active_markets()
                market_prices = {m.get('id'): m for m in markets}
                
                positions_to_close = []
                
                for market_id, position in list(self.paper_positions.items()):
                    market_data = market_prices.get(market_id)
                    if not market_data:
                        continue
                    
                    # Get current price - skip position monitoring if no valid price
                    current_price = market_data.get('yes_price')
                    if current_price is None or current_price == 0:
                        logger.debug(f"[EMERGENCY SL] No price data for {market_id[:16]} - skipping")
                        continue
                    
                    current_price = float(current_price)
                    entry_price = position.get('entry_price', 0)
                    if entry_price == 0:
                        continue
                        
                    side = position.get('side', 'NO')
                    size = position.get('size', 0)
                    
                    # Calculate P&L %
                    if side == 'YES':
                        pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
                    else:  # NO position
                        no_entry = 1 - entry_price
                        no_current = 1 - current_price
                        pnl_pct = (no_current - no_entry) / no_entry if no_entry > 0 else 0
                    
                    # Check for emergency stop loss
                    if pnl_pct <= EMERGENCY_SL_THRESHOLD:
                        logger.warning(f"🚨 [EMERGENCY SL] {position.get('market_question', market_id)[:40]}... at {pnl_pct:.1%} (threshold: {EMERGENCY_SL_THRESHOLD:.0%})")
                        positions_to_close.append((market_id, market_data, pnl_pct))
                
                # Close positions that hit emergency stop loss
                for market_id, market_data, pnl_pct in positions_to_close:
                    try:
                        await self._execute_paper_exit(market_id, market_data, f"emergency_sl_{pnl_pct:.0%}")
                        logger.warning(f"🚨 [EMERGENCY SL] CLOSED position at {pnl_pct:.1%} loss")
                    except Exception as e:
                        logger.error(f"[EMERGENCY SL] Error closing position: {e}")
                
            except Exception as e:
                logger.error(f"[EMERGENCY SL] Error in background task: {e}")
                await asyncio.sleep(5)
        
        logger.info("[EMERGENCY SL] Background task stopped")
    
    async def _trading_loop(self):
        """Main paper trading loop - evaluates markets and executes paper trades"""
        logger.info(f"Paper Trading loop started with {len(self.enabled_strategies)} strategies, {len(self.enabled_asset_classes)} asset classes")
        logger.info(f"Continuous mode: {self.continuous_mode}")
        
        # Calculate trade interval for high-frequency trading
        # 500-1000 trades per 10 min = 0.6-1.2 seconds per trade
        trade_interval = 600.0 / self.trades_per_10min
        logger.info(f"High-frequency mode: {self.trades_per_10min} trades/10min, interval: {trade_interval:.2f}s")
        
        while self.running:
            try:
                # Fetch active markets filtered by enabled asset classes
                markets = await self._get_active_markets()
                
                if not markets:
                    logger.warning("No markets available for trading - waiting 5 seconds before retry")
                    await asyncio.sleep(5)
                    continue
                
                # High-frequency: process ALL markets, not just top 20
                markets_to_process = markets[:100]  # Process up to 100 markets per cycle
                
                # Debug counters
                entry_evaluated = 0
                exit_evaluated = 0
                skipped_asset_class = 0
                
                for market_data in markets_to_process:
                    if not self.running:
                        break
                    
                    market_id = market_data.get('id')
                    question = market_data.get('question', '')
                    
                    # Filter by asset class
                    asset_class = market_data.get('asset_class', market_data.get('category', 'unknown')).lower()
                    if asset_class not in [ac.lower() for ac in self.enabled_asset_classes]:
                        skipped_asset_class += 1
                        continue
                    
                    # =================================================================
                    # ROUTER PRIORITY (5-Lane Highway)
                    # =================================================================
                    # 1. Check existing position first (exits always take priority)
                    # 2. SPORTS: Real odds arbitrage (isolated lane)
                    # 3. GAMMA: Moonshot candidates (opportunistic)
                    # 4. NEWS: Check cache for emergent signals (Lane 5)
                    # 5. STANDARD: HFT/Alpha determination
                    # =================================================================
                    
                    if market_id in self.paper_positions:
                        # Always evaluate exits (even during graceful stop)
                        await self._evaluate_exit(market_id, market_data)
                        exit_evaluated += 1
                    elif not self.graceful_stop:
                        # ===== LANE 5: NEWS/EMERGENT CHECK =====
                        # Check if there's an injected news signal for this market
                        news_signal = await self._check_news_signal(market_id)
                        if news_signal and news_signal.get('bayes_factor', 0) >= 3.0:
                            await self._execute_news_sniper(market_data, news_signal)
                            entry_evaluated += 1
                            continue
                        
                        # Standard entry evaluation (Sports/Gamma/HFT/Alpha)
                        await self._evaluate_entry(market_data)
                        entry_evaluated += 1
                    
                    # High-frequency: minimal pause between markets
                    await asyncio.sleep(trade_interval / len(markets_to_process))
                
                # Log cycle stats every 10 cycles
                if not hasattr(self, '_cycle_count'):
                    self._cycle_count = 0
                self._cycle_count += 1
                if self._cycle_count % 10 == 0:
                    skip_summary = ", ".join([f"{k}:{v}" for k,v in sorted(getattr(self, '_skip_reasons', {}).items(), key=lambda x: -x[1])[:5]])
                    logger.info(f"[CYCLE {self._cycle_count}] Entries: {entry_evaluated}, Exits: {exit_evaluated}, Open: {len(self.paper_positions)}, Attempts: {getattr(self, '_total_entry_attempts', 0)}, Passed: {getattr(self, '_entry_passed_all', 0)}")
                    logger.info(f"[SKIP REASONS] {skip_summary}")
                
                # Check if graceful stop is complete (all positions closed)
                if self.graceful_stop and not self.paper_positions:
                    logger.info("Graceful stop complete - all positions closed")
                    self.running = False
                    break
                
                # Record equity curve point with strategy and asset class breakdowns
                self.equity_curve.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "capital": self.current_capital,
                    "pnl": self.total_pnl,
                    "open_positions": len(self.paper_positions),
                    # Strategy P&L breakdown (legacy)
                    "delta_neutral_pnl": self.strategy_equity.get('delta_neutral', 0),
                    "volatility_pnl": self.strategy_equity.get('volatility_exploitation', 0),
                    "alpha_pnl": self.strategy_equity.get('alpha_directional', 0),
                    "arbitrage_pnl": self.strategy_equity.get('arbitrage', 0),
                    # Three-Speed Lane P&L breakdown (Task 29)
                    "hft_pnl": self.lane_equity.get('HFT', 0),
                    "alpha_lane_pnl": self.lane_equity.get('ALPHA', 0),
                    "gamma_pnl": self.lane_equity.get('GAMMA', 0),
                    # Asset class P&L breakdown
                    "asset_class_equity": dict(self.asset_class_equity)
                })
                
                # Minimal pause between cycles for high-frequency
                await asyncio.sleep(max(0.1, trade_interval))
                
            except Exception as e:
                logger.error(f"Error in paper trading loop: {e}")
                await asyncio.sleep(2)
    
    async def _evaluate_entry(self, market_data: Dict):
        """Evaluate market for potential paper trade entry using ADAPTIVE sizing"""
        try:
            market_id = market_data.get('id', '')
            market_id_short = market_id[:16]
            
            # Track EVERY entry attempt with a simple counter
            if not hasattr(self, '_total_entry_attempts'):
                self._total_entry_attempts = 0
                self._entry_passed_all = 0
                self._skip_reasons = {}
            self._total_entry_attempts += 1
            
            def track_skip(reason):
                self._skip_reasons[reason] = self._skip_reasons.get(reason, 0) + 1
            
            # CIRCUIT BREAKER CHECK: Stop new entries if max drawdown exceeded
            if self.circuit_breaker_triggered:
                track_skip("circuit_breaker")
                return
            
            # Check if we're at max positions limit
            if len(self.paper_positions) >= self.max_open_positions:
                track_skip("max_positions")
                return
            
            # CHECK IF WE ALREADY HAVE POSITION (shouldn't happen but let's track)
            if market_id in self.paper_positions:
                track_skip("already_have_position")
                return
            
            # CHECK AVAILABLE CAPITAL before proceeding
            # Calculate how much is currently deployed
            current_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
            available_capital = self.deployed_capital - current_deployed  # deployed_capital is max allowed
            logger.debug(f"[CAPITAL CHECK] deployed_capital={self.deployed_capital}, current_deployed={current_deployed}, available={available_capital}")
            if available_capital < 5:  # Need at least $5 for min trade
                track_skip("no_available_capital")
                return
            
            asset_class = market_data.get('asset_class', market_data.get('category', 'unknown'))
            
            # LIQUIDITY CHECK: Use user-configured thresholds from Configuration page
            volume_24h = float(market_data.get('volume_24h', 0) or 0)
            volume = float(market_data.get('volume', 0) or 0)
            liquidity = float(market_data.get('liquidity', 0) or 0)
            
            effective_volume = max(volume_24h, volume)
            
            # Use user-defined thresholds from config (Configuration page is source of truth)
            min_vol_threshold = self.min_volume_24h  # From user config
            min_liq_threshold = self.min_liquidity   # From user config
            max_liq_threshold = self.max_liquidity   # From user config
            
            # Check minimum liquidity requirements
            if effective_volume < min_vol_threshold and liquidity < min_liq_threshold:
                track_skip("low_liquidity")
                return
            
            # Check maximum liquidity (if user wants to avoid very liquid markets)
            if liquidity > max_liq_threshold:
                track_skip("high_liquidity")
                return
            
            # CHECK END DATE: Skip markets where the event deadline has passed
            end_date_str = market_data.get('end_date') or market_data.get('endDate') or market_data.get('close_time')
            if end_date_str:
                try:
                    # Parse various date formats
                    if isinstance(end_date_str, str):
                        # Try ISO format first
                        if 'T' in end_date_str:
                            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                        else:
                            # Try other common formats
                            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y']:
                                try:
                                    end_date = datetime.strptime(end_date_str, fmt)
                                    end_date = end_date.replace(tzinfo=timezone.utc)
                                    break
                                except ValueError:
                                    continue
                            else:
                                end_date = None
                    elif isinstance(end_date_str, (int, float)):
                        # Unix timestamp
                        end_date = datetime.fromtimestamp(end_date_str, tz=timezone.utc)
                    else:
                        end_date = None
                    
                    if end_date:
                        now = datetime.now(timezone.utc)
                        if end_date < now:
                            track_skip("expired_end_date")
                            return
                except Exception as e:
                    logger.warning(f"Could not parse end_date '{end_date_str}': {e}")
            
            # CHECK QUESTION TEXT FOR PAST DATES: Parse dates from question itself
            # This catches markets like "Will X happen by January 15, 2026?" where end_date is Jan 31
            question = market_data.get('question', '')
            if question:
                import re
                now = datetime.now(timezone.utc)
                current_year = now.year
                
                # Pattern: "by/before/on January 15, 2026" or "January 15th, 2026"
                date_patterns = [
                    r'(?:by|before|on|until)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})',
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})',
                ]
                
                month_map = {
                    'January': 1, 'February': 2, 'March': 3, 'April': 4,
                    'May': 5, 'June': 6, 'July': 7, 'August': 8,
                    'September': 9, 'October': 10, 'November': 11, 'December': 12
                }
                
                for pattern in date_patterns:
                    match = re.search(pattern, question, re.IGNORECASE)
                    if match:
                        try:
                            month_name = match.group(1) if 'by' not in pattern.lower() else match.group(1)
                            # Handle different group positions based on pattern
                            groups = match.groups()
                            if len(groups) >= 3:
                                month_str = groups[-3] if groups[-3] in month_map else groups[0]
                                day = int(groups[-2])
                                year = int(groups[-1])
                                month = month_map.get(month_str.capitalize(), 0)
                                
                                if month and day and year:
                                    question_date = datetime(year, month, day, tzinfo=timezone.utc)
                                    if question_date < now:
                                        track_skip("semantic_expiry")
                                        return
                        except (ValueError, IndexError) as e:
                            pass  # Date parsing failed, continue
            
            # CHECK CLOSED/RESOLVED STATUS: Skip markets that are already resolved
            is_closed = market_data.get('closed', False) or market_data.get('resolved', False)
            is_active = market_data.get('active', True)
            if is_closed or not is_active:
                track_skip("closed_or_inactive")
                return
            
            # ============================================
            # LIVE EVENT FILTER (Jan 2026 - Critical Fix)
            # ============================================
            # Skip markets that appear to be live/in-progress events
            # These resolve too quickly for our model to be accurate
            question = market_data.get('question', '').lower()
            
            # Pattern 1: Team vs Team sports (NBA, NHL, NFL, etc.)
            # Examples: "Kings vs. Red Wings", "Bucks vs. 76ers", "Seahawks vs. Patriots"
            import re
            sports_pattern = re.compile(
                r'(vs\.?|versus)\s*'  # "vs" or "vs." or "versus"
                r'(?!.*\d{4})',  # But NOT if it has a year (like "2024 election")
                re.IGNORECASE
            )
            
            # Check if it looks like a live sports matchup
            is_sports_matchup = bool(sports_pattern.search(question))
            
            # Pattern 2: Over/Under bets (O/U) - these are always sports
            is_over_under = 'o/u' in question or 'over/under' in question
            
            # Pattern 3: Common sports terms indicating live game
            live_sports_terms = [
                'vs.', ' vs ', 'versus',
                'will win tonight', 'win today',
                'beat the', 'defeat the',
                'score first', 'first goal',
                'first touchdown', 'first basket',
            ]
            has_live_sports_term = any(term in question for term in live_sports_terms)
            
            # Pattern 4: Category check (some sports correctly labeled)
            category = market_data.get('category', market_data.get('asset_class', '')).lower()
            
            # Block if it looks like a live sports event
            if is_sports_matchup or is_over_under or has_live_sports_term:
                track_skip("live_sports_event")
                logger.debug(f"[FILTER] Skipping live sports: {question[:50]}...")
                return
            
            # ============================================
            # STRICT PRICE VALIDATION - REJECT DEFAULT PRICES
            # ============================================
            yes_price = market_data.get('yes_price')
            if yes_price is None or yes_price == 0:
                track_skip("no_price_data")
                return
            
            yes_price = float(yes_price)
            
            # Check for stuck/stale prices - these are likely defaults or no real trading
            if yes_price in [0.0, 1.0]:  # Extreme prices - likely no real data
                track_skip("extreme_price")
                return
            
            # Check for suspicious ~0.5 prices (likely default/no real data)
            if abs(yes_price - 0.5) < 0.02:
                # Price is near 0.5 - require high volume AND real orderbook to proceed
                stale_price_min_volume = min_vol_threshold * self.stuck_price_multiplier
                order_book = market_data.get('order_book', {})
                has_orderbook = bool(order_book.get('bids')) and bool(order_book.get('asks'))
                
                if effective_volume < stale_price_min_volume or not has_orderbook:
                    track_skip("stuck_price_no_orderbook")
                    return
            
            # Get ML signals
            signals = await self._get_signals(market_data)
            
            # Get RL recommendation
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Skip if RL says wait/hold or very low confidence
            # Note: RL confidence is ~0.14 when Q-table hasn't learned (1/7 uniform)
            # Threshold at 0.10 allows trades through until RL learns meaningful patterns
            if rl_action in ['WAIT', 'HOLD'] or rl_confidence < 0.10:
                track_skip("rl_wait_or_low_conf")
                return
            
            # Skip if action is not a clear BUY or SELL
            if 'BUY' not in rl_action and 'SELL' not in rl_action:
                track_skip("rl_no_buy_sell")
                return
            
            # =============================================================
            # EDGE-BASED SIDE SELECTION (Fixed Jan 2026)
            # =============================================================
            # Calculate fair value and edge to determine optimal direction
            # This replaces the sentiment-only approach which was inverted
            
            sentiment = signals.get('sentiment', 0.5)
            sharp_alignment = signals.get('sharp_alignment', 0.5)
            
            # Quick fair value estimate based on sentiment and price
            # Sentiment > 0.5 = bullish, expecting YES to rise
            # We combine sentiment with current price for a basic fair value
            fair_value_estimate = (sentiment * 0.6 + yes_price * 0.4)
            
            # Calculate edges
            effective_price = yes_price + 0.02  # Fee adjustment
            yes_edge = fair_value_estimate - effective_price
            no_edge = (1 - fair_value_estimate) - (1 - yes_price + 0.02)
            
            # Select side based on which has positive edge
            # ==========================================================
            # EDGE DIRECTION SAFEGUARD (Jan 2026)
            # ==========================================================
            # Until model is recalibrated, only trade YES (FV > market)
            if yes_edge > no_edge and yes_edge > 0.005:
                side = 'YES'
                edge = yes_edge
            elif no_edge > yes_edge and no_edge > 0.005:
                # TEMPORARILY SKIP NO trades - model bias issue
                track_skip("no_side_disabled")
                logger.debug(f"[ENTRY] Skipping NO trade (model under review)")
                return
            else:
                # Both edges negative or too small - skip
                track_skip("no_edge")
                return
            
            logger.debug(f"[ENTRY] {market_id_short}... FV={fair_value_estimate:.4f} YES_edge={yes_edge:.4f} NO_edge={no_edge:.4f} → {side}")
            
            # Determine strategy based on signals
            strategy = self._determine_strategy(signals, rl_action, market_data)
            
            # TIME-TO-EXPIRY CHECK: Adjust or skip based on expiry proximity
            expiry_info = self._calculate_time_to_expiry(market_data)
            
            # Check if we should enter at all based on expiry
            if not expiry_info.get('should_enter', True):
                track_skip("expiry_should_not_enter")
                return
            
            # Check strategy-specific expiry rules
            strategy_expiry = self._should_strategy_trade_near_expiry(strategy, expiry_info, rl_confidence)
            if not strategy_expiry.get('should_trade', True):
                track_skip("strategy_expiry_block")
                return
            
            # Get expiry-adjusted size multiplier
            expiry_size_mult = strategy_expiry.get('size_multiplier', 1.0)
            
            # Extract metadata for NEW Polymarket sizer
            market_question = market_data.get('question', '')
            market_tags = market_data.get('tags', [])
            days_to_expiry = expiry_info.get('days_to_expiry')
            
            # Calculate market age in hours (if created_at available)
            market_age_hours = None
            created_at = market_data.get('created_at') or market_data.get('createdAt')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    elif isinstance(created_at, (int, float)):
                        created_dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
                    else:
                        created_dt = None
                    if created_dt:
                        market_age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                except Exception:
                    pass
            
            # Fetch order book for liquidity clamp (if Polymarket sizer enabled)
            # Note: This is optional - the sizer works without it but is more accurate with it
            order_book_asks = []
            order_book_data = {}  # Full orderbook for maker execution
            if self.use_polymarket_sizer:
                try:
                    # Get token IDs from market data
                    # token_ids[0] = YES token, token_ids[1] = NO token (Polymarket convention)
                    token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
                    if token_ids and isinstance(token_ids, list) and len(token_ids) > 0:
                        # Store token IDs for later orderbook fetch
                        market_data['token_ids'] = token_ids
                        
                        # Import and use the API to fetch order book for sizing liquidity check
                        # Note: This fetches YES token orderbook - we'll fetch the correct one after sizing
                        from data.polymarket_api import PolymarketAPI
                        async with PolymarketAPI() as api:
                            order_book_data = await api.get_order_book(token_ids[0])
                            order_book_asks = order_book_data.get('asks', [])
                            # Store for sizing (may be replaced later with correct side's orderbook)
                            if order_book_data.get('bids') and order_book_data.get('asks'):
                                market_data['order_book'] = order_book_data
                                market_data['order_book_token'] = 'YES'  # Track which token's orderbook this is
                                
                                logger.debug(f"[ORDERBOOK] Fetched YES token orderbook for sizing: {market_id[:16]}")
                except Exception as e:
                    logger.debug(f"Could not fetch order book: {e}")
            
            # =================================================================
            # MARKET REGIME CLASSIFICATION (EARLY FILTER)
            # =================================================================
            # Classify market BEFORE expensive computations (sizing, Bayesian, etc.)
            # This saves CPU and API calls on dead/illiquid markets.
            volume_24h = market_data.get('volume_24h', market_data.get('volume', 0)) or 0
            
            if order_book_data.get('bids') and order_book_data.get('asks'):
                bids = order_book_data['bids']
                asks = order_book_data['asks']
                best_bid = float(bids[0]['price']) if bids else 0
                best_ask = float(asks[0]['price']) if asks else 1
                
                # Classify the market regime
                regime, regime_diagnostics = classify_market_regime(
                    best_bid=best_bid,
                    best_ask=best_ask,
                    volume_24h=volume_24h
                )
                
                # Store regime info for later use
                market_data['regime'] = regime
                market_data['regime_diagnostics'] = regime_diagnostics
                
                # ZOMBIE FILTER: Skip immediately - save all subsequent computation
                if regime == MarketRegime.ZOMBIE:
                    reject_reason = regime_diagnostics.get('reject_reason', 'zombie_market')
                    logger.info(f"[REGIME] ZOMBIE market {market_id[:16]}... - SKIP | {reject_reason}")
                    track_skip("regime_zombie")
                    return
                
                # Log regime classification
                spread = best_ask - best_bid
                logger.debug(f"[REGIME] {regime} | {market_id[:16]}... | spread={spread:.2%} | vol=${volume_24h:.0f}")
            else:
                # No orderbook data - can't classify regime, default to TAKER_TIGHT
                market_data['regime'] = MarketRegime.TAKER_TIGHT
                market_data['regime_diagnostics'] = {'reason': 'no_orderbook_data'}
            
            # ADAPTIVE POSITION SIZING - considers liquidity, volume, Kelly, RL confidence
            # Uses self.kelly_fraction and self.kelly_enabled from user config
            sizing_result = self._calculate_position_size(
                rl_confidence=rl_confidence,
                signals=signals,
                market_data=market_data,
                strategy=strategy,
                asset_class=asset_class,
                rl_action=rl_action,
                # NEW parameters for Polymarket sizer
                order_book_asks=order_book_asks,
                market_question=market_question,
                market_tags=market_tags,
                market_age_hours=market_age_hours,
                days_to_expiry=days_to_expiry
            )
            
            # Check if we should trade (liquidity/size requirements met)
            if not sizing_result.get('should_trade', False):
                track_skip("sizing_rejected")
                return
            
            # Apply expiry size multiplier
            position_size = sizing_result.get('position_size', 0) * expiry_size_mult
            
            # Minimum position size for HFT - $5 minimum
            min_position_size = 5
            if position_size < min_position_size:
                track_skip("position_too_small")
                return
            
            # For Polymarket sizer, use the edge-derived side instead of sentiment
            if self.use_polymarket_sizer and '_sizing_side' in sizing_result:
                side = sizing_result['_sizing_side']
            
            # Add expiry info to sizing breakdown for UI display
            sizing_breakdown = sizing_result.get('sizing_breakdown', {})
            sizing_breakdown['expiry_info'] = {
                'hours_to_expiry': expiry_info.get('hours_to_expiry'),
                'days_to_expiry': expiry_info.get('days_to_expiry'),
                'urgency': expiry_info.get('urgency'),
                'expiry_label': expiry_info.get('expiry_label'),
                'size_multiplier': expiry_size_mult,
                'strategy_reason': strategy_expiry.get('reason')
            }
            
            # Execute paper trade with sizing breakdown for learning
            self._entry_passed_all = getattr(self, '_entry_passed_all', 0) + 1
            await self._execute_paper_entry(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=position_size,
                strategy=strategy,
                signals=signals,
                rl_action=rl_action,
                rl_confidence=rl_confidence,
                sizing_breakdown=sizing_result.get('sizing_breakdown', {})
            )
            
        except Exception as e:
            logger.error(f"Error evaluating entry: {e}")
    
    # DEFAULT Exit parameters by STRATEGY - different strategies have different risk profiles
    # NOTE: These are defaults. The actual values are loaded from DB in _load_user_config()
    DEFAULT_EXIT_PARAMS = {
        'delta_neutral': {
            'take_profit': 0.02,    # 2% - quick profits
            'stop_loss': -0.02,     # 2% - tight stop
            'max_hours': 4          # Close faster for paper testing
        },
        'volatility_exploitation': {
            'take_profit': 0.05,    # 5% - capture volatility
            'stop_loss': -0.05,     # 5% - symmetric stop
            'max_hours': 8          # Hold longer for swings
        },
        'alpha_directional': {
            'take_profit': 0.08,    # 8% - conviction trades
            'stop_loss': -0.05,     # 5% - give room to be right
            'max_hours': 12         # Hold for directional moves
        },
        'arbitrage': {
            'take_profit': 0.03,    # 3% - capture spread
            'stop_loss': -0.03,     # 3% - tight risk
            'max_hours': 6          # Standard hold
        },
        # =================================================================
        # SPORTS ARBITRAGE - CRITICAL FIX (Jan 2026)
        # =================================================================
        # Sports bets are BINARY OUTCOME. Different exit logic:
        # - If arb disappears after entry, selling early guarantees loss (spread)
        # - Ride to settlement unless line moves massively in your favor
        # =================================================================
        'sports_arbitrage': {
            'take_profit': 0.30,    # 30% - If line moves massively in your favor pre-game, take free money
            'stop_loss': -1.00,     # 100% - Ride to binary outcome (selling early = guaranteed loss due to spread)
            'max_hours': 24,        # 24h - If game hasn't settled, something is wrong (delayed/cancelled)
            'force_exit_on_time': True  # Force sell at market if time limit hits
        },
        # =================================================================
        # NEWS SNIPER (Lane 5) - Event-driven trades
        # =================================================================
        # News trades have short validity windows - act fast, exit fast
        # =================================================================
        'news_sniper': {
            'take_profit': 0.15,    # 15% - News edge decays quickly, take profits
            'stop_loss': -0.10,     # 10% - Tighter stop since news can be wrong
            'max_hours': 4,         # 4h - News is time-sensitive, don't hold too long
            'force_exit_on_time': True
        }
    }
    
    # Exit parameter adjustments by ASSET CLASS - some markets are more volatile
    EXIT_ADJUSTMENTS_BY_ASSET = {
        'crypto': {
            'tp_mult': 1.5,   # Crypto is volatile, wider TP
            'sl_mult': 1.3,   # Wider SL too
            'time_mult': 0.5  # But close faster
        },
        'politics': {
            'tp_mult': 1.2,
            'sl_mult': 1.0,
            'time_mult': 1.5  # Political events take longer
        },
        'sports': {
            'tp_mult': 1.0,   # No adjustment - sports_arbitrage params are already correct
            'sl_mult': 1.0,   # No adjustment - binary outcome, ride to settlement
            'time_mult': 1.0  # No adjustment - 24h is already appropriate for sports
        },
        'finance': {
            'tp_mult': 0.8,   # More predictable
            'sl_mult': 0.8,
            'time_mult': 1.0
        },
        'entertainment': {
            'tp_mult': 1.0,
            'sl_mult': 1.0,
            'time_mult': 1.0
        },
        'science': {
            'tp_mult': 1.0,
            'sl_mult': 1.0,
            'time_mult': 2.0  # Science takes time
        }
    }
    
    # Default Time-to-expiry thresholds for strategy adjustments (can be overridden by config)
    DEFAULT_EXPIRY_THRESHOLDS = {
        'no_entry_hours': 6,        # No new entries within 6 hours of expiry
        'high_urgency_hours': 24,   # Reduce max hold time, tighten exits
        'medium_urgency_days': 7,   # Boost volatility, reduce delta-neutral
        'normal_days': 30           # Normal trading
    }
    
    # Default Strategy adjustments based on time-to-expiry (can be overridden by config)
    DEFAULT_EXPIRY_STRATEGY_ADJUSTMENTS = {
        'delta_neutral': {
            'disable_within_hours': 48,  # No market making close to expiry
            'size_mult_near_expiry': 0.5
        },
        'volatility_exploitation': {
            'boost_within_days': 7,      # Boost 1.5x in final week
            'boost_multiplier': 1.5,
            'disable_within_hours': 6
        },
        'alpha_directional': {
            'min_confidence_near_expiry': 0.7,  # Only high conviction near expiry
            'disable_within_hours': 6
        },
        'arbitrage': {
            'disable_within_hours': 6    # Keep active longer, guaranteed resolution
        },
        'sports_arbitrage': {
            'disable_within_hours': 1,   # Sports: Only disable 1h before game time
            'ride_to_settlement': True   # Always hold to binary outcome
        }
    }
    
    def _get_expiry_thresholds(self) -> Dict:
        """Get expiry thresholds from config or use defaults."""
        # Use the loaded expiry_thresholds_config if available, otherwise fall back to config dict or defaults
        if hasattr(self, 'expiry_thresholds_config') and self.expiry_thresholds_config:
            return self.expiry_thresholds_config
        return self.config.get('expiry_thresholds', self.DEFAULT_EXPIRY_THRESHOLDS)
    
    def _get_expiry_strategy_adjustments(self) -> Dict:
        """Get strategy expiry adjustments from config or use defaults."""
        # Use the loaded expiry_strategy_adjustments if available
        if hasattr(self, 'expiry_strategy_adjustments') and self.expiry_strategy_adjustments:
            return self.expiry_strategy_adjustments
        return self.config.get('expiry_strategy_adjustments', self.DEFAULT_EXPIRY_STRATEGY_ADJUSTMENTS)
    
    def _parse_end_date(self, market_data: Dict) -> Optional[datetime]:
        """Parse end date from market data, handling various formats"""
        end_date_str = market_data.get('end_date') or market_data.get('endDate') or market_data.get('close_time')
        if not end_date_str:
            return None
            
        try:
            if isinstance(end_date_str, str):
                if 'T' in end_date_str:
                    return datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y']:
                        try:
                            dt = datetime.strptime(end_date_str, fmt)
                            return dt.replace(tzinfo=timezone.utc)
                        except ValueError:
                            continue
            elif isinstance(end_date_str, (int, float)):
                return datetime.fromtimestamp(end_date_str, tz=timezone.utc)
        except Exception:
            pass
        return None
    
    def _calculate_time_to_expiry(self, market_data: Dict) -> Dict:
        """
        Calculate time to expiry and return adjustment factors.
        
        Returns:
            dict with:
                - hours_to_expiry: float or None
                - days_to_expiry: float or None
                - urgency: 'expired' | 'critical' | 'high' | 'medium' | 'normal'
                - position_size_mult: multiplier for position sizing
                - should_enter: whether new entries are allowed
                - expiry_label: human-readable label for UI
        """
        end_date = self._parse_end_date(market_data)
        
        if not end_date:
            # No end date - assume normal trading
            return {
                'hours_to_expiry': None,
                'days_to_expiry': None,
                'urgency': 'normal',
                'position_size_mult': 1.0,
                'should_enter': True,
                'expiry_label': 'No expiry'
            }
        
        now = datetime.now(timezone.utc)
        time_diff = end_date - now
        hours_to_expiry = time_diff.total_seconds() / 3600
        days_to_expiry = hours_to_expiry / 24
        
        # Determine urgency level and adjustments
        if hours_to_expiry <= 0:
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'expired',
                'position_size_mult': 0.0,
                'should_enter': False,
                'expiry_label': 'Expired'
            }
        
        thresholds = self._get_expiry_thresholds()
        
        if hours_to_expiry <= thresholds['no_entry_hours']:
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'critical',
                'position_size_mult': 0.0,
                'should_enter': False,
                'expiry_label': f'{hours_to_expiry:.1f}h ⚠️'
            }
        elif hours_to_expiry <= thresholds['high_urgency_hours']:
            # Scale down position as expiry approaches
            scale = hours_to_expiry / thresholds['high_urgency_hours']
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'high',
                'position_size_mult': max(0.3, scale),
                'should_enter': True,
                'expiry_label': f'{hours_to_expiry:.0f}h 🔴'
            }
        elif days_to_expiry <= thresholds['medium_urgency_days']:
            scale = days_to_expiry / thresholds['medium_urgency_days']
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'medium',
                'position_size_mult': max(0.5, scale),
                'should_enter': True,
                'expiry_label': f'{days_to_expiry:.0f}d 🟡'
            }
        else:
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'normal',
                'position_size_mult': 1.0,
                'should_enter': True,
                'expiry_label': f'{days_to_expiry:.0f}d 🟢'
            }
    
    def _should_strategy_trade_near_expiry(self, strategy: str, expiry_info: Dict, rl_confidence: float = 0.5) -> Dict:
        """
        Determine if a strategy should trade given time-to-expiry.
        
        Returns:
            dict with:
                - should_trade: bool
                - size_multiplier: float (additional multiplier)
                - reason: str
        """
        hours = expiry_info.get('hours_to_expiry')
        days = expiry_info.get('days_to_expiry')
        urgency = expiry_info.get('urgency', 'normal')
        
        # No end date info - allow trading
        if hours is None:
            return {'should_trade': True, 'size_multiplier': 1.0, 'reason': 'no_expiry_info'}
        
        # Expired or critical - no trading
        if urgency in ['expired', 'critical']:
            return {'should_trade': False, 'size_multiplier': 0.0, 'reason': f'too_close_to_expiry_{hours:.1f}h'}
        
        # Get strategy-specific adjustments from config
        all_adjustments = self._get_expiry_strategy_adjustments()
        adjustments = all_adjustments.get(strategy, {})
        
        # Check strategy-specific disable threshold
        disable_hours = adjustments.get('disable_within_hours', 6)
        if hours <= disable_hours:
            return {'should_trade': False, 'size_multiplier': 0.0, 'reason': f'{strategy}_disabled_within_{disable_hours}h'}
        
        # Delta-neutral specific: disable within configured hours (default 48h)
        if strategy == 'delta_neutral' and hours <= adjustments.get('disable_within_hours', 48):
            return {'should_trade': False, 'size_multiplier': 0.0, 'reason': 'delta_neutral_too_close'}
        
        # Alpha-directional: require high confidence near expiry
        if strategy == 'alpha_directional' and urgency in ['high', 'medium']:
            min_conf = adjustments.get('min_confidence_near_expiry', 0.7)
            if rl_confidence < min_conf:
                return {'should_trade': False, 'size_multiplier': 0.0, 'reason': f'alpha_low_confidence_{rl_confidence:.2f}<{min_conf}'}
        
        # Volatility exploitation: boost in final week
        if strategy == 'volatility_exploitation' and days and days <= adjustments.get('boost_within_days', 7):
            boost = adjustments.get('boost_multiplier', 1.5)
            return {'should_trade': True, 'size_multiplier': boost, 'reason': f'volatility_boosted_{boost}x'}
        
        # Default: use expiry position size multiplier
        return {
            'should_trade': True, 
            'size_multiplier': expiry_info.get('position_size_mult', 1.0),
            'reason': f'normal_{urgency}'
        }
    
    def _get_exit_params(self, strategy: str, asset_class: str) -> Dict:
        """Get exit parameters adjusted for strategy and asset class
        
        Uses configurable exit_params from DB (loaded in _load_user_config),
        falling back to DEFAULT_EXIT_PARAMS if not configured.
        Asset class multipliers are also configurable via DB.
        """
        # Base params from user-configured strategy exit params (or defaults)
        strategy_params = self.exit_params_by_strategy.get(strategy)
        if strategy_params:
            base = strategy_params
        elif strategy in self.DEFAULT_EXIT_PARAMS:
            base = self.DEFAULT_EXIT_PARAMS[strategy]
        else:
            # CRITICAL WARNING: Unknown strategy falling back to arbitrage defaults
            logger.warning(f"[EXIT PARAMS] Unknown strategy '{strategy}' - falling back to 'arbitrage' defaults")
            base = self.DEFAULT_EXIT_PARAMS['arbitrage']
        
        # Adjustments from asset class (use DB-loaded or defaults)
        adj = self.asset_class_exit_multipliers.get(asset_class.lower(), {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0})
        
        # For sports_arbitrage, include force_exit_on_time flag
        result = {
            'take_profit': base['take_profit'] * adj['tp_mult'],
            'stop_loss': base['stop_loss'] * adj['sl_mult'],
            'max_hours': base['max_hours'] * adj['time_mult']
        }
        
        # Pass through special flags for sports
        if base.get('force_exit_on_time'):
            result['force_exit_on_time'] = True
        
        return result
    
    # ============================================
    # DYNAMIC EXIT PARAMETERS (Option 4 Framework)
    # ============================================
    
    # Configuration for dynamic TP/SL
    DYNAMIC_EXIT_CONFIG = {
        'tp_capture_pct': 0.10,      # Capture 10% of max possible gain
        'tp_min': 0.005,             # Minimum 0.5% TP
        'tp_max': 0.50,              # Maximum 50% TP
        'sl_base': -0.10,            # -10% SL at 50% price (center)
        'sl_extreme': -0.30,         # -30% SL at 0% or 100% price (edges)
        'extreme_threshold': 0.10,   # 0-10% and 90-100% = extreme
        'moderate_threshold': 0.25,  # 10-25% and 75-90% = moderate
    }
    
    def _calculate_max_gain(self, side: str, entry_price: float) -> float:
        """
        Calculate the theoretical maximum gain percentage for a position.
        
        YES position: Profits when price goes UP toward $1.00
        NO position:  Profits when YES price goes DOWN toward $0.00
        """
        if side == 'YES':
            # Max value = $1.00 per share
            # Max return = (1.00 - entry_price) / entry_price
            if entry_price > 0 and entry_price < 1:
                return (1.0 - entry_price) / entry_price
            return 0
        else:  # NO
            # NO price = 1 - YES price
            # Max NO price = $1.00 (when YES = $0)
            # Max return = entry_yes / (1 - entry_yes)
            no_entry = 1 - entry_price
            if no_entry > 0 and no_entry < 1:
                return entry_price / no_entry
            return 0
    
    def _calculate_extremeness(self, entry_price: float) -> float:
        """
        How far from 50% is this price? (0 = at 50%, 1 = at 0% or 100%)
        
        This determines risk level:
        - At 50%: Both outcomes equally likely, moderate risk
        - At extremes: One outcome heavily favored, less room for error
        """
        return abs(entry_price - 0.5) / 0.5
    
    def _get_dynamic_exit_params(self, side: str, entry_price: float, days_to_expiry: float = None) -> Dict:
        """
        Calculate dynamic TP/SL based on entry price, position side, AND time to expiry.
        
        Time-aware logic:
        - Near expiry (≤3 days): Hold to resolution, no TP/SL
        - Short term (4-7 days): Hold with SL protection only
        - Medium term (8-30 days): Active TP/SL management
        - Long term (>30 days): Quick trade with tight parameters
        
        Key insight: The same price at different expiry times has very different risk profiles.
        """
        cfg = self.dynamic_exit_config
        
        # Step 1: Calculate max possible gain
        max_gain = self._calculate_max_gain(side, entry_price)
        
        # Step 2: Calculate extremeness (0 at 50%, 1 at 0% or 100%)
        extremeness = self._calculate_extremeness(entry_price)
        
        # Step 3: Determine zone based on extremeness
        if extremeness > 0.80:  # 0-10% or 90-100%
            price_zone = 'extreme'
        elif extremeness > 0.50:  # 10-25% or 75-90%
            price_zone = 'moderate'
        else:  # 25-75%
            price_zone = 'mid_range'
        
        # Step 4: TIME-AWARE EXIT STRATEGY
        # Adjust TP/SL based on days to expiry
        if days_to_expiry is not None and days_to_expiry <= 3:
            # HOLD TO RESOLUTION: Near expiry, just wait for market resolution
            exit_mode = 'resolution'
            dynamic_tp = None  # No TP - hold to resolution
            dynamic_sl = None  # No SL - thesis is almost confirmed
            max_hours = max(1, days_to_expiry * 24 - 1)  # Exit 1 hour before expiry
            
        elif days_to_expiry is not None and days_to_expiry <= 7:
            # HOLD WITH PROTECTION: Near expiry but use SL as safety net
            exit_mode = 'hold_protected'
            dynamic_tp = None  # No TP - let it ride
            dynamic_sl = -0.15  # Tighter SL near expiry
            max_hours = max(1, days_to_expiry * 24 - 2)
            
        elif days_to_expiry is not None and days_to_expiry <= 30:
            # ACTIVE MANAGEMENT: Use TP/SL but capture more of max gain
            exit_mode = 'active'
            # For NO at extreme low YES: TP = 50% of max gain (more aggressive capture)
            # For others: standard 10% of max gain
            if side == 'NO' and entry_price < 0.05:
                raw_tp = max_gain * 0.50  # Capture 50% for NO at extreme
            else:
                raw_tp = max_gain * cfg['tp_capture_pct']
            dynamic_tp = max(min(raw_tp, cfg['tp_max']), cfg['tp_min'])
            dynamic_sl = cfg['sl_base'] + (extremeness * (cfg['sl_extreme'] - cfg['sl_base']))
            max_hours = min(days_to_expiry * 12, 168)  # Max 1 week hold
            
        elif days_to_expiry is not None and days_to_expiry > 30:
            # QUICK TRADE: Far from expiry, use tight params and exit fast
            exit_mode = 'quick_trade'
            # Capture only 30% of max gain - take profits quickly
            raw_tp = max_gain * 0.30
            dynamic_tp = max(min(raw_tp, cfg['tp_max']), cfg['tp_min'])
            # Tighter SL for long-dated positions (more can go wrong)
            dynamic_sl = max(cfg['sl_base'] * 0.8, -0.08)  # -8% SL
            max_hours = 24  # Exit within 24 hours regardless
            
        else:
            # UNKNOWN EXPIRY: Use standard dynamic calculation
            exit_mode = 'standard'
            raw_tp = max_gain * cfg['tp_capture_pct']
            dynamic_tp = max(min(raw_tp, cfg['tp_max']), cfg['tp_min'])
            dynamic_sl = cfg['sl_base'] + (extremeness * (cfg['sl_extreme'] - cfg['sl_base']))
            # Default max hours based on price zone
            if price_zone == 'extreme':
                max_hours = 24
            elif price_zone == 'moderate':
                max_hours = 12
            else:
                max_hours = 4
        
        return {
            'take_profit': dynamic_tp,
            'stop_loss': dynamic_sl,
            'max_hours': max_hours,
            'zone': price_zone,
            'exit_mode': exit_mode,
            'max_gain_possible': max_gain,
            'extremeness': extremeness,
            'days_to_expiry': days_to_expiry,
            'raw_tp_before_cap': raw_tp if 'raw_tp' in dir() else None,
            'is_dynamic': True
        }
    
    def _should_enter_no_at_extreme(self, yes_price: float, days_to_expiry: float) -> Dict:
        """
        Time-aware entry filter for NO positions at extreme low YES prices.
        
        Returns decision dict with:
        - should_enter: bool
        - reason: str
        - size_multiplier: float (0-1.5)
        """
        max_gain = yes_price / (1 - yes_price) if yes_price < 1 else 0
        cfg = self.time_entry_config
        
        # Near expiry (≤7 days): Almost always enter
        if days_to_expiry is not None and days_to_expiry <= 7:
            if max_gain >= cfg['min_gain_near_expiry']:
                return {
                    'should_enter': True,
                    'reason': f'near_expiry_{days_to_expiry:.0f}d_gain_{max_gain:.2%}',
                    'size_multiplier': 1.5 if days_to_expiry <= 3 else 1.2
                }
        
        # Medium term (8-30 days): Enter if gain is meaningful
        if days_to_expiry is not None and 7 < days_to_expiry <= 30:
            if max_gain >= cfg['min_gain_medium_term']:
                return {
                    'should_enter': True,
                    'reason': f'medium_term_{days_to_expiry:.0f}d_gain_{max_gain:.2%}',
                    'size_multiplier': 1.0
                }
            else:
                return {
                    'should_enter': False,
                    'reason': f'medium_term_low_gain_{max_gain:.2%}<{cfg["min_gain_medium_term"]:.2%}',
                    'size_multiplier': 0
                }
        
        # Longer term (31-90 days): Need higher gain to justify
        if days_to_expiry is not None and 30 < days_to_expiry <= 90:
            if max_gain >= cfg['min_gain_longer_term']:
                return {
                    'should_enter': True,
                    'reason': f'longer_term_{days_to_expiry:.0f}d_gain_{max_gain:.2%}',
                    'size_multiplier': 0.7
                }
            else:
                return {
                    'should_enter': False,
                    'reason': f'longer_term_low_gain_{max_gain:.2%}<{cfg["min_gain_longer_term"]:.2%}',
                    'size_multiplier': 0
                }
        
        # Far expiry (>90 days): Very selective
        if days_to_expiry is not None and days_to_expiry > 90:
            if cfg['skip_no_extreme_far_expiry'] and yes_price < 0.05:
                return {
                    'should_enter': False,
                    'reason': f'far_expiry_{days_to_expiry:.0f}d_no_extreme_skip',
                    'size_multiplier': 0
                }
            if max_gain >= cfg['min_gain_far_expiry']:
                return {
                    'should_enter': True,
                    'reason': f'far_expiry_{days_to_expiry:.0f}d_high_gain_{max_gain:.2%}',
                    'size_multiplier': 0.5
                }
            else:
                return {
                    'should_enter': False,
                    'reason': f'far_expiry_low_gain_{max_gain:.2%}<{cfg["min_gain_far_expiry"]:.2%}',
                    'size_multiplier': 0
                }
        
        # Unknown expiry: Use default behavior
        return {
            'should_enter': True,
            'reason': 'unknown_expiry_default',
            'size_multiplier': 1.0
        }
    
    def _get_simple_exit_params(self, strategy: str, asset_class: str) -> Dict:
        """
        Get simple/configurable exit parameters (non-dynamic mode).
        Uses exit_params_by_strategy from DB or defaults.
        """
        # Base params from user-configured strategy exit params (or defaults)
        strategy_params = self.exit_params_by_strategy.get(strategy)
        if strategy_params:
            base = strategy_params
        elif strategy in self.DEFAULT_EXIT_PARAMS:
            base = self.DEFAULT_EXIT_PARAMS[strategy]
        else:
            # CRITICAL WARNING: Unknown strategy falling back to arbitrage defaults
            logger.warning(f"[EXIT PARAMS] Unknown strategy '{strategy}' - falling back to 'arbitrage' defaults")
            base = self.DEFAULT_EXIT_PARAMS['arbitrage']
        
        adj = self.asset_class_exit_multipliers.get(
            asset_class.lower(), 
            {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0}
        )
        
        result = {
            'take_profit': base['take_profit'] * adj['tp_mult'],
            'stop_loss': base['stop_loss'] * adj['sl_mult'],
            'max_hours': base['max_hours'] * adj['time_mult'],
            'zone': 'simple',
            'exit_mode': 'simple',
            'max_gain_possible': None,
            'extremeness': None,
            'days_to_expiry': None,
            'is_dynamic': False
        }
        
        # Pass through special flags for sports
        if base.get('force_exit_on_time'):
            result['force_exit_on_time'] = True
        
        return result
    
    async def _evaluate_exit(self, market_id: str, market_data: Dict):
        """
        Evaluate existing paper position for exit using the Alpha-State Exit Engine.
        
        Task 24: Hierarchical exit logic respecting:
        1. State (ACTIVE vs FREE_RIDE)
        2. Strategy (Mechanical vs Alpha)
        3. Asset Class (wide/tight stops based on asset type)
        4. Zone (Whale vs Core)
        
        Falls back to legacy logic if self.use_exit_engine is False.
        """
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            # Get current price - REJECT EXIT if no valid price
            current_price = market_data.get('yes_price')
            if current_price is None or current_price == 0:
                logger.warning(f"[EXIT-SKIP] No valid price for {market_id[:16]} - cannot exit safely")
                return
            
            current_price = float(current_price)
            
            # Use yes_entry_price for internal calculations (stores the YES price at entry)
            yes_entry_price = position.get('yes_entry_price', position['entry_price'])
            side = position['side']
            size = position.get('size', 0)
            strategy = position.get('strategy', 'arbitrage')
            asset_class = position.get('asset_class', 'unknown')
            trade_status = position.get('trade_status', 'ACTIVE')  # ACTIVE or FREE_RIDE
            peak_price = position.get('peak_price', yes_entry_price)  # Track peak for trailing stops
            
            # ==========================================================================
            # FETCH FRESH ORDERBOOK FOR EXIT EVALUATION (not stale entry data!)
            # ==========================================================================
            bids = []
            asks = []
            current_spread_pct = 0.05  # Default 5% spread estimate
            try:
                token_ids = market_data.get('token_ids', [])
                if token_ids:
                    from data.polymarket_api import PolymarketAPI
                    async with PolymarketAPI() as api:
                        fresh_orderbook = await api.get_order_book(token_ids[0])
                        bids = fresh_orderbook.get('bids', [])
                        asks = fresh_orderbook.get('asks', [])
                        if bids and asks:
                            best_bid = float(bids[0]['price'])
                            best_ask = float(asks[0]['price'])
                            mid_price = (best_bid + best_ask) / 2
                            current_spread_pct = (best_ask - best_bid) / mid_price if mid_price > 0 else 0.05
                            logger.debug(f"[EXIT-OB] Fresh orderbook: bid={best_bid}, ask={best_ask}, spread={current_spread_pct:.2%}")
            except Exception as e:
                logger.debug(f"[EXIT-OB] Could not fetch fresh orderbook: {e}")
            
            # Fallback to cached orderbook if fresh fetch failed
            if not bids or not asks:
                order_book = market_data.get('order_book', {})
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
            
            if bids and asks:
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                spread = best_ask - best_bid
                mid_price = (best_bid + best_ask) / 2
                current_spread_pct = spread / mid_price if mid_price > 0 else 0.05
                
                # SANITY CHECK: Reject if spread is too wide (>15%)
                if spread < 0 or spread > 0.15:
                    logger.warning(f"[EXIT-EVAL] Suspicious orderbook spread={spread:.2%}, using midpoint instead")
                    exit_yes_price = current_price
                elif side == 'YES':
                    exit_yes_price = best_bid  # Selling YES = hitting bid
                else:
                    exit_yes_price = best_ask  # Selling NO = buying YES = hitting ask
            else:
                spread_estimate = 0.02
                if side == 'YES':
                    exit_yes_price = current_price - (spread_estimate / 2)
                else:
                    exit_yes_price = current_price + (spread_estimate / 2)
                exit_yes_price = max(0.001, min(0.999, exit_yes_price))
            
            # UPDATE position's current_price for UI display
            if side == 'YES':
                position['current_price'] = exit_yes_price
            else:
                position['current_price'] = 1 - exit_yes_price
            
            # Get time to expiry
            expiry_info = self._calculate_time_to_expiry(market_data)
            hours_to_expiry = expiry_info.get('hours_to_expiry')
            
            # Calculate duration
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            duration_hours = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
            
            # Update peak price for trailing stops
            if exit_yes_price > peak_price:
                peak_price = exit_yes_price
                position['peak_price'] = peak_price
            
            # ============================================
            # USE EXIT ENGINE (Task 24)
            # ============================================
            if self.use_exit_engine:
                decision = self.exit_engine.check_exit(
                    strategy=strategy,
                    asset_class=asset_class,
                    entry_price=yes_entry_price,
                    current_price=exit_yes_price,
                    position_size_usd=size,
                    duration_hours=duration_hours,
                    hours_to_expiry=hours_to_expiry,
                    current_spread_pct=current_spread_pct,
                    trade_status=trade_status,
                    peak_price=peak_price,
                    side=side,  # CRITICAL: Pass side for correct P&L calculation
                )
                
                # Store exit engine decision for UI display
                position['exit_engine_decision'] = {
                    'action': decision.action.value,
                    'reason': decision.reason.value,
                    'zone': decision.zone,
                    'state': decision.state,
                    'pnl_pct': decision.pnl_pct,
                    'tp_threshold': decision.take_profit_threshold,
                    'sl_threshold': decision.stop_loss_threshold,
                    'max_hours': decision.max_hours,
                    'asset_class': decision.asset_class,
                }
                
                # Also store in legacy format for UI compatibility
                position['dynamic_exit_params'] = {
                    'tp': decision.take_profit_threshold,
                    'sl': -abs(decision.stop_loss_threshold) if decision.stop_loss_threshold else None,
                    'max_hours': decision.max_hours,
                    'zone': decision.zone,
                    'exit_mode': f"engine_{decision.reason.value}",
                    'is_dynamic': True,
                }
                
                # Calculate P&L for position update
                if side == 'YES':
                    if yes_entry_price > 0:
                        shares = size / yes_entry_price
                        current_value = shares * exit_yes_price
                        unrealized_pnl = current_value - size
                        pnl_pct = unrealized_pnl / size if size > 0 else 0
                    else:
                        pnl_pct = 0
                        unrealized_pnl = 0
                else:
                    no_entry_price = 1 - yes_entry_price
                    no_exit_price = 1 - exit_yes_price
                    if no_entry_price > 0:
                        shares = size / no_entry_price
                        current_value = shares * no_exit_price
                        unrealized_pnl = current_value - size
                        pnl_pct = unrealized_pnl / size if size > 0 else 0
                    else:
                        pnl_pct = 0
                        unrealized_pnl = 0
                
                position['unrealized_pnl'] = unrealized_pnl
                position['unrealized_pnl_pct'] = pnl_pct
                
                # ============================================
                # EXECUTE EXIT DECISION
                # ============================================
                if decision.action == ExitAction.CLOSE_ALL:
                    exit_reason = f"{decision.reason.value}_{decision.zone}"
                    logger.info(f"📤 EXIT [{decision.zone}]: {market_id[:16]} | {decision.reason.value} | P&L: {pnl_pct:.2%}")
                    await self._execute_paper_exit(market_id, market_data, exit_reason)
                    
                elif decision.action == ExitAction.FREE_ROLL:
                    # Partial sell - sell principal, keep profits running
                    sell_pct = decision.sell_pct
                    sell_amount = size * sell_pct
                    
                    logger.info(f"🎰 FREE_ROLL [{decision.zone}]: {market_id[:16]} | Selling {sell_pct:.0%} (${sell_amount:.2f}) | P&L: {pnl_pct:.2%}")
                    
                    # Execute partial exit
                    await self._execute_paper_partial_exit(market_id, market_data, sell_pct, "free_roll")
                    
                    # Update position status to FREE_RIDE
                    if market_id in self.paper_positions:
                        self.paper_positions[market_id]['trade_status'] = 'FREE_RIDE'
                        self.paper_positions[market_id]['free_roll_time'] = datetime.now(timezone.utc).isoformat()
                        self.paper_positions[market_id]['original_size'] = size
                        logger.info(f"🏠 Position {market_id[:16]} is now HOUSE MONEY (FREE_RIDE)")
                
                # ExitAction.HOLD - do nothing, just log occasionally
                elif decision.action == ExitAction.HOLD:
                    # Log every ~10th check to avoid spam
                    if hasattr(self, '_exit_log_counter'):
                        self._exit_log_counter += 1
                    else:
                        self._exit_log_counter = 0
                    
                    if self._exit_log_counter % 10 == 0:
                        logger.debug(f"⏸️ HOLD [{decision.zone}]: {market_id[:16]} | {decision.reason.value} | P&L: {pnl_pct:.2%}")
                
                return  # Exit engine handled, skip legacy logic
            
            # ============================================
            # LEGACY EXIT LOGIC (fallback if use_exit_engine=False)
            # ============================================
            await self._legacy_evaluate_exit(market_id, market_data, position, exit_yes_price, 
                                             yes_entry_price, side, size, strategy, asset_class,
                                             hours_to_expiry, duration_hours)
                
        except Exception as e:
            logger.error(f"Error evaluating exit: {e}", exc_info=True)
    
    async def _execute_paper_partial_exit(self, market_id: str, market_data: Dict, 
                                          sell_pct: float, reason: str):
        """
        Execute a partial exit (for FREE_ROLL).
        Sells a percentage of the position while keeping the rest running.
        """
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            original_size = position.get('size', 0)
            sell_size = original_size * sell_pct
            remaining_size = original_size - sell_size
            
            if remaining_size < 0.01:  # Dust check
                # Convert to full exit
                await self._execute_paper_exit(market_id, market_data, f"{reason}_dust_convert")
                return
            
            # Calculate realized P&L for the sold portion
            yes_entry_price = position.get('yes_entry_price', position['entry_price'])
            current_price = position.get('current_price', market_data.get('yes_price', yes_entry_price))
            side = position['side']
            
            if side == 'YES':
                if yes_entry_price > 0:
                    shares_sold = sell_size / yes_entry_price
                    exit_value = shares_sold * current_price
                    realized_pnl = exit_value - sell_size
                    pnl_pct = realized_pnl / sell_size if sell_size > 0 else 0
                else:
                    realized_pnl = 0
                    pnl_pct = 0
            else:
                no_entry_price = 1 - yes_entry_price
                no_exit_price = 1 - current_price
                if no_entry_price > 0:
                    shares_sold = sell_size / no_entry_price
                    exit_value = shares_sold * no_exit_price
                    realized_pnl = exit_value - sell_size
                    pnl_pct = realized_pnl / sell_size if sell_size > 0 else 0
                else:
                    realized_pnl = 0
                    pnl_pct = 0
            
            # Update position
            position['size'] = remaining_size
            position['partial_exits'] = position.get('partial_exits', [])
            position['partial_exits'].append({
                'time': datetime.now(timezone.utc).isoformat(),
                'sell_pct': sell_pct,
                'sell_size': sell_size,
                'realized_pnl': realized_pnl,
                'reason': reason,
            })
            
            # Track realized P&L
            self.paper_realized_pnl += realized_pnl
            self.paper_trades_today += 1
            
            # Record partial trade to database
            # Determine strategy lane for partial exit
            strategy_lane = RISK.get_strategy_path(position.get('strategy', 'unknown'))
            
            trade_log = {
                'market_id': market_id,
                'question': market_data.get('question', 'Unknown'),
                'side': side,
                'size': sell_size,
                'entry_price': position['entry_price'],
                'exit_price': current_price,
                'pnl': realized_pnl,
                'pnl_pct': pnl_pct,
                'strategy': position.get('strategy', 'unknown'),
                'strategy_lane': strategy_lane,  # Three-Speed: HFT, ALPHA, or GAMMA
                'asset_class': position.get('asset_class', 'unknown'),
                'exit_reason': f"partial_{reason}",
                'entry_time': position.get('entry_time'),
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'is_partial': True,
                'remaining_size': remaining_size,
                'original_size': original_size,
            }
            await self.db.paper_trades.insert_one(trade_log)
            
            logger.info(f"📊 PARTIAL EXIT: {market_id[:16]} | Sold {sell_pct:.0%} (${sell_size:.2f}) | P&L: ${realized_pnl:.2f} ({pnl_pct:.1%}) | Remaining: ${remaining_size:.2f}")
            
        except Exception as e:
            logger.error(f"Error in partial exit: {e}", exc_info=True)
    
    async def _legacy_evaluate_exit(self, market_id: str, market_data: Dict, position: Dict,
                                    exit_yes_price: float, yes_entry_price: float, side: str,
                                    size: float, strategy: str, asset_class: str,
                                    hours_to_expiry: Optional[float], duration_hours: float):
        """
        Legacy exit evaluation logic (pre-Task 24).
        Kept for fallback/comparison purposes.
        """
        days_to_expiry = hours_to_expiry / 24 if hours_to_expiry else None
        
        # Get exit parameters (dynamic or simple mode)
        if self.use_dynamic_exit:
            exit_params = self._get_dynamic_exit_params(side, yes_entry_price, days_to_expiry)
        else:
            exit_params = self._get_simple_exit_params(strategy, asset_class)
        
        take_profit_threshold = exit_params['take_profit']
        stop_loss_threshold = exit_params['stop_loss']
        max_hours = exit_params['max_hours']
        exit_mode = exit_params.get('exit_mode', 'standard')
        
        # Store exit params in position for UI display
        position['dynamic_exit_params'] = {
            'tp': take_profit_threshold,
            'sl': stop_loss_threshold,
            'max_hours': max_hours,
            'zone': exit_params.get('zone', 'unknown'),
            'exit_mode': exit_mode,
            'is_dynamic': self.use_dynamic_exit
        }
        
        # Calculate P&L
        if side == 'YES':
            if yes_entry_price > 0:
                shares = size / yes_entry_price
                current_value = shares * exit_yes_price
                unrealized_pnl = current_value - size
                pnl_pct = unrealized_pnl / size if size > 0 else 0
            else:
                pnl_pct = 0
                unrealized_pnl = 0
        else:
            no_entry_price = 1 - yes_entry_price
            no_exit_price = 1 - exit_yes_price
            if no_entry_price > 0:
                shares = size / no_entry_price
                current_value = shares * no_exit_price
                unrealized_pnl = current_value - size
                pnl_pct = unrealized_pnl / size if size > 0 else 0
            else:
                pnl_pct = 0
                unrealized_pnl = 0
        
        position['unrealized_pnl'] = unrealized_pnl
        position['unrealized_pnl_pct'] = pnl_pct
        
        # Get RL recommendation
        signals = await self._get_signals(market_data)
        rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
        
        # Exit conditions
        should_exit = False
        exit_reason = None
        
        # 1. Auto-exit for approaching expiry
        if hours_to_expiry is not None and hours_to_expiry <= 1.0:
            should_exit = True
            exit_reason = f"expiry_safety_{hours_to_expiry:.1f}h"
        
        # 2. Take profit
        if not should_exit and take_profit_threshold is not None and pnl_pct >= take_profit_threshold:
            should_exit = True
            exit_reason = f"tp_{pnl_pct:.1%}_{exit_mode}"
        
        # 3. Stop loss
        if not should_exit and stop_loss_threshold is not None and pnl_pct <= stop_loss_threshold:
            should_exit = True
            exit_reason = f"sl_{pnl_pct:.1%}_{exit_mode}"
        
        # 4. RL signal reversal
        if not should_exit and exit_mode != 'resolution' and rl_confidence > 0.7:
            if side == 'YES' and 'SELL' in rl_action:
                should_exit = True
                exit_reason = f"rl_reversal_{rl_action}_{rl_confidence:.0%}"
            elif side == 'NO' and 'BUY' in rl_action:
                should_exit = True
                exit_reason = f"rl_reversal_{rl_action}_{rl_confidence:.0%}"
        
        # 5. Time-based exit
        if not should_exit and max_hours is not None and duration_hours > max_hours:
            should_exit = True
            exit_reason = f"time_{duration_hours:.1f}h>{max_hours:.0f}h_{exit_mode}"
        
        if should_exit:
            logger.info(f"📤 LEGACY EXIT: {market_id[:16]} | {exit_reason} | P&L: {pnl_pct:.2%}")
            await self._execute_paper_exit(market_id, market_data, exit_reason)
    
    async def _execute_paper_entry(self, market_id: str, market_data: Dict, side: str,
                                    size: float, strategy: str, signals: Dict,
                                    rl_action: str, rl_confidence: float,
                                    sizing_breakdown: Dict = None):
        """Execute a paper trade entry with adaptive sizing info"""
        try:
            # Check if we already have a position (shouldn't happen but let's be safe)
            if market_id in self.paper_positions:
                logger.warning(f"[ENTRY-SKIP] Already have position in {market_id[:16]}")
                return
            
            # ============================================
            # STRICT PRICE VALIDATION - NO FALLBACKS
            # ============================================
            # Get current price - REJECT if not available
            current_price = market_data.get('yes_price')
            if current_price is None or current_price == 0:
                logger.warning(f"[ENTRY-REJECT] No valid yes_price for {market_id[:16]} - skipping trade")
                return
            
            current_price = float(current_price)
            
            # Check for suspicious default prices (likely no real data)
            if abs(current_price - 0.5) < 0.02:
                # Price is suspiciously close to 0.5 - check if we have real orderbook
                order_book = market_data.get('order_book', {})
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
                if not bids or not asks:
                    logger.warning(f"[ENTRY-REJECT] Price {current_price:.4f} near 0.5 and no orderbook for {market_id[:16]} - likely default price")
                    return
            
            logger.info(f"[ENTRY-EXEC] Opening {strategy} {side} ${size:.2f} in {market_id[:16]}")
            
            asset_class = market_data.get('asset_class', market_data.get('category', 'unknown'))
            
            # Extract edge from sizing breakdown for maker execution
            edge = (sizing_breakdown or {}).get('edge', 0.02)
            
            # ============================================
            # EXTRACT THEORETICAL PRICE (ALPHA SIGNAL)
            # ============================================
            # CRITICAL: The theoretical_price is the Bayesian posterior probability
            # from the slow path (signal fusion). The maker executor MUST use this
            # as the center for quote generation, NOT the market mid-price.
            theoretical_price = None
            if sizing_breakdown:
                # Primary source: probability_diagnostics from Bayesian fusion
                prob_diag = sizing_breakdown.get('probability_diagnostics', {})
                if prob_diag:
                    theoretical_price = prob_diag.get('final_probability')
                
                # Fallback: model_probability (may be transformed for NO bets)
                if theoretical_price is None:
                    model_prob = sizing_breakdown.get('model_probability')
                    sizing_side = sizing_breakdown.get('_sizing_side', side)
                    if model_prob is not None:
                        # If we bet NO, model_probability was transformed (1-raw)
                        # Convert back to YES probability for quoting
                        if sizing_side == 'NO':
                            theoretical_price = 1 - model_prob
                        else:
                            theoretical_price = model_prob
            
            if theoretical_price is not None:
                logger.info(f"[ALPHA] theoretical_price={theoretical_price:.4f}, market={current_price:.4f}, diff={theoretical_price - current_price:+.4f}")
            else:
                logger.warning(f"[ALPHA] No theoretical_price available - maker will use market mid")
            
            # ============================================
            # MAKER-FIRST EXECUTION STRATEGY
            # ============================================
            execution_result = None
            actual_entry_price = current_price
            
            if self.use_maker_execution:
                # ==========================================================================
                # FETCH CORRECT ORDERBOOK FOR TRADING SIDE
                # ==========================================================================
                # Polymarket has separate orderbooks for YES and NO tokens
                # token_ids[0] = YES token, token_ids[1] = NO token
                token_ids = market_data.get('token_ids', market_data.get('clobTokenIds', []))
                
                # Determine which token we're trading
                # YES side -> YES token (index 0), NO side -> NO token (index 1)
                token_index = 0 if side == 'YES' else 1
                
                # Check if we need to fetch the correct orderbook
                current_ob_token = market_data.get('order_book_token')
                need_fresh_orderbook = (
                    (side == 'YES' and current_ob_token != 'YES') or
                    (side == 'NO' and current_ob_token != 'NO') or
                    current_ob_token is None
                )
                
                if need_fresh_orderbook and token_ids and len(token_ids) > token_index:
                    try:
                        from data.polymarket_api import PolymarketAPI
                        async with PolymarketAPI() as api:
                            token_id = token_ids[token_index]
                            order_book_data = await api.get_order_book(token_id)
                            if order_book_data.get('bids') and order_book_data.get('asks'):
                                market_data['order_book'] = order_book_data
                                market_data['order_book_token'] = side
                                logger.debug(f"[ORDERBOOK] Fetched {side} token orderbook for execution: {market_id[:16]}")
                    except Exception as e:
                        logger.warning(f"[ORDERBOOK] Failed to fetch {side} orderbook: {e}")
                
                # Get orderbook - REJECT if not available
                order_book = market_data.get('order_book', {})
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
                
                # STRICT: Require real orderbook data - NO FALLBACKS
                if not bids or not asks:
                    logger.warning(f"[ENTRY-REJECT] No orderbook data for {market_id[:16]} - cannot execute maker order")
                    return
                
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                spread = best_ask - best_bid
                
                # DEBUG: Log orderbook details when spread is suspicious
                if spread > 0.5:
                    ob_token = market_data.get('order_book_token', 'unknown')
                    logger.warning(f"[ENTRY-DEBUG] Suspicious {ob_token} orderbook for {market_id[:16]}: "
                                  f"bid={best_bid:.4f}, ask={best_ask:.4f}, spread={spread:.4f} "
                                  f"| bids[0]={bids[0]} | asks[0]={asks[0]}")
                
                # Get max spread from config (default to 0.99 for wide tolerance)
                max_spread_config = getattr(self, 'max_spread', 0.99)
                
                # Validate spread is within configured tolerance
                if spread <= 0 or spread > max_spread_config:
                    logger.warning(f"[ENTRY-REJECT] Spread {spread:.4f} exceeds max {max_spread_config:.4f} for {market_id[:16]}")
                    return
                
                should_trade, reason = self.maker_executor.should_trade_given_spread(edge, spread)
                
                if not should_trade:
                    logger.info(f"[MAKER] Skipping trade due to spread: {reason}")
                    return
                
                # Execute with maker-first strategy
                # CRITICAL: Pass theoretical_price so maker quotes are centered on our Alpha
                execution_result = await self.maker_executor.execute_order(
                    side=side,
                    size=size,
                    market_data=market_data,
                    edge=edge,
                    theoretical_price=theoretical_price  # Alpha signal from Bayesian posterior
                )
                
                # Check if order was filled
                if execution_result.fill_status.value != 'filled':
                    logger.info(f"[MAKER] Order not filled: {execution_result.reason}")
                    return
                
                # Use the actual fill price from maker execution
                actual_entry_price = execution_result.fill_price
                
                # ==========================================================================
                # SANITY CHECK: Validate entry price is reasonable
                # ==========================================================================
                # For NO positions, if YES price is very low (<5%), we're buying NO very expensive (>95%)
                # This is usually a bad trade unless we have very high confidence
                if side == 'NO' and actual_entry_price < 0.05:
                    no_price = 1 - actual_entry_price
                    logger.warning(f"[ENTRY-WARN] Buying NO at ${no_price:.4f} (YES=${actual_entry_price:.4f}) - expensive NO entry!")
                elif side == 'YES' and actual_entry_price > 0.95:
                    logger.warning(f"[ENTRY-WARN] Buying YES at ${actual_entry_price:.4f} - expensive YES entry!")
                
                # Validate fill price is not at extreme (suspicious data)
                if actual_entry_price < 0.01 or actual_entry_price > 0.99:
                    logger.warning(f"[ENTRY-SUSPICIOUS] Fill price {actual_entry_price:.4f} is at extreme - may be bad data")
                
                logger.info(f"[MAKER] Executed as {execution_result.order_type.value} @ {actual_entry_price:.4f}")
            
            # Extract expiry info from sizing breakdown
            expiry_info = sizing_breakdown.get('expiry_info', {}) if sizing_breakdown else {}
            
            # Calculate dynamic exit params for this entry
            dynamic_exit = self._get_dynamic_exit_params(side, actual_entry_price)
            
            # Calculate display entry price (actual price for the side being traded)
            if side == 'YES':
                display_entry_price = actual_entry_price
            else:
                # Use actual NO price from API if available, else compute
                api_no_price = market_data.get('no_price')
                display_entry_price = float(api_no_price) if api_no_price else (1 - actual_entry_price)
            
            position = {
                "position_id": str(uuid.uuid4()),
                "market_id": market_id,
                "market_question": market_data.get('question', '')[:100],
                "asset_class": asset_class,
                "side": side,
                "size": size,
                "entry_price": display_entry_price,  # Display price for the side traded
                "yes_entry_price": actual_entry_price,  # Keep YES price for internal calculations
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "strategy": strategy,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "signals": signals,
                "sizing_breakdown": sizing_breakdown or {},  # Store for learning
                # Maker execution info
                "execution_info": {
                    "order_type": execution_result.order_type.value if execution_result else "market",
                    "slippage": execution_result.slippage if execution_result else 0,
                    "spread_captured": execution_result.spread_captured if execution_result else 0,
                    "wait_time_ms": execution_result.wait_time_ms if execution_result else 0,
                    "theoretical_price": theoretical_price,  # Alpha signal used for quoting
                    "market_price": current_price,  # Market price at entry
                    "alpha_diff": round(theoretical_price - current_price, 6) if theoretical_price else None,
                } if execution_result else {},
                # Risk tracking for reward shaping
                "entry_volatility": signals.get('volatility', 0.05),
                "max_drawdown_pct": 0.0,  # Will be updated during position monitoring
                "min_price_seen": actual_entry_price,  # Track worst price for drawdown (YES price)
                "max_price_seen": actual_entry_price,  # Track best price (YES price)
                # Store expiry info for UI display
                "expiry_info": {
                    "hours_to_expiry": expiry_info.get('hours_to_expiry'),
                    "days_to_expiry": expiry_info.get('days_to_expiry'),
                    "urgency": expiry_info.get('urgency', 'normal'),
                    "expiry_label": expiry_info.get('expiry_label', 'No expiry'),
                    "end_date": market_data.get('end_date')
                },
                # Dynamic exit params (Option 4 Framework)
                "dynamic_exit_params": {
                    "tp": dynamic_exit['take_profit'],
                    "sl": dynamic_exit['stop_loss'],
                    "max_hours": dynamic_exit['max_hours'],
                    "zone": dynamic_exit['zone'],
                    "max_gain": dynamic_exit['max_gain_possible'],
                    "extremeness": dynamic_exit['extremeness']
                }
            }
            
            self.paper_positions[market_id] = position
            
            # PERSIST: Save position to database for survival across restarts
            await self._save_position_to_db(market_id, position)
            
            # Only deduct from capital if we have enough
            if self.current_capital >= size:
                self.current_capital -= size
            else:
                # Limit the actual size to available capital
                actual_size = max(0, self.current_capital)
                self.current_capital = 0
                position['size'] = actual_size  # Update position with actual size
            
            self.total_trades += 1
            
            # Track strategy stats
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['trades'] += 1
            
            # Track asset class stats (initialize with full metrics)
            if asset_class not in self.asset_class_stats:
                self.asset_class_stats[asset_class] = {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
            self.asset_class_stats[asset_class]['trades'] += 1
            
            # Log trade with sentiment breakdown
            # Determine strategy lane (HFT/ALPHA/GAMMA) from strategy name
            strategy_lane = RISK.get_strategy_path(strategy)
            
            trade_log = {
                "trade_id": position['position_id'],
                "session_id": self.session_id,
                "type": "entry",
                "market_id": market_id,
                "market_question": position.get('market_question', ''),
                "side": side,
                "size": size,
                "price": display_entry_price,  # Display price for the side traded
                "entry_price": display_entry_price,  # Display price for the side traded
                "yes_entry_price": actual_entry_price,  # Keep YES price for reference
                "strategy": strategy,
                "strategy_lane": strategy_lane,  # Three-Speed: HFT, ALPHA, or GAMMA
                "asset_class": asset_class,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                # Expiry info for UI
                "expiry_info": position.get('expiry_info', {}),
                # Sizing breakdown for analysis and learning
                "sizing_breakdown": sizing_breakdown or {},
                # Execution info for maker/taker analysis
                "execution_info": position.get('execution_info', {}),
                # Sentiment breakdown for UI
                "sentiment": {
                    "final": signals.get('sentiment', 0.5),
                    "strength": signals.get('sentiment_strength', 0),
                    "layers": signals.get('sentiment_layers', {}),
                    "weights": signals.get('sentiment_weights', {}),
                    "components": signals.get('sentiment_components', {}),
                    "enhanced_data": signals.get('enhanced_data', {})
                },
                "volatility": signals.get('volatility', 0),
                "sharp_alignment": signals.get('sharp_alignment', 0)
            }
            self.trade_history.append(trade_log.copy())  # Use copy to prevent MongoDB _id mutation
            await self.db.paper_trades.insert_one(trade_log)
            
            # Broadcast trade event via WebSocket
            await broadcast_paper_event("paper_trade", {"trade": trade_log.copy()})
            await broadcast_paper_event("paper_status_update", {"status": self.get_status()})
            
            exec_type = position.get('execution_info', {}).get('order_type', 'market')
            spread_captured = position.get('execution_info', {}).get('spread_captured', 0)
            logger.info(f"📝 PAPER ENTRY: {side} ${size:.2f} @ {actual_entry_price:.4f} | Strategy: {strategy} | Exec: {exec_type} | Spread: ${spread_captured:.2f}")
            logger.info(f"   Dynamic Exit: TP={dynamic_exit['take_profit']:.1%}, SL={dynamic_exit['stop_loss']:.1%}, MaxHrs={dynamic_exit['max_hours']:.0f} ({dynamic_exit['zone']})")
            
        except Exception as e:
            logger.error(f"Error executing paper entry: {e}")
    
    async def _execute_paper_exit(self, market_id: str, market_data: Dict, exit_reason: str):
        """Execute a paper trade exit and feed reward to RL"""
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            # Get current price - require valid price for exit
            current_yes_price = market_data.get('yes_price')
            if current_yes_price is None or current_yes_price == 0:
                logger.warning(f"[EXIT-SKIP] No valid exit price for {market_id[:16]}")
                return
            
            current_yes_price = float(current_yes_price)
            
            # ==========================================================================
            # FETCH FRESH ORDERBOOK FOR EXIT EXECUTION (not stale entry data!)
            # ==========================================================================
            bids = []
            asks = []
            try:
                token_ids = market_data.get('token_ids', [])
                if token_ids:
                    from data.polymarket_api import PolymarketAPI
                    async with PolymarketAPI() as api:
                        fresh_orderbook = await api.get_order_book(token_ids[0])
                        bids = fresh_orderbook.get('bids', [])
                        asks = fresh_orderbook.get('asks', [])
                        if bids and asks:
                            logger.debug(f"[EXIT-EXEC-OB] Fresh orderbook for execution: bid={bids[0]['price']}, ask={asks[0]['price']}")
            except Exception as e:
                logger.debug(f"[EXIT-EXEC-OB] Could not fetch fresh orderbook: {e}")
            
            # Fallback to cached orderbook if fresh fetch failed
            if not bids or not asks:
                order_book = market_data.get('order_book', {})
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
            
            side = position['side']
            
            if bids and asks:
                # Use orderbook prices - more accurate than midpoint
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                
                # SANITY CHECK: Verify orderbook makes sense
                spread = best_ask - best_bid
                if spread < 0 or spread > 0.15:
                    logger.warning(f"[EXIT-WARN] Suspicious orderbook: bid={best_bid}, ask={best_ask}, spread={spread}")
                    # Fall back to midpoint
                    exit_yes_price = current_yes_price
                elif side == 'YES':
                    # Selling YES = hitting bid
                    exit_yes_price = best_bid
                else:
                    # Selling NO = buying YES = hitting ask
                    exit_yes_price = best_ask
                
                # Additional sanity check: exit price should be close to current price
                price_diff = abs(exit_yes_price - current_yes_price)
                if price_diff > 0.10:  # More than 10% difference is suspicious
                    logger.warning(f"[EXIT-WARN] Exit price {exit_yes_price:.4f} differs significantly from current {current_yes_price:.4f}")
                    # Use current price as fallback for safety
                    if side == 'YES':
                        exit_yes_price = current_yes_price - 0.01  # Conservative sell
                    else:
                        exit_yes_price = current_yes_price + 0.01  # Conservative buy YES
                    exit_yes_price = max(0.001, min(0.999, exit_yes_price))
                    logger.info(f"[EXIT] Using conservative exit price: {exit_yes_price:.4f}")
                
                logger.debug(f"[EXIT] Orderbook: bid={best_bid}, ask={best_ask}, exit_yes={exit_yes_price}")
            else:
                # No orderbook - use midpoint with conservative spread estimate
                spread_estimate = 0.02
                if side == 'YES':
                    exit_yes_price = current_yes_price - (spread_estimate / 2)
                else:
                    exit_yes_price = current_yes_price + (spread_estimate / 2)
                exit_yes_price = max(0.001, min(0.999, exit_yes_price))
            
            # Use yes_entry_price for internal calculations (stores the YES price at entry)
            yes_entry_price = position.get('yes_entry_price', position['entry_price'])
            size = position['size']  # USD invested
            strategy = position['strategy']
            asset_class = position.get('asset_class', 'unknown')
            
            # ==========================================================================
            # CORRECT P&L Calculation based on shares (using spread-aware exit price)
            # ==========================================================================
            if side == 'YES':
                # YES position: buy at entry_price, sell at exit_yes_price
                if yes_entry_price > 0:
                    shares = size / yes_entry_price
                    exit_value = shares * exit_yes_price
                    pnl = exit_value - size
                else:
                    pnl = 0
            else:
                # NO position: buy at (1 - yes_entry_price), sell at (1 - exit_yes_price)
                no_entry_price = 1 - yes_entry_price
                no_exit_price = 1 - exit_yes_price
                if no_entry_price > 0:
                    shares = size / no_entry_price
                    exit_value = shares * no_exit_price
                    pnl = exit_value - size
                else:
                    pnl = 0
            
            pnl_pct = pnl / size if size > 0 else 0
            
            # Track return for distribution
            return_pct = pnl_pct * 100  # Convert to percentage
            self.trade_returns.append(return_pct)
            logger.info(f"📊 Trade return recorded: {return_pct:.2f}% | Total returns tracked: {len(self.trade_returns)}")
            
            # Update metrics
            self.total_pnl += pnl
            self.current_capital += size + pnl
            
            # Track drawdown
            if self.current_capital > self.peak_capital:
                self.peak_capital = self.current_capital
            drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
            self.max_drawdown = max(self.max_drawdown, drawdown)
            
            # CIRCUIT BREAKER: Check if drawdown exceeds max allowed (from Settings)
            drawdown_pct = drawdown * 100
            if drawdown_pct >= self.max_drawdown_pct:
                logger.warning(f"🚨 CIRCUIT BREAKER TRIGGERED! Drawdown {drawdown_pct:.2f}% >= {self.max_drawdown_pct}% limit")
                logger.warning(f"   Peak: ${self.peak_capital:.2f} | Current: ${self.current_capital:.2f} | Loss: ${self.peak_capital - self.current_capital:.2f}")
                self.circuit_breaker_triggered = True
                # Stop accepting new trades - will be checked in main loop
            
            # Track wins
            is_win = pnl > 0
            if is_win:
                self.winning_trades += 1
            
            # Calculate hold time for this trade
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            exit_time = datetime.now(timezone.utc)
            hold_time_seconds = (exit_time - entry_time).total_seconds()
            hold_time_hours = hold_time_seconds / 3600
            
            # Update strategy stats with full metrics including hold time
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['pnl'] += pnl
                # Track hold time for averaging
                if 'total_hold_time' not in self.strategy_stats[strategy]:
                    self.strategy_stats[strategy]['total_hold_time'] = 0.0
                    self.strategy_stats[strategy]['closed_trades'] = 0
                self.strategy_stats[strategy]['total_hold_time'] += hold_time_hours
                self.strategy_stats[strategy]['closed_trades'] += 1
                if is_win:
                    self.strategy_stats[strategy]['wins'] += 1
                    self.strategy_stats[strategy]['gross_profit'] += pnl
                else:
                    self.strategy_stats[strategy]['gross_loss'] += abs(pnl)
            
            # Update strategy equity for equity curve
            if strategy in self.strategy_equity:
                self.strategy_equity[strategy] += pnl
            
            # Update lane equity for Three-Speed equity curve (Task 29)
            strategy_lane = RISK.get_strategy_path(strategy)
            if strategy_lane in self.lane_equity:
                self.lane_equity[strategy_lane] += pnl
            
            # Update asset class stats with full metrics including hold time
            if asset_class not in self.asset_class_stats:
                self.asset_class_stats[asset_class] = {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'total_hold_time': 0.0, 'closed_trades': 0}
                # If we're creating stats for an asset class at exit time, it means the position
                # was recovered/imported from a previous session - count it as a trade
                self.asset_class_stats[asset_class]['trades'] += 1
            # Ensure all fields exist (for positions opened before fix)
            if 'gross_profit' not in self.asset_class_stats[asset_class]:
                self.asset_class_stats[asset_class]['gross_profit'] = 0.0
            if 'gross_loss' not in self.asset_class_stats[asset_class]:
                self.asset_class_stats[asset_class]['gross_loss'] = 0.0
            if 'total_hold_time' not in self.asset_class_stats[asset_class]:
                self.asset_class_stats[asset_class]['total_hold_time'] = 0.0
                self.asset_class_stats[asset_class]['closed_trades'] = 0
            
            self.asset_class_stats[asset_class]['pnl'] += pnl
            self.asset_class_stats[asset_class]['total_hold_time'] += hold_time_hours
            self.asset_class_stats[asset_class]['closed_trades'] += 1
            if is_win:
                self.asset_class_stats[asset_class]['wins'] += 1
                self.asset_class_stats[asset_class]['gross_profit'] += pnl
            else:
                self.asset_class_stats[asset_class]['gross_loss'] += abs(pnl)
            
            # Update asset class equity for equity curve
            if asset_class not in self.asset_class_equity:
                self.asset_class_equity[asset_class] = 0.0
            self.asset_class_equity[asset_class] += pnl
            
            # Store closed trade with hold time calculation
            
            # Calculate RISK-ADJUSTED reward for RL
            reward = self._calculate_rl_reward(
                pnl_pct=pnl_pct, 
                is_win=is_win, 
                exit_reason=exit_reason,
                position=position,
                hold_time_hours=hold_time_hours
            )
            
            # Feed reward to RL engine - IMMEDIATELY updates Q-table for next trade
            await self.rl_engine.update_from_reward(market_id, reward)
            
            # ADAPTIVE LEARNING: Update position sizer with trade outcome
            await self.position_sizer.learn_from_trade(
                strategy=strategy,
                asset_class=asset_class,
                pnl=pnl,
                pnl_pct=pnl_pct,
                is_win=is_win,
                sizing_used=position.get('sizing_breakdown', {})
            )
            
            # For display purposes, store the actual price of the side being traded
            # (not the YES price which is confusing for NO positions)
            if side == 'YES':
                display_entry_price = yes_entry_price  # YES entry price
                display_exit_price = exit_yes_price  # YES exit price (spread-aware)
            else:
                display_entry_price = 1 - yes_entry_price  # NO entry price
                display_exit_price = 1 - exit_yes_price  # NO exit price (spread-aware)
            
            closed_trade = {
                **position,
                "entry_price": display_entry_price,  # Actual price for the side traded
                "exit_price": display_exit_price,    # Actual price for the side traded
                "yes_entry_price": yes_entry_price,      # Keep YES prices for reference
                "yes_exit_price": exit_yes_price,        # Spread-aware exit price
                "exit_time": exit_time.isoformat(),
                "exit_reason": exit_reason,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_time_seconds": hold_time_seconds,
                "reward_signal": reward
            }
            self.closed_trades.append(closed_trade)
            
            # Log trade with hold time
            # Determine strategy lane (HFT/ALPHA/GAMMA) from strategy name
            strategy_lane = RISK.get_strategy_path(strategy)
            
            trade_log = {
                "trade_id": str(uuid.uuid4()),
                "session_id": self.session_id,
                "type": "exit",
                "market_id": market_id,
                "market_question": position.get('market_question', ''),
                "side": side,
                "size": size,
                "entry_price": display_entry_price,  # Actual price for the side traded
                "exit_price": display_exit_price,    # Actual price for the side traded
                "yes_entry_price": yes_entry_price,      # Keep YES prices for reference
                "yes_exit_price": exit_yes_price,        # Spread-aware exit price
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_time_seconds": hold_time_seconds,
                "strategy": strategy,
                "strategy_lane": strategy_lane,  # Three-Speed: HFT, ALPHA, or GAMMA
                "asset_class": asset_class,
                "exit_reason": exit_reason,
                "reward_signal": reward,
                "timestamp": exit_time.isoformat()
            }
            self.trade_history.append(trade_log.copy())  # Use copy to prevent MongoDB _id mutation
            await self.db.paper_trades.insert_one(trade_log)
            
            # Broadcast trade event via WebSocket
            await broadcast_paper_event("paper_trade", {"trade": trade_log.copy()})
            await broadcast_paper_event("paper_status_update", {"status": self.get_status()})
            
            # Remove from open positions
            del self.paper_positions[market_id]
            
            # PERSIST: Delete position from database
            await self._delete_position_from_db(market_id)
            
            emoji = "✅" if is_win else "❌"
            logger.info(f"{emoji} PAPER EXIT: {side} ${size:.2f} | PnL: ${pnl:.2f} ({pnl_pct:.1%}) | Reason: {exit_reason} | RL Reward: {reward:.4f}")
            
        except Exception as e:
            logger.error(f"Error executing paper exit: {e}")
    
    def _calculate_rl_reward(self, pnl_pct: float, is_win: bool, exit_reason: str, 
                              position: Dict = None, hold_time_hours: float = 0) -> float:
        """
        Calculate RISK-ADJUSTED reward signal for RL based on trade outcome.
        
        Improvements over simple P&L:
        1. Risk-adjusted return (penalize high volatility wins)
        2. Drawdown penalty (penalize trades that went deep negative)
        3. Consistency bonus (small wins > volatile big wins)
        4. Hold time efficiency (quick profits better than slow ones)
        """
        # 1. BASE REWARD: Scaled P&L (moderate scaling for signal variation)
        # Map typical P&L range (-10% to +10%) to roughly -1 to +1
        base_reward = pnl_pct * 0.1  # 10% P&L = 1.0 reward
        
        # 2. DRAWDOWN PENALTY: If position went significantly negative before recovering
        if position:
            max_drawdown_pct = position.get('max_drawdown_pct', 0)
            if max_drawdown_pct > 5:  # More than 5% drawdown during trade
                # Penalty scales with how deep it went
                drawdown_penalty = (max_drawdown_pct - 5) * 0.03
                base_reward -= drawdown_penalty
        
        # 3. CONSISTENCY BONUS: Reward small consistent wins over volatile outcomes
        if is_win:
            if 0 < pnl_pct <= 3:  # Small win (0-3%)
                consistency_bonus = 0.2  # Best - consistent edge
            elif 3 < pnl_pct <= 8:  # Medium win (3-8%)
                consistency_bonus = 0.15
            else:  # Large win (>8%)
                consistency_bonus = 0.1  # Good but might be luck
            base_reward += consistency_bonus
        else:
            # Smaller losses are less bad than big losses (already in P&L)
            if pnl_pct < -10:  # Large loss
                base_reward -= 0.2  # Extra penalty for big losses
            elif pnl_pct < -5:  # Medium loss
                base_reward -= 0.1
        
        # 4. HOLD TIME EFFICIENCY: Quick profits are better
        # BUT only for RL-controlled exits (signal_reversal), not automatic TP/SL
        # Automatic exits depend on price movement speed, not RL skill
        if exit_reason == "rl_signal_reversal" and is_win and hold_time_hours > 0:
            if hold_time_hours < 1:  # RL exited profitably in under 1 hour
                base_reward += 0.15  # Smart quick exit
            elif hold_time_hours < 4:  # RL exited profitably in under 4 hours
                base_reward += 0.08
            # No penalty for slow RL exits - at least it exited profitably
        
        # 5. EXIT REASON BONUSES/PENALTIES
        if exit_reason == "take_profit":
            base_reward += 0.2  # Planned exit worked
        elif exit_reason == "rl_signal_reversal" and is_win:
            base_reward += 0.25  # RL reversal was smart - reinforce this!
        elif exit_reason == "stop_loss":
            # Stop loss isn't bad - it's good risk management
            base_reward += 0.05  # Small bonus for respecting stops
        elif exit_reason == "time_limit" and not is_win:
            base_reward -= 0.15  # Penalty for holding losing position too long
        elif exit_reason and "expiry" in exit_reason:
            if not is_win:
                base_reward -= 0.2  # Penalty for holding to expiry with loss
        
        # 6. RISK-ADJUSTED SCALING
        # If we have volatility info, adjust reward
        if position:
            entry_volatility = position.get('entry_volatility', 0.05)
            if entry_volatility > 0:
                # Higher volatility trades need higher returns to be "good"
                # Sharpe-like: reward / risk
                risk_adjusted_factor = 0.05 / max(entry_volatility, 0.01)
                risk_adjusted_factor = np.clip(risk_adjusted_factor, 0.7, 1.5)
                base_reward *= risk_adjusted_factor
        
        return np.clip(base_reward, -2.0, 2.0)  # Clip to reasonable range
    
    def _calculate_position_size(self, rl_confidence: float, signals: Dict, market_data: Dict = None, strategy: str = None, asset_class: str = None, rl_action: str = 'HOLD', order_book_asks: List[Dict] = None, market_question: str = '', market_tags: List[str] = None, market_age_hours: float = None, days_to_expiry: float = None) -> Dict:
        """
        Calculate position size using either NEW Polymarket-optimized or legacy adaptive sizing.
        
        NEW Polymarket Sizer (when use_polymarket_sizer=True):
        - Binary Kelly Criterion (fee-adjusted)
        - Utilization Brake (1-utilization)^1.5
        - Edge-Retention Liquidity Clamp
        - Oracle/Ambiguity Risk Matrix
        - Time/Duration Penalty
        - Correlation Dampener
        - Sector Caps
        
        Legacy Sizer (when use_polymarket_sizer=False):
        - Standard Kelly with learned parameters
        - Volume/liquidity multipliers
        - RL confidence scaling
        - Asset class risk profiles
        
        Returns dict with position_size and full breakdown.
        """
        market_data = market_data or {}
        strategy = strategy or self.enabled_strategies[0] if self.enabled_strategies else 'arbitrage'
        asset_class = asset_class or 'finance'
        order_book_asks = order_book_asks or []
        market_tags = market_tags or []
        
        # ====================================================================
        # NEW: Polymarket-optimized Position Sizing
        # ====================================================================
        if self.use_polymarket_sizer and hasattr(self, 'polymarket_sizer'):
            try:
                logger.info(f"[SIZER] Using Polymarket sizer for entry evaluation")
                
                # Calculate portfolio state
                portfolio_state = self._get_portfolio_state()
                equity = portfolio_state.get('equity', self.current_capital)
                deployed = portfolio_state.get('deployed_capital', 0)
                sector_exposure = portfolio_state.get('sector_exposure', {})
                
                # Get open positions for correlation check (include question for event cap)
                open_positions_list = [
                    {
                        'category': p.get('asset_class', p.get('category', 'unknown')),
                        'tags': p.get('tags', []),
                        'question': p.get('market_question', ''),
                        'size': p.get('size', 0),
                    }
                    for p in self.paper_positions.values()
                ]
                
                # Get ask price from market data - REQUIRE REAL DATA
                yes_price = market_data.get('yes_price')
                if yes_price is None or yes_price == 0:
                    logger.warning(f"[SIZER] No valid yes_price - cannot calculate position size")
                    return {'position_size': 0, 'rejection_reason': 'no_price_data'}
                
                yes_price = float(yes_price)
                
                # Reject suspicious ~0.5 prices without orderbook
                if abs(yes_price - 0.5) < 0.02:
                    order_book = market_data.get('order_book', {})
                    if not order_book.get('bids') or not order_book.get('asks'):
                        logger.warning(f"[SIZER] Price {yes_price:.4f} near 0.5 without orderbook - likely default")
                        return {'position_size': 0, 'rejection_reason': 'suspicious_default_price'}
                
                # Calculate model probability from signals
                # The RL action direction is critical - it tells us which side the model favors
                sentiment = signals.get('sentiment', 0.5)
                
                # Calculate raw model probability WITH DIAGNOSTICS for UI display
                model_diagnostics = self._calculate_model_probability(
                    sentiment=sentiment,
                    sharp_alignment=signals.get('sharp_alignment', 0.5),
                    rl_confidence=rl_confidence,
                    yes_price=yes_price,
                    rl_action=rl_action,
                    return_diagnostics=True
                )
                raw_model_prob = model_diagnostics['final_probability']
                
                # Log Bayesian fusion details
                log_odds = model_diagnostics.get('log_odds', {})
                sig_status = model_diagnostics.get('signal_status', {})
                logger.info(f"[BAYESIAN] base_lo={log_odds.get('base_log_odds', 0):.2f}, sent_delta={log_odds.get('sentiment_delta', 0):.3f} ({sig_status.get('sentiment', '?')}), rl_delta={log_odds.get('rl_delta', 0):.3f} ({sig_status.get('rl', '?')}), final_prob={raw_model_prob:.4f}")
                
                # Determine which side to bet on based on where we see edge
                # BUY/YES: edge when model_prob > effective_yes_price
                # SELL/NO: edge when (1-model_prob) > effective_no_price
                effective_yes_price = yes_price + self.polymarket_fee_pct
                effective_no_price = (1 - yes_price) + self.polymarket_fee_pct
                
                yes_edge = raw_model_prob - effective_yes_price
                no_edge = (1 - raw_model_prob) - effective_no_price
                
                # =============================================================
                # REGIME-AWARE MINIMUM EDGE REQUIREMENTS
                # =============================================================
                # Different regimes require different edge thresholds:
                # - TAKER_TIGHT: 1% (can cross spread profitably)
                # - MAKER_WIDE: 0.5% (we capture spread, need less edge)
                # - ZOMBIE: Already filtered out above
                regime = market_data.get('regime', MarketRegime.TAKER_TIGHT)
                regime_diagnostics = market_data.get('regime_diagnostics', {})
                
                if regime == MarketRegime.MAKER_WIDE:
                    # Wide spread market - we're posting inside spread
                    # Lower edge requirement because we capture spread instead of paying it
                    min_edge = 0.005  # 0.5%
                    execution_strategy = "maker_inside_spread"
                else:
                    # Tight spread market - standard taker strategy
                    # Need higher edge to cover spread + fees
                    min_edge = 0.01  # 1.0%
                    execution_strategy = "taker_if_edge"
                
                # Log edge calculation with regime context
                logger.info(f"[EDGE] regime={regime} | yes_price={yes_price:.3f}, model={raw_model_prob:.4f}, yes_edge={yes_edge:.4f}, no_edge={no_edge:.4f}, min_edge={min_edge:.3f}")
                
                if yes_edge > no_edge and yes_edge > min_edge:
                    # Bet on YES
                    model_probability = raw_model_prob
                    sizer_ask_price = yes_price
                    sizing_side = 'YES'
                elif no_edge > yes_edge and no_edge > min_edge:
                    # Bet on NO - transform to sizer's perspective
                    # Sizer expects: model_prob > ask_price for positive edge
                    # For NO: pass (1-model_prob) as "probability" and (1-yes_price) as "ask"
                    model_probability = 1 - raw_model_prob
                    sizer_ask_price = 1 - yes_price
                    sizing_side = 'NO'
                else:
                    # No positive edge on either side - return proper no-trade result
                    return {
                        'should_trade': False,
                        'position_size': 0,
                        'breakdown': {'reject_reason': 'insufficient_edge', 'reject_detail': f'yes_edge={yes_edge:.4f}, no_edge={no_edge:.4f}, min_edge={min_edge:.4f}'},
                        'sizing_breakdown': {'sizer_mode': 'polymarket', 'reject_reason': 'insufficient_edge'}
                    }
                
                logger.info(f"[MODEL_PROB] yes_price={yes_price:.3f}, raw_prob={raw_model_prob:.3f}, yes_edge={yes_edge:.3f}, no_edge={no_edge:.3f}, min_edge={min_edge:.3f}, sizing_side={sizing_side}")
                
                # Call the new Polymarket sizer
                # deployed_capital = max deployable from user config (initial_capital × capital_deployment_pct)
                logger.info(f"[SIZER CALL] equity={equity:.2f}, deployed={deployed:.2f}, max_deployable={self.deployed_capital:.2f}, model_prob={model_probability:.4f}, ask={sizer_ask_price:.4f}, days={days_to_expiry}, max_pos_pct={self.max_position_size_pct}%")
                sizing_result = self.polymarket_sizer.calculate_position_size(
                    equity=equity,
                    deployed_capital=deployed,
                    model_probability=model_probability,
                    ask_price=sizer_ask_price,  # Use transformed ask for NO bets
                    order_book_asks=order_book_asks,
                    days_to_expiry=days_to_expiry,
                    market_category=asset_class,
                    market_age_hours=market_age_hours,
                    market_question=market_question,
                    market_tags=market_tags,
                    open_positions=open_positions_list,
                    sector_exposure=sector_exposure,
                    max_position_size_pct=self.max_position_size_pct / 100,  # Convert % to decimal
                    max_deployable_capital=self.deployed_capital,  # From user config (initial × deployment%)
                )
                
                # Store the side we calculated for later use
                sizing_result['_sizing_side'] = sizing_side
                
                # Ensure compatibility: copy 'breakdown' to 'sizing_breakdown' for UI
                if 'breakdown' in sizing_result and 'sizing_breakdown' not in sizing_result:
                    sizing_result['sizing_breakdown'] = sizing_result['breakdown']
                elif 'sizing_breakdown' not in sizing_result:
                    sizing_result['sizing_breakdown'] = {}
                
                # Add legacy compatibility fields
                sizing_result['sizing_breakdown']['sizer_mode'] = 'polymarket'
                sizing_result['sizing_breakdown']['rl_confidence'] = rl_confidence
                sizing_result['sizing_breakdown']['model_probability'] = model_probability
                
                # Add regime info for debugging and UI
                sizing_result['sizing_breakdown']['market_regime'] = regime
                sizing_result['sizing_breakdown']['execution_strategy'] = execution_strategy
                sizing_result['sizing_breakdown']['min_edge_required'] = min_edge
                
                # Add probability model diagnostics for UI panel
                sizing_result['sizing_breakdown']['probability_diagnostics'] = model_diagnostics
                
                # Log sizing decision
                if sizing_result['should_trade']:
                    breakdown = sizing_result.get('breakdown', sizing_result.get('sizing_breakdown', {}))
                    logger.info(
                        f"[POLYMARKET SIZER] ACCEPT ${sizing_result['position_size']:.2f} | "
                        f"Edge: {breakdown.get('edge_pct', 0):.1f}% | "
                        f"Util: {breakdown.get('utilization', 0):.1%} | "
                        f"Oracle: {breakdown.get('oracle_mult', 1):.2f}"
                    )
                else:
                    breakdown = sizing_result.get('breakdown', sizing_result.get('sizing_breakdown', {}))
                    logger.info(
                        f"[POLYMARKET SIZER] REJECT: {breakdown.get('reject_reason', 'unknown')} - "
                        f"{breakdown.get('reject_detail', '')}"
                    )
                
                return sizing_result
                
            except Exception as e:
                logger.warning(f"Polymarket sizer error, falling back to legacy: {e}")
                # Fall through to legacy sizer
        
        # ====================================================================
        # LEGACY: Adaptive Position Sizing (backwards compatibility)
        # ====================================================================
        # Inject user config thresholds into market_data for position sizer to use
        market_data_with_config = {
            **market_data,
            '_min_volume_threshold': self.min_volume_24h,
            '_min_liquidity_threshold': self.min_liquidity,
            '_max_liquidity_threshold': self.max_liquidity,
        }
        
        sizing_result = self.position_sizer.calculate_optimal_position_size(
            deployed_capital=self.deployed_capital,
            max_position_pct=self.max_position_size_pct,
            strategy=strategy,
            asset_class=asset_class,
            market_data=market_data_with_config,
            signals=signals,
            rl_action=rl_action,
            rl_confidence=rl_confidence,
            kelly_fraction=self.kelly_fraction,
            kelly_enabled=self.kelly_enabled
        )
        
        # Add mode indicator
        sizing_result['sizing_breakdown']['sizer_mode'] = 'legacy'
        
        # Log sizing decision for analysis
        if sizing_result['should_trade']:
            logger.debug(f"[LEGACY SIZER] ${sizing_result['position_size']:.2f} | "
                        f"Liquidity: {sizing_result['sizing_breakdown']['liquidity_multiplier']:.2f} | "
                        f"RL: {sizing_result['sizing_breakdown']['rl_confidence_multiplier']:.2f}")
        
        return sizing_result
    
    def _calculate_model_probability(
        self,
        sentiment: float,
        sharp_alignment: float,
        rl_confidence: float,
        yes_price: float,
        rl_action: str = 'HOLD',
        return_diagnostics: bool = False
    ) -> float:
        """
        Calculate model probability using BAYESIAN LOG-ODDS FUSION.
        
        This method uses the market price as the ANCHOR (prior belief) and applies
        Bayesian updates from sentiment and RL signals in log-odds space.
        
        Key Properties:
        - Market price is the anchor - model starts from market's estimate
        - Neutral signals (0.5) contribute ZERO delta (no drag toward 0.5)
        - Result naturally respects the scale of the market price
        - No artificial floors or ceilings that create false edge
        
        Math:
        - Log-odds(0.5) = 0.0 (neutral)
        - Log-odds(0.01) = -4.6 (very unlikely)
        - Log-odds(0.99) = +4.6 (very likely)
        
        Example (Neutral Case Verification):
        - market=0.01, sentiment=0.5, rl=HOLD
        - base_log_odds = -4.6
        - sentiment_delta = 0.0 (neutral excluded)
        - rl_delta = 0.0 (HOLD excluded)
        - final_log_odds = -4.6
        - final_prob = 0.01 ✓
        
        Args:
            sentiment: Combined sentiment score (0-1)
            sharp_alignment: Sharp money alignment (unused in Bayesian)
            rl_confidence: RL model confidence (0-1)
            yes_price: Current YES price (market's implied probability)
            rl_action: RL action (BUY_SMALL, SELL_MEDIUM, HOLD, etc.)
            return_diagnostics: If True, returns diagnostic dict instead of float
            
        Returns:
            float: Bayesian model probability, or dict if return_diagnostics=True
        """
        import math
        
        # ================================================================
        # LOG-ODDS HELPER FUNCTIONS
        # ================================================================
        def prob_to_log_odds(prob: float) -> float:
            """Convert probability to log-odds. Neutral (0.5) → 0.0"""
            epsilon = 1e-9
            p = max(epsilon, min(1 - epsilon, prob))
            return math.log(p / (1 - p))
        
        def log_odds_to_prob(log_odds: float) -> float:
            """Convert log-odds to probability (sigmoid)."""
            # Clamp to avoid overflow
            lo = max(-30, min(30, log_odds))
            return 1.0 / (1.0 + math.exp(-lo))
        
        # ================================================================
        # STEP 1: ANCHOR - Market Price as Prior
        # ================================================================
        p_market = yes_price
        base_log_odds = prob_to_log_odds(p_market)
        
        # ================================================================
        # STEP 2: SENTIMENT DELTA (RELATIVE TO MARKET)
        # ================================================================
        # FIX: Calculate sentiment delta as RELATIVE to market, not absolute.
        # 
        # OLD BUG: sentiment_delta = log_odds(sentiment)
        #   - If sentiment=0.40, log_odds=-0.405 (negative)
        #   - This dragged prices DOWN even when market was 0.10 (sentiment > market!)
        #
        # NEW FIX: sentiment_delta = log_odds(sentiment) - log_odds(market)
        #   - If sentiment=0.40 and market=0.10: delta = -0.405 - (-2.20) = +1.79 (BULLISH)
        #   - If sentiment=0.40 and market=0.70: delta = -0.405 - (+0.85) = -1.25 (BEARISH)
        #
        # This matches the RL logic which was already correct!
        # ================================================================
        p_sentiment = sentiment
        
        # Use dynamic weights from self.alpha_weights (Task 19: Dynamic Alpha Tuning)
        NEUTRAL_LOW = self.alpha_weights.get('sentiment_neutral_low', 0.45)
        NEUTRAL_HIGH = self.alpha_weights.get('sentiment_neutral_high', 0.55)
        SENTIMENT_WEIGHT = self.alpha_weights.get('sentiment_weight', 0.50)
        
        # Safety cap for raw delta to prevent hallucination-driven extreme moves
        MAX_SENTIMENT_DELTA = self.alpha_weights.get('max_sentiment_delta', 2.0)
        
        is_sentiment_neutral = NEUTRAL_LOW <= p_sentiment <= NEUTRAL_HIGH
        
        if is_sentiment_neutral:
            weighted_sentiment_delta = 0.0
            sentiment_status = 'neutral_excluded'
            raw_sentiment_delta = 0.0
        else:
            # FIXED: Calculate RELATIVE delta (sentiment vs market)
            sentiment_log_odds = prob_to_log_odds(p_sentiment)
            market_log_odds = base_log_odds  # Already calculated in Step 1
            
            # The "pull" - positive if sentiment > market, negative if sentiment < market
            raw_sentiment_delta = sentiment_log_odds - market_log_odds
            
            # Safety clamp to prevent hallucinations from extreme moves
            raw_sentiment_delta = max(-MAX_SENTIMENT_DELTA, min(MAX_SENTIMENT_DELTA, raw_sentiment_delta))
            
            weighted_sentiment_delta = raw_sentiment_delta * SENTIMENT_WEIGHT
            sentiment_status = 'active'
        
        # ================================================================
        # STEP 3: RL DELTA (Already correct - relative to market)
        # ================================================================
        rl_action = rl_action.upper() if rl_action else 'HOLD'
        
        is_buy = 'BUY' in rl_action
        is_sell = 'SELL' in rl_action
        
        # Action strength determines deviation from market
        if 'LARGE' in rl_action:
            deviation = 0.20
        elif 'MEDIUM' in rl_action:
            deviation = 0.12
        elif 'SMALL' in rl_action:
            deviation = 0.06
        else:
            deviation = 0.0
        
        # Calculate RL's implied probability
        if is_buy:
            p_rl = yes_price + deviation * max(rl_confidence, 0.2)
        elif is_sell:
            p_rl = yes_price - deviation * max(rl_confidence, 0.2)
        else:
            p_rl = yes_price
        
        # Clamp to valid probability
        p_rl = max(1e-9, min(1 - 1e-9, p_rl))
        
        # Use dynamic weights from self.alpha_weights (Task 19: Dynamic Alpha Tuning)
        RL_WEIGHT = self.alpha_weights.get('rl_weight', 0.60)
        MIN_RL_CONFIDENCE = self.alpha_weights.get('min_rl_confidence', 0.15)
        
        is_rl_neutral = (not is_buy and not is_sell) or rl_confidence < MIN_RL_CONFIDENCE
        
        if is_rl_neutral:
            weighted_rl_delta = 0.0
            rl_status = 'neutral_excluded'
        else:
            rl_log_odds = prob_to_log_odds(p_rl)
            # RL delta is relative to market, not absolute neutral
            # This ensures SELL on 0.01 market doesn't create huge negative delta
            market_log_odds = prob_to_log_odds(yes_price)
            rl_delta = rl_log_odds - market_log_odds
            weighted_rl_delta = rl_delta * rl_confidence * RL_WEIGHT
            rl_status = 'active'
        
        # ================================================================
        # STEP 4: BAYESIAN UPDATE
        # ================================================================
        total_delta = weighted_sentiment_delta + weighted_rl_delta
        final_log_odds = base_log_odds + total_delta
        
        # ================================================================
        # STEP 5: CONVERT BACK TO PROBABILITY
        # ================================================================
        # NO ARTIFICIAL CAPS - let the math speak
        bayesian_final_prob = log_odds_to_prob(final_log_odds)
        
        # Log for debugging
        logger.debug(f"[BAYESIAN_PURE] base_lo={base_log_odds:.3f}, sent_delta={weighted_sentiment_delta:.4f}, rl_delta={weighted_rl_delta:.4f}, final_lo={final_log_odds:.3f}, prob={bayesian_final_prob:.6f}")
        
        # ================================================================
        # RETURN
        # ================================================================
        if return_diagnostics:
            return {
                'final_probability': bayesian_final_prob,
                'fusion_method': 'bayesian_log_odds_relative',  # Updated name
                'components': {
                    'p_market': round(p_market, 6),
                    'p_sentiment': round(p_sentiment, 4),
                    'p_rl': round(p_rl, 6),
                },
                'log_odds': {
                    'base_log_odds': round(base_log_odds, 4),
                    'raw_sentiment_delta': round(raw_sentiment_delta, 4),  # NEW: Pre-weight delta
                    'sentiment_delta': round(weighted_sentiment_delta, 4),
                    'rl_delta': round(weighted_rl_delta, 4),
                    'total_delta': round(total_delta, 4),
                    'final_log_odds': round(final_log_odds, 4),
                },
                'weights': {
                    'sentiment_weight': SENTIMENT_WEIGHT,
                    'rl_weight': RL_WEIGHT,
                    'max_sentiment_delta': MAX_SENTIMENT_DELTA,  # NEW: Safety cap
                },
                'signal_status': {
                    'sentiment': sentiment_status,
                    'rl': rl_status,
                    'sentiment_is_neutral': is_sentiment_neutral,
                    'rl_is_neutral': is_rl_neutral,
                },
                'rl_details': {
                    'action': rl_action,
                    'confidence': round(rl_confidence, 4),
                    'deviation': round(deviation, 4),
                    'direction': 'bullish' if is_buy else ('bearish' if is_sell else 'neutral'),
                },
            }
        
        return bayesian_final_prob
    
    def _get_portfolio_state(self) -> Dict:
        """
        Calculate current portfolio state for position sizing.
        
        Returns:
            Dict with equity, deployed_capital, sector_exposure, etc.
        """
        # Calculate cash balance
        positions_cost_basis = sum(p.get('size', 0) for p in self.paper_positions.values())
        cash_balance = self.current_capital - positions_cost_basis + self.total_pnl
        
        # Use portfolio manager
        if hasattr(self, 'portfolio_manager'):
            # Build positions list for portfolio manager
            positions_list = []
            for market_id, pos in self.paper_positions.items():
                entry_price = pos.get('entry_price')
                # STRICT VALIDATION: Skip positions without valid entry_price
                if entry_price is None or entry_price == 0:
                    logger.warning(f"[PORTFOLIO-SKIP] Position {market_id[:16]} has no valid entry_price")
                    continue
                    
                current_price = pos.get('current_price')
                # Use entry_price as fallback for current_price ONLY if entry_price is valid
                if current_price is None or current_price == 0:
                    current_price = entry_price
                    
                positions_list.append({
                    'market_id': market_id,
                    'side': pos.get('side', 'YES'),
                    'size': pos.get('size', 0),
                    'entry_price': float(entry_price),
                    'current_price': float(current_price),
                    'category': pos.get('asset_class', pos.get('category', 'unknown')),
                })
            
            state = self.portfolio_manager.calculate_portfolio_state(
                cash_balance=cash_balance,
                open_positions=positions_list
            )
            return state
        
        # Fallback: Simple calculation
        return {
            'equity': self.current_capital + self.unrealized_pnl,
            'cash_balance': cash_balance,
            'deployed_capital': positions_cost_basis,
            'utilization': positions_cost_basis / max(self.current_capital, 1),
            'sector_exposure': self._calculate_simple_sector_exposure(),
        }
    
    def _calculate_simple_sector_exposure(self) -> Dict[str, float]:
        """Calculate sector exposure without portfolio manager."""
        exposure = {}
        for pos in self.paper_positions.values():
            category = pos.get('asset_class', pos.get('category', 'unknown'))
            if category:
                category = category.lower()
            size = pos.get('size', 0)
            exposure[category] = exposure.get(category, 0) + size
        return exposure
    
    def _calculate_position_size_legacy(self, rl_confidence: float, signals: Dict) -> float:
        """Legacy position sizing for backward compatibility"""
        result = self._calculate_position_size(rl_confidence, signals)
        return result.get('position_size', 0)
    
    def _determine_strategy(self, signals: Dict, rl_action: str, market_data: Dict = None) -> Optional[str]:
        """Determine strategy based on REAL signals from market data
        
        Uses configurable thresholds from self (loaded from DB):
        - volatility_threshold: for volatility exploitation trigger
        - sentiment_strength_threshold: for alpha directional trigger
        - sharp_alignment_threshold: for arbitrage trigger
        - delta_neutral_price_min/max: price range for delta neutral
        """
        volatility = signals.get('volatility', 0.05)
        sentiment = signals.get('sentiment', 0.5)
        sentiment_strength = abs(sentiment - 0.5)
        sharp_alignment = signals.get('sharp_alignment', 0.5)
        price_uncertainty = signals.get('price_uncertainty', 0.5)
        
        # Get price from market data - REQUIRE REAL DATA for strategy selection
        yes_price = None
        if market_data:
            yes_price = market_data.get('yes_price')
        
        if yes_price is None or yes_price == 0:
            # No valid price - default to arbitrage (least price-dependent)
            if 'arbitrage' in self.enabled_strategies:
                return 'arbitrage'
            return self.enabled_strategies[0] if self.enabled_strategies else None
        
        yes_price = float(yes_price)
        
        # Strategy selection based on ACTUAL signals - balanced distribution
        # Uses configurable thresholds (loaded from DB config)
        
        # 1. ALPHA DIRECTIONAL: Prices below 25% or above 75% - clear directional bets
        # Widened from 0.03/0.97 to capture more directional opportunities
        if (yes_price < 0.25 or yes_price > 0.75) and 'alpha_directional' in self.enabled_strategies:
            return 'alpha_directional'
        
        # 2. ARBITRAGE: High liquidity markets with good sharp alignment
        if sharp_alignment > self.sharp_alignment_threshold and 'arbitrage' in self.enabled_strategies:
            return 'arbitrage'
        
        # 3. DELTA NEUTRAL: Mid-range price with moderate volatility - market making
        if (self.delta_neutral_price_min <= yes_price <= self.delta_neutral_price_max 
            and volatility < self.volatility_threshold 
            and 'delta_neutral' in self.enabled_strategies):
            return 'delta_neutral'
        
        # 4. ALPHA DIRECTIONAL: Strong sentiment divergence from 50% (BEFORE volatility)
        if sentiment_strength > self.sentiment_strength_threshold and 'alpha_directional' in self.enabled_strategies:
            return 'alpha_directional'
        
        # 5. VOLATILITY EXPLOITATION: Higher volatility or uncertain markets
        if ((volatility > self.volatility_threshold or price_uncertainty > 0.7) 
            and 'volatility_exploitation' in self.enabled_strategies):
            return 'volatility_exploitation'
        
        # 6. Default: Distribute remaining based on price bucket for variety
        price_bucket = int(yes_price * 10) % 4
        strategies_order = ['delta_neutral', 'arbitrage', 'volatility_exploitation', 'alpha_directional']
        for i in range(4):
            candidate = strategies_order[(price_bucket + i) % 4]
            if candidate in self.enabled_strategies:
                return candidate
        
        # Final fallback
        return self.enabled_strategies[0] if self.enabled_strategies else None
    
    async def _get_signals(self, market_data: Dict) -> Dict:
        """
        Get ULTIMATE ENHANCED signals from multiple data sources:
        1. Market microstructure (price, volume, liquidity)
        2. Price momentum tracking
        3. News sentiment (Finnhub)
        4. Social sentiment (Twitter/Reddit)
        5. LLM analysis (optional)
        """
        try:
            # Extract base market data
            market_id = market_data.get('id', '')
            
            # Get prices - use sensible defaults only for signal calculation (not trading)
            yes_price = market_data.get('yes_price')
            no_price = market_data.get('no_price')
            
            # If no price data, return neutral signals (caller should validate before trading)
            if yes_price is None or yes_price == 0:
                logger.debug(f"[SIGNALS] No price data for {market_id[:16]} - returning neutral signals")
                return {
                    'volatility': 0.05,
                    'sentiment': 0.5,
                    'sharp_alignment': 0.5,
                    'price_uncertainty': 0.5,
                    'volume_signal': 0.0,
                    'momentum': 0.0,
                    'edge': 0.0,
                    'no_price_data': True  # Flag for caller to check
                }
            
            yes_price = float(yes_price)
            no_price = float(no_price) if no_price else 1 - yes_price
            
            volume_24h = float(market_data.get('volume_24h', 0) or 0)
            total_volume = float(market_data.get('volume', 0) or 0)
            liquidity = float(market_data.get('liquidity', 0) or 0)
            spread = float(market_data.get('spread', 0.02) or 0.02)
            outstanding = float(market_data.get('outstanding_contracts', liquidity) or liquidity)
            
            # ================================================================
            # VOLATILITY CALCULATION
            # ================================================================
            price_uncertainty = 1 - abs(yes_price - 0.5) * 2
            volume_factor = min(1.0, volume_24h / 5000000) if volume_24h > 0 else 0
            spread_volatility = min(0.05, spread * 2)
            volatility = (
                price_uncertainty * 0.04 +
                spread_volatility +
                volume_factor * 0.03
            )
            volatility = max(0.01, min(0.15, volatility))
            
            # ================================================================
            # LAYER 1: MARKET MICROSTRUCTURE SENTIMENT
            # ================================================================
            
            # 1A: Base price sentiment
            price_sentiment = yes_price
            
            # 1B: Price momentum (track changes over time)
            momentum_sentiment = 0.5
            if not hasattr(self, '_price_cache'):
                self._price_cache = {}
            
            cache_key = market_id
            current_time = asyncio.get_event_loop().time()
            
            if cache_key in self._price_cache:
                old_price, old_time = self._price_cache[cache_key]
                time_diff = current_time - old_time
                
                if time_diff > 0 and time_diff < 3600:
                    price_change = yes_price - old_price
                    momentum = price_change / max(0.001, old_price)
                    momentum_sentiment = 0.5 + (momentum * 5)
                    momentum_sentiment = max(0, min(1, momentum_sentiment))
            
            self._price_cache[cache_key] = (yes_price, current_time)
            
            # 1C: Volume intensity
            volume_intensity = 0.5
            if total_volume > 0:
                recent_ratio = volume_24h / total_volume
                volume_intensity = min(1.0, recent_ratio * 10)
            
            # 1D: Liquidity-based conviction
            liquidity_sentiment = 0.5
            if yes_price < 0.2:
                liquidity_sentiment = 0.5 - (0.5 * (1 - spread * 10))
            elif yes_price > 0.8:
                liquidity_sentiment = 0.5 + (0.5 * (1 - spread * 10))
            
            # 1E: Whale activity direction
            whale_sentiment = 0.5
            if liquidity > 0:
                whale_ratio = volume_24h / liquidity
                if whale_ratio > 2:
                    whale_sentiment = 0.5 + (yes_price - 0.5) * min(1, whale_ratio / 5)
            
            # 1F: Market maturity weight
            maturity_weight = min(1.0, total_volume / 1000000)
            
            # Combine Layer 1: Market Microstructure (base sentiment)
            market_sentiment = (
                price_sentiment * 0.30 +
                momentum_sentiment * 0.25 +
                volume_intensity * 0.15 +
                liquidity_sentiment * 0.15 +
                whale_sentiment * 0.15
            )
            
            # ================================================================
            # LAYER 2: LLM + CROSS-MARKET CORRELATION (Enhanced Sentiment)
            # ================================================================
            llm_sentiment = 0.5
            llm_confidence = 0.0
            correlation_sentiment = 0.5
            correlation_strength = 0.0
            enhanced_data = {}
            
            # Try to get enhanced sentiment (LLM + Correlation + Polymarket-native)
            try:
                if hasattr(self, 'enhanced_sentiment') and self.enhanced_sentiment:
                    # Get trades and order book for Polymarket-native sentiment
                    trades = []
                    order_book = {}
                    token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
                    
                    if token_ids and len(token_ids) > 0:
                        try:
                            from data.polymarket_api import PolymarketAPI
                            async with PolymarketAPI() as api:
                                trades = await api.get_trades(token_ids[0], limit=30)
                                order_book = await api.get_order_book(token_ids[0])
                        except Exception as e:
                            logger.debug(f"Could not fetch trades/orderbook for sentiment: {e}")
                    
                    enhanced_result = await asyncio.wait_for(
                        self.enhanced_sentiment.analyze(market_data, trades=trades, order_book=order_book),
                        timeout=5.0  # 5 second timeout (longer to allow API calls)
                    )
                    
                    llm_sentiment = enhanced_result.get('llm_sentiment', 0.5)
                    llm_confidence = enhanced_result.get('llm_confidence', 0.0)
                    correlation_sentiment = enhanced_result.get('correlation_sentiment', 0.5)
                    correlation_strength = enhanced_result.get('correlation_strength', 0.0)
                    
                    # NEW: Polymarket-native sentiment signals
                    polymarket_sentiment = enhanced_result.get('polymarket_sentiment', 0.5)
                    polymarket_confidence = enhanced_result.get('polymarket_confidence', 0.0)
                    polymarket_momentum = enhanced_result.get('polymarket_momentum', {})
                    
                    enhanced_data = {
                        'llm_sentiment': llm_sentiment,
                        'llm_confidence': llm_confidence,
                        'llm_reasoning': enhanced_result.get('llm_reasoning', ''),
                        'correlation_sentiment': correlation_sentiment,
                        'correlation_strength': correlation_strength,
                        'category_momentum': enhanced_result.get('category_momentum', 0.0),
                        'related_groups': enhanced_result.get('related_groups', []),
                        'analysis_source': enhanced_result.get('analysis_source', 'none'),
                        # NEW: Polymarket-native fields
                        'polymarket_sentiment': polymarket_sentiment,
                        'polymarket_confidence': polymarket_confidence,
                        'polymarket_momentum': polymarket_momentum,
                        'polymarket_signals': enhanced_result.get('polymarket_signals', {}),
                        'polymarket_interpretation': enhanced_result.get('polymarket_interpretation', ''),
                    }
            except asyncio.TimeoutError:
                logger.debug(f"Enhanced sentiment timeout for {market_id[:16]}")
            except Exception as e:
                logger.debug(f"Enhanced sentiment error: {e}")
            
            # ================================================================
            # LAYER 3: EXTERNAL NEWS/SOCIAL (Finnhub - DISABLED until API key)
            # ================================================================
            news_sentiment = 0.5
            social_sentiment = 0.5
            external_confidence = 0.0  # DISABLED - set to 0 to exclude from fusion
            news_data = {}
            
            # FINNHUB DISABLED - Uncomment when API key is configured
            # Check for Finnhub API key before trying
            finnhub_key = os.environ.get('FINNHUB_API_KEY', '')
            if finnhub_key and hasattr(self, 'social_analyzer') and self.social_analyzer:
                try:
                    social_result = await asyncio.wait_for(
                        self.social_analyzer.analyze_market_sentiment(market_data),
                        timeout=2.0
                    )
                    
                    news_sentiment = social_result.get('news_sentiment', 0.5)
                    social_sentiment = social_result.get('social_sentiment', 0.5)
                    external_confidence = social_result.get('confidence', 0.0)
                    news_data = {
                        'news_count': social_result.get('news_count', 0),
                        'social_buzz': social_result.get('social_buzz', 0),
                        'trending_score': social_result.get('trending_score', 0),
                        'sources': social_result.get('sources', [])
                    }
                except asyncio.TimeoutError:
                    logger.debug(f"External sentiment timeout for {market_id[:16]}")
                except Exception as e:
                    logger.debug(f"External sentiment error: {e}")
            
            external_sentiment = (news_sentiment * 0.6 + social_sentiment * 0.4)
            
            # ================================================================
            # FINAL SENTIMENT FUSION (5 Layers)
            # Uses combined_sentiment from enhanced_sentiment.py as primary
            # ================================================================
            # Get Polymarket-native sentiment from enhanced_data
            polymarket_sentiment = enhanced_data.get('polymarket_sentiment', 0.5)
            polymarket_confidence = enhanced_data.get('polymarket_confidence', 0.0)
            
            # Get GitHub sentiment if available (for crypto markets)
            github_sentiment = enhanced_data.get('github_sentiment', 0.5)
            github_confidence = enhanced_data.get('github_confidence', 0.0)
            
            # Calculate weights based on data availability/confidence
            market_weight = 0.25  # Market microstructure: 25%
            polymarket_weight = polymarket_confidence * 0.25  # Polymarket-native: up to 25%
            llm_weight = llm_confidence * 0.25  # LLM: up to 25%
            corr_weight = correlation_strength * 0.10  # Correlation: up to 10%
            github_weight = github_confidence * 0.15  # GitHub: up to 15% (crypto only)
            # external_weight = 0 (Finnhub disabled)
            
            total_weight = market_weight + polymarket_weight + llm_weight + corr_weight + github_weight
            
            if total_weight > 0:
                raw_sentiment = (
                    market_sentiment * market_weight +
                    polymarket_sentiment * polymarket_weight +
                    llm_sentiment * llm_weight +
                    correlation_sentiment * corr_weight +
                    github_sentiment * github_weight
                ) / total_weight
            else:
                raw_sentiment = market_sentiment
            
            # Apply maturity dampening
            sentiment = raw_sentiment * maturity_weight + 0.5 * (1 - maturity_weight)
            # Allow full range - remove artificial floors that create bias
            sentiment = max(0.001, min(0.999, sentiment))
            
            # Sentiment strength (conviction level)
            sentiment_strength = abs(sentiment - 0.5) * 2
            
            # ================================================================
            # SHARP ALIGNMENT & OTHER SIGNALS
            # ================================================================
            liquidity_score = min(1.0, liquidity / 100000) if liquidity > 0 else 0
            spread_score = max(0, 1 - spread * 10)
            sharp_alignment = (liquidity_score * 0.6 + spread_score * 0.4)
            
            whale_activity = min(1.0, (volume_24h / liquidity) if liquidity > 0 else 0)
            
            signals = {
                'volatility': round(volatility, 4),
                'sentiment': round(sentiment, 4),
                'sentiment_strength': round(sentiment_strength, 4),
                'sentiment_layers': {
                    'market_microstructure': round(market_sentiment, 4),
                    'polymarket_native': round(polymarket_sentiment, 4),
                    'polymarket_confidence': round(polymarket_confidence, 4),
                    'llm_sentiment': round(llm_sentiment, 4),
                    'llm_confidence': round(llm_confidence, 4),
                    'correlation_sentiment': round(correlation_sentiment, 4),
                    'correlation_strength': round(correlation_strength, 4),
                    'github_sentiment': round(github_sentiment, 4),
                    'github_confidence': round(github_confidence, 4),
                    'external_data': 0.5,  # Finnhub disabled
                    'external_confidence': 0.0,  # Finnhub disabled
                },
                'sentiment_weights': {
                    'market_weight': round(market_weight, 4),
                    'polymarket_weight': round(polymarket_weight, 4),
                    'llm_weight': round(llm_weight, 4),
                    'correlation_weight': round(corr_weight, 4),
                    'github_weight': round(github_weight, 4),
                    'external_weight': 0.0,  # Finnhub disabled
                },
                'polymarket_momentum': enhanced_data.get('polymarket_momentum', {}),
                'polymarket_signals': enhanced_data.get('polymarket_signals', {}),
                'sentiment_components': {
                    'price': round(price_sentiment, 4),
                    'momentum': round(momentum_sentiment, 4),
                    'volume_intensity': round(volume_intensity, 4),
                    'liquidity': round(liquidity_sentiment, 4),
                    'whale': round(whale_sentiment, 4),
                    'news': round(news_sentiment, 4),
                    'social': round(social_sentiment, 4),
                    'maturity_weight': round(maturity_weight, 4)
                },
                'enhanced_data': enhanced_data,
                'news_data': news_data,
                'sharp_alignment': round(sharp_alignment, 4),
                'whale_activity': round(whale_activity, 4),
                'price_uncertainty': round(price_uncertainty, 4),
                'volume_factor': round(volume_factor, 4)
            }
            
            # Try to enhance with ML models if available
            try:
                vol_pred = await self.volatility_predictor.predict(market_data)
                if vol_pred and vol_pred.get('predicted_volatility'):
                    # Blend ML prediction with calculated volatility
                    ml_vol = vol_pred.get('predicted_volatility', volatility)
                    signals['volatility'] = round((volatility * 0.5 + ml_vol * 0.5), 4)
            except Exception:
                pass
            
            try:
                sentiment_result = await self.signal_fusion.get_fused_signal(market_data.get('id'), market_data)
                if sentiment_result and sentiment_result.get('sentiment') is not None:
                    ml_sentiment = sentiment_result.get('sentiment', sentiment)
                    signals['sentiment'] = round((sentiment * 0.5 + ml_sentiment * 0.5), 4)
            except Exception:
                pass
            
            try:
                sharp_result = await self.sharp_detector.get_alignment_signal(market_data.get('id'))
                if sharp_result and sharp_result.get('alignment_score') is not None:
                    ml_sharp = sharp_result.get('alignment_score', sharp_alignment)
                    signals['sharp_alignment'] = round((sharp_alignment * 0.5 + ml_sharp * 0.5), 4)
            except Exception:
                pass
            
            return signals
            
        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            # Even fallback should be derived from market data when possible
            return {
                'volatility': 0.05,  # Moderate default
                'sentiment': 0.5,
                'sharp_alignment': 0.5,
                'whale_activity': 0.0
            }
    
    async def _position_monitoring_loop(self):
        """Monitor open positions and update unrealized P&L with REAL prices"""
        while self.running:
            try:
                if self.paper_positions:
                    # Fetch latest market prices from Gamma API
                    markets = await self._get_active_markets()
                    
                    # Build price map - ONLY include markets with valid prices
                    market_prices = {}
                    for m in markets:
                        price = m.get('yes_price')
                        if price is not None and price != 0:
                            market_prices[m['id']] = float(price)
                    
                    total_unrealized = 0.0
                    for market_id, position in self.paper_positions.items():
                        # Use yes_entry_price for internal calculations (stores the YES price at entry)
                        yes_entry_price = position.get('yes_entry_price', position['entry_price'])
                        side = position['side']
                        size = position['size']  # USD invested
                        
                        # Get REAL current price from API - skip if no valid price
                        current_price = market_prices.get(market_id)
                        if current_price is None:
                            # No valid price - use entry price as fallback for display only
                            # This won't affect trading decisions
                            current_price = yes_entry_price
                            logger.debug(f"[UNREALIZED] No price for {market_id[:16]} - using entry price")
                        
                        # Calculate current value and unrealized P&L
                        if side == 'YES':
                            # YES position: buy at yes_entry_price, value at current_price
                            shares = size / yes_entry_price if yes_entry_price > 0 else 0
                            current_value = shares * current_price
                            unrealized = current_value - size
                        else:
                            # NO position: buy at (1 - yes_entry_price), value at (1 - current_price)
                            no_entry = 1 - yes_entry_price
                            no_current = 1 - current_price
                            shares = size / no_entry if no_entry > 0 else 0
                            current_value = shares * no_current
                            unrealized = current_value - size
                        
                        # Update position with current price
                        # Store the actual price for the side being traded (NO price for NO positions)
                        if side == 'YES':
                            position['current_price'] = round(current_price, 4)
                        else:
                            position['current_price'] = round(1 - current_price, 4)  # NO price
                        position['shares'] = round(shares, 2)
                        position['current_value'] = round(current_value, 2)
                        position['unrealized_pnl'] = round(unrealized, 2)
                        position['unrealized_pnl_pct'] = round(unrealized / size, 4) if size > 0 else 0  # Store as decimal (e.g., -0.279 not -27.9)
                        
                        # Track max drawdown for this position (for reward shaping)
                        current_pnl_pct = position['unrealized_pnl_pct']
                        if current_pnl_pct < 0:
                            # Position is underwater - track how bad it got
                            current_drawdown = abs(current_pnl_pct) * 100  # Convert to percentage for display
                            if current_drawdown > position.get('max_drawdown_pct', 0):
                                position['max_drawdown_pct'] = round(current_drawdown, 2)
                        
                        # Track price extremes
                        if current_price < position.get('min_price_seen', current_price):
                            position['min_price_seen'] = current_price
                        if current_price > position.get('max_price_seen', current_price):
                            position['max_price_seen'] = current_price
                        
                        total_unrealized += unrealized
                    
                    self.unrealized_pnl = round(total_unrealized, 2)
                    
                    # =========================================================
                    # GAMMA EXIT SIGNALS (Task 22)
                    # =========================================================
                    # Check for Free Roll / Moonbag / Stop Loss on whale positions
                    try:
                        gamma_market_prices = {}
                        for m in markets:
                            mid = m.get('id')
                            if mid:
                                gamma_market_prices[mid] = {
                                    'best_bid': float(m.get('yes_price', 0) or 0),
                                    'best_ask': float(m.get('yes_price', 0) or 0) + 0.01,
                                    'yes_price': float(m.get('yes_price', 0) or 0),
                                    'no_price': 1 - float(m.get('yes_price', 0) or 0),
                                }
                        
                        exit_orders = self.gamma_trader.check_exit_signals(
                            active_positions=self.paper_positions,
                            current_market_prices=gamma_market_prices
                        )
                        
                        for exit_order in exit_orders:
                            if exit_order.position_id in self.paper_positions:
                                position = self.paper_positions[exit_order.position_id]
                                logger.info(
                                    f"🐋 [GAMMA EXIT] {exit_order.reason.value} | "
                                    f"Market: {exit_order.market_id[:16]}... | "
                                    f"Selling ${exit_order.size:.2f}"
                                )
                                
                                # Execute exit (simplified - mark position for exit)
                                if exit_order.reason.value == 'free_roll':
                                    # Mark free roll as done, reduce position
                                    position['free_roll_done'] = True
                                    position['size'] = position['size'] - exit_order.size
                                    self.current_capital += exit_order.size * exit_order.price
                                else:
                                    # Full exit (moonbag or stop_loss)
                                    await self._close_position(
                                        exit_order.market_id,
                                        exit_order.price,
                                        f"gamma_{exit_order.reason.value}"
                                    )
                    except Exception as e:
                        logger.debug(f"[GAMMA] Exit signal check error: {e}")
                    
                    # Calculate DEPLOYED capital (sum of position sizes)
                    deployed_capital = sum(p.get('size', 0) for p in self.paper_positions.values())
                    
                    # CIRCUIT BREAKER: Check drawdown based on TOTAL EQUITY (cash + deployed + unrealized)
                    # Equity = cash + position_value + unrealized_pnl
                    # Position value = deployed_capital (what we paid for positions)
                    total_equity = self.current_capital + deployed_capital + self.unrealized_pnl
                    
                    if self.peak_capital > 0:
                        # Drawdown should only trigger if total equity drops below peak
                        # NOT when we simply deploy cash to positions
                        combined_drawdown = (self.peak_capital - total_equity) / self.peak_capital
                        combined_drawdown_pct = combined_drawdown * 100
                        
                        if combined_drawdown_pct >= self.max_drawdown_pct and not self.circuit_breaker_triggered:
                            logger.warning(f"🚨 CIRCUIT BREAKER TRIGGERED! Drawdown {combined_drawdown_pct:.2f}% >= {self.max_drawdown_pct}% limit")
                            logger.warning(f"   Peak: ${self.peak_capital:.2f} | Equity: ${total_equity:.2f} (Cash: ${self.current_capital:.2f} + Deployed: ${deployed_capital:.2f} + Unrealized: ${self.unrealized_pnl:.2f})")
                            self.circuit_breaker_triggered = True
                else:
                    self.unrealized_pnl = 0.0
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(5)
    
    async def _learning_loop(self):
        """Periodic RL learning from replay buffer - more aggressive in continuous mode"""
        last_trade_count = 0
        
        while self.running:
            try:
                # Train from replay buffer
                await self.rl_engine.train_from_replay()
                
                # In continuous mode, learn more aggressively
                learning_interval = 30 if self.continuous_mode else 60
                
                # Save model periodically (every 10 trades or every 5 minutes in continuous mode)
                trades_since_last_save = self.total_trades - last_trade_count
                if self.total_trades > 0:
                    should_save = (
                        trades_since_last_save >= 10 or 
                        (self.continuous_mode and trades_since_last_save >= 5)
                    )
                    if should_save:
                        await self.rl_engine.save_model()
                        last_trade_count = self.total_trades
                        logger.info(f"RL model saved - {self.total_trades} total trades, continuous={self.continuous_mode}")
                
                # Update cumulative stats in database for running totals
                await self._update_cumulative_stats()
                
                await asyncio.sleep(learning_interval)
                
            except Exception as e:
                logger.error(f"Error in learning loop: {e}")
                await asyncio.sleep(30)
    
    async def _update_cumulative_stats(self):
        """Update cumulative trading stats across all sessions"""
        try:
            # Update cumulative strategy stats
            for strategy, stats in self.strategy_stats.items():
                if stats['trades'] > 0:
                    await self.db.cumulative_stats.update_one(
                        {"type": "strategy", "name": strategy},
                        {
                            "$inc": {
                                "total_trades": 0,  # Don't double count, just ensure doc exists
                            },
                            "$set": {
                                "last_updated": datetime.now(timezone.utc).isoformat(),
                                "last_session_id": self.session_id
                            },
                            "$setOnInsert": {
                                "type": "strategy",
                                "name": strategy,
                                "created": datetime.now(timezone.utc).isoformat()
                            }
                        },
                        upsert=True
                    )
            
            # Update cumulative asset class stats
            for asset_class, stats in self.asset_class_stats.items():
                if stats['trades'] > 0:
                    await self.db.cumulative_stats.update_one(
                        {"type": "asset_class", "name": asset_class},
                        {
                            "$set": {
                                "last_updated": datetime.now(timezone.utc).isoformat(),
                                "last_session_id": self.session_id
                            },
                            "$setOnInsert": {
                                "type": "asset_class",
                                "name": asset_class,
                                "created": datetime.now(timezone.utc).isoformat()
                            }
                        },
                        upsert=True
                    )
        except Exception as e:
            logger.debug(f"Error updating cumulative stats: {e}")
    
    async def _close_all_positions(self):
        """Close all open paper positions at current market prices"""
        markets = await self._get_active_markets()
        
        # Build lookup map using both 'id' and 'condition_id' since markets use different identifiers
        market_data_map = {}
        for m in markets:
            if m.get('id'):
                market_data_map[m['id']] = m
            if m.get('condition_id'):
                market_data_map[m['condition_id']] = m
        
        logger.info(f"[CLOSE_ALL] Closing {len(self.paper_positions)} positions, {len(markets)} markets in lookup")
        
        for market_id in list(self.paper_positions.keys()):
            position = self.paper_positions[market_id]
            market_data = market_data_map.get(market_id)
            
            # Get position's stored prices for comparison
            pos_entry = position.get('entry_price', 0)  # Display entry price (NO price for NO positions)
            pos_current = position.get('current_price')  # Display current price (NO price for NO positions)
            pos_side = position.get('side', 'YES')
            pos_yes_entry = position.get('yes_entry_price')  # Internal YES entry price
            
            # Debug: log position prices
            logger.debug(f"[CLOSE_ALL] Position {market_id[:16]}: side={pos_side}, entry={pos_entry}, current={pos_current}, yes_entry={pos_yes_entry}")
            
            # Calculate what the YES price should be based on position data
            if pos_side == 'YES':
                # For YES positions, current_price is YES price directly
                pos_yes_current = pos_current if pos_current else pos_yes_entry
            else:
                # For NO positions, current_price is NO price, so convert to YES
                if pos_current:
                    pos_yes_current = 1 - pos_current  # Convert NO price back to YES
                else:
                    # Fallback: use entry YES price (no change)
                    pos_yes_current = pos_yes_entry if pos_yes_entry else (1 - pos_entry if pos_entry else None)
            
            if market_data:
                fresh_yes_price = market_data.get('yes_price')
                
                # STRICT: Require valid fresh price for closing
                if fresh_yes_price is None or fresh_yes_price == 0:
                    logger.warning(f"[CLOSE_ALL] No valid fresh price for {market_id[:16]} - using position's last known price")
                    # Use position's computed current price
                    if pos_yes_current is not None:
                        market_data = {
                            'yes_price': pos_yes_current,
                            'id': market_id,
                            'question': position.get('market_question', 'Unknown')
                        }
                    else:
                        logger.error(f"[CLOSE_ALL] Cannot close {market_id[:16]} - no valid price available")
                        continue
                else:
                    fresh_yes_price = float(fresh_yes_price)
                    price_diff = abs(fresh_yes_price - pos_yes_current) if pos_yes_current else 0
                    
                    if price_diff > 0.1:  # More than 10% price difference - suspicious
                        logger.warning(f"[CLOSE_ALL] LARGE PRICE DIFF for {market_id[:16]}: "
                                     f"Fresh YES={fresh_yes_price:.4f}, Computed Position YES={pos_yes_current:.4f}, "
                                     f"Diff={price_diff:.4f}")
                        logger.info(f"[CLOSE_ALL] Raw position data: current_price={pos_current}, yes_entry={pos_yes_entry}, side={pos_side}")
                        # Use position's last known price instead of suspicious fresh price
                        market_data = {
                            'yes_price': pos_yes_current,
                            'id': market_id,
                            'question': position.get('market_question', 'Unknown')
                        }
                        logger.info(f"[CLOSE_ALL] Using computed position YES price: {pos_yes_current:.4f}")
            else:
                # Market not found in fresh fetch - use position's last known price
                logger.warning(f"[CLOSE_ALL] Market {market_id[:16]} not in fresh fetch - using last known price")
                
                # Reconstruct market data from position's current_price if available
                if pos_current and pos_side == 'NO':
                    yes_price = 1 - pos_current
                elif pos_current:
                    yes_price = pos_current
                else:
                    yes_price = pos_yes_entry
                    logger.warning(f"[CLOSE_ALL] Using entry price {yes_price:.4f} as exit - no P&L change")
                
                market_data = {
                    'yes_price': yes_price,
                    'id': market_id,
                    'question': position.get('market_question', 'Unknown')
                }
            
            await self._execute_paper_exit(market_id, market_data, "session_end")
    
    async def _save_session_results(self):
        """Save paper trading session results to database"""
        try:
            win_rate = self.winning_trades / max(self.total_trades, 1)
            
            # Calculate session duration
            end_time = datetime.now(timezone.utc)
            if self.session_start_time:
                duration_seconds = int((end_time - self.session_start_time).total_seconds())
            else:
                duration_seconds = 0
            
            session_results = {
                "session_id": self.session_id,
                "type": "paper_trading",
                "end_time": end_time.isoformat(),
                "duration_seconds": duration_seconds,
                "status": "completed",
                "initial_capital": float(self.initial_capital),
                "deployed_capital_limit": float(self.deployed_capital),  # Max allowed deployment from config
                "final_capital": float(self.current_capital),
                "total_pnl": float(self.total_pnl),
                "total_pnl_pct": float((self.total_pnl / self.deployed_capital) * 100) if self.deployed_capital > 0 else 0,
                "total_pnl_pct_on_total": float((self.total_pnl / self.initial_capital) * 100),
                "total_trades": int(self.total_trades),
                "winning_trades": int(self.winning_trades),
                "win_rate": float(win_rate),
                "max_drawdown": float(self.max_drawdown),
                "strategy_stats": sanitize_for_json(self.strategy_stats),
                "asset_class_stats": sanitize_for_json(self.asset_class_stats),
                "closed_trades": sanitize_for_json(self.closed_trades[-100:])  # Last 100 trades
            }
            
            await self.db.paper_trading_sessions.update_one(
                {"session_id": self.session_id},
                {"$set": session_results}
            )
            
            logger.info(f"Paper Trading Session Saved: {self.session_id}")
            
        except Exception as e:
            logger.error(f"Error saving session results: {e}")
    
    async def _learn_from_session(self):
        """Final RL learning from entire session"""
        try:
            # Learn from all closed trades
            for trade in self.closed_trades:
                reward = trade.get('reward_signal', 0)
                await self.rl_engine.update_from_reward(trade['market_id'], reward)
            
            # Batch training
            await self.rl_engine.train_from_replay()
            await self.rl_engine.save_model()
            
            logger.info(f"RL learned from {len(self.closed_trades)} paper trades")
            
        except Exception as e:
            logger.error(f"Error in session learning: {e}")
    
    async def _get_active_markets(self) -> List[Dict]:
        """
        Get active markets with DUAL-ZONE quality filters.
        
        Task 21: Dual-Zone Risk Architecture
        - WHALE ZONE (price < $0.10): Lower volume threshold, tick-based spread
        - CORE ZONE (price >= $0.10): Higher volume threshold, percentage spread
        
        Uses WebSocket service for real-time data when available,
        falls back to REST API polling when WebSocket is unavailable.
        """
        try:
            # ================================================================
            # QUALITY CONTROL - From risk_config.py (Single Source of Truth)
            # ================================================================
            TOP_N_MARKETS = RISK.TOP_N_MARKETS
            
            live_markets = []
            data_source = "REST"
            cycle_count = getattr(self, '_cycle_count', 0)
            
            # Quality metrics for this fetch
            quality_stats = {
                'total_fetched': 0,
                'rejected_low_volume': 0,
                'rejected_extreme_price': 0,
                'rejected_low_liquidity': 0,
                'rejected_no_price': 0,
                'passed_quality': 0,
                'whale_zone_count': 0,
                'core_zone_count': 0,
            }
            
            # Try WebSocket service first for faster, real-time data
            if self.use_websocket_data and self.realtime_market_service:
                try:
                    ws_markets = self.realtime_market_service.get_markets(limit=200)
                    if ws_markets and len(ws_markets) > 10:
                        live_markets = ws_markets
                        data_source = "WebSocket"
                        
                        # Get stats for logging
                        ws_stats = self.realtime_market_service.get_stats()
                        if cycle_count % 50 == 1:  # Log every 50 cycles
                            logger.info(f"📡 WebSocket data: {ws_stats.get('ws_updates', 0)} updates, "
                                       f"{ws_stats.get('prices_cached', 0)} prices cached")
                except Exception as e:
                    logger.warning(f"WebSocket fetch failed: {e} - falling back to REST")
            
            # Fall back to REST API if WebSocket data not available
            if not live_markets:
                from data.polymarket_api import PolymarketAPI
                async with PolymarketAPI() as api:
                    live_markets = await api.get_markets(limit=200)
                    data_source = "REST"
            
            if not live_markets:
                logger.warning(f"No markets returned from {data_source}")
                return []
            
            quality_stats['total_fetched'] = len(live_markets)
            
            # ================================================================
            # PRE-FLIGHT QUALITY CONTROL - The "Bouncer" (Category-Aware)
            # ================================================================
            # Task 21: Different thresholds for Whale Zone vs Core Zone
            # Task: Sports Strategy - Dynamic overrides for sports markets
            
            # Get sports config for dynamic overrides
            sports_config = get_sports_config()
            
            quality_markets = []
            sports_markets_passed = 0
            
            for m in live_markets:
                market_id = m.get('id', 'unknown')[:16]
                question = m.get('question', '')
                
                # ==========================================================
                # CATEGORY DETECTION (Sports Green Lane)
                # ==========================================================
                is_sports = is_sports_market(question)
                
                # PRICE VALIDATION (First - cheapest check)
                yes_price = m.get('yes_price')
                if yes_price is None or yes_price == 0:
                    quality_stats['rejected_no_price'] += 1
                    continue
                
                yes_price = float(yes_price)
                
                # ==========================================================
                # DYNAMIC PRICE CAPS (Sports Override)
                # ==========================================================
                # Sports: Allow heavy favorites (0.98-0.99) and longshots (0.01)
                # Non-Sports: Standard kill switch (0.03-0.97)
                if is_sports and sports_config.enabled:
                    safe_min = sports_config.min_price_cap
                    safe_max = sports_config.max_price_cap
                else:
                    safe_min = RISK.KILL_SWITCH_LOW
                    safe_max = RISK.KILL_SWITCH_HIGH
                
                if yes_price < safe_min:
                    quality_stats['rejected_extreme_price'] += 1
                    continue
                if yes_price > safe_max:
                    quality_stats['rejected_extreme_price'] += 1
                    continue
                
                # ============================================================
                # DYNAMIC VOLUME/LIQUIDITY CHECK (Sports Override)
                # ============================================================
                volume_24h = float(m.get('volume_24h', 0) or 0)
                liquidity = float(m.get('liquidity', 0) or 0)
                
                # Sports markets use sports_config thresholds (lower)
                # Non-sports use zone-specific thresholds
                if is_sports and sports_config.enabled:
                    min_volume = sports_config.min_volume
                    min_liquidity = sports_config.min_liquidity
                else:
                    zone_params = get_zone_parameters(yes_price)
                    min_volume = zone_params['min_volume']
                    min_liquidity = zone_params['min_liquidity']
                
                if volume_24h < min_volume:
                    quality_stats['rejected_low_volume'] += 1
                    continue
                
                if liquidity < min_liquidity:
                    quality_stats['rejected_low_liquidity'] += 1
                    continue
                
                # Track zone distribution
                if yes_price < RISK.WHALE_PRICE_CEILING:
                    quality_stats['whale_zone_count'] += 1
                else:
                    quality_stats['core_zone_count'] += 1
                
                # Track sports markets separately
                if is_sports:
                    sports_markets_passed += 1
                    m['_is_sports'] = True  # Flag for routing
                
                # Market passed category-aware quality checks!
                quality_markets.append(m)
            
            quality_stats['passed_quality'] = len(quality_markets)
            quality_stats['sports_markets'] = sports_markets_passed
            
            # ================================================================
            # SORT BY VOLUME & TAKE TOP N
            # ================================================================
            # Focus on the most liquid markets for best execution
            quality_markets = sorted(
                quality_markets,
                key=lambda x: float(x.get('volume_24h', 0) or 0),
                reverse=True
            )[:TOP_N_MARKETS]
            
            # ================================================================
            # QUALITY CONTROL LOGGING
            # ================================================================
            if cycle_count % 20 == 1:
                rejection_rate = 1 - (quality_stats['passed_quality'] / max(quality_stats['total_fetched'], 1))
                logger.info(
                    f"🔍 [QUALITY CONTROL] {data_source}: {quality_stats['passed_quality']}/{quality_stats['total_fetched']} passed "
                    f"({rejection_rate:.0%} rejected) | Top {len(quality_markets)} by volume"
                )
                if quality_stats['rejected_extreme_price'] > 0:
                    logger.info(f"   └─ Extreme prices: {quality_stats['rejected_extreme_price']} (settled/dead markets)")
                if quality_stats['rejected_low_volume'] > 0:
                    logger.info(f"   └─ Low volume: {quality_stats['rejected_low_volume']} (ghost towns)")
            
            # Store quality stats for status endpoint
            self._last_quality_stats = quality_stats
            
            # Cache top markets in DB for analytics (less frequently)
            if quality_markets and cycle_count % 100 == 1:
                for m in quality_markets[:50]:
                    yes_price = m.get('yes_price')
                    if yes_price is None:
                        continue  # Skip markets without valid prices
                    
                    market_doc = {
                        "condition_id": m.get('condition_id') or m.get('id'),
                        "id": m.get('id'),
                        "question": m.get('question', ''),
                        "category": m.get('category', 'unknown'),
                        "yes_price": float(yes_price),
                        "no_price": float(m.get('no_price', 1 - float(yes_price))),
                        "liquidity": float(m.get('liquidity', 0) or 0),
                        "volume": float(m.get('volume', 0) or 0),
                        "volume_24h": float(m.get('volume_24h', 0) or 0),
                        "spread": float(m.get('spread', 0) or 0),
                        "end_date": m.get('end_date'),
                        "active": m.get('active', True),
                        "data_source": data_source,
                        "quality_pass": True,
                        "last_update": datetime.now(timezone.utc).isoformat()
                    }
                    await self.db.markets.update_one(
                        {"condition_id": market_doc['condition_id']},
                        {"$set": market_doc},
                        upsert=True
                    )
            
            return quality_markets
            
        except Exception as e:
            logger.error(f"Error getting markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def update_alpha_weights(self, new_weights: Dict) -> Dict:
        """
        Update Alpha model weights at runtime (Task 19: Dynamic Alpha Tuning).
        
        This allows real-time tuning of how much each signal source influences
        the Bayesian probability calculation:
        - sentiment_weight: LLM/news sentiment influence (default 0.50)
        - rl_weight: Reinforcement learning model influence (default 0.60)
        - sentiment_neutral_low/high: Neutral band bounds (default 0.45-0.55)
        - max_sentiment_delta: Safety cap for extreme sentiment moves
        - min_rl_confidence: Minimum RL confidence to act on signals
        
        Args:
            new_weights: Dict with weight keys to update
            
        Returns:
            Dict with updated weights and status
        """
        valid_keys = [
            'sentiment_weight', 'rl_weight', 'sharp_weight',
            'sentiment_neutral_low', 'sentiment_neutral_high',
            'max_sentiment_delta', 'min_rl_confidence'
        ]
        
        updated = {}
        errors = []
        
        for key, value in new_weights.items():
            if key not in valid_keys:
                errors.append(f"Unknown weight key: {key}")
                continue
            
            try:
                # Validate ranges
                val = float(value)
                if key in ['sentiment_weight', 'rl_weight', 'sharp_weight']:
                    if not (0.0 <= val <= 2.0):
                        errors.append(f"{key} must be between 0.0 and 2.0")
                        continue
                elif key in ['sentiment_neutral_low', 'sentiment_neutral_high']:
                    if not (0.0 <= val <= 1.0):
                        errors.append(f"{key} must be between 0.0 and 1.0")
                        continue
                elif key == 'max_sentiment_delta':
                    if not (0.1 <= val <= 10.0):
                        errors.append(f"{key} must be between 0.1 and 10.0")
                        continue
                elif key == 'min_rl_confidence':
                    if not (0.0 <= val <= 1.0):
                        errors.append(f"{key} must be between 0.0 and 1.0")
                        continue
                
                self.alpha_weights[key] = val
                updated[key] = val
            except ValueError:
                errors.append(f"Invalid value for {key}: {value}")
        
        logger.info(f"[ALPHA TUNING] Updated weights: {updated}")
        
        return {
            "success": len(errors) == 0,
            "updated": updated,
            "errors": errors,
            "current_weights": self.alpha_weights.copy()
        }
    
    def get_alpha_weights(self) -> Dict:
        """Get current Alpha model weights."""
        return self.alpha_weights.copy()
    
    def get_status(self) -> Dict:
        """Get current paper trading status with full analytics"""
        win_rate = self.winning_trades / max(self.total_trades, 1)
        
        # Calculate session duration
        if self.session_start_time:
            duration_seconds = int((datetime.now(timezone.utc) - self.session_start_time).total_seconds())
        else:
            duration_seconds = 0
        
        # =================================================================
        # RECALCULATE UNREALIZED P&L ON-DEMAND FOR ACCURACY
        # =================================================================
        # Don't rely on cached position values - calculate fresh using latest prices
        total_unrealized = 0.0
        for market_id, position in self.paper_positions.items():
            size = position.get('size', 0)
            if size <= 0:
                continue
                
            side = position.get('side', 'YES')
            yes_entry_price = position.get('yes_entry_price', position.get('entry_price', 0))
            
            # Get current price from market data if available, else use stored current_price
            current_price = position.get('current_price', yes_entry_price)
            
            # For NO positions, current_price is stored as NO price, convert back to YES price for calculation
            if side == 'NO' and current_price < 1:
                # current_price is already the NO price, YES price = 1 - NO price
                yes_current = 1 - current_price
            else:
                yes_current = current_price
            
            # Calculate unrealized P&L
            if side == 'YES':
                shares = size / yes_entry_price if yes_entry_price > 0 else 0
                current_value = shares * yes_current
                unrealized = current_value - size
            else:
                no_entry = 1 - yes_entry_price
                no_current = 1 - yes_current
                shares = size / no_entry if no_entry > 0 else 0
                current_value = shares * no_current
                unrealized = current_value - size
            
            # Update position with fresh calculation
            position['unrealized_pnl'] = round(unrealized, 2)
            total_unrealized += unrealized
        
        self.unrealized_pnl = round(total_unrealized, 2)
        
        # Calculate strategy results with profit factors (like backtest)
        # Include unrealized P&L from open positions
        strategy_results = {}
        
        # Calculate unrealized P&L by strategy from open positions
        strategy_unrealized = {}
        strategy_open_positions = {}
        for pos in self.paper_positions.values():
            strategy = pos.get('strategy', 'unknown')
            if strategy not in strategy_unrealized:
                strategy_unrealized[strategy] = 0.0
                strategy_open_positions[strategy] = 0
            strategy_unrealized[strategy] += pos.get('unrealized_pnl', 0)
            strategy_open_positions[strategy] += 1
        
        # Build results from pre-initialized strategy_stats (single source of truth)
        for strategy, stats in self.strategy_stats.items():
            trades = stats.get('trades', 0)
            wins = stats.get('wins', 0)
            pnl = stats.get('pnl', 0)
            gross_profit = stats.get('gross_profit', 0)
            gross_loss = stats.get('gross_loss', 0)
            unrealized = strategy_unrealized.get(strategy, 0)
            open_pos = strategy_open_positions.get(strategy, 0)
            total_hold_time = stats.get('total_hold_time', 0)
            closed_trades = stats.get('closed_trades', 0)
            avg_hold_time = total_hold_time / closed_trades if closed_trades > 0 else 0
            
            # Only include strategies with activity (trades or open positions)
            if trades > 0 or open_pos > 0:
                strategy_results[strategy] = {
                    'trades': trades,  # Closed trades
                    'open_positions': open_pos,
                    'wins': wins,
                    'pnl': pnl,  # Realized P&L (closed)
                    'unrealized_pnl': round(unrealized, 2),  # Live P&L (open)
                    'total_pnl': round(pnl + unrealized, 2),  # Total P&L
                    'win_rate': wins / trades if trades > 0 else 0,
                    'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else (2.0 if gross_profit > 0 else 0),
                    'avg_hold_time': round(avg_hold_time, 2),  # Average hold time in hours
                    'gross_profit': gross_profit,
                    'gross_loss': gross_loss
                }
        
        # ==============================================================
        # TWO-SPEED ARCHITECTURE: HFT vs ALPHA BREAKDOWN
        # ==============================================================
        # HFT Path: delta_neutral, volatility_exploitation (fast, reactive)
        # Alpha Path: alpha_directional, arbitrage (slower, ML-driven)
        HFT_STRATEGIES = {'delta_neutral', 'volatility_exploitation'}
        ALPHA_STRATEGIES = {'alpha_directional', 'arbitrage'}
        
        # Aggregate by execution path
        hft_stats = {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
        alpha_stats = {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
        
        for strategy, stats in self.strategy_stats.items():
            if strategy in HFT_STRATEGIES:
                hft_stats['trades'] += stats.get('trades', 0)
                hft_stats['wins'] += stats.get('wins', 0)
                hft_stats['pnl'] += stats.get('pnl', 0)
                hft_stats['gross_profit'] += stats.get('gross_profit', 0)
                hft_stats['gross_loss'] += stats.get('gross_loss', 0)
            elif strategy in ALPHA_STRATEGIES:
                alpha_stats['trades'] += stats.get('trades', 0)
                alpha_stats['wins'] += stats.get('wins', 0)
                alpha_stats['pnl'] += stats.get('pnl', 0)
                alpha_stats['gross_profit'] += stats.get('gross_profit', 0)
                alpha_stats['gross_loss'] += stats.get('gross_loss', 0)
        
        # Calculate HFT/Alpha capital allocation
        hft_capital = self.deployed_capital * (self.hft_allocation_pct / 100)
        alpha_capital = self.deployed_capital * (self.alpha_allocation_pct / 100)
        
        # Calculate deployed capital by path (from open positions)
        hft_deployed = sum(
            p.get('size', 0) for p in self.paper_positions.values()
            if p.get('strategy') in HFT_STRATEGIES
        )
        alpha_deployed = sum(
            p.get('size', 0) for p in self.paper_positions.values()
            if p.get('strategy') in ALPHA_STRATEGIES
        )
        
        # Calculate unrealized P&L by path
        hft_unrealized = sum(
            p.get('unrealized_pnl', 0) for p in self.paper_positions.values()
            if p.get('strategy') in HFT_STRATEGIES
        )
        alpha_unrealized = sum(
            p.get('unrealized_pnl', 0) for p in self.paper_positions.values()
            if p.get('strategy') in ALPHA_STRATEGIES
        )
        
        execution_path_stats = {
            'hft': {
                'name': 'HFT (Fast Path)',
                'strategies': list(HFT_STRATEGIES),
                'allocated_capital': round(hft_capital, 2),
                'deployed_capital': round(hft_deployed, 2),
                'utilization_pct': round((hft_deployed / hft_capital * 100) if hft_capital > 0 else 0, 1),
                'realized_pnl': round(hft_stats['pnl'], 2),
                'unrealized_pnl': round(hft_unrealized, 2),
                'total_pnl': round(hft_stats['pnl'] + hft_unrealized, 2),
                'return_pct': round((hft_stats['pnl'] / hft_capital * 100) if hft_capital > 0 else 0, 2),
                'total_return_pct': round(((hft_stats['pnl'] + hft_unrealized) / hft_capital * 100) if hft_capital > 0 else 0, 2),
                'trades': hft_stats['trades'],
                'wins': hft_stats['wins'],
                'win_rate': round(hft_stats['wins'] / hft_stats['trades'] * 100 if hft_stats['trades'] > 0 else 0, 1),
                'profit_factor': round(hft_stats['gross_profit'] / hft_stats['gross_loss'] if hft_stats['gross_loss'] > 0 else (2.0 if hft_stats['gross_profit'] > 0 else 0), 2)
            },
            'alpha': {
                'name': 'Alpha (Slow Path)',
                'strategies': list(ALPHA_STRATEGIES),
                'allocated_capital': round(alpha_capital, 2),
                'deployed_capital': round(alpha_deployed, 2),
                'utilization_pct': round((alpha_deployed / alpha_capital * 100) if alpha_capital > 0 else 0, 1),
                'realized_pnl': round(alpha_stats['pnl'], 2),
                'unrealized_pnl': round(alpha_unrealized, 2),
                'total_pnl': round(alpha_stats['pnl'] + alpha_unrealized, 2),
                'return_pct': round((alpha_stats['pnl'] / alpha_capital * 100) if alpha_capital > 0 else 0, 2),
                'total_return_pct': round(((alpha_stats['pnl'] + alpha_unrealized) / alpha_capital * 100) if alpha_capital > 0 else 0, 2),
                'trades': alpha_stats['trades'],
                'wins': alpha_stats['wins'],
                'win_rate': round(alpha_stats['wins'] / alpha_stats['trades'] * 100 if alpha_stats['trades'] > 0 else 0, 1),
                'profit_factor': round(alpha_stats['gross_profit'] / alpha_stats['gross_loss'] if alpha_stats['gross_loss'] > 0 else (2.0 if alpha_stats['gross_profit'] > 0 else 0), 2)
            }
        }
        
        # Calculate asset class results with profit factors
        # Include unrealized P&L from open positions
        asset_class_results = {}
        
        # Calculate unrealized P&L by asset class from open positions
        asset_class_unrealized = {}
        asset_class_open_positions = {}
        for pos in self.paper_positions.values():
            ac = pos.get('asset_class', 'unknown')
            if ac not in asset_class_unrealized:
                asset_class_unrealized[ac] = 0.0
                asset_class_open_positions[ac] = 0
            asset_class_unrealized[ac] += pos.get('unrealized_pnl', 0)
            asset_class_open_positions[ac] += 1
        
        # Build results from pre-initialized asset_class_stats (single source of truth)
        for asset_class, stats in self.asset_class_stats.items():
            trades = stats.get('trades', 0)
            wins = stats.get('wins', 0)
            pnl = stats.get('pnl', 0)
            gross_profit = stats.get('gross_profit', 0)
            gross_loss = stats.get('gross_loss', 0)
            unrealized = asset_class_unrealized.get(asset_class, 0)
            open_pos = asset_class_open_positions.get(asset_class, 0)
            total_hold_time = stats.get('total_hold_time', 0)
            closed_trades = stats.get('closed_trades', 0)
            avg_hold_time = total_hold_time / closed_trades if closed_trades > 0 else 0
            
            # Only include asset classes with activity (trades or open positions)
            if trades > 0 or open_pos > 0:
                asset_class_results[asset_class] = {
                    'trades': trades,  # Closed trades
                    'open_positions': open_pos,
                    'wins': wins,
                    'pnl': pnl,  # Realized P&L (closed)
                    'unrealized_pnl': round(unrealized, 2),  # Live P&L (open)
                    'total_pnl': round(pnl + unrealized, 2),  # Total P&L
                    'win_rate': wins / trades if trades > 0 else 0,
                    'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else (2.0 if gross_profit > 0 else 0),
                    'avg_hold_time': round(avg_hold_time, 2),  # Average hold time in hours
                    'gross_profit': gross_profit,
                    'gross_loss': gross_loss
                }
        
        # Calculate returns distribution (realized trades)
        returns_distribution = self._calculate_returns_distribution()
        
        # Calculate unrealized P&L distribution (open positions)
        unrealized_returns = []
        for pos in self.paper_positions.values():
            if pos.get('size', 0) > 0:
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)
                side = pos.get('side', 'YES')
                
                # Calculate unrealized return %
                if side == 'YES':
                    if entry > 0:
                        pnl_pct = ((current - entry) / entry) * 100
                    else:
                        pnl_pct = 0
                else:  # NO position
                    no_entry = 1 - entry
                    no_current = 1 - current
                    if no_entry > 0:
                        pnl_pct = ((no_current - no_entry) / no_entry) * 100
                    else:
                        pnl_pct = 0
                
                unrealized_returns.append(pnl_pct)
        
        unrealized_distribution = self._calculate_distribution_from_returns(unrealized_returns) if unrealized_returns else {}
        
        # Calculate total P&L including unrealized
        combined_pnl = self.total_pnl + self.unrealized_pnl
        
        # Calculate ACTUAL deployed capital (sum of open position sizes)
        actual_deployed = sum(p.get('size', 0) for p in self.paper_positions.values())
        
        # Calculate total equity = cash + deployed + unrealized
        total_equity = self.current_capital + actual_deployed + self.unrealized_pnl
        
        # Calculate TRUE drawdown based on total equity, not just cash
        true_drawdown_pct = ((self.peak_capital - total_equity) / self.peak_capital * 100) if self.peak_capital > 0 else 0
        
        return {
            "session_id": self.session_id,
            "running": self.running,
            "start_time": self.session_start_time.isoformat() if self.session_start_time else None,
            "duration_seconds": duration_seconds,
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,  # Highest capital reached
            "total_equity": round(total_equity, 2),  # Cash + Deployed + Unrealized
            "current_drawdown_pct": round(max(0, true_drawdown_pct), 2),  # True drawdown based on equity
            "deployed_capital": round(actual_deployed, 2),  # ACTUAL deployed (sum of position sizes)
            "max_deployed_capital": self.deployed_capital,  # Max allowed deployment (config setting)
            "total_pnl": self.total_pnl,  # Realized P&L (closed trades)
            "unrealized_pnl": self.unrealized_pnl,  # Unrealized P&L (open positions)
            "combined_pnl": combined_pnl,  # Total = Realized + Unrealized
            # Return percentages based on deployed capital (what was actually risked)
            "total_pnl_pct": (self.total_pnl / self.deployed_capital) * 100 if self.deployed_capital > 0 else 0,
            "combined_pnl_pct": (combined_pnl / self.deployed_capital) * 100 if self.deployed_capital > 0 else 0,
            # Also show returns based on total capital for reference
            "total_pnl_pct_on_total": (self.total_pnl / self.initial_capital) * 100,
            "combined_pnl_pct_on_total": (combined_pnl / self.initial_capital) * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "max_drawdown": self.max_drawdown,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,  # Whether max drawdown was hit
            "open_positions": len(self.paper_positions),
            "strategy_results": strategy_results,
            "asset_class_results": asset_class_results,
            "execution_path_stats": execution_path_stats,  # HFT vs Alpha breakdown
            "returns_distribution": returns_distribution,  # Realized trades distribution
            "unrealized_distribution": unrealized_distribution,  # Open positions distribution
            "pnl_distribution": returns_distribution if returns_distribution.get('bins') else unrealized_distribution,  # For backward compat
            "trade_returns": self.trade_returns[-100:],  # Last 100 returns for charts
            "equity_curve": self.equity_curve[-200:],  # Last 200 points for better charts
            "strategy_equity": self.strategy_equity,  # Running P&L by strategy
            "lane_equity": self.lane_equity,  # Three-Speed Lane P&L (HFT/ALPHA/GAMMA)
            "asset_class_equity": self.asset_class_equity,  # Running P&L by asset class
            "enabled_strategies": self.enabled_strategies,
            "enabled_asset_classes": self.enabled_asset_classes,
            "continuous_mode": self.continuous_mode,
            "graceful_stop": self.graceful_stop,
            # =============================================================
            # TWO-SPEED ARCHITECTURE: Health Metrics
            # =============================================================
            "two_speed_architecture": {
                "active_regime": "HYBRID_PARALLEL",  # Both loops running
                "hft_loop_active": self.running,
                "alpha_loop_active": self.running,
                "alpha_targets_count": len(self.strategy_context.get_all_targets()) if hasattr(self, 'strategy_context') else 0,
                "bridge_stats": self.strategy_context.get_stats() if hasattr(self, 'strategy_context') else {},
            },
            # QUALITY CONTROL: Market filtering metrics (Task 18)
            # =============================================================
            "quality_control": {
                "markets_fetched": self._last_quality_stats.get('total_fetched', 0),
                "markets_passed": self._last_quality_stats.get('passed_quality', 0),
                "rejection_rate": round(1 - (self._last_quality_stats.get('passed_quality', 0) / max(self._last_quality_stats.get('total_fetched', 1), 1)), 3),
                "rejected_low_volume": self._last_quality_stats.get('rejected_low_volume', 0),
                "rejected_extreme_price": self._last_quality_stats.get('rejected_extreme_price', 0),
                "rejected_low_liquidity": self._last_quality_stats.get('rejected_low_liquidity', 0),
                "rejected_no_price": self._last_quality_stats.get('rejected_no_price', 0),
            },
            # ALPHA MODEL WEIGHTS (Task 19: Dynamic Alpha Tuning)
            # Shows "Who is driving the car" - sentiment (News Reader) vs RL (Math Geek)
            "alpha_weights": self.alpha_weights.copy(),
            # Configuration parameters being used
            "config": {
                "initial_capital": self.initial_capital,
                "capital_deployment_pct": self.capital_deployment_pct,
                "max_position_size_pct": self.max_position_size_pct,
                "max_position_size": self.max_position_size,
                "kelly_fraction": self.kelly_fraction,
                "max_drawdown_pct": self.max_drawdown_pct,
                "trades_per_10min": self.trades_per_10min,
                "trade_interval_seconds": self.trade_interval
            },
            # Dynamic exit mode settings
            "exit_mode": {
                "use_dynamic_exit": self.use_dynamic_exit,
                "mode_name": "Dynamic (Time-Aware)" if self.use_dynamic_exit else "Simple (Configurable)",
                "dynamic_config": self.dynamic_exit_config if self.use_dynamic_exit else None,
                "time_entry_config": self.time_entry_config if self.use_dynamic_exit else None
            },
            # Position sizer learning stats
            "position_sizer_learning": self.position_sizer.get_learning_stats() if hasattr(self, 'position_sizer') else {},
            "ai_learning": {
                "rl_updates_this_session": len(self.closed_trades),
                "learning_active": self.running,
                "learning_immediately_applied": True,  # Q-table updates are immediate
                "signals_used": ["volatility", "sentiment", "sharp_alignment"],
                "strategies_learning": self.enabled_strategies
            }
        }
    
    async def get_ai_stats(self) -> Dict:
        """Get detailed AI/ML statistics for the paper trading session"""
        try:
            rl_stats = await self.rl_engine.get_training_stats()
            return {
                "rl_stats": rl_stats,
                "session_learning": {
                    "trades_fed_to_rl": len(self.closed_trades),
                    "total_reward_signals": sum(t.get('reward_signal', 0) for t in self.closed_trades),
                    "avg_reward": sum(t.get('reward_signal', 0) for t in self.closed_trades) / max(len(self.closed_trades), 1),
                    "positive_rewards": sum(1 for t in self.closed_trades if t.get('reward_signal', 0) > 0),
                    "negative_rewards": sum(1 for t in self.closed_trades if t.get('reward_signal', 0) < 0)
                },
                "signal_usage": {
                    "volatility_signals": self.total_trades,
                    "sentiment_signals": self.total_trades,
                    "sharp_signals": self.total_trades
                }
            }
        except Exception as e:
            logger.error(f"Error getting AI stats: {e}")
            return {}
    
    def _calculate_returns_distribution(self) -> Dict:
        """Calculate returns distribution histogram like backtest"""
        return self._calculate_distribution_from_returns(self.trade_returns)
    
    def _calculate_distribution_from_returns(self, returns: List[float]) -> Dict:
        """Calculate returns distribution histogram from any returns array"""
        if not returns:
            return {"bins": [], "stats": {}}
        
        # Create histogram bins
        bins = []
        bin_edges = [-50, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 50]
        
        for i in range(len(bin_edges) - 1):
            min_val = bin_edges[i]
            max_val = bin_edges[i + 1]
            count = sum(1 for r in returns if min_val <= r < max_val)
            bins.append({
                "min": min_val,
                "max": max_val,
                "label": f"{min_val}% to {max_val}%",
                "count": count
            })
        
        # Calculate stats
        returns_array = np.array(returns)
        stats = {
            "mean": float(np.mean(returns_array)),
            "median": float(np.median(returns_array)),
            "std": float(np.std(returns_array)),
            "positive_returns": sum(1 for r in returns if r > 0),
            "negative_returns": sum(1 for r in returns if r < 0),
            "skewness": float(self._calculate_skewness(returns_array)),
            "kurtosis": float(self._calculate_kurtosis(returns_array))
        }
        
        return {"bins": bins, "stats": stats}
    
    def _calculate_skewness(self, data: np.ndarray) -> float:
        """Calculate skewness of returns"""
        if len(data) < 3:
            return 0.0
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 3))
    
    def _calculate_kurtosis(self, data: np.ndarray) -> float:
        """Calculate kurtosis of returns"""
        if len(data) < 4:
            return 0.0
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 4) - 3)
    
    def get_positions(self) -> List[Dict]:
        """Get current open paper positions (sanitized for JSON)"""
        return [sanitize_for_json(pos) for pos in self.paper_positions.values()]
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history (sanitized for JSON)"""
        return [sanitize_for_json(trade) for trade in self.trade_history[-limit:]]
