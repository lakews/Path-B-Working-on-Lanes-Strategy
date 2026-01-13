import logging
from typing import Dict, List, Optional
import asyncio
from datetime import datetime, timezone
from database import get_db
from ml.signal_fusion import SignalFusionEngine
from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
from trading.execution_engine import ExecutionEngine
from trading.position_manager import PositionManager
from trading.risk_controller import RiskController
from trading.spread_calibrator import SpreadCalibrator
from models import OrderSide, StrategyType
from config import config

logger = logging.getLogger(__name__)

class DeltaNeutralStrategy:
    """Delta-neutral market making strategy
    Default mode: Zero directional exposure, capture spreads
    """
    
    def __init__(self):
        self.db = get_db()
        self.signal_fusion = SignalFusionEngine()
        self.kelly_optimizer = KellySharpeOptimizer()
        self.execution = ExecutionEngine()
        self.position_mgr = PositionManager()
        self.risk_ctrl = RiskController()
        self.hedge_ratio = 0.80
        self.target_spread = 0.02
        
    async def execute_strategy(self, market_data: Dict) -> Optional[Dict]:
        """Execute delta-neutral strategy
        Simultaneously buy and sell to capture spread
        """
        try:
            market_id = market_data.get('id')
            yes_price = market_data.get('yes_price', 0.5)
            no_price = market_data.get('no_price', 0.5)
            
            spread = abs(yes_price + no_price - 1.0)
            
            if spread < self.target_spread:
                return None
            
            signal = await self.signal_fusion.generate_trading_signal(market_data)
            
            if signal['confidence'] < 0.4:
                return None
            
            position_size, kelly_pct = await self.kelly_optimizer.calculate_position_size(
                market_data,
                signal['confidence'],
                0.55
            )
            
            if position_size < 10:
                return None
            
            shares = position_size / yes_price
            hedge_shares = shares * self.hedge_ratio
            
            approved, reason = await self.risk_ctrl.check_trade_approval(
                market_id,
                position_size,
                signal['confidence']
            )
            
            if not approved:
                logger.info(f"Trade rejected: {reason}")
                return None
            
            yes_result = await self.execution.execute_order(
                market_id=market_id,
                side=OrderSide.BUY,
                price=yes_price,
                shares=shares,
                strategy=StrategyType.DELTA_NEUTRAL
            )
            
            if yes_result['status'] == 'FILLED':
                no_result = await self.execution.execute_order(
                    market_id=market_id,
                    side=OrderSide.SELL,
                    price=no_price,
                    shares=hedge_shares,
                    strategy=StrategyType.DELTA_NEUTRAL
                )
                
                await self.position_mgr.open_position(
                    market_id=market_id,
                    side=OrderSide.BUY,
                    shares=shares,
                    price=yes_price,
                    strategy=StrategyType.DELTA_NEUTRAL
                )
                
                logger.info(f"Delta-neutral position opened: {market_id}")
                
                return {
                    "strategy": "delta_neutral",
                    "yes_trade": yes_result,
                    "no_trade": no_result,
                    "spread_captured": spread
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing delta-neutral strategy: {e}")
            return None