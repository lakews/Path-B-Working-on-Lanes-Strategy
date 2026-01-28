import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from database import get_db
from services.market_data_service import MarketDataService
from data.historical_collector import HistoricalDataCollector
from ml.sharp_detector import SharpDetector
from ml.rl_engine import RLAdaptiveEngine
from ml.volatility_predictor import VolatilityPredictor
from ml.signal_fusion import SignalFusionEngine
from strategies.delta_neutral import DeltaNeutralStrategy
from strategies.volatility_exploitation import VolatilityExploitationStrategy
from strategies.alpha_directional import AlphaDirectionalStrategy
from strategies.arbitrage import MultiMarketArbitrageStrategy
from trading.position_manager import PositionManager
from trading.risk_controller import RiskController
from config import config

logger = logging.getLogger(__name__)

class ApexTrader:
    """Main APEX TRADER orchestrator with full RL integration
    Coordinates all AI modules, strategies, and execution
    """
    
    def __init__(self, paper_mode: bool = False):
        self.db = get_db()
        self.market_data_service = MarketDataService()
        self.historical_collector = HistoricalDataCollector()
        self.sharp_detector = SharpDetector()
        
        # ML Engines
        self.rl_engine = RLAdaptiveEngine()
        self.volatility_predictor = VolatilityPredictor()
        self.signal_fusion = SignalFusionEngine()
        
        # Trading Strategies
        self.delta_neutral_strategy = DeltaNeutralStrategy()
        self.volatility_strategy = VolatilityExploitationStrategy()
        self.alpha_strategy = AlphaDirectionalStrategy()
        self.arbitrage_strategy = MultiMarketArbitrageStrategy()
        
        self.position_mgr = PositionManager()
        self.risk_ctrl = RiskController()
        
        self.running = False
        self.paper_mode = paper_mode
        self.trade_interval = config.TRADE_INTERVAL_SECONDS
        
        # Performance tracking for RL feedback
        self.pending_trades: Dict[str, Dict] = {}  # market_id -> trade info
        
        logger.info(f"ApexTrader initialized - Paper Mode: {paper_mode}")
        
    async def start(self):
        """Start APEX TRADER system"""
        try:
            self.running = True
            mode_str = "PAPER" if self.paper_mode else "LIVE"
            logger.info(f"Starting APEX TRADER in {mode_str} mode...")
            
            # Load RL model
            await self.rl_engine.load_model()
            
            await asyncio.gather(
                self._trading_loop(),
                self._monitoring_loop(),
                self._sharp_detection_loop(),
                self._rl_learning_loop(),
                self.historical_collector.start_collection()
            )
            
        except Exception as e:
            logger.error(f"Error starting APEX TRADER: {e}")
            raise
    
    async def stop(self):
        """Stop APEX TRADER system"""
        self.running = False
        await self.historical_collector.stop_collection()
        
        # Save RL model on stop
        await self.rl_engine.save_model()
        
        logger.info("APEX TRADER stopped")
    
    async def _trading_loop(self):
        """Main trading loop - executes strategies with RL guidance"""
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
        """Evaluate market and execute appropriate strategy with RL input"""
        try:
            market_id = market_data.get('id')
            
            # Check existing position
            existing_position = await self.position_mgr.get_position(market_id)
            
            if existing_position:
                await self._manage_existing_position(existing_position, market_data)
                return
            
            # Get ML signals
            signals = await self._get_ml_signals(market_data)
            
            # Get RL recommendation
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            # Skip if RL says wait or low confidence
            if rl_action == 'WAIT' or rl_confidence < 0.35:
                return
            
            # Get strategy confidence from RL
            strategy_confidences = await self._get_strategy_confidences(market_data, signals)
            
            # Execute best strategy based on RL guidance
            result = None
            best_strategy = max(strategy_confidences, key=strategy_confidences.get)
            
            if best_strategy == 'volatility_exploitation' and strategy_confidences[best_strategy] > 0.4:
                result = await self._execute_with_rl(
                    self.volatility_strategy, market_data, signals, rl_action, rl_confidence
                )
                if result:
                    logger.info(f"Volatility trade executed: {market_id} (RL: {rl_action}, conf: {rl_confidence:.2f})")
                    return
            
            if best_strategy == 'alpha_directional' and strategy_confidences[best_strategy] > 0.4:
                result = await self._execute_with_rl(
                    self.alpha_strategy, market_data, signals, rl_action, rl_confidence
                )
                if result:
                    logger.info(f"Alpha-directional trade executed: {market_id} (RL: {rl_action})")
                    return
            
            if best_strategy == 'arbitrage' and strategy_confidences[best_strategy] > 0.4:
                result = await self._execute_with_rl(
                    self.arbitrage_strategy, market_data, signals, rl_action, rl_confidence
                )
                if result:
                    logger.info(f"Arbitrage trade executed: {market_id}")
                    return
            
            if best_strategy == 'delta_neutral' and strategy_confidences[best_strategy] > 0.4:
                result = await self._execute_with_rl(
                    self.delta_neutral_strategy, market_data, signals, rl_action, rl_confidence
                )
                if result:
                    logger.info(f"Delta-neutral trade executed: {market_id}")
                    return
                    
        except Exception as e:
            logger.error(f"Error evaluating market: {e}")
    
    async def _execute_with_rl(self, strategy, market_data: Dict, signals: Dict, 
                               rl_action: str, rl_confidence: float) -> Optional[Dict]:
        """Execute strategy with RL-informed position sizing"""
        try:
            market_id = market_data.get('id')
            
            # STRICT PRICE VALIDATION - Reject trades without valid price data
            yes_price = market_data.get('yes_price')
            if yes_price is None or yes_price == 0:
                logger.warning(f"[RL-REJECT] Missing price data for {market_id[:16] if market_id else 'unknown'} - skipping trade")
                return None
            yes_price = float(yes_price)
            
            if self.paper_mode:
                # Paper mode - simulate execution
                result = await strategy.evaluate_opportunity(market_data)
                if result and result.get('should_trade'):
                    # Record pending trade for RL feedback
                    self.pending_trades[market_id] = {
                        'entry_price': yes_price,
                        'entry_time': datetime.now(timezone.utc).isoformat(),
                        'strategy': strategy.__class__.__name__,
                        'rl_action': rl_action,
                        'rl_confidence': rl_confidence,
                        'signals': signals
                    }
                    
                    # Log paper trade
                    await self.db.paper_trades.insert_one({
                        "market_id": market_id,
                        "type": "entry",
                        "strategy": strategy.__class__.__name__,
                        "rl_action": rl_action,
                        "rl_confidence": rl_confidence,
                        "price": yes_price,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "paper_mode": True
                    })
                    
                    return result
            else:
                # Live mode - actual execution
                result = await strategy.execute_strategy(market_data)
                if result:
                    # Record for RL feedback
                    self.pending_trades[market_id] = {
                        'entry_price': yes_price,
                        'entry_time': datetime.now(timezone.utc).isoformat(),
                        'strategy': strategy.__class__.__name__,
                        'rl_action': rl_action,
                        'rl_confidence': rl_confidence
                    }
                return result
                
        except Exception as e:
            logger.error(f"Error executing with RL: {e}")
            return None
    
    async def _get_ml_signals(self, market_data: Dict) -> Dict:
        """Aggregate ML signals for trading decision"""
        signals = {
            'volatility': 0.02,
            'sentiment': 0.5,
            'sharp_alignment': 0.5,
            'whale_activity': 0.0
        }
        
        try:
            # Volatility prediction
            vol_pred = await self.volatility_predictor.predict(market_data)
            signals['volatility'] = vol_pred.get('predicted_volatility', 0.02)
        except Exception as e:
            logger.debug(f"Volatility prediction error: {e}")
        
        try:
            # Signal fusion (sentiment + other signals)
            fused = await self.signal_fusion.get_fused_signal(market_data.get('id'), market_data)
            signals['sentiment'] = fused.get('sentiment', 0.5)
        except Exception as e:
            logger.debug(f"Signal fusion error: {e}")
        
        try:
            # Sharp trader alignment
            sharp = await self.sharp_detector.get_alignment_signal(market_data.get('id'))
            signals['sharp_alignment'] = sharp.get('alignment_score', 0.5)
        except Exception as e:
            logger.debug(f"Sharp detection error: {e}")
        
        return signals
    
    async def _get_strategy_confidences(self, market_data: Dict, signals: Dict) -> Dict[str, float]:
        """Get RL-based confidence for each strategy"""
        confidences = {}
        
        for strategy_name in ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']:
            try:
                conf = await self.rl_engine.get_strategy_confidence(strategy_name, market_data)
                confidences[strategy_name] = conf
            except:
                confidences[strategy_name] = 0.25  # Default equal weight
        
        return confidences
    
    async def _manage_existing_position(self, position: Dict, market_data: Dict):
        """Manage existing position with RL-guided exit decisions"""
        try:
            # STRICT PRICE VALIDATION - Cannot manage position without valid price
            current_price = market_data.get('yes_price')
            if current_price is None or current_price == 0:
                logger.warning(f"[POSITION-SKIP] Missing price data for position management - skipping")
                return
            current_price = float(current_price)
            entry_price = position['avg_price']
            market_id = market_data.get('id')
            side = position.get('side', 'YES')
            
            # =================================================================
            # SIDE-AWARE P&L CALCULATION (Critical Fix - Jan 2026)
            # =================================================================
            if side.upper() == 'YES':
                profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            else:
                # NO position: profits when YES price falls
                no_entry = 1 - entry_price
                no_current = 1 - current_price
                profit_pct = (no_current - no_entry) / no_entry if no_entry > 0 else 0
            
            # Get RL exit recommendation
            signals = await self._get_ml_signals(market_data)
            rl_action, rl_confidence = await self.rl_engine.get_optimal_action(market_data, signals)
            
            should_exit = False
            exit_reason = None
            
            # Target profit reached
            if profit_pct > 0.50:
                should_exit = True
                exit_reason = "target_profit"
                logger.info(f"Exiting position - target profit reached: {profit_pct:.2%}")
            
            # Stop loss
            elif profit_pct < -0.20:
                should_exit = True
                exit_reason = "stop_loss"
                logger.info(f"Exiting position - stop loss: {profit_pct:.2%}")
            
            # RL recommends exit with high confidence
            elif 'SELL' in rl_action and rl_confidence > 0.7:
                should_exit = True
                exit_reason = "rl_exit_signal"
                logger.info(f"Exiting position - RL signal: {rl_action} ({rl_confidence:.2f})")
            
            if should_exit:
                # Calculate reward for RL
                reward = self._calculate_trade_reward(profit_pct, exit_reason)
                
                # Feed reward to RL engine
                await self.rl_engine.update_from_reward(market_id, reward)
                
                # Close position
                if not self.paper_mode:
                    pnl = await self.position_mgr.close_position(position['id'], current_price)
                    logger.info(f"Position closed with PnL: ${pnl:.2f}")
                else:
                    # Paper mode - log the exit
                    await self.db.paper_trades.insert_one({
                        "market_id": market_id,
                        "type": "exit",
                        "exit_reason": exit_reason,
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": profit_pct,
                        "rl_reward": reward,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "paper_mode": True
                    })
                
                # Remove from pending trades
                if market_id in self.pending_trades:
                    del self.pending_trades[market_id]
                
        except Exception as e:
            logger.error(f"Error managing position: {e}")
    
    def _calculate_trade_reward(self, pnl_pct: float, exit_reason: str) -> float:
        """Calculate reward signal for RL based on trade outcome"""
        import numpy as np
        
        # Base reward from P&L
        reward = pnl_pct * 10
        
        # Bonuses/penalties based on exit reason
        if exit_reason == "target_profit":
            reward += 0.5
        elif exit_reason == "stop_loss":
            reward -= 0.2
        elif exit_reason == "rl_exit_signal":
            reward += 0.3 if pnl_pct > 0 else -0.1
        
        return np.clip(reward, -2.0, 2.0)
    
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
                    # STRICT PRICE VALIDATION - Only include markets with valid prices
                    market_prices = {
                        m['id']: float(m['yes_price']) 
                        for m in markets
                        if m.get('yes_price') is not None and m.get('yes_price') != 0
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
    
    async def _rl_learning_loop(self):
        """Periodic RL learning from experience replay"""
        while self.running:
            try:
                # Train from replay buffer
                await self.rl_engine.train_from_replay()
                
                # Periodically save model
                await self.rl_engine.save_model()
                
                logger.info("RL model trained and saved")
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in RL learning loop: {e}")
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
