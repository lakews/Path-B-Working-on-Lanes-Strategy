import asyncio
import logging
from typing import Dict, List
from datetime import datetime, timezone
from database import get_db
from services.market_data_service import MarketDataService
from data.historical_collector import HistoricalDataCollector
from ml.sharp_detector import SharpDetector
from strategies.delta_neutral import DeltaNeutralStrategy
from strategies.volatility_exploitation import VolatilityExploitationStrategy
from strategies.alpha_directional import AlphaDirectionalStrategy
from trading.position_manager import PositionManager
from trading.risk_controller import RiskController
from config import config

logger = logging.getLogger(__name__)

class ApexTrader:
    """Main APEX TRADER orchestrator
    Coordinates all AI modules, strategies, and execution
    """
    
    def __init__(self):
        self.db = get_db()
        self.market_data_service = MarketDataService()
        self.historical_collector = HistoricalDataCollector()
        self.sharp_detector = SharpDetector()
        
        self.delta_neutral_strategy = DeltaNeutralStrategy()
        self.volatility_strategy = VolatilityExploitationStrategy()
        self.alpha_strategy = AlphaDirectionalStrategy()
        
        self.position_mgr = PositionManager()
        self.risk_ctrl = RiskController()
        
        self.running = False
        self.trade_interval = config.TRADE_INTERVAL_SECONDS
        
    async def start(self):
        """Start APEX TRADER system"""
        try:
            self.running = True
            logger.info("Starting APEX TRADER...")
            
            await asyncio.gather(
                self._trading_loop(),
                self._monitoring_loop(),
                self._sharp_detection_loop(),
                self.historical_collector.start_collection()
            )
            
        except Exception as e:
            logger.error(f"Error starting APEX TRADER: {e}")
            raise
    
    async def stop(self):
        """Stop APEX TRADER system"""
        self.running = False
        await self.historical_collector.stop_collection()
        logger.info("APEX TRADER stopped")
    
    async def _trading_loop(self):
        """Main trading loop - executes strategies"""
        logger.info(f"Trading loop started. Target: {config.TRADES_PER_10MIN} trades/10min")
        
        while self.running:
            try:
                markets = await self._get_active_markets()
                
                for market_data in markets:
                    await self._evaluate_and_trade(market_data)
                    
                    await asyncio.sleep(self.trade_interval)
                
                if not markets:
                    await asyncio.sleep(5)
                    
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(5)
    
    async def _evaluate_and_trade(self, market_data: Dict):
        """Evaluate market and execute appropriate strategy"""
        try:
            market_id = market_data.get('id')
            
            existing_position = await self.position_mgr.get_position(market_id)
            
            if existing_position:
                await self._manage_existing_position(existing_position, market_data)
                return
            
            result = await self.volatility_strategy.execute_strategy(market_data)
            if result:
                logger.info(f"Volatility trade executed: {market_id}")
                return
            
            result = await self.alpha_strategy.execute_strategy(market_data)
            if result:
                logger.info(f"Alpha-directional trade executed: {market_id}")
                return
            
            result = await self.delta_neutral_strategy.execute_strategy(market_data)
            if result:
                logger.info(f"Delta-neutral trade executed: {market_id}")
                return
                
        except Exception as e:
            logger.error(f"Error evaluating market: {e}")
    
    async def _manage_existing_position(self, position: Dict, market_data: Dict):
        """Manage existing position - check for exit conditions"""
        try:
            current_price = market_data.get('yes_price', 0.5)
            entry_price = position['avg_price']
            
            profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            
            should_exit = False
            
            if profit_pct > 0.50:
                should_exit = True
                logger.info(f"Exiting position - target profit reached: {profit_pct:.2%}")
            
            elif profit_pct < -0.20:
                should_exit = True
                logger.info(f"Exiting position - stop loss: {profit_pct:.2%}")
            
            if should_exit:
                pnl = await self.position_mgr.close_position(position['id'], current_price)
                logger.info(f"Position closed with PnL: ${pnl:.2f}")
                
        except Exception as e:
            logger.error(f"Error managing position: {e}")
    
    async def _monitoring_loop(self):
        """Monitor performance and update metrics"""
        while self.running:
            try:
                metrics = await self.risk_ctrl.calculate_current_metrics()
                
                logger.info(
                    f"Performance: Capital=${metrics.get('total_capital', 0):.2f}, "
                    f"PnL=${metrics.get('total_pnl', 0):.2f}, "
                    f"Win Rate={metrics.get('win_rate', 0):.2%}, "
                    f"Sharpe={metrics.get('sharpe_ratio', 0):.2f}"
                )
                
                positions = await self.position_mgr.get_all_positions()
                if positions:
                    markets = await self._get_active_markets()
                    market_prices = {
                        m['id']: m.get('yes_price', 0.5) 
                        for m in markets
                    }
                    await self.position_mgr.update_positions(market_prices)
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(30)
    
    async def _sharp_detection_loop(self):
        """Periodic sharp trader identification"""
        while self.running:
            try:
                await self.sharp_detector.identify_sharp_traders()
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in sharp detection: {e}")
                await asyncio.sleep(300)
    
    async def _get_active_markets(self) -> List[Dict]:
        """Get active markets from database"""
        try:
            cursor = self.db.markets.find(
                {"liquidity": {"$gte": 1000}},
                {"_id": 0}
            ).limit(100)
            
            return await cursor.to_list(length=100)
            
        except Exception as e:
            logger.error(f"Error getting active markets: {e}")
            return []