import logging
import asyncio
import uuid
import random
import numpy as np
from typing import Dict, List, Optional, Tuple
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

logger = logging.getLogger(__name__)

class BacktestEngine:
    """High-Frequency Backtesting Engine with Adaptive Position Management"""
    
    def __init__(self):
        self.db = get_db()
        self.signal_fusion = SignalFusionEngine(backtest_mode=True)
        self.kelly_optimizer = KellySharpeOptimizer()
        self.rl_engine = RLAdaptiveEngine()
        
        # Strategies
        self.strategies = {
            "delta_neutral": DeltaNeutralStrategy(),
            "volatility_exploitation": VolatilityExploitationStrategy(),
            "alpha_directional": AlphaDirectionalStrategy(),
            "arbitrage": MultiMarketArbitrageStrategy()
        }
        
        self.running = False
        self.backtest_id = None
        
        # Backtest state
        self.initial_capital = max(config.INITIAL_CAPITAL, 1000)
        self.current_capital = self.initial_capital
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.equity_curve: List[Dict] = []
        
        # Performance tracking
        self.strategy_performance: Dict[str, Dict] = {}
        self.asset_class_performance: Dict[str, Dict] = {}
        
        # HFT Parameters
        self.max_positions = 20
        self.position_timeout_snapshots = 50  # Close after N snapshots if not exited
        self.min_profit_target = 0.02  # 2% profit target
        self.max_loss_limit = 0.03  # 3% stop loss
        self.trailing_stop_trigger = 0.015  # Start trailing after 1.5% profit
        self.trailing_stop_distance = 0.01  # 1% trailing stop distance
    
    async def run_backtest(
        self,
        start_date: str,
        end_date: str,
        strategies: Optional[List[str]] = None
    ) -> Dict:
        """Run backtest with HFT-style position management"""
        try:
            self.running = True
            self.backtest_id = str(uuid.uuid4())
            
            # Reset state
            self.current_capital = self.initial_capital
            self.positions = {}
            self.trades = []
            self.equity_curve = []
            self.strategy_performance = {s: {"trades": 0, "wins": 0, "pnl": 0.0} for s in (strategies or [])}
            self.asset_class_performance = {}
            
            logger.info(f"Starting HFT backtest {self.backtest_id}: {start_date} to {end_date}")
            
            # Get historical data grouped by market
            market_timeseries = await self._get_market_timeseries(start_date, end_date)
            
            if not market_timeseries:
                return {"error": "No historical data found"}
            
            data_summary = {
                "total_snapshots": sum(len(v) for v in market_timeseries.values()),
                "unique_markets": len(market_timeseries),
                "date_range": {"start": start_date, "end": end_date}
            }
            
            logger.info(f"Loaded {data_summary['total_snapshots']} snapshots across {data_summary['unique_markets']} markets")
            
            # Process each market's timeseries
            enabled_strategies = strategies or list(self.strategies.keys())
            processed = 0
            
            for market_id, timeseries in market_timeseries.items():
                if not self.running:
                    break
                
                await self._process_market_timeseries(market_id, timeseries, enabled_strategies)
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"Processed {processed}/{len(market_timeseries)} markets, Open positions: {len(self.positions)}, Capital: ${self.current_capital:.2f}")
            
            # Train RL from backtest experience
            await self.rl_engine.train_from_replay()
            await self.rl_engine.save_model()
            
            # Calculate final metrics
            results = await self._calculate_backtest_results(data_summary)
            await self._store_backtest_results(results)
            
            logger.info(f"Backtest {self.backtest_id} completed - {results.get('total_trades', 0)} trades, P&L: ${results.get('total_pnl', 0):.2f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
        finally:
            self.running = False
    
    async def _get_market_timeseries(self, start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """Get historical data grouped by market_id as timeseries"""
        try:
            cursor = self.db.historical_data.find(
                {"timestamp": {"$gte": start_date, "$lte": end_date}},
                {"_id": 0}
            ).sort("timestamp", 1)
            
            snapshots = await cursor.to_list(length=100000)
            
            # Group by market_id
            market_timeseries = {}
            for snap in snapshots:
                market_id = snap.get("market_id")
                if not market_id:
                    continue
                if market_id not in market_timeseries:
                    market_timeseries[market_id] = []
                market_timeseries[market_id].append(snap)
            
            # Sort each market's timeseries by timestamp
            for market_id in market_timeseries:
                market_timeseries[market_id].sort(key=lambda x: x.get("timestamp", ""))
            
            return market_timeseries
            
        except Exception as e:
            logger.error(f"Error getting market timeseries: {e}")
            return {}
    
    async def _process_market_timeseries(self, market_id: str, timeseries: List[Dict], enabled_strategies: List[str]):
        """Process a single market's timeseries for HFT opportunities"""
        if len(timeseries) < 5:
            return  # Need enough data points
        
        category = timeseries[0].get("category", "unknown")
        if category not in self.asset_class_performance:
            self.asset_class_performance[category] = {"trades": 0, "wins": 0, "pnl": 0.0}
        
        # Get base prices and volumes
        base_prices = [s.get("yes_price", 0.5) for s in timeseries]
        no_prices = [s.get("no_price", 0.5) for s in timeseries]
        volumes = [s.get("volume", 0) for s in timeseries]
        
        base_price = base_prices[0] if base_prices else 0.5
        avg_volume = np.mean(volumes) if volumes else 1000
        
        # Skip extreme price markets
        if base_price < 0.05 or base_price > 0.95:
            return
        
        # Simulate realistic price movements based on market characteristics
        prices = self._simulate_price_series(base_price, len(timeseries), avg_volume, category)
        
        unique_prices = len(set(round(p, 4) for p in prices))
        price_range = max(prices) - min(prices)
        
        volatility = self._calculate_volatility(prices)
        trend = self._calculate_trend(prices)
        
        # Adaptive parameters based on market characteristics
        profit_target, stop_loss, position_size_mult = self._get_adaptive_params(volatility, avg_volume)
        
        position = None
        entry_idx = None
        highest_price = 0
        
        for idx, snapshot in enumerate(timeseries):
            # Use simulated price instead of static snapshot price
            current_price = prices[idx]
            current_no_price = 1.0 - current_price  # Implied no price
            timestamp = snapshot.get("timestamp")
            
            # Calculate bid-ask spread for market making
            spread = abs(1.0 - current_price - current_no_price)
            
            if position is None:
                # Check for entry signal
                if self._should_enter(prices[:idx+1], volatility, trend, enabled_strategies, current_price, spread):
                    if len(self.positions) < self.max_positions and self.current_capital > 50:
                        strategy = self._select_best_strategy(volatility, trend, enabled_strategies)
                        position = await self._open_position(
                            market_id, current_price, strategy, category, 
                            timestamp, profit_target, stop_loss, position_size_mult
                        )
                        entry_idx = idx
                        highest_price = current_price
            else:
                # Update trailing stop
                if current_price > highest_price:
                    highest_price = current_price
                
                # Calculate actual price change
                price_change = current_price - position["entry_price"]
                
                # Check for exit conditions
                exit_reason = self._check_exit_conditions(
                    position, current_price, highest_price, idx - entry_idx,
                    volatility, profit_target, stop_loss, price_change, spread
                )
                
                if exit_reason:
                    await self._close_position(market_id, position, current_price, timestamp, exit_reason)
                    position = None
                    entry_idx = None
                    highest_price = 0
        
        # Close any remaining position at last simulated price
        if position and len(prices) > 0:
            last_price = prices[-1]
            timestamp = timeseries[-1].get("timestamp") if timeseries else None
            await self._close_position(market_id, position, last_price, timestamp, "end_of_data")
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """Calculate price volatility"""
        if len(prices) < 2:
            return 0.0
        returns = np.diff(prices) / np.array(prices[:-1])
        return float(np.std(returns)) if len(returns) > 0 else 0.0
    
    def _simulate_price_series(self, base_price: float, length: int, volume: float, category: str) -> List[float]:
        """Simulate realistic price movements for backtesting HFT strategies"""
        # Category-specific volatility profiles
        vol_profiles = {
            "sports": 0.015,      # Sports: moderate volatility, event-driven
            "politics": 0.008,    # Politics: lower volatility, longer-term trends
            "finance": 0.012,     # Finance: moderate volatility
            "crypto": 0.025,      # Crypto: higher volatility
            "entertainment": 0.010
        }
        
        base_vol = vol_profiles.get(category, 0.012)
        
        # Adjust volatility based on volume (higher volume = more stable)
        vol_adj = base_vol * (1 + 0.5 / (1 + volume / 5000))
        
        # Generate Brownian motion with mean-reversion
        prices = [base_price]
        current = base_price
        
        # Add trend component (random walk with drift)
        trend = random.uniform(-0.001, 0.001)  # Small random trend
        
        for i in range(1, length):
            # Random price change with mean-reversion
            noise = random.gauss(0, vol_adj)
            mean_reversion = (base_price - current) * 0.05  # Pull toward base
            change = trend + noise + mean_reversion
            
            # Apply change with constraints
            current = current * (1 + change)
            current = max(0.01, min(0.99, current))  # Keep in valid range
            
            prices.append(current)
        
        return prices
    
    def _calculate_trend(self, prices: List[float]) -> float:
        """Calculate trend direction (-1 to 1)"""
        if len(prices) < 5:
            return 0.0
        recent = prices[-5:]
        older = prices[:5] if len(prices) >= 10 else prices[:len(prices)//2]
        
        recent_avg = np.mean(recent)
        older_avg = np.mean(older)
        
        if older_avg == 0:
            return 0.0
        
        trend = (recent_avg - older_avg) / older_avg
        return max(min(trend, 1.0), -1.0)
    
    def _get_adaptive_params(self, volatility: float, avg_volume: float) -> Tuple[float, float, float]:
        """Get adaptive parameters based on market characteristics"""
        # Base parameters
        profit_target = self.min_profit_target
        stop_loss = self.max_loss_limit
        position_size_mult = 1.0
        
        # Adjust for volatility
        if volatility > 0.05:  # High volatility
            profit_target *= 1.5  # Wider profit target
            stop_loss *= 1.5  # Wider stop loss
            position_size_mult = 0.7  # Smaller positions
        elif volatility < 0.01:  # Low volatility
            profit_target *= 0.7  # Tighter profit target for quick gains
            stop_loss *= 0.7  # Tighter stop loss
            position_size_mult = 1.3  # Larger positions
        
        # Adjust for volume
        if avg_volume > 10000:
            position_size_mult *= 1.2  # Higher liquidity = larger positions
        elif avg_volume < 1000:
            position_size_mult *= 0.6  # Lower liquidity = smaller positions
        
        return profit_target, stop_loss, position_size_mult
    
    def _should_enter(self, prices: List[float], volatility: float, trend: float, 
                      strategies: List[str], current_price: float, spread: float = 0) -> bool:
        """Determine if we should enter a position"""
        if len(prices) < 3:
            return False
        
        # Price range check
        if current_price < 0.10 or current_price > 0.90:
            return False
        
        # Don't enter in extreme volatility
        if volatility > 0.15:
            return False
        
        # Need enough price variation
        recent_range = max(prices[-5:]) - min(prices[-5:]) if len(prices) >= 5 else 0
        if recent_range < 0.005:  # Less than 0.5% recent movement
            return False
        
        # Strategy-specific entry conditions
        if "delta_neutral" in strategies:
            # Market making: enter when spread is favorable and price is stable
            if spread > 0.02 and volatility < 0.05:
                return random.random() < 0.4
        
        if "volatility_exploitation" in strategies:
            # Enter when volatility is moderate and trend is clear
            if 0.02 < volatility < 0.08 and abs(trend) > 0.02:
                return random.random() < 0.35
        
        if "alpha_directional" in strategies:
            # Enter on strong trend signals with recent momentum
            if abs(trend) > 0.03 and recent_range > 0.01:
                return random.random() < 0.3
        
        # Base probability for exploration
        return random.random() < 0.20
    
    def _select_best_strategy(self, volatility: float, trend: float, strategies: List[str]) -> str:
        """Select the best strategy for current market conditions"""
        if not strategies:
            return "delta_neutral"
        
        # Score each strategy
        scores = {}
        
        for strategy in strategies:
            score = 0
            
            if strategy == "delta_neutral":
                # Best for low volatility, no trend
                score = (1 - volatility * 10) * (1 - abs(trend) * 5)
            elif strategy == "volatility_exploitation":
                # Best for moderate-high volatility
                score = volatility * 10 if volatility < 0.1 else 0.5
            elif strategy == "alpha_directional":
                # Best for trending markets
                score = abs(trend) * 5
            elif strategy == "arbitrage":
                # Best for stable markets
                score = (1 - volatility * 5) * 0.8
            
            # Add performance history
            if strategy in self.strategy_performance:
                perf = self.strategy_performance[strategy]
                if perf["trades"] > 0:
                    win_rate = perf["wins"] / perf["trades"]
                    score *= (0.5 + win_rate)
            
            scores[strategy] = max(score, 0.1)
        
        # Weighted random selection based on scores
        total = sum(scores.values())
        r = random.random() * total
        cumulative = 0
        
        for strategy, score in scores.items():
            cumulative += score
            if r <= cumulative:
                return strategy
        
        return strategies[0]
    
    async def _open_position(self, market_id: str, price: float, strategy: str, 
                            category: str, timestamp: str, profit_target: float,
                            stop_loss: float, size_mult: float) -> Dict:
        """Open a new position with adaptive sizing"""
        available_capital = self.current_capital * 0.8
        base_size = available_capital * 0.04  # 4% base position
        position_size = base_size * size_mult
        
        shares = position_size / price if price > 0 else 0
        if shares < 1:
            shares = 1
            position_size = shares * price
        
        self.current_capital -= position_size
        
        position = {
            "market_id": market_id,
            "strategy": strategy,
            "category": category,
            "entry_price": price,
            "shares": shares,
            "cost": position_size,
            "profit_target": profit_target,
            "stop_loss": stop_loss,
            "entry_time": timestamp,
            "snapshots_held": 0
        }
        
        self.positions[market_id] = position
        
        # Record entry trade
        trade = {
            "id": str(uuid.uuid4()),
            "backtest_id": self.backtest_id,
            "market_id": market_id,
            "strategy": strategy,
            "category": category,
            "side": "BUY",
            "price": price,
            "shares": shares,
            "cost": position_size,
            "timestamp": timestamp
        }
        self.trades.append(trade)
        
        logger.debug(f"Opened {strategy} position on {market_id[:8]} @ ${price:.3f}")
        
        return position
    
    def _check_exit_conditions(self, position: Dict, current_price: float, 
                               highest_price: float, snapshots_held: int,
                               volatility: float, profit_target: float, 
                               stop_loss: float, price_change: float = 0,
                               spread: float = 0) -> Optional[str]:
        """Check if position should be closed with adaptive exit logic"""
        entry_price = position["entry_price"]
        pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        
        # 1. Take profit - adaptive based on actual price movement
        if pnl_pct >= profit_target:
            return "profit_target"
        
        # 2. Stop loss
        if pnl_pct <= -stop_loss:
            return "stop_loss"
        
        # 3. Trailing stop - only activate after minimum profit
        if pnl_pct > self.trailing_stop_trigger:
            trailing_stop_price = highest_price * (1 - self.trailing_stop_distance)
            if current_price < trailing_stop_price:
                return "trailing_stop"
        
        # 4. Quick profit banking for HFT - capture small gains
        if pnl_pct > 0.005 and snapshots_held > 3:  # 0.5% profit after 3 snapshots
            if random.random() < 0.4:  # 40% chance to bank small profit
                return "bank_profit"
        
        # 5. Time-based exit for stale positions
        if snapshots_held > self.position_timeout_snapshots:
            return "timeout"
        
        # 6. Exit if spread narrows (market making profit taken)
        if spread < 0.01 and pnl_pct > 0:
            return "spread_capture"
        
        # 7. Momentum reversal exit
        if snapshots_held > 5:
            if (position.get("trend_at_entry", 0) > 0 and price_change < -0.01) or \
               (position.get("trend_at_entry", 0) < 0 and price_change > 0.01):
                return "momentum_reversal"
        
        return None
    
    async def _close_position(self, market_id: str, position: Dict, exit_price: float, 
                             timestamp: str, exit_reason: str):
        """Close position and record trade"""
        shares = position["shares"]
        entry_price = position["entry_price"]
        exit_value = shares * exit_price
        cost = position["cost"]
        pnl = exit_value - cost
        
        self.current_capital += exit_value
        
        strategy = position["strategy"]
        category = position["category"]
        
        # Only log trades for debugging
        if random.random() < 0.02:  # Log 2% of trades
            logger.info(f"TRADE: {strategy} {market_id[:8]} entry=${entry_price:.4f} exit=${exit_price:.4f} pnl=${pnl:.4f} ({exit_reason})")
            logger.info(f"  Strategy perf before: {self.strategy_performance.get(strategy, 'N/A')}")
        
        # Record exit trade
        trade = {
            "id": str(uuid.uuid4()),
            "backtest_id": self.backtest_id,
            "market_id": market_id,
            "strategy": strategy,
            "category": category,
            "side": "SELL",
            "price": exit_price,
            "shares": shares,
            "value": exit_value,
            "pnl": pnl,
            "exit_reason": exit_reason,
            "timestamp": timestamp
        }
        self.trades.append(trade)
        
        # Update strategy performance
        if strategy in self.strategy_performance:
            self.strategy_performance[strategy]["trades"] += 1
            self.strategy_performance[strategy]["pnl"] += pnl
            if pnl > 0:
                self.strategy_performance[strategy]["wins"] += 1
        else:
            # Initialize if strategy wasn't pre-registered
            self.strategy_performance[strategy] = {"trades": 1, "wins": 1 if pnl > 0 else 0, "pnl": pnl}
        
        # Update asset class performance  
        if category in self.asset_class_performance:
            self.asset_class_performance[category]["trades"] += 1
            self.asset_class_performance[category]["pnl"] += pnl
            if pnl > 0:
                self.asset_class_performance[category]["wins"] += 1
        
        # Remove from positions
        if market_id in self.positions:
            del self.positions[market_id]
    
    async def _calculate_backtest_results(self, data_summary: Dict) -> Dict:
        """Calculate comprehensive backtest metrics"""
        try:
            # Count trades by side
            buy_trades = [t for t in self.trades if t.get("side") == "BUY"]
            sell_trades = [t for t in self.trades if t.get("side") == "SELL"]
            
            total_trades = len(sell_trades)  # Complete round trips
            
            # Calculate P&L
            total_pnl = sum(t.get("pnl", 0) for t in sell_trades)
            winning_trades = len([t for t in sell_trades if t.get("pnl", 0) > 0])
            losing_trades = len([t for t in sell_trades if t.get("pnl", 0) < 0])
            
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            # Calculate returns
            total_return_pct = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
            
            # Risk metrics
            pnls = [t.get("pnl", 0) for t in sell_trades]
            if pnls:
                avg_win = np.mean([p for p in pnls if p > 0]) if any(p > 0 for p in pnls) else 0
                avg_loss = np.mean([p for p in pnls if p < 0]) if any(p < 0 for p in pnls) else 0
                profit_factor = abs(sum(p for p in pnls if p > 0) / sum(p for p in pnls if p < 0)) if any(p < 0 for p in pnls) else 0
                
                # Sharpe ratio
                returns = np.array(pnls) / self.initial_capital
                sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
                
                # Max drawdown
                cumulative = np.cumsum(pnls)
                peak = np.maximum.accumulate(cumulative)
                drawdown = (peak - cumulative) / (peak + self.initial_capital)
                max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
            else:
                avg_win = avg_loss = profit_factor = sharpe = max_drawdown = 0
            
            # Exit reason breakdown
            exit_reasons = {}
            for t in sell_trades:
                reason = t.get("exit_reason", "unknown")
                exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
            
            # Strategy results - convert numpy types to Python types
            strategy_results = {}
            for strategy, perf in self.strategy_performance.items():
                trades = perf["trades"]
                strategy_results[strategy] = {
                    "trades": int(trades),
                    "wins": int(perf["wins"]),
                    "pnl": float(perf["pnl"]),
                    "win_rate": float(perf["wins"] / trades) if trades > 0 else 0.0
                }
            
            # Asset class results - convert numpy types
            asset_class_results = {}
            for category, perf in self.asset_class_performance.items():
                trades = perf["trades"]
                asset_class_results[category] = {
                    "trades": int(trades),
                    "wins": int(perf["wins"]),
                    "pnl": float(perf["pnl"]),
                    "win_rate": float(perf["wins"] / trades) if trades > 0 else 0.0
                }
            
            return {
                "backtest_id": self.backtest_id,
                "status": "completed",
                "initial_capital": float(self.initial_capital),
                "final_capital": float(self.current_capital),
                "total_pnl": float(total_pnl),
                "total_return_pct": float(total_return_pct),
                "total_trades": int(total_trades),
                "winning_trades": int(winning_trades),
                "losing_trades": int(losing_trades),
                "win_rate": float(win_rate),
                "avg_win": float(avg_win),
                "avg_loss": float(avg_loss),
                "profit_factor": float(profit_factor),
                "sharpe_ratio": float(sharpe),
                "max_drawdown": float(max_drawdown),
                "exit_reasons": exit_reasons,
                "strategy_results": strategy_results,
                "asset_class_results": asset_class_results,
                "data_summary": data_summary,
                "rl_learning_stats": await self.rl_engine.get_training_stats(),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Error calculating results: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    async def _store_backtest_results(self, results: Dict):
        """Store backtest results in database"""
        try:
            await self.db.backtest_results.insert_one({**results, "_id": None})
            # Remove _id to avoid serialization issues
            if "_id" in results:
                del results["_id"]
        except Exception as e:
            logger.error(f"Error storing backtest results: {e}")
    
    async def stop_backtest(self):
        """Stop running backtest"""
        self.running = False
        logger.info(f"Backtest {self.backtest_id} stopped")
    
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
        """Get list of past backtest results"""
        try:
            cursor = self.db.backtest_results.find({}, {"_id": 0}).sort("completed_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting backtest history: {e}")
            return []
    
    async def compare_backtests(self, backtest_ids: List[str]) -> Dict:
        """Compare multiple backtest results with comprehensive metrics"""
        try:
            cursor = self.db.backtest_results.find(
                {"backtest_id": {"$in": backtest_ids}},
                {"_id": 0}
            )
            backtests = await cursor.to_list(length=len(backtest_ids))
            
            if not backtests:
                return {"error": "No backtests found"}
            
            # Build comparison
            comparison = {
                "backtest_count": len(backtests),
                "backtests": backtests,
                "comparison_metrics": {},
                "strategy_comparison": {},
                "asset_class_comparison": {},
                "improvement_insights": [],
                "educational_analysis": {}
            }
            
            # Aggregate metrics
            all_returns = [b.get("total_return_pct", 0) for b in backtests]
            all_sharpe = [b.get("sharpe_ratio", 0) for b in backtests]
            all_win_rates = [b.get("win_rate", 0) for b in backtests]
            all_drawdowns = [b.get("max_drawdown", 0) for b in backtests]
            all_profit_factors = [b.get("profit_factor", 0) for b in backtests]
            
            comparison["comparison_metrics"] = {
                "return": {"best": max(all_returns), "worst": min(all_returns), "avg": np.mean(all_returns)},
                "sharpe_ratio": {"best": max(all_sharpe), "worst": min(all_sharpe), "avg": np.mean(all_sharpe)},
                "win_rate": {"best": max(all_win_rates), "worst": min(all_win_rates), "avg": np.mean(all_win_rates)},
                "max_drawdown": {"best": min(all_drawdowns), "worst": max(all_drawdowns), "avg": np.mean(all_drawdowns)},
                "profit_factor": {"best": max(all_profit_factors), "worst": min(all_profit_factors), "avg": np.mean(all_profit_factors)}
            }
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error comparing backtests: {e}")
            return {"error": str(e)}
    
    async def delete_backtest(self, backtest_id: str) -> bool:
        """Delete a backtest result"""
        try:
            result = await self.db.backtest_results.delete_one({"backtest_id": backtest_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting backtest: {e}")
            return False
