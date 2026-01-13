import logging
from typing import Dict, List
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
            
            # Portfolio volatility
            portfolio_volatility = await self._calculate_portfolio_volatility()
            
            metrics = {
                **overall_metrics,
                "strategy_performance": strategy_metrics,
                "asset_class_performance": asset_class_metrics,
                "portfolio_volatility": portfolio_volatility,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Store in database
            await self.db.analytics.insert_one(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating comprehensive metrics: {e}")
            return {}
    
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
            cursor = self.db.trades.find({})
            return await cursor.to_list(length=10000)
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    async def _get_all_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            cursor = self.db.positions.find({})
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
