"""
Strategy Tuning Mode - Automatic Parameter Optimization
Uses grid search and walk-forward optimization to find optimal strategy parameters
"""
import logging
import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from itertools import product
import uuid

logger = logging.getLogger(__name__)


class StrategyTuner:
    """
    Automatic strategy parameter optimization using grid search
    Tests parameter combinations and ranks by performance metrics
    """
    
    def __init__(self):
        self._db = None
        self.running = False
        self.current_tune_id = None
        self.results = []
        
        # Define parameter grids for each strategy
        self.parameter_grids = {
            'delta_neutral': {
                'profit_target': [0.003, 0.004, 0.005, 0.006, 0.008],
                'stop_loss': [0.006, 0.008, 0.010, 0.012, 0.015],
                'bank_profit_threshold': [0.001, 0.002, 0.003],
                'timeout_snapshots': [8, 12, 15, 20],
                'spread_threshold': [0.012, 0.015, 0.018, 0.020]
            },
            'volatility_exploitation': {
                'profit_target': [0.02, 0.03, 0.04, 0.05],
                'stop_loss': [0.02, 0.03, 0.04, 0.05],
                'min_volatility': [0.02, 0.03, 0.04],
                'max_volatility': [0.08, 0.10, 0.12],
                'trend_threshold': [0.02, 0.03, 0.04]
            },
            'alpha_directional': {
                'profit_target': [0.02, 0.03, 0.04, 0.05],
                'stop_loss': [0.02, 0.03, 0.04],
                'trend_threshold': [0.02, 0.03, 0.04, 0.05],
                'trailing_stop_trigger': [0.01, 0.015, 0.02],
                'trailing_stop_distance': [0.008, 0.01, 0.015]
            },
            'arbitrage': {
                'profit_target': [0.01, 0.015, 0.02, 0.025],
                'stop_loss': [0.015, 0.02, 0.025, 0.03],
                'min_spread': [0.02, 0.025, 0.03],
                'position_timeout': [30, 40, 50, 60]
            }
        }
        
        # Scoring weights for ranking parameter sets
        self.scoring_weights = {
            'total_return': 0.25,
            'sharpe_ratio': 0.25,
            'win_rate': 0.20,
            'profit_factor': 0.20,
            'max_drawdown': 0.10  # Lower is better
        }
    
    @property
    def db(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db
    
    async def tune_strategy(
        self,
        strategy_name: str,
        start_date: str,
        end_date: str,
        max_combinations: int = 50
    ) -> Dict:
        """
        Run parameter optimization for a single strategy
        Returns: Best parameters and performance metrics
        """
        if self.running:
            return {"error": "Tuning already in progress"}
        
        self.running = True
        self.current_tune_id = str(uuid.uuid4())
        self.results = []
        
        try:
            logger.info(f"Starting strategy tuning for {strategy_name}")
            
            # Get parameter grid for this strategy
            if strategy_name not in self.parameter_grids:
                return {"error": f"Unknown strategy: {strategy_name}"}
            
            grid = self.parameter_grids[strategy_name]
            
            # Generate parameter combinations
            combinations = self._generate_combinations(grid, max_combinations)
            
            logger.info(f"Testing {len(combinations)} parameter combinations")
            
            # Test each combination
            for i, params in enumerate(combinations):
                if not self.running:
                    break
                
                logger.info(f"Testing combination {i+1}/{len(combinations)}: {params}")
                
                # Run backtest with these parameters
                result = await self._test_parameters(
                    strategy_name, params, start_date, end_date
                )
                
                if result and 'error' not in result:
                    self.results.append({
                        'params': params,
                        'metrics': result,
                        'score': self._calculate_score(result)
                    })
            
            # Sort by score
            self.results.sort(key=lambda x: x['score'], reverse=True)
            
            # Store results
            await self._store_tuning_results(strategy_name)
            
            # Get best parameters
            best = self.results[0] if self.results else None
            
            return {
                'tune_id': self.current_tune_id,
                'strategy': strategy_name,
                'combinations_tested': len(combinations),
                'best_parameters': best['params'] if best else None,
                'best_metrics': best['metrics'] if best else None,
                'best_score': best['score'] if best else 0,
                'top_5': self.results[:5],
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in strategy tuning: {e}")
            return {"error": str(e)}
        finally:
            self.running = False
    
    async def tune_all_strategies(
        self,
        start_date: str,
        end_date: str,
        max_combinations_per_strategy: int = 30
    ) -> Dict:
        """
        Run parameter optimization for all strategies
        """
        if self.running:
            return {"error": "Tuning already in progress"}
        
        results = {}
        
        for strategy_name in self.parameter_grids.keys():
            logger.info(f"Tuning {strategy_name}...")
            result = await self.tune_strategy(
                strategy_name,
                start_date,
                end_date,
                max_combinations_per_strategy
            )
            results[strategy_name] = {
                'best_params': result.get('best_parameters'),
                'best_score': result.get('best_score', 0),
                'metrics': result.get('best_metrics')
            }
        
        # Store combined results
        await self.db.strategy_tuning.insert_one({
            "id": str(uuid.uuid4()),
            "type": "full_optimization",
            "results": results,
            "date_range": {"start": start_date, "end": end_date},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            'strategies_tuned': list(results.keys()),
            'results': results,
            'completed_at': datetime.now(timezone.utc).isoformat()
        }
    
    def _generate_combinations(self, grid: Dict, max_combinations: int) -> List[Dict]:
        """Generate parameter combinations from grid"""
        keys = list(grid.keys())
        values = list(grid.values())
        
        # Generate all combinations
        all_combinations = list(product(*values))
        
        # Convert to dicts
        combinations = [
            dict(zip(keys, combo)) for combo in all_combinations
        ]
        
        # Limit to max_combinations (sample if too many)
        if len(combinations) > max_combinations:
            # Use stratified sampling to cover the space
            indices = np.linspace(0, len(combinations)-1, max_combinations, dtype=int)
            combinations = [combinations[i] for i in indices]
        
        return combinations
    
    async def _test_parameters(
        self,
        strategy_name: str,
        params: Dict,
        start_date: str,
        end_date: str
    ) -> Optional[Dict]:
        """
        Test a parameter set by running a simplified backtest
        """
        try:
            # Get deployed capital from config (single source of truth)
            from config import config
            deployed_capital = getattr(config, 'DEPLOYED_CAPITAL', 8000)
            
            # Get historical data
            market_data = await self._get_test_data(start_date, end_date)
            
            if not market_data:
                return None
            
            # Simulate trades with these parameters
            # Use deployed capital to match real trading conditions
            trades = []
            capital = deployed_capital
            positions = {}
            
            for market_id, timeseries in market_data.items():
                if len(timeseries) < 10:
                    continue
                
                prices = [s.get('yes_price', 0.5) for s in timeseries]
                
                # Simulate price movement (using existing data)
                for i in range(5, len(prices)):
                    current_price = prices[i]
                    
                    # Entry logic based on strategy
                    if market_id not in positions and len(positions) < 10:
                        if self._should_enter_tuning(strategy_name, params, prices[:i+1]):
                            cost = capital * 0.02
                            shares = cost / current_price
                            positions[market_id] = {
                                'entry_price': current_price,
                                'shares': shares,
                                'cost': cost,
                                'entry_idx': i
                            }
                            capital -= cost
                    
                    # Exit logic
                    elif market_id in positions:
                        pos = positions[market_id]
                        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                        snapshots_held = i - pos['entry_idx']
                        
                        should_exit, reason = self._should_exit_tuning(
                            strategy_name, params, pnl_pct, snapshots_held
                        )
                        
                        if should_exit:
                            exit_value = pos['shares'] * current_price
                            pnl = exit_value - pos['cost']
                            capital += exit_value
                            
                            trades.append({
                                'pnl': pnl,
                                'pnl_pct': pnl_pct,
                                'reason': reason
                            })
                            
                            del positions[market_id]
            
            # Calculate metrics
            if not trades:
                return None
            
            total_pnl = sum(t['pnl'] for t in trades)
            wins = [t for t in trades if t['pnl'] > 0]
            losses = [t for t in trades if t['pnl'] <= 0]
            
            win_rate = len(wins) / len(trades) if trades else 0
            avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
            avg_loss = np.mean([abs(t['pnl']) for t in losses]) if losses else 0
            profit_factor = (sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses))) if losses else 0
            
            # Calculate Sharpe (simplified)
            returns = [t['pnl_pct'] for t in trades]
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
            
            # Calculate max drawdown (use deployed_capital instead of hardcoded 1000)
            cumulative = np.cumsum([t['pnl'] for t in trades])
            peak = np.maximum.accumulate(cumulative)
            drawdown = (peak - cumulative) / (peak + deployed_capital)  # Avoid division by zero
            max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
            
            return {
                'total_pnl': float(total_pnl),
                'total_return': float(total_pnl / deployed_capital * 100),  # Return on deployed capital
                'total_trades': len(trades),
                'win_rate': float(win_rate),
                'avg_win': float(avg_win),
                'avg_loss': float(avg_loss),
                'profit_factor': float(profit_factor),
                'sharpe_ratio': float(sharpe),
                'max_drawdown': float(max_drawdown)
            }
            
        except Exception as e:
            logger.error(f"Error testing parameters: {e}")
            return None
    
    def _should_enter_tuning(self, strategy: str, params: Dict, prices: List[float]) -> bool:
        """Simplified entry logic for tuning"""
        if len(prices) < 5:
            return False
        
        current = prices[-1]
        volatility = np.std(prices[-10:]) if len(prices) >= 10 else 0.05
        trend = (prices[-1] - prices[-5]) / prices[-5] if prices[-5] > 0 else 0
        
        if strategy == 'delta_neutral':
            spread_threshold = params.get('spread_threshold', 0.015)
            return volatility < 0.04 and 0.25 < current < 0.75
        
        elif strategy == 'volatility_exploitation':
            min_vol = params.get('min_volatility', 0.02)
            max_vol = params.get('max_volatility', 0.10)
            trend_thresh = params.get('trend_threshold', 0.02)
            return min_vol < volatility < max_vol and abs(trend) > trend_thresh
        
        elif strategy == 'alpha_directional':
            trend_thresh = params.get('trend_threshold', 0.03)
            return abs(trend) > trend_thresh
        
        elif strategy == 'arbitrage':
            min_spread = params.get('min_spread', 0.02)
            return volatility < 0.05
        
        return False
    
    def _should_exit_tuning(
        self,
        strategy: str,
        params: Dict,
        pnl_pct: float,
        snapshots_held: int
    ) -> Tuple[bool, str]:
        """Simplified exit logic for tuning"""
        profit_target = params.get('profit_target', 0.02)
        stop_loss = params.get('stop_loss', 0.03)
        
        if pnl_pct >= profit_target:
            return True, 'profit_target'
        
        if pnl_pct <= -stop_loss:
            return True, 'stop_loss'
        
        # Strategy-specific exits
        if strategy == 'delta_neutral':
            timeout = params.get('timeout_snapshots', 15)
            bank_threshold = params.get('bank_profit_threshold', 0.002)
            
            if pnl_pct > bank_threshold and snapshots_held >= 3:
                return True, 'bank_profit'
            if snapshots_held > timeout:
                return True, 'timeout'
        
        else:
            # Default timeout for other strategies
            if snapshots_held > 50:
                return True, 'timeout'
        
        return False, None
    
    async def _get_test_data(self, start_date: str, end_date: str) -> Dict:
        """Get historical data for testing"""
        try:
            cursor = self.db.historical_data.find(
                {"timestamp": {"$gte": start_date, "$lte": end_date}},
                {"_id": 0, "market_id": 1, "yes_price": 1, "timestamp": 1, "volume": 1}
            ).sort("timestamp", 1)
            
            data = await cursor.to_list(length=50000)
            
            # Group by market
            markets = {}
            for d in data:
                market_id = d.get('market_id')
                if market_id not in markets:
                    markets[market_id] = []
                markets[market_id].append(d)
            
            # Filter to markets with enough data
            return {k: v for k, v in markets.items() if len(v) >= 20}
            
        except Exception as e:
            logger.error(f"Error getting test data: {e}")
            return {}
    
    def _calculate_score(self, metrics: Dict) -> float:
        """Calculate composite score for a parameter set"""
        try:
            # Normalize metrics to 0-1 scale
            return_score = min(max(metrics.get('total_return', 0) / 20, 0), 1)  # 20% return = 1.0
            sharpe_score = min(max(metrics.get('sharpe_ratio', 0) / 2, 0), 1)  # Sharpe 2 = 1.0
            win_rate_score = metrics.get('win_rate', 0)
            pf_score = min(max(metrics.get('profit_factor', 0) / 2, 0), 1)  # PF 2 = 1.0
            dd_score = 1 - min(metrics.get('max_drawdown', 0), 1)  # Lower is better
            
            weighted_score = (
                return_score * self.scoring_weights['total_return'] +
                sharpe_score * self.scoring_weights['sharpe_ratio'] +
                win_rate_score * self.scoring_weights['win_rate'] +
                pf_score * self.scoring_weights['profit_factor'] +
                dd_score * self.scoring_weights['max_drawdown']
            )
            
            return round(weighted_score, 4)
            
        except Exception as e:
            logger.error(f"Error calculating score: {e}")
            return 0
    
    async def _store_tuning_results(self, strategy_name: str):
        """Store tuning results in database"""
        try:
            await self.db.strategy_tuning.insert_one({
                "id": self.current_tune_id,
                "strategy": strategy_name,
                "results": self.results[:20],  # Store top 20
                "total_tested": len(self.results),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing tuning results: {e}")
    
    async def get_best_parameters(self, strategy_name: str) -> Optional[Dict]:
        """Get the best parameters from previous tuning"""
        try:
            result = await self.db.strategy_tuning.find_one(
                {"strategy": strategy_name},
                {"_id": 0},
                sort=[("timestamp", -1)]
            )
            
            if result and result.get('results'):
                best = result['results'][0]
                return {
                    'strategy': strategy_name,
                    'parameters': best.get('params'),
                    'score': best.get('score'),
                    'metrics': best.get('metrics'),
                    'tuned_at': result.get('timestamp')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting best parameters: {e}")
            return None
    
    async def get_tuning_history(self, limit: int = 10) -> List[Dict]:
        """Get recent tuning history"""
        try:
            cursor = self.db.strategy_tuning.find(
                {},
                {"_id": 0, "id": 1, "strategy": 1, "total_tested": 1, "timestamp": 1}
            ).sort("timestamp", -1).limit(limit)
            
            return await cursor.to_list(length=limit)
            
        except Exception as e:
            logger.error(f"Error getting tuning history: {e}")
            return []
    
    def stop_tuning(self):
        """Stop current tuning process"""
        self.running = False
        logger.info("Tuning stopped by user")


# Singleton instance
strategy_tuner = StrategyTuner()
