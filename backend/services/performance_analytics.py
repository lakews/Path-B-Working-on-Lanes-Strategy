import logging
from typing import Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from database import get_db
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

class PerformanceAnalytics:
    """Enhanced performance analytics with strategy and asset class breakdowns"""
    
    def __init__(self):
        self.db = get_db()
    
    async def calculate_comprehensive_metrics(self) -> Dict:
        """Calculate all performance metrics including strategy and asset class breakdowns"""
        try:
            trades = await self._get_all_trades()
            positions = await self._get_all_positions()
            
            # Overall metrics
            overall_metrics = await self._calculate_overall_metrics(trades, positions)
            
            # Strategy-level metrics
            strategy_metrics = await self._calculate_strategy_metrics(trades)
            
            # Asset class metrics (by category)
            asset_class_metrics = await self._calculate_asset_class_metrics(trades)
            
            # Lane metrics (HFT/ALPHA/GAMMA) - Three-Speed Architecture
            lane_metrics = self._calculate_lane_metrics(trades)
            
            # Portfolio volatility
            portfolio_volatility = await self._calculate_portfolio_volatility()
            
            # Advanced metrics
            advanced_metrics = await self._calculate_advanced_metrics(trades)
            
            # Build clean metrics dict (no ObjectIds)
            metrics = {
                "total_trades": overall_metrics.get("total_trades", 0),
                "overall_win_rate": overall_metrics.get("overall_win_rate", 0.0),
                "winning_trades": overall_metrics.get("winning_trades", 0),
                "losing_trades": overall_metrics.get("losing_trades", 0),
                "total_pnl": overall_metrics.get("total_pnl", 0.0),
                "realized_pnl": overall_metrics.get("realized_pnl", 0.0),
                "unrealized_pnl": overall_metrics.get("unrealized_pnl", 0.0),
                "strategy_performance": strategy_metrics,
                "asset_class_performance": asset_class_metrics,
                "lane_performance": lane_metrics,  # Three-Speed: HFT/ALPHA/GAMMA breakdown
                "portfolio_volatility": portfolio_volatility,
                **advanced_metrics,  # Add advanced metrics
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Store in database
            try:
                await self.db.analytics.insert_one(metrics.copy())
            except Exception as e:
                logger.warning(f"Could not store analytics: {e}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating comprehensive metrics: {e}")
            return {
                "total_trades": 0,
                "overall_win_rate": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "strategy_performance": {},
                "asset_class_performance": {},
                "portfolio_volatility": 0.0,
                "sortino_ratio": 0.0,
                "profit_factor": 0.0,
                "win_loss_ratio": 0.0,
                "recovery_factor": 0.0,
                "expectancy": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _calculate_overall_metrics(self, trades: List[Dict], positions: List[Dict]) -> Dict:
        """Calculate overall portfolio metrics"""
        try:
            if not trades:
                return {
                    "total_trades": 0,
                    "overall_win_rate": 0.0,
                    "total_pnl": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0
                }
            
            # Win rate
            winning_trades = [t for t in trades if self._is_winning_trade(t)]
            win_rate = len(winning_trades) / len(trades) if trades else 0
            
            # Total P&L
            total_pnl = sum(self._calculate_trade_pnl(t) for t in trades)
            
            # Add unrealized P&L from open positions
            unrealized_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)
            
            return {
                "total_trades": len(trades),
                "overall_win_rate": win_rate,
                "winning_trades": len(winning_trades),
                "losing_trades": len(trades) - len(winning_trades),
                "total_pnl": total_pnl,
                "realized_pnl": total_pnl,
                "unrealized_pnl": unrealized_pnl
            }
            
        except Exception as e:
            logger.error(f"Error calculating overall metrics: {e}")
            return {}
    
    async def _calculate_strategy_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate win rate and performance by strategy"""
        try:
            strategy_stats = defaultdict(lambda: {
                'trades': [],
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0
            })
            
            for trade in trades:
                strategy = trade.get('strategy', 'unknown')
                strategy_stats[strategy]['trades'].append(trade)
                
                pnl = self._calculate_trade_pnl(trade)
                strategy_stats[strategy]['total_pnl'] += pnl
                
                if self._is_winning_trade(trade):
                    strategy_stats[strategy]['wins'] += 1
                else:
                    strategy_stats[strategy]['losses'] += 1
            
            # Calculate metrics for each strategy
            result = {}
            for strategy, stats in strategy_stats.items():
                total = len(stats['trades'])
                result[strategy] = {
                    "total_trades": total,
                    "wins": stats['wins'],
                    "losses": stats['losses'],
                    "win_rate": stats['wins'] / total if total > 0 else 0,
                    "total_pnl": stats['total_pnl'],
                    "avg_pnl_per_trade": stats['total_pnl'] / total if total > 0 else 0,
                    "classification": self._classify_strategy_performance(
                        stats['wins'] / total if total > 0 else 0,
                        stats['total_pnl']
                    )
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating strategy metrics: {e}")
            return {}
    
    async def _calculate_asset_class_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate win rate and performance by asset class (market category)"""
        try:
            # Get market categories for each trade
            category_stats = defaultdict(lambda: {
                'trades': [],
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0
            })
            
            for trade in trades:
                market_id = trade.get('market_id')
                
                # Fetch market to get category
                market = await self.db.markets.find_one(
                    {"id": market_id},
                    {"category": 1, "_id": 0}
                )
                category = market.get('category', 'unknown') if market else 'unknown'
                
                category_stats[category]['trades'].append(trade)
                
                pnl = self._calculate_trade_pnl(trade)
                category_stats[category]['total_pnl'] += pnl
                
                if self._is_winning_trade(trade):
                    category_stats[category]['wins'] += 1
                else:
                    category_stats[category]['losses'] += 1
            
            # Calculate metrics for each asset class
            result = {}
            for category, stats in category_stats.items():
                total = len(stats['trades'])
                result[category] = {
                    "total_trades": total,
                    "wins": stats['wins'],
                    "losses": stats['losses'],
                    "win_rate": stats['wins'] / total if total > 0 else 0,
                    "total_pnl": stats['total_pnl'],
                    "avg_pnl_per_trade": stats['total_pnl'] / total if total > 0 else 0
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating asset class metrics: {e}")
            return {}
    
    async def _calculate_portfolio_volatility(self) -> float:
        """Calculate portfolio volatility (standard deviation of returns)"""
        try:
            # Get recent performance snapshots
            cursor = self.db.performance_metrics.find(
                {},
                {"total_capital": 1, "_id": 0}
            ).sort("timestamp", 1).limit(100)
            
            docs = await cursor.to_list(length=100)
            
            if len(docs) < 10:
                return 0.0
            
            # Calculate returns
            capitals = [doc['total_capital'] for doc in docs]
            returns = []
            for i in range(1, len(capitals)):
                ret = (capitals[i] - capitals[i-1]) / capitals[i-1] if capitals[i-1] > 0 else 0
                returns.append(ret)
            
            if not returns:
                return 0.0
            
            # Calculate annualized volatility
            volatility = np.std(returns) * np.sqrt(252)  # Annualized
            
            return float(volatility)
            
        except Exception as e:
            logger.error(f"Error calculating portfolio volatility: {e}")
            return 0.0
    
    def _classify_strategy_performance(self, win_rate: float, total_pnl: float) -> str:
        """Classify strategy performance"""
        if win_rate >= 0.80 and total_pnl > 0:
            return "Excellent"
        elif win_rate >= 0.65 and total_pnl > 0:
            return "Good"
        elif win_rate >= 0.50 and total_pnl > 0:
            return "Moderate"
        elif total_pnl > 0:
            return "Profitable (Low Win Rate)"
        else:
            return "Underperforming"
    
    def _is_winning_trade(self, trade: Dict) -> bool:
        """Check if trade was profitable"""
        pnl = self._calculate_trade_pnl(trade)
        return pnl > 0
    
    def _calculate_trade_pnl(self, trade: Dict) -> float:
        """Calculate P&L for a trade"""
        try:
            side = trade.get('side')
            price = trade.get('price', 0)
            shares = trade.get('shares', 0)
            fee = trade.get('fee', 0)
            
            # Simplified P&L calculation
            # In real scenario, would compare entry/exit prices
            if side == 'SELL':
                pnl = (price * shares) - fee
            else:
                pnl = -(price * shares) - fee
            
            return pnl
            
        except Exception as e:
            logger.error(f"Error calculating trade P&L: {e}")
            return 0.0
    
    async def _get_all_trades(self) -> List[Dict]:
        """Get all trades"""
        try:
            cursor = self.db.trades.find({}, {"_id": 0})
            return await cursor.to_list(length=10000)
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    async def _get_all_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            cursor = self.db.positions.find({}, {"_id": 0})
            return await cursor.to_list(length=1000)
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    async def get_latest_analytics(self) -> Dict:
        """Get latest comprehensive analytics"""
        try:
            analytics = await self.db.analytics.find_one(
                {},
                {"_id": 0},
                sort=[("timestamp", -1)]
            )
            return analytics if analytics else {}
        except Exception as e:
            logger.error(f"Error getting latest analytics: {e}")
            return {}
    
    async def _calculate_advanced_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate advanced performance metrics"""
        try:
            if not trades:
                return {
                    "sortino_ratio": 0.0,
                    "profit_factor": 0.0,
                    "win_loss_ratio": 0.0,
                    "recovery_factor": 0.0,
                    "expectancy": 0.0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                    "max_consecutive_wins": 0,
                    "max_consecutive_losses": 0
                }
            
            # Get returns
            returns = [self._calculate_trade_pnl(t) for t in trades]
            
            # Sortino Ratio (only penalizes downside)
            sortino = self._calculate_sortino(returns)
            
            # Profit Factor
            wins = [r for r in returns if r > 0]
            losses = [abs(r) for r in returns if r < 0]
            profit_factor = sum(wins) / sum(losses) if losses and sum(losses) > 0 else 0
            
            # Win/Loss Ratio
            avg_win = np.mean(wins) if wins else 0
            avg_loss = np.mean(losses) if losses else 0
            win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
            
            # Recovery Factor
            total_pnl = sum(returns)
            max_dd = await self._get_max_drawdown()
            recovery_factor = total_pnl / max_dd if max_dd > 0 else 0
            
            # Expectancy (average $ per trade)
            expectancy = np.mean(returns)
            
            # Consecutive wins/losses
            max_wins, max_losses = self._calculate_streaks(returns)
            
            return {
                "sortino_ratio": sortino,
                "profit_factor": profit_factor,
                "win_loss_ratio": win_loss_ratio,
                "recovery_factor": recovery_factor,
                "expectancy": expectancy,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "max_consecutive_wins": max_wins,
                "max_consecutive_losses": max_losses
            }
            
        except Exception as e:
            logger.error(f"Error calculating advanced metrics: {e}")
            return {
                "sortino_ratio": 0.0,
                "profit_factor": 0.0,
                "win_loss_ratio": 0.0,
                "recovery_factor": 0.0,
                "expectancy": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0
            }
    
    def _calculate_sortino(self, returns: List[float]) -> float:
        """Calculate Sortino ratio (only penalizes downside volatility)"""
        try:
            if len(returns) < 2:
                return 0.0
            
            mean_return = np.mean(returns)
            downside_returns = [r for r in returns if r < 0]
            
            if not downside_returns:
                return 0.0
            
            downside_std = np.std(downside_returns)
            
            if downside_std == 0:
                return 0.0
            
            sortino = (mean_return / downside_std) * np.sqrt(252)
            return sortino
            
        except Exception as e:
            logger.error(f"Error calculating Sortino: {e}")
            return 0.0
    
    def _calculate_streaks(self, returns: List[float]) -> Tuple[int, int]:
        """Calculate max consecutive wins and losses"""
        try:
            if not returns:
                return 0, 0
            
            max_wins = 0
            max_losses = 0
            current_wins = 0
            current_losses = 0
            
            for ret in returns:
                if ret > 0:
                    current_wins += 1
                    current_losses = 0
                    max_wins = max(max_wins, current_wins)
                elif ret < 0:
                    current_losses += 1
                    current_wins = 0
                    max_losses = max(max_losses, current_losses)
            
            return max_wins, max_losses
            
        except Exception as e:
            logger.error(f"Error calculating streaks: {e}")
            return 0, 0
    
    async def _get_max_drawdown(self) -> float:
        """Get current max drawdown"""
        try:
            cursor = self.db.performance_metrics.find(
                {},
                {"max_drawdown": 1, "_id": 0}
            ).sort("timestamp", -1).limit(1)
            
            doc = await cursor.to_list(length=1)
            if doc:
                return doc[0].get('max_drawdown', 0)
            return 0
            
        except Exception as e:
            logger.error(f"Error getting max drawdown: {e}")
            return 0
