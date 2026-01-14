"""
Paper Trading Engine with Full RL Integration
Simulates live trading, tracks positions, and feeds rewards to RL for continuous learning
"""
import asyncio
import logging
import uuid
from typing import Dict, List, Optional
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

class PaperTrader:
    """
    Paper Trading Engine - Simulates live trading without real money
    
    Key Features:
    - Tracks virtual positions and P&L
    - Feeds trade outcomes to RL for learning
    - Uses same signals as live trading
    - Records all decisions for analysis
    """
    
    def __init__(self, initial_capital: float = 10000.0):
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
        
        # User configuration (loaded from DB)
        self.enabled_strategies = ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
        self.enabled_asset_classes = ['finance', 'politics', 'crypto', 'entertainment', 'science', 'sports']
        
        # Paper positions tracking
        self.paper_positions: Dict[str, Dict] = {}
        self.closed_trades: List[Dict] = []
        self.trade_history: List[Dict] = []
        
        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
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
        
        # Equity curve tracking
        self.equity_curve: List[Dict] = []
        
        # Learning parameters
        self.kelly_fraction = 0.25
        self.max_position_pct = 0.1  # Max 10% of capital per position
        self.trade_interval = 5  # Seconds between trade evaluations
        
        logger.info(f"Paper Trader initialized - Session: {self.session_id}, Capital: ${initial_capital}")
    
    async def _load_user_config(self):
        """Load user trading configuration from database"""
        try:
            config = await self.db.user_config.find_one({"type": "trading_preferences"})
            if config:
                if "enabled_strategies" in config:
                    self.enabled_strategies = config["enabled_strategies"]
                if "enabled_asset_classes" in config:
                    self.enabled_asset_classes = config["enabled_asset_classes"]
                logger.info(f"Loaded user config: {len(self.enabled_strategies)} strategies, {len(self.enabled_asset_classes)} asset classes")
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
            self._learning_loop()
        )
    
    async def stop(self):
        """Stop paper trading and save final results"""
        self.running = False
        
        # Close all open positions at current prices
        await self._close_all_positions()
        
        # Save session results
        await self._save_session_results()
        
        # Final RL learning from session
        await self._learn_from_session()
        
        logger.info(f"Paper Trading Stopped - Total PnL: ${self.total_pnl:.2f}")
    
    async def _init_session(self):
        """Initialize paper trading session in database"""
        session_doc = {
            "session_id": self.session_id,
            "type": "paper_trading",
            "initial_capital": self.initial_capital,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "trades": [],
            "positions": []
        }
        await self.db.paper_trading_sessions.insert_one(session_doc)
    
    async def _trading_loop(self):
        """Main paper trading loop - evaluates markets and executes paper trades"""
        logger.info("Paper Trading loop started")
        
        while self.running:
            try:
                # Fetch active markets
                markets = await self._get_active_markets()
                
                for market_data in markets[:20]:  # Limit to top 20 markets
                    if not self.running:
                        break
                    
                    # Check existing paper position
                    market_id = market_data.get('id')
                    if market_id in self.paper_positions:
                        await self._evaluate_exit(market_id, market_data)
                    else:
                        await self._evaluate_entry(market_data)
                    
                    await asyncio.sleep(0.5)  # Brief pause between markets
                
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
            self.trade_history.append(trade_log)
            await self.db.paper_trades.insert_one(trade_log)
            
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
            
            # Update strategy stats
            if strategy in self.strategy_stats:
                self.strategy_stats[strategy]['pnl'] += pnl
                if is_win:
                    self.strategy_stats[strategy]['wins'] += 1
            
            # Update asset class stats
            if asset_class in self.asset_class_stats:
                self.asset_class_stats[asset_class]['pnl'] += pnl
                if is_win:
                    self.asset_class_stats[asset_class]['wins'] += 1
            
            # Calculate reward for RL
            reward = self._calculate_rl_reward(pnl_pct, is_win, exit_reason)
            
            # Feed reward to RL engine
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
            self.trade_history.append(trade_log)
            await self.db.paper_trades.insert_one(trade_log)
            
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
        """Calculate position size using Kelly Criterion and RL confidence"""
        # Base position from Kelly
        win_rate = self.winning_trades / max(self.total_trades, 1)
        if win_rate == 0:
            win_rate = 0.5  # Default assumption
        
        avg_win = 0.15  # Assume 15% avg win
        avg_loss = 0.10  # Assume 10% avg loss
        
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win if avg_win > 0 else 0
        kelly = max(0, min(kelly, self.kelly_fraction))  # Fractional Kelly
        
        # Scale by RL confidence
        confidence_multiplier = 0.5 + (rl_confidence * 0.5)  # 0.5 to 1.0
        
        # Calculate position size
        max_position = self.current_capital * self.max_position_pct
        position_size = self.current_capital * kelly * confidence_multiplier
        position_size = min(position_size, max_position)
        
        return round(position_size, 2)
    
    def _determine_strategy(self, signals: Dict, rl_action: str) -> str:
        """Determine which strategy to use based on signals"""
        volatility = signals.get('volatility', 0.02)
        sentiment_strength = abs(signals.get('sentiment', 0.5) - 0.5)
        sharp_alignment = signals.get('sharp_alignment', 0.5)
        
        # High volatility -> volatility exploitation
        if volatility > 0.05:
            return 'volatility_exploitation'
        
        # Strong sentiment + sharp alignment -> alpha directional
        if sentiment_strength > 0.2 and sharp_alignment > 0.6:
            return 'alpha_directional'
        
        # Low volatility, neutral -> delta neutral
        if volatility < 0.02:
            return 'delta_neutral'
        
        # Default to arbitrage if conditions allow
        return 'arbitrage'
    
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
                        
                        total_unrealized += unrealized
                    
                    logger.debug(f"Paper Positions: {len(self.paper_positions)} | Unrealized: ${total_unrealized:.2f}")
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(10)
    
    async def _learning_loop(self):
        """Periodic RL learning from replay buffer"""
        while self.running:
            try:
                # Train from replay buffer every few minutes
                await self.rl_engine.train_from_replay()
                
                # Save model periodically
                if self.total_trades > 0 and self.total_trades % 10 == 0:
                    await self.rl_engine.save_model()
                    logger.info("RL model saved during paper trading")
                
                await asyncio.sleep(60)  # Learn every minute
                
            except Exception as e:
                logger.error(f"Error in learning loop: {e}")
                await asyncio.sleep(60)
    
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
        """Get current paper trading status"""
        win_rate = self.winning_trades / max(self.total_trades, 1)
        
        return {
            "session_id": self.session_id,
            "running": self.running,
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": (self.total_pnl / self.initial_capital) * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "max_drawdown": self.max_drawdown,
            "open_positions": len(self.paper_positions),
            "strategy_stats": self.strategy_stats,
            "asset_class_stats": self.asset_class_stats
        }
    
    def get_positions(self) -> List[Dict]:
        """Get current open paper positions"""
        return list(self.paper_positions.values())
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history"""
        return self.trade_history[-limit:]
