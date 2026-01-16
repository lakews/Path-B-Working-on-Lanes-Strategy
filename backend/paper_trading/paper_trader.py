"""
Paper Trading Engine with Full RL Integration
Simulates live trading, tracks positions, and feeds rewards to RL for continuous learning
"""
import asyncio
import logging
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
        
        # Import adaptive position sizer
        from ml.adaptive_position_sizer import get_position_sizer
        self.position_sizer = get_position_sizer()
        
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
        self.volatility_threshold = 0.05           # Threshold for volatility strategy
        self.sentiment_strength_threshold = 0.25   # Threshold for alpha directional
        self.sharp_alignment_threshold = 0.8       # Threshold for arbitrage
        self.delta_neutral_price_min = 0.35        # Min price for delta neutral
        self.delta_neutral_price_max = 0.65        # Max price for delta neutral
        
        # Sentiment-based side selection thresholds (configurable via UI)
        self.bullish_sentiment_threshold = 0.55    # Above this → YES
        self.bearish_sentiment_threshold = 0.45    # Below this → NO
        
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
        self.asset_class_equity: Dict[str, float] = {}
        
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
                
                for market_data in markets_to_process:
                    if not self.running:
                        break
                    
                    # Filter by asset class
                    asset_class = market_data.get('asset_class', market_data.get('category', 'unknown')).lower()
                    if asset_class not in [ac.lower() for ac in self.enabled_asset_classes]:
                        continue
                    
                    # Check existing paper position
                    market_id = market_data.get('id')
                    if market_id in self.paper_positions:
                        # Always evaluate exits (even during graceful stop)
                        await self._evaluate_exit(market_id, market_data)
                    elif not self.graceful_stop:
                        # Only evaluate new entries if not in graceful stop mode
                        await self._evaluate_entry(market_data)
                    
                    # High-frequency: minimal pause between markets
                    await asyncio.sleep(trade_interval / len(markets_to_process))
                
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
            # CIRCUIT BREAKER CHECK: Stop new entries if max drawdown exceeded
            if self.circuit_breaker_triggered:
                logger.debug("Circuit breaker active - no new entries allowed")
                return
            
            # Check if we're at max positions limit
            if len(self.paper_positions) >= self.max_open_positions:
                return  # Skip new entries when at capacity
            
            market_id = market_data.get('id')
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
                logger.debug(f"Skipping {market_id[:16]}: below min thresholds (vol={effective_volume} < {min_vol_threshold}, liq={liquidity} < {min_liq_threshold})")
                return
            
            # Check maximum liquidity (if user wants to avoid very liquid markets)
            if liquidity > max_liq_threshold:
                logger.debug(f"Skipping {market_id[:16]}: above max liquidity ({liquidity} > {max_liq_threshold})")
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
                            question = market_data.get('question', '')[:50]
                            logger.warning(f"⛔ BLOCKING EXPIRED MARKET: {market_id[:16]} - deadline {end_date.date()} < today {now.date()} - {question}")
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
                                        logger.warning(f"⛔ BLOCKING SEMANTICALLY EXPIRED: {market_id[:16]} - question date {question_date.date()} < today {now.date()} - {question[:50]}")
                                        return
                        except (ValueError, IndexError) as e:
                            pass  # Date parsing failed, continue
            
            # CHECK CLOSED/RESOLVED STATUS: Skip markets that are already resolved
            is_closed = market_data.get('closed', False) or market_data.get('resolved', False)
            is_active = market_data.get('active', True)
            if is_closed or not is_active:
                question = market_data.get('question', '')[:50]
                logger.debug(f"Skipping {market_id[:16]}: market is closed/resolved - {question}")
                return
            
            # Check for stuck/stale prices - skip markets with default prices unless high volume confirms they're real
            yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
            if yes_price in [0.0, 0.5, 1.0]:  # Default/stuck prices
                # Use user-configured multiplier for stuck price volume requirement
                stale_price_min_volume = min_vol_threshold * self.stuck_price_multiplier
                if effective_volume < stale_price_min_volume:
                    logger.debug(f"Skipping {market_id[:16]}: stuck price ({yes_price}) requires {self.stuck_price_multiplier}x volume ({effective_volume} < {stale_price_min_volume})")
                    return
            
            # Get ML signals
            signals = await self._get_signals(market_data)
            
            # Get RL recommendation
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Skip if RL says wait/hold or very low confidence
            if rl_action in ['WAIT', 'HOLD'] or rl_confidence < 0.15:
                return
            
            # Skip if action is not a clear BUY or SELL
            if 'BUY' not in rl_action and 'SELL' not in rl_action:
                return
            
            # OVERRIDE: Use sentiment-based side selection for more balanced YES/NO
            # RL action determines size, but sentiment determines direction
            sentiment = signals.get('sentiment', 0.5)
            if sentiment > 0.55:
                # Bullish sentiment -> YES (BUY)
                side = 'YES'
                if 'SELL' in rl_action:
                    # Convert SELL to equivalent BUY size
                    rl_action = rl_action.replace('SELL', 'BUY')
            elif sentiment < 0.45:
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
                question = market_data.get('question', '')[:50]
                logger.debug(f"Skipping {market_id[:16]}: {expiry_info.get('urgency')} - {expiry_info.get('expiry_label')} - {question}")
                return
            
            # Check strategy-specific expiry rules
            strategy_expiry = self._should_strategy_trade_near_expiry(strategy, expiry_info, rl_confidence)
            if not strategy_expiry.get('should_trade', True):
                logger.debug(f"Skipping {market_id[:16]}: {strategy} blocked near expiry - {strategy_expiry.get('reason')}")
                return
            
            # Get expiry-adjusted size multiplier
            expiry_size_mult = strategy_expiry.get('size_multiplier', 1.0)
            
            # ADAPTIVE POSITION SIZING - considers liquidity, volume, Kelly, RL confidence
            # Uses self.kelly_fraction and self.kelly_enabled from user config
            sizing_result = self._calculate_position_size(
                rl_confidence=rl_confidence,
                signals=signals,
                market_data=market_data,
                strategy=strategy,
                asset_class=asset_class,
                rl_action=rl_action
            )
            
            # Check if we should trade (liquidity/size requirements met)
            if not sizing_result.get('should_trade', False):
                logger.debug(f"Skipping {market_id[:16]}: position sizing rejected")
                return
            
            # Apply expiry size multiplier
            position_size = sizing_result.get('position_size', 0) * expiry_size_mult
            
            # Minimum position size for HFT - $5 minimum
            min_position_size = 5
            if position_size < min_position_size:
                logger.debug(f"Skipping {market_id[:16]}: position_size={position_size:.2f} < {min_position_size}")
                return
            
            # Side already determined above based on sentiment
            # (removed duplicate side assignment)
            
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
    
    async def _evaluate_exit(self, market_id: str, market_data: Dict):
        """Evaluate existing paper position for exit using strategy/asset-specific params"""
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
            
            # Get exit parameters for this strategy + asset class combination
            exit_params = self._get_exit_params(strategy, asset_class)
            take_profit_threshold = exit_params['take_profit']
            stop_loss_threshold = exit_params['stop_loss']
            max_hours = exit_params['max_hours']
            
            # Calculate unrealized P&L using SAME LOGIC as _execute_paper_exit
            # This ensures TP/SL triggers match actual P&L
            if side == 'YES':
                # YES position: bought YES shares at entry_price, now worth current_price
                if entry_price > 0:
                    shares = size / entry_price
                    current_value = shares * current_price
                    unrealized_pnl = current_value - size
                    pnl_pct = unrealized_pnl / size if size > 0 else 0
                else:
                    pnl_pct = 0
            else:
                # NO position: bought NO shares at (1 - entry_price), now worth (1 - current_price)
                no_entry_price = 1 - entry_price
                no_current_price = 1 - current_price
                if no_entry_price > 0:
                    shares = size / no_entry_price
                    current_value = shares * no_current_price
                    unrealized_pnl = current_value - size
                    pnl_pct = unrealized_pnl / size if size > 0 else 0
                else:
                    pnl_pct = 0
            
            # Get RL recommendation for exit
            signals = await self._get_signals(market_data)
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Exit conditions
            should_exit = False
            exit_reason = None
            
            # AUTO-EXIT FOR APPROACHING EXPIRY (1 hour before market resolution)
            expiry_info = self._calculate_time_to_expiry(market_data)
            hours_to_expiry = expiry_info.get('hours_to_expiry')
            
            if hours_to_expiry is not None and hours_to_expiry <= 1.0:
                # Force exit 1 hour before expiry - market will resolve soon
                should_exit = True
                exit_reason = f"expiry_safety_exit_{hours_to_expiry:.1f}h"
                logger.info(f"⚠️ AUTO-EXIT: {market_id[:16]} expires in {hours_to_expiry:.1f}h - forcing exit")
            
            # Take profit - configurable by strategy/asset
            elif pnl_pct >= take_profit_threshold:
                should_exit = True
                exit_reason = "take_profit"
            
            # Stop loss - configurable by strategy/asset
            elif pnl_pct <= stop_loss_threshold:
                should_exit = True
                exit_reason = "stop_loss"
            
            # RL suggests opposite action with high confidence
            elif rl_confidence > 0.7:
                if side == 'YES' and 'SELL' in rl_action:
                    should_exit = True
                    exit_reason = "rl_signal_reversal"
                elif side == 'NO' and 'BUY' in rl_action:
                    should_exit = True
                    exit_reason = "rl_signal_reversal"
            
            # Time-based exit - configurable by strategy/asset
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            hours_open = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
            if hours_open > max_hours:
                should_exit = True
                exit_reason = "time_limit"
            
            # WARN but don't force exit for positions expiring within 6 hours
            if not should_exit and hours_to_expiry is not None and hours_to_expiry <= 6.0 and hours_to_expiry > 1.0:
                logger.warning(f"⏱️ Position {market_id[:16]} expires in {hours_to_expiry:.1f}h - consider manual exit")
            
            if should_exit:
                # Log exit parameters used
                logger.debug(f"Exit triggered for {market_id[:16]}: {exit_reason} | Strategy: {strategy}, Asset: {asset_class}")
                logger.debug(f"  Params: TP={take_profit_threshold:.0%}, SL={stop_loss_threshold:.0%}, MaxHrs={max_hours:.1f}")
                await self._execute_paper_exit(market_id, market_data, exit_reason)
                
        except Exception as e:
            logger.error(f"Error evaluating exit: {e}")
    
    async def _execute_paper_entry(self, market_id: str, market_data: Dict, side: str,
                                    size: float, strategy: str, signals: Dict,
                                    rl_action: str, rl_confidence: float,
                                    sizing_breakdown: Dict = None):
        """Execute a paper trade entry with adaptive sizing info"""
        try:
            current_price = market_data.get('yes_price', 0.5)
            asset_class = market_data.get('asset_class', market_data.get('category', 'unknown'))
            
            # Extract expiry info from sizing breakdown
            expiry_info = sizing_breakdown.get('expiry_info', {}) if sizing_breakdown else {}
            
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
                # Store expiry info for UI display
                "expiry_info": {
                    "hours_to_expiry": expiry_info.get('hours_to_expiry'),
                    "days_to_expiry": expiry_info.get('days_to_expiry'),
                    "urgency": expiry_info.get('urgency', 'normal'),
                    "expiry_label": expiry_info.get('expiry_label', 'No expiry'),
                    "end_date": market_data.get('end_date')
                }
            }
            
            self.paper_positions[market_id] = position
            self.current_capital -= size
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
            
            # Calculate reward for RL
            reward = self._calculate_rl_reward(pnl_pct, is_win, exit_reason)
            
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
            
            # Store closed trade with hold time calculation
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            exit_time = datetime.now(timezone.utc)
            hold_time_seconds = (exit_time - entry_time).total_seconds()
            
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
    
    def _calculate_rl_reward(self, pnl_pct: float, is_win: bool, exit_reason: str) -> float:
        """Calculate reward signal for RL based on trade outcome"""
        # Base reward from P&L
        reward = pnl_pct * 10  # Scale up small percentages
        
        # Bonus for wins, penalty for losses
        if is_win:
            reward += 0.2
        else:
            reward -= 0.1
        
        # Bonus for good exit reasons
        if exit_reason == "take_profit":
            reward += 0.3
        elif exit_reason == "rl_signal_reversal" and is_win:
            reward += 0.2  # Good RL reversal call
        elif exit_reason == "stop_loss":
            reward -= 0.1  # Minor penalty for hitting stop loss
        elif exit_reason == "time_limit" and not is_win:
            reward -= 0.2  # Penalty for holding losing position too long
        
        return np.clip(reward, -2.0, 2.0)  # Clip to reasonable range
    
    def _calculate_position_size(self, rl_confidence: float, signals: Dict, market_data: Dict = None, strategy: str = None, asset_class: str = None, rl_action: str = 'HOLD') -> Dict:
        """
        Calculate position size using ADAPTIVE position sizing.
        
        Uses multiple factors:
        - Liquidity (volume, outstanding contracts)
        - Kelly criterion with learned parameters
        - RL confidence
        - Volatility regime
        - Asset class and strategy risk profiles
        
        Returns dict with position_size and full breakdown.
        """
        # Use adaptive position sizer
        market_data = market_data or {}
        strategy = strategy or self.enabled_strategies[0] if self.enabled_strategies else 'arbitrage'
        asset_class = asset_class or 'finance'
        
        # Inject user config thresholds into market_data for position sizer to use
        market_data_with_config = {
            **market_data,
            '_min_volume_threshold': self.min_volume_24h,  # User-configured threshold
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
            kelly_enabled=self.kelly_enabled  # Pass kelly_enabled toggle from user config
        )
        
        # Log sizing decision for analysis
        if sizing_result['should_trade']:
            logger.debug(f"Position sizing: ${sizing_result['position_size']:.2f} | "
                        f"Liquidity: {sizing_result['sizing_breakdown']['liquidity_multiplier']:.2f} | "
                        f"RL: {sizing_result['sizing_breakdown']['rl_confidence_multiplier']:.2f}")
        
        return sizing_result
    
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
        
        # 1. ALPHA DIRECTIONAL: Extreme prices (< 0.10 or > 0.90) - clear directional bets
        if (yes_price < 0.10 or yes_price > 0.90) and 'alpha_directional' in self.enabled_strategies:
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
            
            # Try to get enhanced sentiment (LLM + Correlation)
            try:
                if hasattr(self, 'enhanced_sentiment') and self.enhanced_sentiment:
                    enhanced_result = await asyncio.wait_for(
                        self.enhanced_sentiment.analyze(market_data),
                        timeout=3.0  # 3 second timeout
                    )
                    
                    llm_sentiment = enhanced_result.get('llm_sentiment', 0.5)
                    llm_confidence = enhanced_result.get('llm_confidence', 0.0)
                    correlation_sentiment = enhanced_result.get('correlation_sentiment', 0.5)
                    correlation_strength = enhanced_result.get('correlation_strength', 0.0)
                    
                    enhanced_data = {
                        'llm_sentiment': llm_sentiment,
                        'llm_confidence': llm_confidence,
                        'llm_reasoning': enhanced_result.get('llm_reasoning', ''),
                        'correlation_sentiment': correlation_sentiment,
                        'correlation_strength': correlation_strength,
                        'category_momentum': enhanced_result.get('category_momentum', 0.0),
                        'related_groups': enhanced_result.get('related_groups', []),
                        'analysis_source': enhanced_result.get('analysis_source', 'none')
                    }
            except asyncio.TimeoutError:
                logger.debug(f"Enhanced sentiment timeout for {market_id[:16]}")
            except Exception as e:
                logger.debug(f"Enhanced sentiment error: {e}")
            
            # ================================================================
            # LAYER 3: EXTERNAL NEWS/SOCIAL (Finnhub - if available)
            # ================================================================
            news_sentiment = 0.5
            social_sentiment = 0.5
            external_confidence = 0.0
            news_data = {}
            
            # Try to get news/social sentiment (non-blocking, with timeout)
            try:
                if hasattr(self, 'social_analyzer') and self.social_analyzer:
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
            # FINAL SENTIMENT FUSION (4 Layers)
            # ================================================================
            # Calculate weights based on data availability/confidence
            market_weight = 0.40  # Market microstructure always gets 40%
            llm_weight = llm_confidence * 0.30  # LLM gets up to 30% based on confidence
            corr_weight = correlation_strength * 0.15  # Correlation gets up to 15%
            external_weight = external_confidence * 0.15  # External data gets up to 15%
            
            total_weight = market_weight + llm_weight + corr_weight + external_weight
            
            if total_weight > 0:
                raw_sentiment = (
                    market_sentiment * market_weight +
                    llm_sentiment * llm_weight +
                    correlation_sentiment * corr_weight +
                    external_sentiment * external_weight
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
                    'llm_sentiment': round(llm_sentiment, 4),
                    'llm_confidence': round(llm_confidence, 4),
                    'correlation_sentiment': round(correlation_sentiment, 4),
                    'correlation_strength': round(correlation_strength, 4),
                    'external_data': round(external_sentiment, 4),
                    'external_confidence': round(external_confidence, 4),
                },
                'sentiment_weights': {
                    'market_weight': round(market_weight, 4),
                    'llm_weight': round(llm_weight, 4),
                    'correlation_weight': round(corr_weight, 4),
                    'external_weight': round(external_weight, 4),
                },
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
                        
                        total_unrealized += unrealized
                    
                    self.unrealized_pnl = round(total_unrealized, 2)
                    
                    # CIRCUIT BREAKER: Check drawdown including unrealized losses
                    combined_capital = self.current_capital + self.unrealized_pnl
                    if self.peak_capital > 0:
                        combined_drawdown = (self.peak_capital - combined_capital) / self.peak_capital
                        combined_drawdown_pct = combined_drawdown * 100
                        
                        if combined_drawdown_pct >= self.max_drawdown_pct and not self.circuit_breaker_triggered:
                            logger.warning(f"🚨 CIRCUIT BREAKER TRIGGERED (unrealized)! Drawdown {combined_drawdown_pct:.2f}% >= {self.max_drawdown_pct}% limit")
                            logger.warning(f"   Peak: ${self.peak_capital:.2f} | Combined: ${combined_capital:.2f} | Unrealized: ${self.unrealized_pnl:.2f}")
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
        
        return {
            "session_id": self.session_id,
            "running": self.running,
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,  # Highest capital reached
            "current_drawdown_pct": ((self.peak_capital - self.current_capital) / self.peak_capital * 100) if self.peak_capital > 0 else 0,
            "deployed_capital": self.deployed_capital,  # Capital available for trading
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
        """Get current open paper positions"""
        return list(self.paper_positions.values())
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history"""
        return self.trade_history[-limit:]
