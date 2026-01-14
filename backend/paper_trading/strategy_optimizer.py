"""
Strategy Optimizer - Learns optimal parameters from paper trading results
Refines trade detection, execution timing, position sizing, and strategy selection
"""
import logging
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timezone
from database import get_db
import uuid

logger = logging.getLogger(__name__)

class StrategyOptimizer:
    """
    Learns and optimizes trading strategy parameters from paper trading results
    
    Optimizes:
    - Entry/Exit thresholds
    - Position sizing parameters
    - Strategy selection weights
    - Risk parameters (stop loss, take profit)
    - Timing parameters
    """
    
    def __init__(self):
        self.db = get_db()
        
        # Optimizable parameters with defaults
        self.params = {
            # Entry thresholds
            'min_rl_confidence': 0.4,
            'min_sentiment_strength': 0.15,
            'min_sharp_alignment': 0.5,
            'min_volatility_threshold': 0.01,
            'max_volatility_threshold': 0.15,
            
            # Exit thresholds
            'take_profit_pct': 0.30,
            'stop_loss_pct': 0.15,
            'max_hold_hours': 24,
            
            # Position sizing
            'kelly_fraction': 0.25,
            'max_position_pct': 0.10,
            'min_position_size': 10,
            
            # Strategy weights (sum to 1.0)
            'strategy_weights': {
                'delta_neutral': 0.25,
                'volatility_exploitation': 0.25,
                'alpha_directional': 0.25,
                'arbitrage': 0.25
            },
            
            # Timing
            'trade_interval_seconds': 5,
            'position_check_interval': 10,
            
            # Risk
            'max_open_positions': 10,
            'max_drawdown_limit': 0.20,
            'daily_loss_limit': 0.05
        }
        
        # Learning rates for different parameter types
        self.learning_rates = {
            'thresholds': 0.1,
            'sizing': 0.05,
            'timing': 0.02,
            'weights': 0.08
        }
        
        # Performance history for analysis
        self.optimization_history: List[Dict] = []
    
    async def load_params(self) -> Dict:
        """Load optimized parameters from database"""
        try:
            doc = await self.db.strategy_params.find_one(
                {"type": "optimized"},
                sort=[("timestamp", -1)]
            )
            if doc:
                self.params = doc.get('params', self.params)
                logger.info("Loaded optimized strategy parameters")
            return self.params
        except Exception as e:
            logger.error(f"Error loading params: {e}")
            return self.params
    
    async def save_params(self):
        """Save current parameters to database"""
        try:
            await self.db.strategy_params.insert_one({
                "id": str(uuid.uuid4()),
                "type": "optimized",
                "params": self.params,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.info("Saved optimized strategy parameters")
        except Exception as e:
            logger.error(f"Error saving params: {e}")
    
    async def optimize_from_paper_session(self, session_id: str) -> Dict:
        """Optimize parameters based on paper trading session results"""
        try:
            # Load session data
            session = await self.db.paper_trading_sessions.find_one({"session_id": session_id})
            if not session:
                return {"error": "Session not found"}
            
            # Load trade history for this session
            cursor = self.db.paper_trades.find({"session_id": session_id})
            trades = await cursor.to_list(length=1000)
            
            if len(trades) < 10:
                return {"error": "Not enough trades to optimize", "trades": len(trades)}
            
            # Analyze trades and optimize
            optimizations = {}
            
            # 1. Optimize entry thresholds
            entry_opt = await self._optimize_entry_thresholds(trades)
            optimizations['entry_thresholds'] = entry_opt
            
            # 2. Optimize exit thresholds
            exit_opt = await self._optimize_exit_thresholds(trades)
            optimizations['exit_thresholds'] = exit_opt
            
            # 3. Optimize position sizing
            sizing_opt = await self._optimize_position_sizing(trades, session)
            optimizations['position_sizing'] = sizing_opt
            
            # 4. Optimize strategy weights
            weight_opt = await self._optimize_strategy_weights(session)
            optimizations['strategy_weights'] = weight_opt
            
            # 5. Optimize timing
            timing_opt = await self._optimize_timing(trades)
            optimizations['timing'] = timing_opt
            
            # Save optimized parameters
            await self.save_params()
            
            # Store optimization history
            opt_record = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "optimizations": optimizations,
                "params_after": self.params.copy(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.db.optimization_history.insert_one(opt_record)
            self.optimization_history.append(opt_record)
            
            logger.info(f"Strategy optimization complete from session {session_id}")
            
            return {
                "success": True,
                "optimizations": optimizations,
                "new_params": self.params
            }
            
        except Exception as e:
            logger.error(f"Error optimizing from session: {e}")
            return {"error": str(e)}
    
    async def _optimize_entry_thresholds(self, trades: List[Dict]) -> Dict:
        """Optimize entry signal thresholds based on winning vs losing trades"""
        try:
            winning_trades = [t for t in trades if t.get('type') == 'exit' and t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('type') == 'exit' and t.get('pnl', 0) <= 0]
            
            if not winning_trades or not losing_trades:
                return {"skipped": "Insufficient data"}
            
            # Analyze RL confidence patterns
            avg_win_confidence = np.mean([t.get('rl_confidence', 0.5) for t in winning_trades])
            avg_lose_confidence = np.mean([t.get('rl_confidence', 0.5) for t in losing_trades])
            
            # Adjust minimum confidence threshold
            if avg_win_confidence > avg_lose_confidence:
                # Winning trades had higher confidence - raise threshold
                new_threshold = (avg_win_confidence + self.params['min_rl_confidence']) / 2
                old_threshold = self.params['min_rl_confidence']
                self.params['min_rl_confidence'] = round(new_threshold, 3)
                
                return {
                    "min_rl_confidence": {
                        "old": old_threshold,
                        "new": self.params['min_rl_confidence'],
                        "reason": f"Winning avg: {avg_win_confidence:.3f}, Losing avg: {avg_lose_confidence:.3f}"
                    }
                }
            
            return {"no_change": "Confidence patterns inconclusive"}
            
        except Exception as e:
            logger.error(f"Error optimizing entry thresholds: {e}")
            return {"error": str(e)}
    
    async def _optimize_exit_thresholds(self, trades: List[Dict]) -> Dict:
        """Optimize take profit and stop loss levels"""
        try:
            exit_trades = [t for t in trades if t.get('type') == 'exit']
            if not exit_trades:
                return {"skipped": "No exit trades"}
            
            changes = {}
            
            # Analyze take profit exits
            tp_exits = [t for t in exit_trades if t.get('exit_reason') == 'take_profit']
            if tp_exits:
                avg_tp_pnl = np.mean([t.get('pnl_pct', 0) for t in tp_exits])
                # If average TP exit is well above threshold, we might be exiting too early
                if avg_tp_pnl > self.params['take_profit_pct'] * 1.5:
                    old_tp = self.params['take_profit_pct']
                    self.params['take_profit_pct'] = min(0.50, old_tp * 1.1)
                    changes['take_profit_pct'] = {
                        "old": old_tp,
                        "new": self.params['take_profit_pct'],
                        "reason": f"Average TP exit at {avg_tp_pnl:.1%}, raising threshold"
                    }
            
            # Analyze stop loss exits
            sl_exits = [t for t in exit_trades if t.get('exit_reason') == 'stop_loss']
            if sl_exits:
                avg_sl_pnl = np.mean([t.get('pnl_pct', 0) for t in sl_exits])
                # If stop loss hits are very frequent, tighten stop loss
                sl_rate = len(sl_exits) / len(exit_trades)
                if sl_rate > 0.3:  # More than 30% of exits are stop losses
                    old_sl = self.params['stop_loss_pct']
                    self.params['stop_loss_pct'] = max(0.08, old_sl * 0.9)
                    changes['stop_loss_pct'] = {
                        "old": old_sl,
                        "new": self.params['stop_loss_pct'],
                        "reason": f"High stop loss rate ({sl_rate:.1%}), tightening"
                    }
            
            return changes if changes else {"no_change": "Exit thresholds optimal"}
            
        except Exception as e:
            logger.error(f"Error optimizing exit thresholds: {e}")
            return {"error": str(e)}
    
    async def _optimize_position_sizing(self, trades: List[Dict], session: Dict) -> Dict:
        """Optimize Kelly fraction and position size limits"""
        try:
            exit_trades = [t for t in trades if t.get('type') == 'exit']
            if not exit_trades:
                return {"skipped": "No exit trades"}
            
            changes = {}
            
            # Calculate actual win rate and average win/loss
            wins = [t for t in exit_trades if t.get('pnl', 0) > 0]
            losses = [t for t in exit_trades if t.get('pnl', 0) <= 0]
            
            if wins and losses:
                win_rate = len(wins) / len(exit_trades)
                avg_win_pct = np.mean([t.get('pnl_pct', 0) for t in wins])
                avg_loss_pct = abs(np.mean([t.get('pnl_pct', 0) for t in losses]))
                
                # Calculate optimal Kelly
                if avg_win_pct > 0 and avg_loss_pct > 0:
                    optimal_kelly = (win_rate * avg_win_pct - (1 - win_rate) * avg_loss_pct) / avg_win_pct
                    optimal_kelly = max(0.05, min(0.5, optimal_kelly))  # Bound between 5% and 50%
                    
                    old_kelly = self.params['kelly_fraction']
                    # Gradually move towards optimal
                    self.params['kelly_fraction'] = round(
                        old_kelly + self.learning_rates['sizing'] * (optimal_kelly - old_kelly), 3
                    )
                    
                    changes['kelly_fraction'] = {
                        "old": old_kelly,
                        "new": self.params['kelly_fraction'],
                        "optimal": round(optimal_kelly, 3),
                        "reason": f"Win rate: {win_rate:.1%}, Avg win: {avg_win_pct:.1%}, Avg loss: {avg_loss_pct:.1%}"
                    }
            
            # Optimize max position size based on drawdown
            max_dd = session.get('max_drawdown', 0)
            if max_dd > 0.15:  # High drawdown - reduce position sizes
                old_max = self.params['max_position_pct']
                self.params['max_position_pct'] = max(0.05, old_max * 0.9)
                changes['max_position_pct'] = {
                    "old": old_max,
                    "new": self.params['max_position_pct'],
                    "reason": f"High drawdown ({max_dd:.1%}), reducing max position"
                }
            
            return changes if changes else {"no_change": "Sizing optimal"}
            
        except Exception as e:
            logger.error(f"Error optimizing position sizing: {e}")
            return {"error": str(e)}
    
    async def _optimize_strategy_weights(self, session: Dict) -> Dict:
        """Optimize strategy selection weights based on performance"""
        try:
            strategy_stats = session.get('strategy_stats', {})
            if not strategy_stats:
                return {"skipped": "No strategy stats"}
            
            changes = {}
            total_pnl = sum(s.get('pnl', 0) for s in strategy_stats.values())
            
            if total_pnl == 0:
                return {"no_change": "No P&L to optimize from"}
            
            new_weights = {}
            for strategy, stats in strategy_stats.items():
                trades = stats.get('trades', 0)
                if trades == 0:
                    new_weights[strategy] = 0.1  # Minimum weight for untested
                    continue
                
                pnl = stats.get('pnl', 0)
                wins = stats.get('wins', 0)
                win_rate = wins / trades
                
                # Score based on P&L contribution and win rate
                pnl_score = pnl / abs(total_pnl) if total_pnl != 0 else 0
                combined_score = 0.6 * pnl_score + 0.4 * win_rate
                
                # Convert score to weight (ensure positive)
                new_weights[strategy] = max(0.05, combined_score + 0.25)
            
            # Normalize weights to sum to 1
            total_weight = sum(new_weights.values())
            if total_weight > 0:
                new_weights = {k: round(v / total_weight, 3) for k, v in new_weights.items()}
            
            old_weights = self.params['strategy_weights'].copy()
            
            # Gradually move towards new weights
            for strategy in new_weights:
                old_w = old_weights.get(strategy, 0.25)
                new_w = new_weights[strategy]
                self.params['strategy_weights'][strategy] = round(
                    old_w + self.learning_rates['weights'] * (new_w - old_w), 3
                )
            
            changes['strategy_weights'] = {
                "old": old_weights,
                "new": self.params['strategy_weights'],
                "optimal_target": new_weights
            }
            
            return changes
            
        except Exception as e:
            logger.error(f"Error optimizing strategy weights: {e}")
            return {"error": str(e)}
    
    async def _optimize_timing(self, trades: List[Dict]) -> Dict:
        """Optimize trading timing parameters"""
        try:
            exit_trades = [t for t in trades if t.get('type') == 'exit']
            if not exit_trades:
                return {"skipped": "No exit trades"}
            
            changes = {}
            
            # Analyze time-based exits
            time_exits = [t for t in exit_trades if t.get('exit_reason') == 'time_limit']
            if time_exits:
                # Check if time-based exits are profitable or not
                time_exit_pnl = np.mean([t.get('pnl', 0) for t in time_exits])
                time_exit_rate = len(time_exits) / len(exit_trades)
                
                if time_exit_pnl < 0 and time_exit_rate > 0.2:
                    # Many time exits losing - reduce max hold time
                    old_hours = self.params['max_hold_hours']
                    self.params['max_hold_hours'] = max(6, old_hours * 0.8)
                    changes['max_hold_hours'] = {
                        "old": old_hours,
                        "new": self.params['max_hold_hours'],
                        "reason": f"Time exits losing (avg ${time_exit_pnl:.2f}), reducing hold time"
                    }
                elif time_exit_pnl > 0:
                    # Time exits profitable - could hold longer
                    old_hours = self.params['max_hold_hours']
                    self.params['max_hold_hours'] = min(72, old_hours * 1.1)
                    changes['max_hold_hours'] = {
                        "old": old_hours,
                        "new": self.params['max_hold_hours'],
                        "reason": f"Time exits profitable, extending hold time"
                    }
            
            return changes if changes else {"no_change": "Timing optimal"}
            
        except Exception as e:
            logger.error(f"Error optimizing timing: {e}")
            return {"error": str(e)}
    
    async def get_optimization_stats(self) -> Dict:
        """Get current optimization statistics and parameter history"""
        try:
            cursor = self.db.optimization_history.find().sort("timestamp", -1).limit(10)
            history = await cursor.to_list(length=10)
            
            return {
                "current_params": self.params,
                "recent_optimizations": [{
                    "session_id": h.get('session_id'),
                    "timestamp": h.get('timestamp'),
                    "optimizations": h.get('optimizations')
                } for h in history]
            }
            
        except Exception as e:
            logger.error(f"Error getting optimization stats: {e}")
            return {"error": str(e)}
    
    def get_params(self) -> Dict:
        """Get current optimized parameters"""
        return self.params.copy()
