import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timezone, timedelta
from database import get_db
from config import config
import numpy as np

logger = logging.getLogger(__name__)

class RiskController:
    """Multi-layer risk management with circuit breakers"""
    
    def __init__(self):
        self.db = get_db()
        self.max_drawdown_pct = config.MAX_DRAWDOWN_PCT / 100
        self.max_position_size = config.MAX_POSITION_SIZE
        self.deployed_capital = config.DEPLOYED_CAPITAL
        self.circuit_breaker_active = False
        self.circuit_breaker_until = None
        self.kelly_fraction = config.KELLY_FRACTION
        self.min_kelly = config.MIN_KELLY_FRACTION
        self.max_kelly = config.MAX_KELLY_FRACTION
        
    async def check_trade_approval(
        self,
        market_id: str,
        trade_size: float,
        confidence: float
    ) -> Tuple[bool, str]:
        """Check if trade passes all risk checks
        Returns: (approved, reason)
        """
        try:
            if self.circuit_breaker_active:
                if datetime.now(timezone.utc) < self.circuit_breaker_until:
                    return False, "Circuit breaker active"
                else:
                    await self.reset_circuit_breaker()
            
            if trade_size > self.max_position_size:
                return False, f"Position size ${trade_size:.2f} exceeds max ${self.max_position_size:.2f}"
            
            if confidence < 0.3:
                return False, f"Confidence {confidence:.2%} too low"
            
            drawdown_ok, drawdown_msg = await self._check_drawdown()
            if not drawdown_ok:
                return False, drawdown_msg
            
            exposure_ok, exposure_msg = await self._check_exposure(trade_size)
            if not exposure_ok:
                return False, exposure_msg
            
            concentration_ok, conc_msg = await self._check_concentration(market_id, trade_size)
            if not concentration_ok:
                return False, conc_msg
            
            return True, "Approved"
            
        except Exception as e:
            logger.error(f"Error in trade approval: {e}")
            return False, f"Risk check error: {str(e)}"
    
    async def _check_drawdown(self) -> Tuple[bool, str]:
        """Check if current drawdown is within limits"""
        try:
            metrics = await self.db.performance_metrics.find_one(
                {},
                sort=[("timestamp", -1)]
            )
            
            if not metrics:
                return True, "No metrics yet"
            
            current_drawdown = metrics.get('max_drawdown', 0)
            
            if current_drawdown > self.max_drawdown_pct:
                await self.activate_circuit_breaker("Max drawdown exceeded")
                return False, f"Drawdown {current_drawdown:.2%} exceeds limit {self.max_drawdown_pct:.2%}"
            
            return True, "Drawdown within limits"
            
        except Exception as e:
            logger.error(f"Error checking drawdown: {e}")
            return False, "Drawdown check failed"
    
    async def _check_exposure(self, new_trade_size: float) -> Tuple[bool, str]:
        """Check total portfolio exposure"""
        try:
            positions = await self.db.positions.find({}).to_list(length=1000)
            
            total_exposure = sum(p['shares'] * p['avg_price'] for p in positions)
            
            total_with_new = total_exposure + new_trade_size
            
            if total_with_new > self.deployed_capital:
                return False, f"Total exposure ${total_with_new:.2f} exceeds deployed capital ${self.deployed_capital:.2f}"
            
            return True, "Exposure within limits"
            
        except Exception as e:
            logger.error(f"Error checking exposure: {e}")
            return False, "Exposure check failed"
    
    async def _check_concentration(self, market_id: str, new_size: float) -> Tuple[bool, str]:
        """Check single market concentration"""
        try:
            position = await self.db.positions.find_one({"market_id": market_id})
            
            current_size = 0
            if position:
                current_size = position['shares'] * position['avg_price']
            
            total_size = current_size + new_size
            concentration = total_size / config.INITIAL_CAPITAL
            
            if concentration > 0.10:
                return False, f"Market concentration {concentration:.2%} exceeds 10% limit"
            
            return True, "Concentration within limits"
            
        except Exception as e:
            logger.error(f"Error checking concentration: {e}")
            return False, "Concentration check failed"
    
    async def activate_circuit_breaker(self, reason: str, duration_minutes: int = 30):
        """Activate circuit breaker to halt trading"""
        try:
            self.circuit_breaker_active = True
            self.circuit_breaker_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            
            await self.db.system_events.insert_one({
                "event_type": "circuit_breaker_activated",
                "reason": reason,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "active_until": self.circuit_breaker_until.isoformat()
            })
            
            logger.warning(f"Circuit breaker activated: {reason}")
            
        except Exception as e:
            logger.error(f"Error activating circuit breaker: {e}")
    
    async def reset_circuit_breaker(self):
        """Reset circuit breaker"""
        try:
            self.circuit_breaker_active = False
            self.circuit_breaker_until = None
            
            await self.db.system_events.insert_one({
                "event_type": "circuit_breaker_reset",
                "reset_at": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info("Circuit breaker reset")
            
        except Exception as e:
            logger.error(f"Error resetting circuit breaker: {e}")
    
    async def calculate_current_metrics(self) -> Dict:
        """Calculate current portfolio metrics"""
        try:
            positions = await self.db.positions.find({}).to_list(length=1000)
            
            total_unrealized_pnl = sum(p.get('unrealized_pnl', 0) for p in positions)
            
            trades = await self.db.trades.find({}).to_list(length=10000)
            total_realized_pnl = sum(
                (t['price'] * t['shares']) - t.get('fee', 0) 
                for t in trades if t.get('side') == 'SELL'
            ) - sum(
                (t['price'] * t['shares']) + t.get('fee', 0) 
                for t in trades if t.get('side') == 'BUY'
            )
            
            total_pnl = total_realized_pnl + total_unrealized_pnl
            total_capital = config.INITIAL_CAPITAL + total_pnl
            
            deployed = sum(p['shares'] * p['avg_price'] for p in positions)
            
            win_trades = len([t for t in trades if self._is_winning_trade(t)])
            total_trades = len(trades)
            win_rate = win_trades / total_trades if total_trades > 0 else 0
            
            drawdown = await self._calculate_drawdown()
            
            sharpe = await self._calculate_portfolio_sharpe()
            
            avg_latency = np.mean([t.get('execution_latency_ms', 0) for t in trades]) if trades else 0
            
            metrics = {
                "id": f"metrics_{int(datetime.now(timezone.utc).timestamp())}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_capital": total_capital,
                "deployed_capital": deployed,
                "total_pnl": total_pnl,
                "realized_pnl": total_realized_pnl,
                "unrealized_pnl": total_unrealized_pnl,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe,
                "max_drawdown": drawdown,
                "num_trades": total_trades,
                "num_positions": len(positions),
                "avg_execution_latency_ms": avg_latency
            }
            
            await self.db.performance_metrics.insert_one(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {}
    
    def _is_winning_trade(self, trade: Dict) -> bool:
        """Check if trade was profitable"""
        return trade.get('price', 0) > trade.get('avg_cost', trade.get('price', 0))
    
    async def _calculate_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        try:
            cursor = self.db.performance_metrics.find(
                {},
                {"total_capital": 1, "_id": 0}
            ).sort("timestamp", 1).limit(1000)
            
            docs = await cursor.to_list(length=1000)
            capitals = [doc['total_capital'] for doc in docs]
            
            if len(capitals) < 2:
                return 0.0
            
            peak = capitals[0]
            max_dd = 0.0
            
            for capital in capitals:
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
            
            return max_dd
            
        except Exception as e:
            logger.error(f"Error calculating drawdown: {e}")
            return 0.0
    
    async def _calculate_portfolio_sharpe(self) -> float:
        """Calculate portfolio Sharpe ratio"""
        try:
            cursor = self.db.performance_metrics.find(
                {},
                {"total_pnl": 1, "_id": 0}
            ).sort("timestamp", 1).limit(100)
            
            docs = await cursor.to_list(length=100)
            
            if len(docs) < 10:
                return 0.0
            
            returns = []
            for i in range(1, len(docs)):
                ret = (docs[i]['total_pnl'] - docs[i-1]['total_pnl']) / config.INITIAL_CAPITAL
                returns.append(ret)
            
            if len(returns) < 2:
                return 0.0
            
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            
            sharpe = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0
            
            return sharpe
            
        except Exception as e:
            logger.error(f"Error calculating Sharpe: {e}")
            return 0.0