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
    """
    
    def __init__(self, initial_capital: float = 10000.0, continuous_mode: bool = False):
        self.db = get_db()
        self.rl_engine = RLAdaptiveEngine()
        self.market_data_service = MarketDataService()
        self.sharp_detector = SharpDetector()
        self.volatility_predictor = VolatilityPredictor()
        self.signal_fusion = SignalFusionEngine()
        
        self.running = False
        self.session_id = str(uuid.uuid4())[:8]
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # Continuous mode settings
        self.continuous_mode = continuous_mode
        self.graceful_stop = False  # When True, stop accepting new trades but close existing
        self.stop_requested = False
        
        # User configuration (loaded from DB) - FULL CONFIG PARAMETERS
        self.enabled_strategies = ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
        self.enabled_asset_classes = ['finance', 'politics', 'crypto', 'entertainment', 'science', 'sports']
        
        # Trading configuration parameters (loaded from DB/config)
        self.capital_deployment_pct = config.CAPITAL_DEPLOYMENT_PCT  # % of capital to deploy
        self.max_position_size_pct = config.MAX_POSITION_SIZE_PCT  # % of DEPLOYED capital per position
        self.kelly_fraction = config.KELLY_FRACTION  # Kelly criterion multiplier
        self.max_drawdown_pct = config.MAX_DRAWDOWN_PCT  # Maximum allowed drawdown %
        self.trades_per_10min = config.TRADES_PER_10MIN  # Target trades per 10 minutes
        
        # Calculated values based on config
        self.deployed_capital = initial_capital * (self.capital_deployment_pct / 100)
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
        self.peak_capital = initial_capital
        
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
        logger.info(f"  Capital: ${initial_capital} | Deployed: ${self.deployed_capital} ({self.capital_deployment_pct}%)")
        logger.info(f"  Max Position: ${self.max_position_size} ({self.max_position_size_pct}% of deployed)")
        logger.info(f"  Kelly: {self.kelly_fraction} | Max Drawdown: {self.max_drawdown_pct}% | Trade Interval: {self.trade_interval:.1f}s")
    
    async def _load_user_config(self):
        """Load ALL user trading configuration from database"""
        try:
            user_config = await self.db.user_config.find_one({"type": "trading_preferences"})
            if user_config:
                # Load enabled strategies and asset classes
                if "enabled_strategies" in user_config:
                    self.enabled_strategies = user_config["enabled_strategies"]
                if "enabled_asset_classes" in user_config:
                    self.enabled_asset_classes = user_config["enabled_asset_classes"]
                
                # Load trading parameters
                if "capital_deployment_pct" in user_config:
                    self.capital_deployment_pct = float(user_config["capital_deployment_pct"])
                if "max_position_size_pct" in user_config:
                    self.max_position_size_pct = float(user_config["max_position_size_pct"])
                if "kelly_fraction" in user_config:
                    self.kelly_fraction = float(user_config["kelly_fraction"])
                if "max_drawdown_pct" in user_config:
                    self.max_drawdown_pct = float(user_config["max_drawdown_pct"])
                if "trades_per_10min" in user_config:
                    self.trades_per_10min = int(user_config["trades_per_10min"])
                
                # Recalculate derived values based on loaded config
                self.deployed_capital = self.initial_capital * (self.capital_deployment_pct / 100)
                self.max_position_size = self.deployed_capital * (self.max_position_size_pct / 100)
                self.trade_interval = max(1, 600 / self.trades_per_10min)
                
                logger.info("Loaded user config from DB:")
                logger.info(f"  Strategies: {len(self.enabled_strategies)} | Asset Classes: {len(self.enabled_asset_classes)}")
                logger.info(f"  Capital Deployment: {self.capital_deployment_pct}% | Max Position: {self.max_position_size_pct}%")
                logger.info(f"  Deployed Capital: ${self.deployed_capital} | Max Position Size: ${self.max_position_size}")
                logger.info(f"  Kelly: {self.kelly_fraction} | Max Drawdown: {self.max_drawdown_pct}%")
        except Exception as e:
            logger.warning(f"Could not load user config: {e}")
    
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
        
        while self.running:
            try:
                # Fetch active markets filtered by enabled asset classes
                markets = await self._get_active_markets()
                
                for market_data in markets[:20]:  # Limit to top 20 markets
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
                    
                    await asyncio.sleep(0.5)  # Brief pause between markets
                
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
                
                await asyncio.sleep(self.trade_interval)
                
            except Exception as e:
                logger.error(f"Error in paper trading loop: {e}")
                await asyncio.sleep(5)
    
    async def _evaluate_entry(self, market_data: Dict):
        """Evaluate market for potential paper trade entry"""
        try:
            market_id = market_data.get('id')
            
            # Get ML signals
            signals = await self._get_signals(market_data)
            
            # Get RL recommendation
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Skip if RL says wait or low confidence
            if rl_action == 'WAIT' or rl_confidence < 0.4:
                return
            
            # Determine position size based on Kelly and RL confidence
            position_size = self._calculate_position_size(rl_confidence, signals)
            
            if position_size < 10:  # Minimum position size
                return
            
            # Determine strategy based on signals
            strategy = self._determine_strategy(signals, rl_action)
            
            # Determine side (YES/NO)
            side = 'YES' if 'BUY' in rl_action else 'NO'
            
            # Execute paper trade
            await self._execute_paper_entry(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=position_size,
                strategy=strategy,
                signals=signals,
                rl_action=rl_action,
                rl_confidence=rl_confidence
            )
            
        except Exception as e:
            logger.error(f"Error evaluating entry: {e}")
    
    async def _evaluate_exit(self, market_id: str, market_data: Dict):
        """Evaluate existing paper position for exit"""
        try:
            position = self.paper_positions.get(market_id)
            if not position:
                return
            
            current_price = market_data.get('yes_price', 0.5)
            entry_price = position['entry_price']
            side = position['side']
            
            # Calculate unrealized P&L
            if side == 'YES':
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            else:
                pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
            
            # Get RL recommendation for exit
            signals = await self._get_signals(market_data)
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Exit conditions
            should_exit = False
            exit_reason = None
            
            # Take profit
            if pnl_pct > 0.3:  # 30% profit
                should_exit = True
                exit_reason = "take_profit"
            
            # Stop loss
            elif pnl_pct < -0.15:  # 15% loss
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
            
            # Time-based exit (positions open too long)
            entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
            hours_open = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
            if hours_open > 24:  # Close after 24 hours
                should_exit = True
                exit_reason = "time_limit"
            
            if should_exit:
                await self._execute_paper_exit(market_id, market_data, exit_reason)
                
        except Exception as e:
            logger.error(f"Error evaluating exit: {e}")
    
    async def _execute_paper_entry(self, market_id: str, market_data: Dict, side: str,
                                    size: float, strategy: str, signals: Dict,
                                    rl_action: str, rl_confidence: float):
        """Execute a paper trade entry"""
        try:
            current_price = market_data.get('yes_price', 0.5)
            asset_class = market_data.get('asset_class', 'unknown')
            
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
                "signals": signals
            }
            
            self.paper_positions[market_id] = position
            self.current_capital -= size
            self.total_trades += 1
            
            # Track strategy stats
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['trades'] += 1
            
            # Track asset class stats
            if asset_class not in self.asset_class_stats:
                self.asset_class_stats[asset_class] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
            self.asset_class_stats[asset_class]['trades'] += 1
            
            # Log trade
            trade_log = {
                "trade_id": position['position_id'],
                "session_id": self.session_id,
                "type": "entry",
                "market_id": market_id,
                "side": side,
                "size": size,
                "price": current_price,
                "strategy": strategy,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "timestamp": datetime.now(timezone.utc).isoformat()
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
            size = position['size']
            strategy = position['strategy']
            asset_class = position.get('asset_class', 'unknown')
            
            # Calculate P&L
            if side == 'YES':
                pnl = (current_price - entry_price) * size / entry_price
            else:
                pnl = (entry_price - current_price) * size / entry_price
            
            pnl_pct = pnl / size if size > 0 else 0
            
            # Track return for distribution
            self.trade_returns.append(pnl_pct * 100)  # Store as percentage
            
            # Update metrics
            self.total_pnl += pnl
            self.current_capital += size + pnl
            
            # Track drawdown
            if self.current_capital > self.peak_capital:
                self.peak_capital = self.current_capital
            drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
            self.max_drawdown = max(self.max_drawdown, drawdown)
            
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
            
            # Store closed trade
            closed_trade = {
                **position,
                "exit_price": current_price,
                "exit_time": datetime.now(timezone.utc).isoformat(),
                "exit_reason": exit_reason,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "reward_signal": reward
            }
            self.closed_trades.append(closed_trade)
            
            # Log trade
            trade_log = {
                "trade_id": str(uuid.uuid4()),
                "session_id": self.session_id,
                "type": "exit",
                "market_id": market_id,
                "side": side,
                "size": size,
                "entry_price": entry_price,
                "exit_price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "strategy": strategy,
                "exit_reason": exit_reason,
                "reward_signal": reward,
                "timestamp": datetime.now(timezone.utc).isoformat()
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
    
    def _calculate_position_size(self, rl_confidence: float, signals: Dict) -> float:
        """Calculate position size using Kelly Criterion and RL confidence
        
        Position size is calculated as a % of DEPLOYED capital (not total capital)
        - deployed_capital = initial_capital * capital_deployment_pct
        - max_position = deployed_capital * max_position_size_pct
        - position_size = deployed_capital * kelly * confidence_multiplier (capped at max_position)
        """
        # Base position from Kelly
        win_rate = self.winning_trades / max(self.total_trades, 1)
        if win_rate == 0:
            win_rate = 0.5  # Default assumption
        
        avg_win = 0.15  # Assume 15% avg win
        avg_loss = 0.10  # Assume 10% avg loss
        
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win if avg_win > 0 else 0
        kelly = max(0, min(kelly, self.kelly_fraction))  # Fractional Kelly capped by user config
        
        # Scale by RL confidence
        confidence_multiplier = 0.5 + (rl_confidence * 0.5)  # 0.5 to 1.0
        
        # Calculate available capital for trading (respecting capital deployment %)
        # deployed_capital is already calculated from initial_capital * capital_deployment_pct
        available_capital = min(self.current_capital, self.deployed_capital)
        
        # Calculate position size based on deployed capital
        position_size = available_capital * kelly * confidence_multiplier
        
        # Cap at max_position_size (which is max_position_size_pct of deployed_capital)
        position_size = min(position_size, self.max_position_size)
        
        # Ensure we don't exceed current available capital
        position_size = min(position_size, self.current_capital * 0.9)  # Leave 10% buffer
        
        return round(position_size, 2)
    
    def _determine_strategy(self, signals: Dict, rl_action: str) -> Optional[str]:
        """Determine which strategy to use based on signals and enabled strategies"""
        volatility = signals.get('volatility', 0.02)
        sentiment_strength = abs(signals.get('sentiment', 0.5) - 0.5)
        sharp_alignment = signals.get('sharp_alignment', 0.5)
        
        # High volatility -> volatility exploitation
        if volatility > 0.05 and 'volatility_exploitation' in self.enabled_strategies:
            return 'volatility_exploitation'
        
        # Strong sentiment + sharp alignment -> alpha directional
        if sentiment_strength > 0.2 and sharp_alignment > 0.6 and 'alpha_directional' in self.enabled_strategies:
            return 'alpha_directional'
        
        # Low volatility, neutral -> delta neutral
        if volatility < 0.02 and 'delta_neutral' in self.enabled_strategies:
            return 'delta_neutral'
        
        # Default to arbitrage if enabled
        if 'arbitrage' in self.enabled_strategies:
            return 'arbitrage'
        
        # Return first enabled strategy as fallback
        return self.enabled_strategies[0] if self.enabled_strategies else None
    
    async def _get_signals(self, market_data: Dict) -> Dict:
        """Get ML signals for market evaluation"""
        try:
            signals = {
                'volatility': 0.02,
                'sentiment': 0.5,
                'sharp_alignment': 0.5,
                'whale_activity': 0.0
            }
            
            # Get volatility prediction
            try:
                vol_pred = await self.volatility_predictor.predict(market_data)
                signals['volatility'] = vol_pred.get('predicted_volatility', 0.02)
            except:
                pass
            
            # Get sentiment
            try:
                sentiment = await self.signal_fusion.get_fused_signal(market_data.get('id'), market_data)
                signals['sentiment'] = sentiment.get('sentiment', 0.5)
            except:
                pass
            
            # Get sharp trader alignment
            try:
                sharp_signals = await self.sharp_detector.get_alignment_signal(market_data.get('id'))
                signals['sharp_alignment'] = sharp_signals.get('alignment_score', 0.5)
            except:
                pass
            
            return signals
            
        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            return {'volatility': 0.02, 'sentiment': 0.5, 'sharp_alignment': 0.5}
    
    async def _position_monitoring_loop(self):
        """Monitor open positions and update unrealized P&L"""
        while self.running:
            try:
                if self.paper_positions:
                    markets = await self._get_active_markets()
                    market_prices = {m['id']: m.get('yes_price', 0.5) for m in markets}
                    
                    total_unrealized = 0.0
                    for market_id, position in self.paper_positions.items():
                        current_price = market_prices.get(market_id, position['entry_price'])
                        entry_price = position['entry_price']
                        side = position['side']
                        size = position['size']
                        
                        if side == 'YES':
                            unrealized = (current_price - entry_price) * size / entry_price
                        else:
                            unrealized = (entry_price - current_price) * size / entry_price
                        
                        # Update position with current unrealized P&L
                        position['current_price'] = current_price
                        position['unrealized_pnl'] = unrealized
                        position['unrealized_pnl_pct'] = (unrealized / size) * 100 if size > 0 else 0
                        
                        total_unrealized += unrealized
                    
                    # Update total unrealized P&L for status display
                    self.unrealized_pnl = total_unrealized
                    
                    logger.debug(f"Paper Positions: {len(self.paper_positions)} | Unrealized: ${total_unrealized:.2f}")
                else:
                    self.unrealized_pnl = 0.0
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(10)
    
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
        """Get active markets from database"""
        try:
            cursor = self.db.markets.find(
                {"liquidity": {"$gte": 1000}},
                {"_id": 0}
            ).limit(100)
            return await cursor.to_list(length=100)
        except Exception as e:
            logger.error(f"Error getting markets: {e}")
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
        
        # Calculate returns distribution
        returns_distribution = self._calculate_returns_distribution()
        
        # Calculate total P&L including unrealized
        combined_pnl = self.total_pnl + self.unrealized_pnl
        
        return {
            "session_id": self.session_id,
            "running": self.running,
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
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
            "open_positions": len(self.paper_positions),
            "strategy_results": strategy_results,
            "asset_class_results": asset_class_results,
            "returns_distribution": returns_distribution,
            "equity_curve": self.equity_curve[-200:],  # Last 200 points for better charts
            "strategy_equity": self.strategy_equity,  # Running P&L by strategy
            "asset_class_equity": self.asset_class_equity,  # Running P&L by asset class
            "enabled_strategies": self.enabled_strategies,
            "enabled_asset_classes": self.enabled_asset_classes,
            "continuous_mode": self.continuous_mode,
            "graceful_stop": self.graceful_stop,
            # Configuration parameters being used
            "config": {
                "capital_deployment_pct": self.capital_deployment_pct,
                "max_position_size_pct": self.max_position_size_pct,
                "max_position_size": self.max_position_size,
                "kelly_fraction": self.kelly_fraction,
                "max_drawdown_pct": self.max_drawdown_pct,
                "trades_per_10min": self.trades_per_10min,
                "trade_interval_seconds": self.trade_interval
            },
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
        if not self.trade_returns:
            return {"bins": [], "stats": {}}
        
        # Create histogram bins
        bins = []
        bin_edges = [-50, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 50]
        
        for i in range(len(bin_edges) - 1):
            min_val = bin_edges[i]
            max_val = bin_edges[i + 1]
            count = sum(1 for r in self.trade_returns if min_val <= r < max_val)
            bins.append({
                "min": min_val,
                "max": max_val,
                "label": f"{min_val}% to {max_val}%",
                "count": count
            })
        
        # Calculate stats
        returns_array = np.array(self.trade_returns)
        stats = {
            "mean": float(np.mean(returns_array)),
            "median": float(np.median(returns_array)),
            "std": float(np.std(returns_array)),
            "positive_returns": sum(1 for r in self.trade_returns if r > 0),
            "negative_returns": sum(1 for r in self.trade_returns if r < 0),
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
