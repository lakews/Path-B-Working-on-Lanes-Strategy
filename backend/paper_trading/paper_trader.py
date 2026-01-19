"""
Paper Trading Engine with Full RL Integration
Simulates live trading, tracks positions, and feeds rewards to RL for continuous learning
"""
import asyncio
import logging
import os
import uuid
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone
from database import get_db
from ml.rl_engine import RLAdaptiveEngine
from services.market_data_service import MarketDataService
from ml.sharp_detector import SharpDetector
from ml.volatility_predictor import VolatilityPredictor
from ml.signal_fusion import SignalFusionEngine
from ml.social_sentiment import SocialSentimentAnalyzer
from ml.enhanced_sentiment import get_enhanced_sentiment_analyzer
from config import config
import numpy as np

logger = logging.getLogger(__name__)

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
        
        # Market selection thresholds (configurable)
        self.min_liquidity = 100.0
        self.max_liquidity = 1000000.0  # NEW: Max liquidity filter
        self.min_volume_24h = 1000.0
        self.max_spread = 0.05
        self.max_open_positions = 50
        self.stuck_price_multiplier = 2.0  # Volume multiplier for stuck prices (0.0, 0.5, 1.0)
        
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
        
        # Current capital starts at initial (will be set properly after config load)
        self.current_capital = self.initial_capital
        
        # Calculated values based on config (will be recalculated after config load)
        self.deployed_capital = self.initial_capital * (self.capital_deployment_pct / 100)
        self.max_position_size = self.deployed_capital * (self.max_position_size_pct / 100)
        
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
        self.strategy_stats = {
            'delta_neutral': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'volatility_exploitation': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'alpha_directional': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
        }
        
        # Asset class tracking (with full metrics like backtest)
        self.asset_class_stats = {}
        
        # Returns distribution tracking
        self.trade_returns: List[float] = []
        
        # Equity curve tracking - now with strategy and asset class breakdowns
        self.equity_curve: List[Dict] = []
        self.strategy_equity: Dict[str, float] = {
            'delta_neutral': 0.0,
            'volatility_exploitation': 0.0,
            'alpha_directional': 0.0,
            'arbitrage': 0.0
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
                
                # Update polymarket sizer config if enabled
                if hasattr(self, 'polymarket_sizer') and self.polymarket_sizer:
                    self.polymarket_sizer.config['polymarket_fee_pct'] = self.polymarket_fee_pct
                    self.polymarket_sizer.config['sector_caps'].update(self.sector_caps)
                    self.polymarket_sizer.config['kelly_multiplier'] = self.kelly_fraction
                    self.polymarket_sizer.config['min_bet_floor'] = self.min_position_size
                
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
        """Start paper trading session"""
        self.running = True
        logger.info(f"Starting Paper Trading Session: {self.session_id}")
        
        # Load user configuration
        await self._load_user_config()
        
        # Load RL model
        await self.rl_engine.load_model()
        
        # Initialize session in DB
        await self._init_session()
        
        # Run trading loops
        await asyncio.gather(
            self._trading_loop(),
            self._position_monitoring_loop(),
            self._learning_loop(),
            self._continuous_mode_handler()
        )
    
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
        
        # Save session results
        await self._save_session_results()
        
        # Final RL learning from session
        await self._learn_from_session()
        
        logger.info(f"Paper Trading Stopped - Total PnL: ${self.total_pnl:.2f}")
    
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
        session_doc = {
            "session_id": self.session_id,
            "type": "paper_trading",
            "continuous_mode": self.continuous_mode,
            "initial_capital": self.initial_capital,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "trades": [],
            "positions": []
        }
        await self.db.paper_trading_sessions.insert_one(session_doc)
    
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
                    
                    # Filter by asset class
                    asset_class = market_data.get('asset_class', market_data.get('category', 'unknown')).lower()
                    if asset_class not in [ac.lower() for ac in self.enabled_asset_classes]:
                        skipped_asset_class += 1
                        continue
                    
                    # Check existing paper position
                    market_id = market_data.get('id')
                    if market_id in self.paper_positions:
                        # Always evaluate exits (even during graceful stop)
                        await self._evaluate_exit(market_id, market_data)
                        exit_evaluated += 1
                    elif not self.graceful_stop:
                        # Only evaluate new entries if not in graceful stop mode
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
                    # Strategy P&L breakdown
                    "delta_neutral_pnl": self.strategy_equity.get('delta_neutral', 0),
                    "volatility_pnl": self.strategy_equity.get('volatility_exploitation', 0),
                    "alpha_pnl": self.strategy_equity.get('alpha_directional', 0),
                    "arbitrage_pnl": self.strategy_equity.get('arbitrage', 0),
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
            
            # Check for stuck/stale prices - skip markets with default prices unless high volume confirms they're real
            yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
            if yes_price in [0.0, 0.5, 1.0]:  # Default/stuck prices
                # Use user-configured multiplier for stuck price volume requirement
                stale_price_min_volume = min_vol_threshold * self.stuck_price_multiplier
                if effective_volume < stale_price_min_volume:
                    track_skip("stuck_price")
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
            
            # SENTIMENT-BASED SIDE SELECTION (configurable thresholds)
            # RL action determines size, but sentiment determines direction
            sentiment = signals.get('sentiment', 0.5)
            if sentiment > self.bullish_sentiment_threshold:
                # Bullish sentiment -> YES (BUY)
                side = 'YES'
                if 'SELL' in rl_action:
                    # Convert SELL to equivalent BUY size
                    rl_action = rl_action.replace('SELL', 'BUY')
            elif sentiment < self.bearish_sentiment_threshold:
                # Bearish sentiment -> NO (SELL)  
                side = 'NO'
                if 'BUY' in rl_action:
                    # Convert BUY to equivalent SELL size
                    rl_action = rl_action.replace('BUY', 'SELL')
            else:
                # Neutral sentiment -> use RL action directly
                side = 'YES' if 'BUY' in rl_action else 'NO'
            
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
            if self.use_polymarket_sizer:
                try:
                    # Get token ID from market data
                    token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
                    if token_ids and isinstance(token_ids, list) and len(token_ids) > 0:
                        # Import and use the API to fetch order book
                        from data.polymarket_api import PolymarketAPI
                        async with PolymarketAPI() as api:
                            order_book = await api.get_order_book(token_ids[0])
                            order_book_asks = order_book.get('asks', [])
                except Exception as e:
                    logger.debug(f"Could not fetch order book: {e}")
            
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
            'tp_mult': 1.0,
            'sl_mult': 0.8,   # Tighter SL for sports
            'time_mult': 0.25 # Events end quickly
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
    
    # Time-to-expiry thresholds for strategy adjustments
    EXPIRY_THRESHOLDS = {
        'no_entry_hours': 6,        # No new entries within 6 hours of expiry
        'high_urgency_hours': 24,   # Reduce max hold time, tighten exits
        'medium_urgency_days': 7,   # Boost volatility, reduce delta-neutral
        'normal_days': 30           # Normal trading
    }
    
    # Strategy adjustments based on time-to-expiry
    EXPIRY_STRATEGY_ADJUSTMENTS = {
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
        }
    }
    
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
        elif hours_to_expiry <= self.EXPIRY_THRESHOLDS['no_entry_hours']:
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'critical',
                'position_size_mult': 0.0,
                'should_enter': False,
                'expiry_label': f'{hours_to_expiry:.1f}h ⚠️'
            }
        elif hours_to_expiry <= self.EXPIRY_THRESHOLDS['high_urgency_hours']:
            # Scale down position as expiry approaches
            scale = hours_to_expiry / self.EXPIRY_THRESHOLDS['high_urgency_hours']
            return {
                'hours_to_expiry': hours_to_expiry,
                'days_to_expiry': days_to_expiry,
                'urgency': 'high',
                'position_size_mult': max(0.3, scale),
                'should_enter': True,
                'expiry_label': f'{hours_to_expiry:.0f}h 🔴'
            }
        elif days_to_expiry <= self.EXPIRY_THRESHOLDS['medium_urgency_days']:
            scale = days_to_expiry / self.EXPIRY_THRESHOLDS['medium_urgency_days']
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
        
        adjustments = self.EXPIRY_STRATEGY_ADJUSTMENTS.get(strategy, {})
        
        # Check strategy-specific disable threshold
        disable_hours = adjustments.get('disable_within_hours', 6)
        if hours <= disable_hours:
            return {'should_trade': False, 'size_multiplier': 0.0, 'reason': f'{strategy}_disabled_within_{disable_hours}h'}
        
        # Delta-neutral specific: disable within 48h
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
        base = self.exit_params_by_strategy.get(strategy, self.DEFAULT_EXIT_PARAMS.get(strategy, self.DEFAULT_EXIT_PARAMS['arbitrage']))
        
        # Adjustments from asset class (use DB-loaded or defaults)
        adj = self.asset_class_exit_multipliers.get(asset_class.lower(), {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0})
        
        return {
            'take_profit': base['take_profit'] * adj['tp_mult'],
            'stop_loss': base['stop_loss'] * adj['sl_mult'],
            'max_hours': base['max_hours'] * adj['time_mult']
        }
    
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
        base = self.exit_params_by_strategy.get(
            strategy, 
            self.DEFAULT_EXIT_PARAMS.get(strategy, self.DEFAULT_EXIT_PARAMS['arbitrage'])
        )
        adj = self.asset_class_exit_multipliers.get(
            asset_class.lower(), 
            {'tp_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0}
        )
        
        return {
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
    
    async def _evaluate_exit(self, market_id: str, market_data: Dict):
        """
        Evaluate existing paper position for exit.
        
        Supports two modes (controlled by self.use_dynamic_exit):
        1. DYNAMIC MODE: Time-aware TP/SL based on max gain, expiry, and price zone
        2. SIMPLE MODE: Configurable TP/SL from exit_params_by_strategy
        """
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            current_price = float(market_data.get('yes_price', 0.5) or 0.5)
            entry_price = position['entry_price']
            side = position['side']
            size = position.get('size', 0)
            strategy = position.get('strategy', 'arbitrage')
            asset_class = position.get('asset_class', 'unknown')
            
            # UPDATE position's current_price for UI display
            position['current_price'] = current_price
            
            # Get time to expiry
            expiry_info = self._calculate_time_to_expiry(market_data)
            days_to_expiry = expiry_info.get('days_to_expiry')
            hours_to_expiry = expiry_info.get('hours_to_expiry')
            
            # ============================================
            # GET EXIT PARAMETERS (Dynamic or Simple mode)
            # ============================================
            if self.use_dynamic_exit:
                # DYNAMIC MODE: Time-aware exit params
                exit_params = self._get_dynamic_exit_params(side, entry_price, days_to_expiry)
            else:
                # SIMPLE MODE: Configurable exit params
                exit_params = self._get_simple_exit_params(strategy, asset_class)
            
            take_profit_threshold = exit_params['take_profit']
            stop_loss_threshold = exit_params['stop_loss']
            max_hours = exit_params['max_hours']
            zone = exit_params.get('zone', 'unknown')
            exit_mode = exit_params.get('exit_mode', 'standard')
            max_gain_possible = exit_params.get('max_gain_possible')
            extremeness = exit_params.get('extremeness')
            
            # Store exit params in position for UI display
            position['dynamic_exit_params'] = {
                'tp': take_profit_threshold,
                'sl': stop_loss_threshold,
                'max_hours': max_hours,
                'zone': zone,
                'exit_mode': exit_mode,
                'max_gain': max_gain_possible,
                'extremeness': extremeness,
                'days_to_expiry': days_to_expiry,
                'is_dynamic': self.use_dynamic_exit
            }
            
            # ============================================
            # CALCULATE UNREALIZED P&L
            # ============================================
            if side == 'YES':
                if entry_price > 0:
                    shares = size / entry_price
                    current_value = shares * current_price
                    unrealized_pnl = current_value - size
                    pnl_pct = unrealized_pnl / size if size > 0 else 0
                else:
                    pnl_pct = 0
                    unrealized_pnl = 0
            else:
                no_entry_price = 1 - entry_price
                no_current_price = 1 - current_price
                if no_entry_price > 0:
                    shares = size / no_entry_price
                    current_value = shares * no_current_price
                    unrealized_pnl = current_value - size
                    pnl_pct = unrealized_pnl / size if size > 0 else 0
                else:
                    pnl_pct = 0
                    unrealized_pnl = 0
            
            # UPDATE position's unrealized P&L for UI display
            position['unrealized_pnl'] = unrealized_pnl
            position['unrealized_pnl_pct'] = pnl_pct
            
            # Get RL recommendation for exit
            signals = await self._get_signals(market_data)
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # ============================================
            # EXIT CONDITIONS (Priority Order)
            # ============================================
            should_exit = False
            exit_reason = None
            
            # 1. AUTO-EXIT FOR APPROACHING EXPIRY (1 hour before market resolution)
            if hours_to_expiry is not None and hours_to_expiry <= 1.0:
                should_exit = True
                exit_reason = f"expiry_safety_{hours_to_expiry:.1f}h"
                logger.info(f"⚠️ AUTO-EXIT: {market_id[:16]} expires in {hours_to_expiry:.1f}h")
            
            # 2. TAKE PROFIT (only if TP threshold is set - None means hold to resolution)
            if not should_exit and take_profit_threshold is not None and pnl_pct >= take_profit_threshold:
                should_exit = True
                max_gain_str = f"of_{max_gain_possible:.0%}max" if max_gain_possible else ""
                exit_reason = f"tp_{pnl_pct:.1%}_{exit_mode}{max_gain_str}"
                logger.info(f"✅ TP EXIT: {market_id[:16]} | P&L: {pnl_pct:.1%} >= {take_profit_threshold:.1%} ({exit_mode})")
            
            # 3. STOP LOSS (only if SL threshold is set - None means no SL protection)
            if not should_exit and stop_loss_threshold is not None and pnl_pct <= stop_loss_threshold:
                should_exit = True
                exit_reason = f"sl_{pnl_pct:.1%}_{exit_mode}"
                logger.info(f"🛑 SL EXIT: {market_id[:16]} | P&L: {pnl_pct:.1%} <= {stop_loss_threshold:.1%} ({exit_mode})")
            
            # 4. RL SIGNAL REVERSAL (high confidence opposite signal) - skip in resolution mode
            if not should_exit and exit_mode != 'resolution' and rl_confidence > 0.7:
                if side == 'YES' and 'SELL' in rl_action:
                    should_exit = True
                    exit_reason = f"rl_reversal_{rl_action}_{rl_confidence:.0%}"
                elif side == 'NO' and 'BUY' in rl_action:
                    should_exit = True
                    exit_reason = f"rl_reversal_{rl_action}_{rl_confidence:.0%}"
            
            # 5. TIME-BASED EXIT
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            hours_open = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
            if not should_exit and max_hours is not None and hours_open > max_hours:
                should_exit = True
                exit_reason = f"time_{hours_open:.1f}h>{max_hours:.0f}h_{exit_mode}"
                logger.info(f"⏰ TIME EXIT: {market_id[:16]} | Open: {hours_open:.1f}h > {max_hours:.0f}h ({exit_mode})")
            
            # WARN but don't force exit for positions expiring within 6 hours
            if not should_exit and hours_to_expiry is not None and hours_to_expiry <= 6.0 and hours_to_expiry > 1.0:
                logger.warning(f"⏱️ Position {market_id[:16]} expires in {hours_to_expiry:.1f}h - P&L: {pnl_pct:.2%}")
            
            # ============================================
            # EXECUTE EXIT
            # ============================================
            if should_exit:
                tp_str = f"{take_profit_threshold:.1%}" if take_profit_threshold else "None"
                sl_str = f"{stop_loss_threshold:.1%}" if stop_loss_threshold else "None"
                logger.info(f"📤 EXIT: {market_id[:16]} | Reason: {exit_reason} | Mode: {exit_mode}")
                logger.debug(f"  Params: TP={tp_str}, SL={sl_str}, MaxHrs={max_hours}")
                logger.debug(f"  Position: {side} @ ${entry_price:.4f} -> ${current_price:.4f} | P&L: ${unrealized_pnl:.2f} ({pnl_pct:.2%})")
                await self._execute_paper_exit(market_id, market_data, exit_reason)
                
        except Exception as e:
            logger.error(f"Error evaluating exit: {e}")
    
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
            
            logger.info(f"[ENTRY-EXEC] Opening {strategy} {side} ${size:.2f} in {market_id[:16]}")
            
            current_price = market_data.get('yes_price', 0.5)
            asset_class = market_data.get('asset_class', market_data.get('category', 'unknown'))
            
            # Extract expiry info from sizing breakdown
            expiry_info = sizing_breakdown.get('expiry_info', {}) if sizing_breakdown else {}
            
            # Calculate dynamic exit params for this entry
            dynamic_exit = self._get_dynamic_exit_params(side, current_price)
            
            position = {
                "position_id": str(uuid.uuid4()),
                "market_id": market_id,
                "market_question": market_data.get('question', '')[:100],
                "asset_class": asset_class,
                "side": side,
                "size": size,
                "entry_price": current_price,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "strategy": strategy,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "signals": signals,
                "sizing_breakdown": sizing_breakdown or {},  # Store for learning
                # Risk tracking for reward shaping
                "entry_volatility": signals.get('volatility', 0.05),
                "max_drawdown_pct": 0.0,  # Will be updated during position monitoring
                "min_price_seen": current_price,  # Track worst price for drawdown
                "max_price_seen": current_price,  # Track best price
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
            trade_log = {
                "trade_id": position['position_id'],
                "session_id": self.session_id,
                "type": "entry",
                "market_id": market_id,
                "market_question": position.get('market_question', ''),
                "side": side,
                "size": size,
                "price": current_price,
                "entry_price": current_price,  # For consistency with exit trades
                "strategy": strategy,
                "asset_class": asset_class,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                # Expiry info for UI
                "expiry_info": position.get('expiry_info', {}),
                # Sizing breakdown for analysis and learning
                "sizing_breakdown": sizing_breakdown or {},
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
            
            logger.info(f"📝 PAPER ENTRY: {side} ${size:.2f} @ {current_price:.4f} | Strategy: {strategy} | RL: {rl_action} ({rl_confidence:.2f})")
            logger.info(f"   Dynamic Exit: TP={dynamic_exit['take_profit']:.1%}, SL={dynamic_exit['stop_loss']:.1%}, MaxHrs={dynamic_exit['max_hours']:.0f} ({dynamic_exit['zone']})")
            
        except Exception as e:
            logger.error(f"Error executing paper entry: {e}")
    
    async def _execute_paper_exit(self, market_id: str, market_data: Dict, exit_reason: str):
        """Execute a paper trade exit and feed reward to RL"""
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            current_price = market_data.get('yes_price', 0.5)
            entry_price = position['entry_price']
            side = position['side']
            size = position['size']  # USD invested
            strategy = position['strategy']
            asset_class = position.get('asset_class', 'unknown')
            
            # CORRECT P&L Calculation based on shares
            # For YES: we buy YES shares at yes_price, sell at exit yes_price
            # For NO: we buy NO shares at (1 - yes_price), sell at exit (1 - yes_price)
            if side == 'YES':
                # YES position: buy at entry_price, sell at current_price
                if entry_price > 0:
                    shares = size / entry_price
                    exit_value = shares * current_price
                    pnl = exit_value - size
                else:
                    pnl = 0
            else:
                # NO position: buy at (1 - entry_price), sell at (1 - current_price)
                no_entry_price = 1 - entry_price
                no_exit_price = 1 - current_price
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
            
            # Update strategy stats with full metrics
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['pnl'] += pnl
                if is_win:
                    self.strategy_stats[strategy]['wins'] += 1
                    self.strategy_stats[strategy]['gross_profit'] += pnl
                else:
                    self.strategy_stats[strategy]['gross_loss'] += abs(pnl)
            
            # Update strategy equity for equity curve
            if strategy in self.strategy_equity:
                self.strategy_equity[strategy] += pnl
            
            # Update asset class stats with full metrics
            if asset_class not in self.asset_class_stats:
                self.asset_class_stats[asset_class] = {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
            # Ensure gross_profit and gross_loss exist (for positions opened before fix)
            if 'gross_profit' not in self.asset_class_stats[asset_class]:
                self.asset_class_stats[asset_class]['gross_profit'] = 0.0
            if 'gross_loss' not in self.asset_class_stats[asset_class]:
                self.asset_class_stats[asset_class]['gross_loss'] = 0.0
            self.asset_class_stats[asset_class]['pnl'] += pnl
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
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            exit_time = datetime.now(timezone.utc)
            hold_time_seconds = (exit_time - entry_time).total_seconds()
            hold_time_hours = hold_time_seconds / 3600
            
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
            
            closed_trade = {
                **position,
                "exit_price": current_price,
                "exit_time": exit_time.isoformat(),
                "exit_reason": exit_reason,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_time_seconds": hold_time_seconds,
                "reward_signal": reward
            }
            self.closed_trades.append(closed_trade)
            
            # Log trade with hold time
            trade_log = {
                "trade_id": str(uuid.uuid4()),
                "session_id": self.session_id,
                "type": "exit",
                "market_id": market_id,
                "market_question": position.get('market_question', ''),
                "side": side,
                "size": size,
                "entry_price": entry_price,
                "exit_price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "hold_time_seconds": hold_time_seconds,
                "strategy": strategy,
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
                
                # Get open positions for correlation check
                open_positions_list = [
                    {
                        'category': p.get('asset_class', p.get('category', 'unknown')),
                        'tags': p.get('tags', []),
                    }
                    for p in self.paper_positions.values()
                ]
                
                # Get ask price from market data
                yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
                
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
                
                # Log renormalization details
                renorm = model_diagnostics.get('renormalization', {})
                sig_status = model_diagnostics.get('signal_status', {})
                logger.info(f"[RENORM] active_signals={renorm.get('active_signals', 3)}, sentiment={sig_status.get('sentiment', 'unknown')}, rl={sig_status.get('rl', 'unknown')}, num={renorm.get('numerator', 0):.4f}, den={renorm.get('denominator', 1):.2f}")
                
                # Determine which side to bet on based on where we see edge
                # BUY/YES: edge when model_prob > effective_yes_price
                # SELL/NO: edge when (1-model_prob) > effective_no_price
                effective_yes_price = yes_price + self.polymarket_fee_pct
                effective_no_price = (1 - yes_price) + self.polymarket_fee_pct
                
                yes_edge = raw_model_prob - effective_yes_price
                no_edge = (1 - raw_model_prob) - effective_no_price
                
                # Choose the side with positive edge
                if yes_edge > no_edge and yes_edge > 0:
                    # Bet on YES
                    model_probability = raw_model_prob
                    sizer_ask_price = yes_price
                    sizing_side = 'YES'
                elif no_edge > yes_edge and no_edge > 0:
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
                        'breakdown': {'reject_reason': 'no_edge_either_side', 'reject_detail': f'yes_edge={yes_edge:.4f}, no_edge={no_edge:.4f}'},
                        'sizing_breakdown': {'sizer_mode': 'polymarket', 'reject_reason': 'no_edge_either_side'}
                    }
                
                logger.info(f"[MODEL_PROB] yes_price={yes_price:.3f}, raw_prob={raw_model_prob:.3f}, yes_edge={yes_edge:.3f}, no_edge={no_edge:.3f}, sizing_side={sizing_side}")
                
                # Call the new Polymarket sizer
                logger.info(f"[SIZER CALL] equity={equity:.2f}, deployed={deployed:.2f}, model_prob={model_probability:.4f}, ask={sizer_ask_price:.4f}, days={days_to_expiry}")
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
                    sector_exposure=sector_exposure
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
        Calculate model probability using WEIGHTED ENSEMBLE approach.
        
        Combines multiple probability estimates:
        P_final = w1 * P_market + w2 * P_sentiment + w3 * P_rl
        
        This is statistically sound because:
        - All inputs are probabilities (0-1)
        - Weights sum to 1
        - Output is naturally bounded (no >100% issues)
        
        Components:
        - P_market: Market's implied probability (yes_price)
        - P_sentiment: AI sentiment as probability estimate
        - P_rl: DQN's implied probability from action + confidence
        
        The model only deviates from market when signals disagree.
        
        Args:
            return_diagnostics: If True, returns a dict with full diagnostic breakdown
        """
        # ================================================================
        # COMPONENT 1: Market Probability (P_market)
        # ================================================================
        # The market's current estimate - our baseline
        p_market = yes_price
        
        # ================================================================
        # COMPONENT 2: Sentiment Probability (P_sentiment)
        # ================================================================
        # Sentiment score (0-1) directly represents probability estimate
        # 0.65 sentiment → model thinks 65% chance of YES
        p_sentiment = sentiment
        
        # ================================================================
        # COMPONENT 3: RL Probability (P_rl)
        # ================================================================
        # Convert DQN action + confidence into implied probability
        # BUY = thinks YES is underpriced → P_rl > market
        # SELL = thinks YES is overpriced → P_rl < market
        
        rl_action = rl_action.upper() if rl_action else 'HOLD'
        
        # Determine direction and strength
        is_buy = 'BUY' in rl_action
        is_sell = 'SELL' in rl_action
        
        # Action strength determines how far from market the RL thinks true prob is
        if 'LARGE' in rl_action:
            deviation = 0.20  # Thinks true prob is 20% different from market
        elif 'MEDIUM' in rl_action:
            deviation = 0.12  # 12% different
        elif 'SMALL' in rl_action:
            deviation = 0.06  # 6% different
        else:
            deviation = 0.0   # HOLD = agrees with market
        
        # Scale deviation by confidence (0-1)
        # Low confidence = smaller deviation
        scaled_deviation = deviation * max(rl_confidence, 0.2)
        
        # Calculate RL's implied probability
        if is_buy:
            # BUY: RL thinks YES is underpriced → true prob is HIGHER
            p_rl = yes_price + scaled_deviation
        elif is_sell:
            # SELL: RL thinks YES is overpriced → true prob is LOWER
            p_rl = yes_price - scaled_deviation
        else:
            # HOLD: RL agrees with market
            p_rl = yes_price
        
        # Clamp P_rl to valid range
        p_rl = max(0.01, min(0.99, p_rl))
        
        # Log components for debugging
        logger.debug(f"[PROB_COMPONENTS] p_market={p_market:.4f}, p_sentiment={p_sentiment:.4f}, p_rl={p_rl:.4f} (action={rl_action}, dev={scaled_deviation:.4f})")
        
        # ================================================================
        # WEIGHTED ENSEMBLE WITH RENORMALIZATION
        # ================================================================
        # Key insight: If a signal is "neutral" (0.45-0.55), it provides
        # NO information and should be EXCLUDED from the calculation.
        # We renormalize weights so remaining signals share the vote.
        #
        # Without renormalization: neutral sentiment (0.5) pulls everything to 0.5
        # With renormalization: neutral sentiment is excluded, market+RL decide
        
        # Base max weights
        max_w_market = 0.50      # Market is generally efficient
        max_w_sentiment = 0.25   # AI sentiment analysis  
        max_w_rl = 0.25          # DQN reinforcement learning
        
        # ================================================================
        # STEP 1: Determine active weights (filter out neutral signals)
        # ================================================================
        
        # Market always participates (it's the baseline)
        w_market = max_w_market
        
        # Sentiment: If neutral (0.45-0.55), weight = 0 (abstains from voting)
        is_sentiment_neutral = 0.45 <= p_sentiment <= 0.55
        if is_sentiment_neutral:
            w_sentiment = 0.0
            sentiment_status = 'neutral_excluded'
        else:
            w_sentiment = max_w_sentiment
            sentiment_status = 'active'
        
        # RL: If HOLD action or very low confidence, weight = 0
        is_rl_neutral = (not is_buy and not is_sell) or rl_confidence < 0.15
        if is_rl_neutral:
            w_rl = 0.0
            rl_status = 'neutral_excluded'
        else:
            # Scale RL weight by confidence
            w_rl = max_w_rl * min(1.0, rl_confidence / 0.5)  # Full weight at 50% confidence
            rl_status = 'active'
        
        # ================================================================
        # STEP 2: Calculate numerator (weighted sum of active signals)
        # ================================================================
        numerator = (
            w_market * p_market +
            w_sentiment * p_sentiment +
            w_rl * p_rl
        )
        
        # ================================================================
        # STEP 3: Calculate denominator (sum of active weights)
        # ================================================================
        denominator = w_market + w_sentiment + w_rl
        
        # ================================================================
        # STEP 4: Renormalize - divide to get final probability
        # ================================================================
        if denominator > 0:
            model_prob = numerator / denominator
        else:
            # Safety: if somehow all weights are 0, fall back to market
            model_prob = p_market
        
        # Final clamp to valid probability range
        final_prob = max(0.01, min(0.99, model_prob))
        
        # Calculate effective weights after renormalization (for diagnostics)
        if denominator > 0:
            eff_w_market = w_market / denominator
            eff_w_sentiment = w_sentiment / denominator
            eff_w_rl = w_rl / denominator
        else:
            eff_w_market, eff_w_sentiment, eff_w_rl = 1.0, 0.0, 0.0
        
        # Return diagnostics if requested
        if return_diagnostics:
            return {
                'final_probability': final_prob,
                'components': {
                    'p_market': round(p_market, 4),
                    'p_sentiment': round(p_sentiment, 4),
                    'p_rl': round(p_rl, 4),
                },
                'raw_weights': {
                    'w_market': round(w_market, 4),
                    'w_sentiment': round(w_sentiment, 4),
                    'w_rl': round(w_rl, 4),
                },
                'effective_weights': {
                    'w_market': round(eff_w_market, 4),
                    'w_sentiment': round(eff_w_sentiment, 4),
                    'w_rl': round(eff_w_rl, 4),
                },
                'signal_status': {
                    'sentiment': sentiment_status,
                    'rl': rl_status,
                    'sentiment_is_neutral': is_sentiment_neutral,
                    'rl_is_neutral': is_rl_neutral,
                },
                'renormalization': {
                    'numerator': round(numerator, 6),
                    'denominator': round(denominator, 4),
                    'active_signals': sum([1 for w in [w_market, w_sentiment, w_rl] if w > 0]),
                },
                'contributions': {
                    'market_contribution': round(w_market * p_market, 6),
                    'sentiment_contribution': round(w_sentiment * p_sentiment, 6),
                    'rl_contribution': round(w_rl * p_rl, 6),
                },
                'rl_details': {
                    'action': rl_action,
                    'confidence': round(rl_confidence, 4),
                    'deviation': round(scaled_deviation, 4),
                    'direction': 'bullish' if is_buy else ('bearish' if is_sell else 'neutral'),
                },
                'pre_clamp': round(model_prob, 4),
            }
        
        return final_prob
    
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
                positions_list.append({
                    'market_id': market_id,
                    'side': pos.get('side', 'YES'),
                    'size': pos.get('size', 0),
                    'entry_price': pos.get('entry_price', 0.5),
                    'current_price': pos.get('current_price', pos.get('entry_price', 0.5)),
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
        
        # Get price from market data
        yes_price = 0.5
        if market_data:
            yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
        
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
            yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
            no_price = float(market_data.get('no_price', 0.5) or 0.5)
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
            sentiment = max(0.05, min(0.95, sentiment))
            
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
                    market_prices = {m['id']: float(m.get('yes_price', 0.5) or 0.5) for m in markets}
                    
                    total_unrealized = 0.0
                    for market_id, position in self.paper_positions.items():
                        entry_price = position['entry_price']
                        side = position['side']
                        size = position['size']  # USD invested
                        
                        # Get REAL current price from API (no simulation)
                        current_price = market_prices.get(market_id, entry_price)
                        
                        # Calculate shares owned
                        shares = size / entry_price if entry_price > 0 else 0
                        
                        # Calculate current value and unrealized P&L
                        if side == 'YES':
                            current_value = shares * current_price
                            unrealized = current_value - size
                        else:
                            no_entry = 1 - entry_price
                            no_current = 1 - current_price
                            no_shares = size / no_entry if no_entry > 0 else 0
                            current_value = no_shares * no_current
                            unrealized = current_value - size
                        
                        # Update position
                        position['current_price'] = round(current_price, 4)
                        position['shares'] = round(shares, 2)
                        position['current_value'] = round(current_value, 2)
                        position['unrealized_pnl'] = round(unrealized, 2)
                        position['unrealized_pnl_pct'] = round((unrealized / size) * 100, 2) if size > 0 else 0
                        
                        # Track max drawdown for this position (for reward shaping)
                        current_pnl_pct = position['unrealized_pnl_pct']
                        if current_pnl_pct < 0:
                            # Position is underwater - track how bad it got
                            current_drawdown = abs(current_pnl_pct)
                            if current_drawdown > position.get('max_drawdown_pct', 0):
                                position['max_drawdown_pct'] = round(current_drawdown, 2)
                        
                        # Track price extremes
                        if current_price < position.get('min_price_seen', current_price):
                            position['min_price_seen'] = current_price
                        if current_price > position.get('max_price_seen', current_price):
                            position['max_price_seen'] = current_price
                        
                        total_unrealized += unrealized
                    
                    self.unrealized_pnl = round(total_unrealized, 2)
                    
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
        """Close all open paper positions"""
        markets = await self._get_active_markets()
        market_data_map = {m['id']: m for m in markets}
        
        for market_id in list(self.paper_positions.keys()):
            market_data = market_data_map.get(market_id, {'yes_price': 0.5})
            await self._execute_paper_exit(market_id, market_data, "session_end")
    
    async def _save_session_results(self):
        """Save paper trading session results to database"""
        try:
            win_rate = self.winning_trades / max(self.total_trades, 1)
            
            session_results = {
                "session_id": self.session_id,
                "type": "paper_trading",
                "end_time": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
                "initial_capital": self.initial_capital,
                "final_capital": self.current_capital,
                "total_pnl": self.total_pnl,
                "total_pnl_pct": (self.total_pnl / self.initial_capital) * 100,
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "win_rate": win_rate,
                "max_drawdown": self.max_drawdown,
                "strategy_stats": self.strategy_stats,
                "asset_class_stats": self.asset_class_stats,
                "closed_trades": self.closed_trades[-100:]  # Last 100 trades
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
        """Get active markets from Gamma API with configurable filters"""
        try:
            # Always fetch fresh from Gamma API for high-frequency trading
            logger.info(f"Fetching markets (min_liquidity: ${self.min_liquidity}, min_volume: ${self.min_volume_24h})")
            
            from data.polymarket_api import PolymarketAPI
            async with PolymarketAPI() as api:
                live_markets = await api.get_markets(limit=200)  # Fetch more markets
                
                if not live_markets:
                    logger.warning("No markets returned from Gamma API")
                    return []
                
                # Filter markets by liquidity, volume, and spread
                filtered_markets = []
                for m in live_markets:
                    liquidity = float(m.get('liquidity', 0) or 0)
                    volume_24h = float(m.get('volume_24h', 0) or 0)
                    spread = float(m.get('spread', 1) or 1)
                    
                    # Apply filters
                    if liquidity < self.min_liquidity:
                        continue
                    if volume_24h < self.min_volume_24h:
                        continue
                    if spread > self.max_spread:
                        continue
                    
                    filtered_markets.append(m)
                
                logger.info(f"Filtered to {len(filtered_markets)} tradeable markets (from {len(live_markets)} total)")
                
                # Cache top markets in DB for analytics
                if filtered_markets:
                    for m in filtered_markets[:100]:
                        market_doc = {
                            "condition_id": m.get('condition_id') or m.get('id'),
                            "id": m.get('id'),
                            "question": m.get('question', ''),
                            "category": m.get('category', 'unknown'),
                            "yes_price": float(m.get('yes_price', 0.5) or 0.5),
                            "no_price": float(m.get('no_price', 0.5) or 0.5),
                            "liquidity": float(m.get('liquidity', 0) or 0),
                            "volume": float(m.get('volume', 0) or 0),
                            "volume_24h": float(m.get('volume_24h', 0) or 0),
                            "spread": float(m.get('spread', 0) or 0),
                            "end_date": m.get('end_date'),
                            "active": m.get('active', True),
                            "last_update": datetime.now(timezone.utc).isoformat()
                        }
                        await self.db.markets.update_one(
                            {"condition_id": market_doc['condition_id']},
                            {"$set": market_doc},
                            upsert=True
                        )
                
                return filtered_markets
                
        except Exception as e:
            logger.error(f"Error getting markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_status(self) -> Dict:
        """Get current paper trading status with full analytics"""
        win_rate = self.winning_trades / max(self.total_trades, 1)
        
        # Calculate strategy results with profit factors (like backtest)
        strategy_results = {}
        for strategy, stats in self.strategy_stats.items():
            trades = stats.get('trades', 0)
            wins = stats.get('wins', 0)
            pnl = stats.get('pnl', 0)
            gross_profit = stats.get('gross_profit', 0)
            gross_loss = stats.get('gross_loss', 0)
            
            strategy_results[strategy] = {
                'trades': trades,
                'wins': wins,
                'pnl': pnl,
                'win_rate': wins / trades if trades > 0 else 0,
                'profit_factor': gross_profit / gross_loss if gross_loss > 0 else (2.0 if gross_profit > 0 else 0),
                'gross_profit': gross_profit,
                'gross_loss': gross_loss
            }
        
        # Calculate asset class results with profit factors
        asset_class_results = {}
        for asset_class, stats in self.asset_class_stats.items():
            trades = stats.get('trades', 0)
            wins = stats.get('wins', 0)
            pnl = stats.get('pnl', 0)
            gross_profit = stats.get('gross_profit', 0)
            gross_loss = stats.get('gross_loss', 0)
            
            asset_class_results[asset_class] = {
                'trades': trades,
                'wins': wins,
                'pnl': pnl,
                'win_rate': wins / trades if trades > 0 else 0,
                'profit_factor': gross_profit / gross_loss if gross_loss > 0 else (2.0 if gross_profit > 0 else 0),
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
            "total_pnl_pct": (self.total_pnl / self.initial_capital) * 100,
            "combined_pnl_pct": (combined_pnl / self.initial_capital) * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "max_drawdown": self.max_drawdown,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,  # Whether max drawdown was hit
            "open_positions": len(self.paper_positions),
            "strategy_results": strategy_results,
            "asset_class_results": asset_class_results,
            "returns_distribution": returns_distribution,  # Realized trades distribution
            "unrealized_distribution": unrealized_distribution,  # Open positions distribution
            "pnl_distribution": returns_distribution if returns_distribution.get('bins') else unrealized_distribution,  # For backward compat
            "trade_returns": self.trade_returns[-100:],  # Last 100 returns for charts
            "equity_curve": self.equity_curve[-200:],  # Last 200 points for better charts
            "strategy_equity": self.strategy_equity,  # Running P&L by strategy
            "asset_class_equity": self.asset_class_equity,  # Running P&L by asset class
            "enabled_strategies": self.enabled_strategies,
            "enabled_asset_classes": self.enabled_asset_classes,
            "continuous_mode": self.continuous_mode,
            "graceful_stop": self.graceful_stop,
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
