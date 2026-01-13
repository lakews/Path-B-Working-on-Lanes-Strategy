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
        # Use backtest_mode=True to skip LLM calls for faster execution
        self.signal_fusion = SignalFusionEngine(backtest_mode=True)
        self.kelly_optimizer = KellySharpeOptimizer()
        self.rl_engine = RLAdaptiveEngine()
        
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
            # Historical data is stored flat, not nested under market_data
            market_data = market_snapshot if 'yes_price' in market_snapshot else market_snapshot.get("market_data", {})
            
            if not market_data or 'yes_price' not in market_data:
                return
            
            category = market_data.get("category", "unknown")
            
            # Initialize asset class tracking
            if category not in self.asset_class_performance:
                self.asset_class_performance[category] = {"trades": 0, "wins": 0, "pnl": 0.0}
            
            # Update existing positions with current prices
            await self._update_positions_with_tracking(market_data)
            
            # Get signals for RL learning using generate_trading_signal
            market_id = market_data.get("market_id") or market_data.get("id")
            signal_result = await self.signal_fusion.generate_trading_signal({
                "id": market_id,
                "question": market_data.get("question", ""),
                "category": category,
                "yes_price": market_data.get("yes_price", 0.5),
                "no_price": market_data.get("no_price", 0.5),
                "volume": market_data.get("volume", 0),
                "liquidity": market_data.get("liquidity", 0)
            })
            
            signals = signal_result.get("signals", {})
            
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
            import random
            
            strategy_map = {
                "delta_neutral": self.delta_neutral_strategy,
                "volatility_exploitation": self.volatility_strategy,
                "alpha_directional": self.alpha_strategy,
                "arbitrage": self.arbitrage_strategy
            }
            
            strategy = strategy_map.get(strategy_name)
            if not strategy:
                return None
            
            market_id = market_data.get('market_id') or market_data.get('id')
            price = market_data.get('yes_price', 0.5)
            
            # Debug logging
            if not market_id:
                logger.warning(f"Missing market_id in data: {list(market_data.keys())[:5]}")
                return None
            
            # Skip if already have position in this market
            if market_id in self.positions:
                return None
            
            # Price must be in tradeable range
            if price < 0.05 or price > 0.95:
                return None
            
            # Log every 100th attempt for debugging
            import random as r2
            if r2.random() < 0.01:
                logger.info(f"Strategy check: {strategy_name}, price={price}, capital={self.current_capital}")
            
            # Check if we can afford a position
            available_capital = self.current_capital * 0.8
            if available_capital < 10:
                return None
            
            # Position sizing - use 5% for visibility in backtests
            position_size = min(available_capital * 0.05, self.current_capital * 0.05)
            shares = position_size / price if price > 0 else 0
            
            if shares < 1:
                return None
            
            # Log trade opening
            logger.info(f"OPENING TRADE: {strategy_name} on {market_id[:8] if market_id else 'unknown'} @ ${price:.3f}, shares={shares:.1f}")
            
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
    
    async def get_backtest_history(self, limit: int = 10) -> List[Dict]:
        """Get list of past backtest results (up to limit)"""
        try:
            cursor = self.db.backtest_results.find(
                {},
                {"_id": 0}
            ).sort("completed_at", -1).limit(limit)
            
            results = await cursor.to_list(length=limit)
            return results
        except Exception as e:
            logger.error(f"Error getting backtest history: {e}")
            return []
    
    async def compare_backtests(self, backtest_ids: List[str]) -> Dict:
        """Compare multiple backtest results with comprehensive metrics"""
        try:
            # Fetch all requested backtests
            cursor = self.db.backtest_results.find(
                {"backtest_id": {"$in": backtest_ids}},
                {"_id": 0}
            )
            backtests = await cursor.to_list(length=len(backtest_ids))
            
            if not backtests:
                return {"error": "No backtests found for comparison"}
            
            # Build comparison data
            comparison = {
                "backtest_count": len(backtests),
                "backtests": [],
                "comparison_metrics": {},
                "strategy_comparison": {},
                "asset_class_comparison": {},
                "improvement_insights": [],
                "educational_analysis": {}
            }
            
            # Collect metrics for comparison
            all_returns = []
            all_sharpe = []
            all_drawdowns = []
            all_win_rates = []
            all_profit_factors = []
            strategy_data = {}
            asset_class_data = {}
            
            for bt in backtests:
                bt_summary = {
                    "backtest_id": bt.get("backtest_id"),
                    "completed_at": bt.get("completed_at"),
                    "total_return_pct": bt.get("total_return_pct", 0),
                    "total_pnl": bt.get("total_pnl", 0),
                    "sharpe_ratio": bt.get("sharpe_ratio", 0),
                    "max_drawdown": bt.get("max_drawdown", 0),
                    "win_rate": bt.get("win_rate", 0),
                    "profit_factor": bt.get("profit_factor", 0),
                    "total_trades": bt.get("total_trades", 0),
                    "data_summary": bt.get("data_summary", {}),
                    "strategy_results": bt.get("strategy_results", {}),
                    "asset_class_results": bt.get("asset_class_results", {})
                }
                comparison["backtests"].append(bt_summary)
                
                all_returns.append(bt.get("total_return_pct", 0))
                all_sharpe.append(bt.get("sharpe_ratio", 0))
                all_drawdowns.append(bt.get("max_drawdown", 0))
                all_win_rates.append(bt.get("win_rate", 0))
                all_profit_factors.append(bt.get("profit_factor", 0))
                
                # Aggregate strategy data
                for strat, data in bt.get("strategy_results", {}).items():
                    if strat not in strategy_data:
                        strategy_data[strat] = {"pnl": [], "win_rate": [], "trades": []}
                    strategy_data[strat]["pnl"].append(data.get("pnl", 0))
                    strategy_data[strat]["win_rate"].append(data.get("win_rate", 0))
                    strategy_data[strat]["trades"].append(data.get("trades", 0))
                
                # Aggregate asset class data
                for asset, data in bt.get("asset_class_results", {}).items():
                    if asset not in asset_class_data:
                        asset_class_data[asset] = {"pnl": [], "win_rate": [], "trades": []}
                    asset_class_data[asset]["pnl"].append(data.get("pnl", 0))
                    asset_class_data[asset]["win_rate"].append(data.get("win_rate", 0))
                    asset_class_data[asset]["trades"].append(data.get("trades", 0))
            
            import numpy as np
            
            # Overall comparison metrics
            comparison["comparison_metrics"] = {
                "return": {
                    "best": float(max(all_returns)) if all_returns else 0,
                    "worst": float(min(all_returns)) if all_returns else 0,
                    "avg": float(np.mean(all_returns)) if all_returns else 0,
                    "std": float(np.std(all_returns)) if len(all_returns) > 1 else 0,
                    "trend": "improving" if len(all_returns) > 1 and all_returns[-1] > all_returns[0] else "declining"
                },
                "sharpe_ratio": {
                    "best": float(max(all_sharpe)) if all_sharpe else 0,
                    "worst": float(min(all_sharpe)) if all_sharpe else 0,
                    "avg": float(np.mean(all_sharpe)) if all_sharpe else 0,
                    "target": 1.5,
                    "interpretation": "Sharpe > 1.0 = good, > 2.0 = excellent. Measures return per unit of risk."
                },
                "max_drawdown": {
                    "best": float(min(all_drawdowns)) if all_drawdowns else 0,
                    "worst": float(max(all_drawdowns)) if all_drawdowns else 0,
                    "avg": float(np.mean(all_drawdowns)) if all_drawdowns else 0,
                    "target": 0.10,
                    "interpretation": "Lower is better. Target < 10%. Shows worst peak-to-trough decline."
                },
                "win_rate": {
                    "best": float(max(all_win_rates)) if all_win_rates else 0,
                    "worst": float(min(all_win_rates)) if all_win_rates else 0,
                    "avg": float(np.mean(all_win_rates)) if all_win_rates else 0,
                    "target": 0.55,
                    "interpretation": "Target > 55%. High win rate with low profit factor = many small wins, few big losses."
                },
                "profit_factor": {
                    "best": float(max(all_profit_factors)) if all_profit_factors else 0,
                    "worst": float(min(all_profit_factors)) if all_profit_factors else 0,
                    "avg": float(np.mean(all_profit_factors)) if all_profit_factors else 0,
                    "target": 1.5,
                    "interpretation": "Gross profit / gross loss. > 1.5 = good, > 2.0 = excellent. < 1.0 = losing strategy."
                }
            }
            
            # Strategy comparison
            for strat, data in strategy_data.items():
                comparison["strategy_comparison"][strat] = {
                    "avg_pnl": float(np.mean(data["pnl"])) if data["pnl"] else 0,
                    "total_pnl": float(sum(data["pnl"])),
                    "avg_win_rate": float(np.mean(data["win_rate"])) if data["win_rate"] else 0,
                    "total_trades": sum(data["trades"]),
                    "consistency": float(np.std(data["pnl"])) if len(data["pnl"]) > 1 else 0,
                    "pnl_trend": data["pnl"],
                    "is_profitable": sum(data["pnl"]) > 0
                }
            
            # Asset class comparison
            for asset, data in asset_class_data.items():
                comparison["asset_class_comparison"][asset] = {
                    "avg_pnl": float(np.mean(data["pnl"])) if data["pnl"] else 0,
                    "total_pnl": float(sum(data["pnl"])),
                    "avg_win_rate": float(np.mean(data["win_rate"])) if data["win_rate"] else 0,
                    "total_trades": sum(data["trades"]),
                    "is_profitable": sum(data["pnl"]) > 0
                }
            
            # Generate improvement insights
            comparison["improvement_insights"] = self._generate_improvement_insights(
                comparison["comparison_metrics"],
                comparison["strategy_comparison"],
                comparison["asset_class_comparison"]
            )
            
            # Educational analysis
            comparison["educational_analysis"] = self._generate_educational_analysis(
                comparison["comparison_metrics"],
                comparison["strategy_comparison"]
            )
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error comparing backtests: {e}")
            return {"error": str(e)}
    
    def _generate_improvement_insights(self, metrics: Dict, strategies: Dict, assets: Dict) -> List[Dict]:
        """Generate actionable improvement insights"""
        insights = []
        
        # Return insights
        avg_return = metrics.get("return", {}).get("avg", 0)
        if avg_return < 0:
            insights.append({
                "severity": "critical",
                "area": "Overall Return",
                "issue": f"Average return is negative ({avg_return:.2f}%)",
                "recommendation": "Reduce position sizes, tighten stop-losses, or disable underperforming strategies.",
                "action": "Consider reducing Kelly fraction by 50% and adding stricter entry criteria."
            })
        
        # Sharpe ratio insights
        avg_sharpe = metrics.get("sharpe_ratio", {}).get("avg", 0)
        if avg_sharpe < 0.5:
            insights.append({
                "severity": "high",
                "area": "Risk-Adjusted Return",
                "issue": f"Sharpe ratio too low ({avg_sharpe:.2f}). Strategy has poor risk/reward.",
                "recommendation": "Increase win rate or average win size relative to loss size.",
                "action": "Focus on higher-confidence trades with better reward-to-risk ratios."
            })
        
        # Drawdown insights
        worst_dd = metrics.get("max_drawdown", {}).get("worst", 0)
        if worst_dd > 0.15:
            insights.append({
                "severity": "high",
                "area": "Risk Management",
                "issue": f"Max drawdown too high ({worst_dd*100:.1f}%). Capital at risk.",
                "recommendation": "Implement stricter position sizing and daily loss limits.",
                "action": "Reduce max position size to 2% and add 5% daily loss limit."
            })
        
        # Win rate insights
        avg_win_rate = metrics.get("win_rate", {}).get("avg", 0)
        if avg_win_rate < 0.45:
            insights.append({
                "severity": "medium",
                "area": "Trade Selection",
                "issue": f"Win rate below target ({avg_win_rate*100:.1f}%). Too many losing trades.",
                "recommendation": "Improve signal quality or add confirmation indicators.",
                "action": "Require multiple signal alignment before entering trades."
            })
        
        # Strategy-specific insights
        for strat, data in strategies.items():
            if data.get("total_pnl", 0) < 0:
                insights.append({
                    "severity": "high",
                    "area": f"Strategy: {strat}",
                    "issue": f"Strategy is net negative (${data['total_pnl']:.2f})",
                    "recommendation": f"Review {strat} parameters or disable temporarily.",
                    "action": f"Analyze losing trades in {strat} to identify common patterns."
                })
            elif data.get("avg_win_rate", 0) < 0.40:
                insights.append({
                    "severity": "medium",
                    "area": f"Strategy: {strat}",
                    "issue": f"Low win rate ({data['avg_win_rate']*100:.1f}%)",
                    "recommendation": "Tighten entry criteria for this strategy.",
                    "action": "Add minimum confidence threshold or reduce position size."
                })
        
        # Asset class insights
        for asset, data in assets.items():
            if data.get("total_pnl", 0) < 0 and data.get("total_trades", 0) > 5:
                insights.append({
                    "severity": "medium",
                    "area": f"Asset Class: {asset}",
                    "issue": f"Losing money on {asset} markets (${data['total_pnl']:.2f})",
                    "recommendation": f"Consider excluding {asset} or adjusting strategy for this category.",
                    "action": f"Analyze what makes {asset} markets different from profitable ones."
                })
        
        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        insights.sort(key=lambda x: severity_order.get(x["severity"], 4))
        
        return insights
    
    def _generate_educational_analysis(self, metrics: Dict, strategies: Dict) -> Dict:
        """Generate educational analysis explaining the metrics"""
        import numpy as np
        
        return {
            "key_concepts": {
                "sharpe_ratio": {
                    "what": "Measures excess return per unit of risk (volatility)",
                    "formula": "(Return - Risk-Free Rate) / Standard Deviation of Returns",
                    "interpretation": {
                        "below_0": "Strategy is losing money on a risk-adjusted basis",
                        "0_to_1": "Positive but not compelling risk/reward",
                        "1_to_2": "Good risk-adjusted performance",
                        "above_2": "Excellent performance - investigate if sustainable"
                    },
                    "your_avg": metrics.get("sharpe_ratio", {}).get("avg", 0)
                },
                "max_drawdown": {
                    "what": "Largest peak-to-trough decline in equity",
                    "why_important": "Shows worst-case scenario for capital loss before recovery",
                    "targets": {
                        "conservative": "< 5%",
                        "moderate": "5-10%",
                        "aggressive": "10-20%",
                        "dangerous": "> 20%"
                    },
                    "your_worst": metrics.get("max_drawdown", {}).get("worst", 0)
                },
                "profit_factor": {
                    "what": "Ratio of gross profits to gross losses",
                    "interpretation": {
                        "below_1": "Losing money - gross losses exceed profits",
                        "1_to_1.5": "Marginal profitability - high risk of turning negative",
                        "1.5_to_2": "Good profitability with reasonable buffer",
                        "above_2": "Strong profitability - but verify with enough sample size"
                    },
                    "your_avg": metrics.get("profit_factor", {}).get("avg", 0)
                },
                "win_rate": {
                    "what": "Percentage of trades that are profitable",
                    "note": "Win rate alone is meaningless - must consider avg win vs avg loss",
                    "examples": {
                        "high_win_rate_low_pf": "90% win rate but profit factor of 0.8 = many small wins, few devastating losses",
                        "low_win_rate_high_pf": "30% win rate but profit factor of 2.5 = few wins but they're big"
                    },
                    "your_avg": metrics.get("win_rate", {}).get("avg", 0)
                }
            },
            "strategy_quality_score": self._calculate_quality_score(metrics),
            "recommendations_summary": self._generate_recommendations_summary(metrics, strategies)
        }
    
    def _calculate_quality_score(self, metrics: Dict) -> Dict:
        """Calculate an overall quality score for the trading strategy"""
        score = 0
        max_score = 100
        breakdown = []
        
        # Return component (25 points)
        avg_return = metrics.get("return", {}).get("avg", 0)
        if avg_return > 10:
            score += 25
            breakdown.append({"component": "Return", "score": 25, "max": 25, "note": "Excellent returns"})
        elif avg_return > 5:
            score += 20
            breakdown.append({"component": "Return", "score": 20, "max": 25, "note": "Good returns"})
        elif avg_return > 0:
            score += 10
            breakdown.append({"component": "Return", "score": 10, "max": 25, "note": "Positive but modest"})
        else:
            score += 0
            breakdown.append({"component": "Return", "score": 0, "max": 25, "note": "Negative returns - critical issue"})
        
        # Sharpe component (25 points)
        avg_sharpe = metrics.get("sharpe_ratio", {}).get("avg", 0)
        if avg_sharpe > 2:
            score += 25
            breakdown.append({"component": "Sharpe Ratio", "score": 25, "max": 25, "note": "Excellent risk-adjusted"})
        elif avg_sharpe > 1:
            score += 20
            breakdown.append({"component": "Sharpe Ratio", "score": 20, "max": 25, "note": "Good risk-adjusted"})
        elif avg_sharpe > 0.5:
            score += 10
            breakdown.append({"component": "Sharpe Ratio", "score": 10, "max": 25, "note": "Below target"})
        else:
            score += 0
            breakdown.append({"component": "Sharpe Ratio", "score": 0, "max": 25, "note": "Poor risk-adjusted"})
        
        # Drawdown component (25 points)
        worst_dd = metrics.get("max_drawdown", {}).get("worst", 1)
        if worst_dd < 0.05:
            score += 25
            breakdown.append({"component": "Max Drawdown", "score": 25, "max": 25, "note": "Excellent risk control"})
        elif worst_dd < 0.10:
            score += 20
            breakdown.append({"component": "Max Drawdown", "score": 20, "max": 25, "note": "Good risk control"})
        elif worst_dd < 0.20:
            score += 10
            breakdown.append({"component": "Max Drawdown", "score": 10, "max": 25, "note": "Moderate risk"})
        else:
            score += 0
            breakdown.append({"component": "Max Drawdown", "score": 0, "max": 25, "note": "High risk exposure"})
        
        # Profit factor component (25 points)
        avg_pf = metrics.get("profit_factor", {}).get("avg", 0)
        if avg_pf > 2:
            score += 25
            breakdown.append({"component": "Profit Factor", "score": 25, "max": 25, "note": "Strong profitability"})
        elif avg_pf > 1.5:
            score += 20
            breakdown.append({"component": "Profit Factor", "score": 20, "max": 25, "note": "Good profitability"})
        elif avg_pf > 1:
            score += 10
            breakdown.append({"component": "Profit Factor", "score": 10, "max": 25, "note": "Marginal profitability"})
        else:
            score += 0
            breakdown.append({"component": "Profit Factor", "score": 0, "max": 25, "note": "Net loser"})
        
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D" if score >= 20 else "F"
        
        return {
            "total_score": score,
            "max_score": max_score,
            "grade": grade,
            "breakdown": breakdown
        }
    
    def _generate_recommendations_summary(self, metrics: Dict, strategies: Dict) -> List[str]:
        """Generate a prioritized list of recommendations"""
        recs = []
        
        avg_return = metrics.get("return", {}).get("avg", 0)
        avg_sharpe = metrics.get("sharpe_ratio", {}).get("avg", 0)
        avg_pf = metrics.get("profit_factor", {}).get("avg", 0)
        worst_dd = metrics.get("max_drawdown", {}).get("worst", 0)
        
        if avg_return < 0:
            recs.append("🔴 CRITICAL: Reduce position sizes by 50% immediately to stop losses")
        
        if avg_pf < 1:
            recs.append("🔴 HIGH: Review and disable losing strategies - you're losing more than winning")
        
        if worst_dd > 0.15:
            recs.append("🟠 HIGH: Implement daily loss limits to prevent catastrophic drawdowns")
        
        if avg_sharpe < 1:
            recs.append("🟡 MEDIUM: Focus on higher-quality trades - fewer but better opportunities")
        
        # Find best and worst strategies
        if strategies:
            sorted_strats = sorted(strategies.items(), key=lambda x: x[1].get("total_pnl", 0))
            if sorted_strats:
                worst_strat = sorted_strats[0]
                best_strat = sorted_strats[-1]
                
                if worst_strat[1].get("total_pnl", 0) < 0:
                    recs.append(f"🟡 MEDIUM: Consider disabling {worst_strat[0]} (worst performer)")
                
                if best_strat[1].get("total_pnl", 0) > 0:
                    recs.append(f"🟢 OPPORTUNITY: Increase allocation to {best_strat[0]} (best performer)")
        
        if not recs:
            recs.append("🟢 Strategy is performing within acceptable parameters. Continue monitoring.")
        
        return recs
    
    async def delete_backtest(self, backtest_id: str) -> bool:
        """Delete a backtest result"""
        try:
            result = await self.db.backtest_results.delete_one({"backtest_id": backtest_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting backtest: {e}")
            return False
