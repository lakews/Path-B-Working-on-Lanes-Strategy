import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from database import get_db
from ml.signal_fusion import SignalFusionEngine
from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
from strategies.delta_neutral import DeltaNeutralStrategy
from strategies.volatility_exploitation import VolatilityExploitationStrategy
from strategies.alpha_directional import AlphaDirectionalStrategy
from config import config
import uuid

logger = logging.getLogger(__name__)

class BacktestEngine:
    """Backtesting engine for testing strategies on historical data"""
    
    def __init__(self):
        self.db = get_db()
        self.signal_fusion = SignalFusionEngine()
        self.kelly_optimizer = KellySharpeOptimizer()
        
        self.delta_neutral_strategy = DeltaNeutralStrategy()
        self.volatility_strategy = VolatilityExploitationStrategy()
        self.alpha_strategy = AlphaDirectionalStrategy()
        
        self.running = False
        self.backtest_id = None
        
        # Backtest state
        self.initial_capital = config.INITIAL_CAPITAL
        self.current_capital = config.INITIAL_CAPITAL
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        
    async def run_backtest(
        self,
        start_date: str,
        end_date: str,
        strategies: List[str] = None
    ) -> Dict:
        """Run backtest on historical data"""
        try:
            self.running = True
            self.backtest_id = str(uuid.uuid4())
            
            logger.info(f"Starting backtest {self.backtest_id}: {start_date} to {end_date}")
            
            # Reset state
            self.current_capital = self.initial_capital
            self.positions = {}
            self.trades = []
            self.equity_curve = []
            
            # Get historical market data
            historical_markets = await self._get_historical_markets(start_date, end_date)
            
            if not historical_markets:
                return {
                    "error": "No historical data available for selected date range",
                    "backtest_id": self.backtest_id
                }
            
            logger.info(f"Processing {len(historical_markets)} historical market snapshots")
            
            # Process each historical snapshot
            for idx, market_snapshot in enumerate(historical_markets):
                if not self.running:
                    break
                
                await self._process_snapshot(market_snapshot, strategies)
                
                # Record equity point
                self.equity_curve.append({
                    "timestamp": market_snapshot.get("timestamp"),
                    "equity": self.current_capital,
                    "num_positions": len(self.positions)
                })
                
                # Progress logging
                if idx % 100 == 0:
                    logger.info(f"Backtest progress: {idx}/{len(historical_markets)} snapshots")
            
            # Calculate final metrics
            results = await self._calculate_backtest_results()
            
            # Store backtest results
            await self._store_backtest_results(results)
            
            logger.info(f"Backtest {self.backtest_id} completed")
            
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
    
    async def _process_snapshot(self, market_snapshot: Dict, enabled_strategies: List[str]):
        """Process a single market snapshot"""
        try:
            market_data = market_snapshot.get("market_data", {})
            
            if not market_data:
                return
            
            # Update existing positions with current prices
            await self._update_positions(market_data)
            
            # Try strategies
            if not enabled_strategies or "delta_neutral" in enabled_strategies:
                await self._try_strategy(self.delta_neutral_strategy, market_data, "delta_neutral")
            
            if not enabled_strategies or "volatility_exploitation" in enabled_strategies:
                await self._try_strategy(self.volatility_strategy, market_data, "volatility_exploitation")
            
            if not enabled_strategies or "alpha_directional" in enabled_strategies:
                await self._try_strategy(self.alpha_strategy, market_data, "alpha_directional")
            
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
            # Close all remaining positions at last price
            for market_id, position in self.positions.items():
                # Assume last price
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
                ret = (self.equity_curve[i]['equity'] - self.equity_curve[i-1]['equity']) / self.equity_curve[i-1]['equity']
                returns.append(ret)
            
            import numpy as np
            sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0
            
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
                "sharpe_ratio": sharpe_ratio,
                "equity_curve": self.equity_curve[-100:],  # Last 100 points
                "trades_summary": closed_trades[-20:],  # Last 20 trades
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error calculating backtest results: {e}")
            return {}
    
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
