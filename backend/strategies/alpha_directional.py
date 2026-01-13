import logging
from typing import Dict, Optional
from database import get_db
from ml.signal_fusion import SignalFusionEngine
from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
from trading.execution_engine import ExecutionEngine
from trading.position_manager import PositionManager
from trading.risk_controller import RiskController
from models import OrderSide, StrategyType

logger = logging.getLogger(__name__)

class AlphaDirectionalStrategy:
    """Alpha-directional strategy with directional exposure
    Activated when confidence > 0.7
    Target: Capture 30-100x multipliers on reversals
    """
    
    def __init__(self):
        self.db = get_db()
        self.signal_fusion = SignalFusionEngine()
        self.kelly_optimizer = KellySharpeOptimizer()
        self.execution = ExecutionEngine()
        self.position_mgr = PositionManager()
        self.risk_ctrl = RiskController()
        self.confidence_threshold = 0.70
        self.max_directional_allocation = 0.80
        
    async def execute_strategy(self, market_data: Dict) -> Optional[Dict]:
        """Execute alpha-directional strategy
        Take deliberate directional exposure based on strong signals
        """
        try:
            market_id = market_data.get('id')
            yes_price = market_data.get('yes_price', 0.5)
            
            signal = await self.signal_fusion.generate_trading_signal(market_data)
            
            if signal['confidence'] < self.confidence_threshold:
                return None
            
            if signal['recommended_action'] == 'WAIT':
                return None
            
            bayesian_posterior = signal.get('bayesian_posterior', 0.5)
            
            position_size, kelly_pct = await self.kelly_optimizer.calculate_position_size(
                market_data,
                signal['confidence'],
                bayesian_posterior
            )
            
            directional_size = position_size * self.max_directional_allocation
            
            if directional_size < 15:
                return None
            
            side = OrderSide.BUY if signal['position_direction'] == 'YES' else OrderSide.SELL
            shares = directional_size / yes_price if yes_price > 0 else 0
            
            approved, reason = await self.risk_ctrl.check_trade_approval(
                market_id,
                directional_size,
                signal['confidence']
            )
            
            if not approved:
                logger.info(f"Alpha-directional trade rejected: {reason}")
                return None
            
            result = await self.execution.execute_order(
                market_id=market_id,
                side=side,
                price=yes_price,
                shares=shares,
                strategy=StrategyType.ALPHA_DIRECTIONAL
            )
            
            if result['status'] == 'FILLED':
                await self.position_mgr.open_position(
                    market_id=market_id,
                    side=side,
                    shares=shares,
                    price=yes_price,
                    strategy=StrategyType.ALPHA_DIRECTIONAL
                )
                
                logger.info(f"Alpha-directional position: {market_id} {side} @ ${yes_price:.3f}")
                
                return {
                    "strategy": "alpha_directional",
                    "trade": result,
                    "confidence": signal['confidence'],
                    "bayesian_posterior": bayesian_posterior,
                    "directional_allocation": self.max_directional_allocation
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing alpha-directional strategy: {e}")
            return None