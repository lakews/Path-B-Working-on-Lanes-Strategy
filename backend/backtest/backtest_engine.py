import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from database import get_db
from ml.signal_fusion import SignalFusionEngine
from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
from ml.rl_engine import RLAdaptiveEngine
from strategies.delta_neutral import DeltaNeutralStrategy
from strategies.volatility_exploitation import VolatilityExploitationStrategy
from strategies.alpha_directional import AlphaDirectionalStrategy
from strategies.arbitrage import MultiMarketArbitrageStrategy
from config import config
import uuid

logger = logging.getLogger(__name__)

class BacktestEngine:
    """Backtesting engine for testing strategies on historical data"""
    
    def __init__(self):
        self.db = get_db()
        self.signal_fusion = SignalFusionEngine()
        self.kelly_optimizer = KellySharpeOptimizer()
        self.rl_engine = RLAdaptiveEngine()  # Add RL engine for learning
        
        self.delta_neutral_strategy = DeltaNeutralStrategy()
        self.volatility_strategy = VolatilityExploitationStrategy()
        self.alpha_strategy = AlphaDirectionalStrategy()
        self.arbitrage_strategy = MultiMarketArbitrageStrategy()
        
        self.running = False
        self.backtest_id = None
        
        # Backtest state
        self.initial_capital = config.INITIAL_CAPITAL
        self.current_capital = config.INITIAL_CAPITAL
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        
        # Performance tracking by strategy and asset class
        self.strategy_performance = {}
        self.asset_class_performance = {}
        self.data_summary = {}
        
    async def run_backtest(
        self,
        start_date: str,
        end_date: str,
        strategies: List[str] = None
    ) -> Dict:
        """Run backtest on historical data with RL learning"""
        try:
            self.running = True
            self.backtest_id = str(uuid.uuid4())
            
            logger.info(f"Starting backtest {self.backtest_id}: {start_date} to {end_date}")
            
            # Reset state
            self.current_capital = self.initial_capital
            self.positions = {}
            self.trades = []
            self.equity_curve = []
            self.strategy_performance = {s: {"trades": 0, "wins": 0, "pnl": 0.0, "positions": []} for s in (strategies or [])}
            self.asset_class_performance = {}
            
            # Load RL model if exists
            await self.rl_engine.load_model()
            
            # Get historical market data with summary
            historical_markets, self.data_summary = await self._get_historical_markets_with_summary(start_date, end_date)
            
            if not historical_markets:
                return {
                    "error": "No historical data available for selected date range",
                    "backtest_id": self.backtest_id,
                    "data_summary": self.data_summary
                }
            
            logger.info(f"Processing {len(historical_markets)} historical market snapshots")
            
            # Process each historical snapshot
            for idx, market_snapshot in enumerate(historical_markets):
                if not self.running:
                    break
                
                await self._process_snapshot_with_learning(market_snapshot, strategies)
                
                # Record equity point
                self.equity_curve.append({
                    "timestamp": market_snapshot.get("timestamp"),
                    "equity": self.current_capital,
                    "num_positions": len(self.positions)
                })
                
                # Progress logging
                if idx % 100 == 0:
                    logger.info(f"Backtest progress: {idx}/{len(historical_markets)} snapshots")
            
            # Train RL from replay buffer after backtest
            await self.rl_engine.train_from_replay()
            await self.rl_engine.save_model()
            
            # Calculate final metrics
            results = await self._calculate_backtest_results()
            
            # Store backtest results
            await self._store_backtest_results(results)
            
            logger.info(f"Backtest {self.backtest_id} completed - RL model updated")
            
            return results
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            return {"error": str(e)}
        finally:
            self.running = False
    
    async def stop_backtest(self):
        """Stop running backtest"""
        self.running = False
        logger.info(f"Backtest {self.backtest_id} stopped")
    
    async def _get_historical_markets_with_summary(self, start_date: str, end_date: str):
        """Get historical markets with data summary"""
        try:
            # Query historical data
            cursor = self.db.historical_data.find(
                {
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                },
                {"_id": 0}
            ).sort("timestamp", 1)
            
            markets = await cursor.to_list(length=50000)
            
            # Build data summary
            if markets:
                categories = {}
                for m in markets:
                    cat = m.get("category", "unknown")
                    if cat not in categories:
                        categories[cat] = 0
                    categories[cat] += 1
                
                timestamps = [m.get("timestamp") for m in markets if m.get("timestamp")]
                
                summary = {
                    "total_snapshots": len(markets),
                    "unique_markets": len(set(m.get("market_id") for m in markets if m.get("market_id"))),
                    "date_range": {
                        "start": min(timestamps) if timestamps else None,
                        "end": max(timestamps) if timestamps else None
                    },
                    "categories": categories,
                    "avg_volume": sum(m.get("volume", 0) for m in markets) / len(markets) if markets else 0,
                    "avg_liquidity": sum(m.get("liquidity", 0) for m in markets) / len(markets) if markets else 0
                }
            else:
                summary = {"total_snapshots": 0, "unique_markets": 0, "date_range": {}, "categories": {}}
            
            # Transform to market data format
            market_data_list = []
            for m in markets:
                market_data_list.append({
                    "timestamp": m.get("timestamp"),
                    "market_data": {
                        "id": m.get("market_id"),
                        "question": m.get("question"),
                        "category": m.get("category"),
                        "yes_price": m.get("yes_price", 0.5),
                        "no_price": m.get("no_price", 0.5),
                        "volume": m.get("volume", 0),
                        "liquidity": m.get("liquidity", 0)
                    }
                })
            
            return market_data_list, summary
            
        except Exception as e:
            logger.error(f"Error getting historical markets: {e}")
            return [], {"error": str(e)}
    
    async def _process_snapshot_with_learning(self, market_snapshot: Dict, enabled_strategies: List[str]):
        """Process a single market snapshot with RL learning"""
        try:
            market_data = market_snapshot.get("market_data", {})
            
            if not market_data:
                return
            
            category = market_data.get("category", "unknown")
            
            # Initialize asset class tracking
            if category not in self.asset_class_performance:
                self.asset_class_performance[category] = {"trades": 0, "wins": 0, "pnl": 0.0}
            
            # Update existing positions with current prices
            await self._update_positions_with_tracking(market_data)
            
            # Get signals for RL learning
            signals = await self.signal_fusion.get_fused_signals({
                "market_id": market_data.get("id"),
                "yes_price": market_data.get("yes_price", 0.5),
                "no_price": market_data.get("no_price", 0.5),
                "volume": market_data.get("volume", 0),
                "liquidity": market_data.get("liquidity", 0)
            })
            
            # Get RL action recommendation
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Try strategies with tracking
            if enabled_strategies:
                for strategy_name in enabled_strategies:
                    strategy_result = await self._run_strategy_with_tracking(
                        strategy_name, market_data, category, rl_action, rl_confidence
                    )
                    
                    # Update RL with reward from strategy result
                    if strategy_result and strategy_result.get("pnl"):
                        reward = strategy_result["pnl"] / self.initial_capital  # Normalize reward
                        await self.rl_engine.update_from_reward(market_data.get("id"), reward)
                    
        except Exception as e:
            logger.error(f"Error processing snapshot: {e}")
            
            # Try strategies
            if not enabled_strategies or "delta_neutral" in enabled_strategies:
                await self._try_strategy(self.delta_neutral_strategy, market_data, "delta_neutral")
            
            if not enabled_strategies or "volatility_exploitation" in enabled_strategies:
                await self._try_strategy(self.volatility_strategy, market_data, "volatility_exploitation")
            
            if not enabled_strategies or "alpha_directional" in enabled_strategies:
                await self._try_strategy(self.alpha_strategy, market_data, "alpha_directional")
            
            if not enabled_strategies or "arbitrage" in enabled_strategies:
                await self._try_strategy(self.arbitrage_strategy, market_data, "arbitrage")
            
        except Exception as e:
            logger.error(f"Error processing snapshot: {e}")
    
    async def _try_strategy(self, strategy, market_data: Dict, strategy_name: str):
        """Try executing a strategy (simulated)"""
        try:
            # Simulate strategy execution
            # In backtest, we don't actually execute orders
            # We just record what would have happened
            
            market_id = market_data.get('id')
            price = market_data.get('yes_price', 0.5)
            
            # Check if we can afford a position
            available_capital = self.current_capital * 0.8  # 80% deployment
            
            if available_capital < 10:
                return
            
            # Simulate position sizing
            position_size = min(available_capital * 0.03, self.current_capital * 0.03)
            shares = position_size / price if price > 0 else 0
            
            if shares < 1:
                return
            
            # Record simulated trade
            trade = {
                "id": str(uuid.uuid4()),
                "backtest_id": self.backtest_id,
                "market_id": market_id,
                "strategy": strategy_name,
                "side": "BUY",
                "price": price,
                "shares": shares,
                "cost": position_size,
                "timestamp": market_data.get("last_update")
            }
            
            self.trades.append(trade)
            
            # Open position
            self.positions[market_id] = {
                "strategy": strategy_name,
                "entry_price": price,
                "shares": shares,
                "cost": position_size
            }
            
            # Reduce capital
            self.current_capital -= position_size
            
        except Exception as e:
            logger.error(f"Error trying strategy: {e}")
    
    async def _update_positions(self, market_data: Dict):
        """Update positions with current market prices"""
        try:
            market_id = market_data.get('id')
            current_price = market_data.get('yes_price', 0.5)
            
            if market_id in self.positions:
                position = self.positions[market_id]
                entry_price = position['entry_price']
                shares = position['shares']
                
                # Check exit conditions
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
                
                # Exit if profit > 50% or loss > 20%
                if pnl_pct > 0.5 or pnl_pct < -0.2:
                    exit_value = shares * current_price
                    self.current_capital += exit_value
                    
                    # Record exit
                    self.trades.append({
                        "id": str(uuid.uuid4()),
                        "backtest_id": self.backtest_id,
                        "market_id": market_id,
                        "strategy": position['strategy'],
                        "side": "SELL",
                        "price": current_price,
                        "shares": shares,
                        "value": exit_value,
                        "pnl": exit_value - position['cost'],
                        "timestamp": market_data.get("last_update")
                    })
                    
                    # Close position
                    del self.positions[market_id]
                    
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
    
    async def _get_historical_markets(self, start_date: str, end_date: str) -> List[Dict]:
        """Get historical market snapshots"""
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            cursor = self.db.historical_data.find({
                "timestamp": {
                    "$gte": start_dt.isoformat(),
                    "$lte": end_dt.isoformat()
                }
            }).sort("timestamp", 1)
            
            historical = await cursor.to_list(length=10000)
            
            # Group by market
            snapshots = []
            for item in historical:
                snapshots.append({
                    "timestamp": item.get("timestamp"),
                    "market_data": {
                        "id": item.get("market_id"),
                        "yes_price": item.get("yes_price"),
                        "no_price": item.get("no_price"),
                        "volume": item.get("volume"),
                        "liquidity": item.get("liquidity"),
                        "category": item.get("category"),
                        "last_update": item.get("timestamp")
                    }
                })
            
            return snapshots
            
        except Exception as e:
            logger.error(f"Error getting historical markets: {e}")
            return []
    
    async def _calculate_backtest_results(self) -> Dict:
        """Calculate backtest performance metrics"""
        try:
            # Close all remaining positions at last price with tracking
            for market_id, position in self.positions.items():
                self.current_capital += position['shares'] * position['entry_price']
            
            total_pnl = self.current_capital - self.initial_capital
            total_return = (total_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0
            
            # Calculate win rate
            closed_trades = [t for t in self.trades if t.get('side') == 'SELL']
            winning_trades = [t for t in closed_trades if t.get('pnl', 0) > 0]
            win_rate = len(winning_trades) / len(closed_trades) if closed_trades else 0
            
            # Calculate max drawdown
            max_drawdown = 0
            peak = self.initial_capital
            for point in self.equity_curve:
                equity = point['equity']
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)
            
            # Calculate Sharpe ratio (simplified)
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_eq = self.equity_curve[i-1]['equity']
                if prev_eq > 0:
                    ret = (self.equity_curve[i]['equity'] - prev_eq) / prev_eq
                    returns.append(ret)
            
            import numpy as np
            sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0
            
            # Calculate profit factor
            gross_profit = sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) > 0)
            gross_loss = abs(sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # Calculate strategy performance breakdown
            strategy_results = {}
            for trade in closed_trades:
                strategy = trade.get('strategy', 'unknown')
                if strategy not in strategy_results:
                    strategy_results[strategy] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                strategy_results[strategy]['trades'] += 1
                strategy_results[strategy]['pnl'] += trade.get('pnl', 0)
                if trade.get('pnl', 0) > 0:
                    strategy_results[strategy]['wins'] += 1
            
            # Calculate win rate per strategy
            for strategy in strategy_results:
                data = strategy_results[strategy]
                data['win_rate'] = data['wins'] / data['trades'] if data['trades'] > 0 else 0
            
            # Calculate asset class performance breakdown
            asset_class_results = {}
            for trade in closed_trades:
                category = trade.get('category', 'unknown')
                if category not in asset_class_results:
                    asset_class_results[category] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                asset_class_results[category]['trades'] += 1
                asset_class_results[category]['pnl'] += trade.get('pnl', 0)
                if trade.get('pnl', 0) > 0:
                    asset_class_results[category]['wins'] += 1
            
            # Add asset class data from tracking
            for category, data in self.asset_class_performance.items():
                if category not in asset_class_results:
                    asset_class_results[category] = data
            
            # Calculate win rate per asset class
            for category in asset_class_results:
                data = asset_class_results[category]
                data['win_rate'] = data['wins'] / data['trades'] if data['trades'] > 0 else 0
            
            # Get RL learning stats
            rl_stats = await self.rl_engine.get_training_stats()
            
            results = {
                "backtest_id": self.backtest_id,
                "status": "completed",
                "initial_capital": self.initial_capital,
                "final_capital": self.current_capital,
                "total_pnl": total_pnl,
                "total_return_pct": total_return,
                "total_trades": len(self.trades),
                "closed_trades": len(closed_trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(closed_trades) - len(winning_trades),
                "win_rate": win_rate,
                "max_drawdown": max_drawdown,
                "sharpe_ratio": float(sharpe_ratio) if not np.isnan(sharpe_ratio) else 0,
                "profit_factor": profit_factor,
                "equity_curve": self.equity_curve[-100:],  # Last 100 points
                "trades_summary": closed_trades[-20:],  # Last 20 trades
                "strategy_results": strategy_results,
                "asset_class_results": asset_class_results,
                "data_summary": self.data_summary,
                "rl_learning_stats": rl_stats,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error calculating backtest results: {e}")
            return {}
    
    async def _update_positions_with_tracking(self, market_data: Dict):
        """Update positions with current market prices and track performance"""
        try:
            market_id = market_data.get('id')
            current_price = market_data.get('yes_price', 0.5)
            category = market_data.get('category', 'unknown')
            
            if market_id in self.positions:
                position = self.positions[market_id]
                entry_price = position['entry_price']
                shares = position['shares']
                strategy = position.get('strategy', 'unknown')
                
                # Check exit conditions
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
                
                # Exit if profit > 50% or loss > 20%
                if pnl_pct > 0.5 or pnl_pct < -0.2:
                    exit_value = shares * current_price
                    pnl = exit_value - position['cost']
                    self.current_capital += exit_value
                    
                    # Record exit trade with category
                    trade_record = {
                        "id": str(uuid.uuid4()),
                        "backtest_id": self.backtest_id,
                        "market_id": market_id,
                        "strategy": strategy,
                        "category": category,
                        "side": "SELL",
                        "price": current_price,
                        "shares": shares,
                        "value": exit_value,
                        "pnl": pnl,
                        "timestamp": market_data.get("last_update")
                    }
                    self.trades.append(trade_record)
                    
                    # Update strategy performance
                    if strategy in self.strategy_performance:
                        self.strategy_performance[strategy]['trades'] += 1
                        self.strategy_performance[strategy]['pnl'] += pnl
                        if pnl > 0:
                            self.strategy_performance[strategy]['wins'] += 1
                    
                    # Update asset class performance
                    if category in self.asset_class_performance:
                        self.asset_class_performance[category]['trades'] += 1
                        self.asset_class_performance[category]['pnl'] += pnl
                        if pnl > 0:
                            self.asset_class_performance[category]['wins'] += 1
                    
                    # Close position
                    del self.positions[market_id]
                    
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
    
    async def _run_strategy_with_tracking(self, strategy_name: str, market_data: Dict, category: str, rl_action: str, rl_confidence: float) -> Optional[Dict]:
        """Run a strategy with performance tracking"""
        try:
            strategy_map = {
                "delta_neutral": self.delta_neutral_strategy,
                "volatility_exploitation": self.volatility_strategy,
                "alpha_directional": self.alpha_strategy,
                "arbitrage": self.arbitrage_strategy
            }
            
            strategy = strategy_map.get(strategy_name)
            if not strategy:
                return None
            
            market_id = market_data.get('id')
            price = market_data.get('yes_price', 0.5)
            
            # Skip if already have position in this market
            if market_id in self.positions:
                return None
            
            # Check if we can afford a position
            available_capital = self.current_capital * 0.8
            if available_capital < 10:
                return None
            
            # Use RL confidence to adjust position sizing
            rl_multiplier = 1.0
            if rl_confidence > 0.7:
                rl_multiplier = 1.2
            elif rl_confidence < 0.3:
                rl_multiplier = 0.8
            
            # Simulate position sizing (3% max)
            position_size = min(available_capital * 0.03 * rl_multiplier, self.current_capital * 0.03)
            shares = position_size / price if price > 0 else 0
            
            if shares < 1:
                return None
            
            # Record simulated trade
            trade = {
                "id": str(uuid.uuid4()),
                "backtest_id": self.backtest_id,
                "market_id": market_id,
                "strategy": strategy_name,
                "category": category,
                "side": "BUY",
                "price": price,
                "shares": shares,
                "cost": position_size,
                "rl_action": rl_action,
                "rl_confidence": rl_confidence,
                "timestamp": market_data.get("last_update")
            }
            
            self.trades.append(trade)
            
            # Open position
            self.positions[market_id] = {
                "strategy": strategy_name,
                "category": category,
                "entry_price": price,
                "shares": shares,
                "cost": position_size
            }
            
            # Reduce capital
            self.current_capital -= position_size
            
            return {"opened": True, "strategy": strategy_name, "category": category}
            
        except Exception as e:
            logger.error(f"Error running strategy with tracking: {e}")
            return None
    
    async def _store_backtest_results(self, results: Dict):
        """Store backtest results in database"""
        try:
            await self.db.backtest_results.insert_one(results)
            logger.info(f"Backtest results stored: {self.backtest_id}")
        except Exception as e:
            logger.error(f"Error storing backtest results: {e}")
    
    async def get_backtest_results(self, backtest_id: Optional[str] = None) -> Dict:
        """Get backtest results"""
        try:
            if backtest_id:
                result = await self.db.backtest_results.find_one(
                    {"backtest_id": backtest_id},
                    {"_id": 0}
                )
            else:
                result = await self.db.backtest_results.find_one(
                    {},
                    {"_id": 0},
                    sort=[("completed_at", -1)]
                )
            
            return result if result else {}
        except Exception as e:
            logger.error(f"Error getting backtest results: {e}")
            return {}
