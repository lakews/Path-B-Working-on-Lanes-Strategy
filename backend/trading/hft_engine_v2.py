"""
HFT ENGINE V2 - HIGH-FREQUENCY TRADING ENGINE
==============================================

Implements 5 HFT sub-strategies with PATH A/B signal integration:
1. Delta-Neutral Market Making (35% allocation)
2. Volatility Exploitation (10% allocation)
3. Extreme Spread Capture (15% allocation)
4. Sharp Trader Following (20% allocation)
5. Liquidity Provision (20% allocation)

MongoDB-Only Architecture:
- Reads PATH B (hft_opportunities) for speed/market context
- Reads PATH A (signals) for intelligence/bayes_factor

CRITICAL CONSTRAINTS (MUST RESPECT):
- Kelly Criterion (0.25 fractional sizing)
- 3% max position cap
- Never bypass existing capital management
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from trading.hft_config import (
    HFTConfig, HFTMode, NewsStrength,
    get_news_strength, get_multipliers, get_price_zone
)

logger = logging.getLogger(__name__)


class HighFrequencyTradingEngine:
    """
    HFT Engine V2 - 5 Sub-Strategy Implementation
    
    Features:
    - Operates in 5 distinct trading modes
    - Reads news signals from MongoDB (PATH A for intelligence, PATH B for speed)
    - Dynamically adjusts spreads/positions based on news strength
    - Integrates seamlessly with existing infrastructure
    - Respects ALL constraints (Kelly, 3% cap, capital limits)
    """
    
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Initialize HFT Engine with injected dependencies.
        
        Args:
            dependencies: Dict containing:
                - db: MongoDB database connection
                - market_data_svc: Market data service
                - paper_trader: Paper trading instance
                - position_manager: Position management
                - kelly_optimizer: Kelly criterion optimizer (optional)
                - spread_calibrator: Spread calculation (optional)
                - volatility_predictor: Volatility prediction (optional)
                - sharp_detector: Sharp trader detection (optional)
                - performance_analytics: Analytics logging (optional)
        """
        # Required dependencies
        self.db = dependencies.get('db')
        self.market_data_svc = dependencies.get('market_data_svc')
        self.paper_trader = dependencies.get('paper_trader')
        self.position_manager = dependencies.get('position_manager')
        
        # Optional dependencies (graceful degradation)
        self.kelly_optimizer = dependencies.get('kelly_optimizer')
        self.spread_calibrator = dependencies.get('spread_calibrator')
        self.volatility_predictor = dependencies.get('volatility_predictor')
        self.sharp_detector = dependencies.get('sharp_detector')
        self.performance_analytics = dependencies.get('performance_analytics')
        
        # Engine state
        self._running = False
        self._last_cycle_time = None
        
        # Statistics
        self.stats = {
            'cycles_executed': 0,
            'trades_executed': 0,
            'trades_by_mode': {mode.value: 0 for mode in HFTMode},
            'paused_cycles': 0,
            'path_a_hits': 0,
            'path_b_hits': 0,
            'total_pnl': 0.0,
            'errors': 0
        }
        
        logger.info("[HFT V2] Engine initialized with MongoDB signal integration")
    
    async def start_hft_loop(self):
        """
        Main HFT background loop.
        Runs continuously, executing HFT strategies every 500ms.
        """
        logger.info("[HFT V2] Starting continuous HFT loop...")
        self._running = True
        
        while self._running:
            try:
                cycle_start = time.time()
                
                # Get active markets
                markets = await self._get_active_markets()
                
                if markets:
                    # Process each market
                    for market in markets[:50]:  # Limit to top 50 for speed
                        try:
                            await self.execute_hft_scalp(market)
                        except Exception as e:
                            logger.debug(f"[HFT V2] Market error: {e}")
                            continue
                
                self.stats['cycles_executed'] += 1
                
                # Calculate cycle time and sleep
                cycle_time_ms = (time.time() - cycle_start) * 1000
                self._last_cycle_time = cycle_time_ms
                
                # Target 500ms cycles
                sleep_time = max(0.1, (500 - cycle_time_ms) / 1000)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("[HFT V2] Loop cancelled")
                break
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"[HFT V2] Loop error: {e}", exc_info=True)
                await asyncio.sleep(1.0)
        
        logger.info("[HFT V2] HFT loop stopped")
    
    async def stop(self):
        """Stop the HFT engine"""
        self._running = False
        logger.info("[HFT V2] Stop requested")
    
    async def execute_hft_scalp(self, market_data: Dict) -> Optional[Dict]:
        """
        Main entry point for HFT execution on a single market.
        
        Flow:
        1. Check PATH B for fresh news broadcast (speed)
        2. If news exists, get PATH A analysis (intelligence)
        3. Classify news strength and get multipliers
        4. If PAUSE mode, skip cycle
        5. Select appropriate HFT mode based on price zone
        6. Build trade parameters (respecting constraints)
        7. Execute via paper_trader
        8. Log to analytics
        
        Args:
            market_data: Market data dict with id, price, volume, etc.
            
        Returns:
            Trade result dict or None if no trade
        """
        try:
            market_id = market_data.get('id', market_data.get('condition_id', ''))
            if not market_id:
                return None
            
            # Get current price
            yes_price = float(market_data.get('yes_price', market_data.get('price', 0.5)))
            
            # STEP 1: Check PATH B for fresh news broadcast (speed check)
            has_news, opportunity = await self._check_path_b_opportunity(market_id)
            
            # STEP 2: Get PATH A analysis for intelligence (bayes_factor)
            signal = None
            bayes_factor = 0.0
            if has_news:
                signal = await self._read_path_a_signal(market_id)
                if signal:
                    bayes_factor = signal.get('bayes_factor', 0.0)
                    self.stats['path_a_hits'] += 1
            
            # STEP 3: Classify news strength and get multipliers
            news_strength = get_news_strength(bayes_factor)
            multipliers = get_multipliers(news_strength)
            
            # STEP 4: If PAUSE mode, skip entire cycle
            if news_strength == NewsStrength.PAUSE:
                self.stats['paused_cycles'] += 1
                logger.debug(f"[HFT V2] PAUSE: {market_id[:16]}... BF={bayes_factor:.1f}")
                return None
            
            # STEP 5: Select HFT mode based on price zone and conditions
            hft_mode = await self._select_hft_mode(market_id, market_data, yes_price)
            
            if not hft_mode:
                return None
            
            # STEP 6: Build trade parameters (respecting ALL constraints)
            trade_params = await self._build_trade_params(
                hft_mode=hft_mode,
                market_id=market_id,
                market_data=market_data,
                multipliers=multipliers,
                signal=signal
            )
            
            if not trade_params:
                return None
            
            # STEP 7: Execute via appropriate strategy method
            result = await self._execute_strategy(
                hft_mode=hft_mode,
                market_id=market_id,
                market_data=market_data,
                trade_params=trade_params,
                signal=signal
            )
            
            if result and result.get('success'):
                self.stats['trades_executed'] += 1
                self.stats['trades_by_mode'][hft_mode.value] += 1
                
                # STEP 8: Log to analytics
                await self._log_hft_trade(
                    market_id=market_id,
                    hft_mode=hft_mode,
                    trade_params=trade_params,
                    result=result,
                    bayes_factor=bayes_factor,
                    news_strength=news_strength
                )
            
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[HFT V2] Execute error: {e}")
            return None
    
    async def _check_path_b_opportunity(self, market_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check PATH B (hft_opportunities) for fresh news broadcast.
        
        PATH B provides:
        - Speed (10s TTL, fast lookup)
        - Market context (price, volume, liquidity)
        - News headline + urgency
        
        Returns:
            Tuple of (has_news: bool, opportunity: Dict or None)
        """
        try:
            if self.db is None:
                return False, None
            
            opportunity = await self.db.hft_opportunities.find_one(
                {
                    'market_id': market_id,
                    'type': 'path_b',
                    'expires_at': {'$gt': datetime.now(timezone.utc)}
                },
                {'_id': 0}
            )
            
            if opportunity:
                self.stats['path_b_hits'] += 1
                return True, opportunity
            
            return False, None
            
        except Exception as e:
            logger.debug(f"[HFT V2] PATH B check error: {e}")
            return False, None
    
    async def _read_path_a_signal(self, market_id: str) -> Optional[Dict]:
        """
        Read PATH A signal from MongoDB signals collection.
        
        PATH A provides:
        - Intelligence (LLM-analyzed)
        - bayes_factor (for news strength classification)
        - direction (YES/NO)
        - confidence
        - impact_level
        
        Returns:
            Signal dict or None if not found/expired
        """
        try:
            if self.db is None:
                return None
            
            signal = await self.db.signals.find_one(
                {
                    'market_id': market_id,
                    'type': 'path_a',
                    'expires_at': {'$gt': datetime.now(timezone.utc)}
                },
                {'_id': 0},
                sort=[('timestamp', -1)]
            )
            
            return signal
            
        except Exception as e:
            logger.debug(f"[HFT V2] PATH A read error: {e}")
            return None
    
    async def _select_hft_mode(
        self, market_id: str, market_data: Dict, price: float
    ) -> Optional[HFTMode]:
        """
        Select the appropriate HFT mode based on market conditions.
        
        Logic:
        - Extreme prices (0-0.10 or 0.90-1.0) → Volatility or Extreme Spread
        - Standard prices (0.10-0.90) → Delta Neutral, Sharp Following, or Liquidity
        - High volume markets → Liquidity Provision
        - Sharp activity detected → Sharp Following
        
        Returns:
            HFTMode enum or None if no suitable mode
        """
        try:
            zone = get_price_zone(price)
            volume_24h = float(market_data.get('volume_24h', market_data.get('volume', 0)) or 0)
            
            # EXTREME ZONES: Volatility exploitation or extreme spread
            if zone in ['extreme_low', 'extreme_high']:
                # Check volatility score
                vol_score = market_data.get('volatility', 0.5)
                
                if vol_score >= HFTConfig.VOLATILITY_MIN_SCORE:
                    return HFTMode.VOLATILITY_EXPLOIT
                else:
                    return HFTMode.EXTREME_SPREAD
            
            # STANDARD ZONE: Multiple strategies possible
            
            # Check for sharp trader activity first (highest priority in standard zone)
            if self.sharp_detector:
                try:
                    is_sharp = await self._check_sharp_activity(market_id)
                    if is_sharp:
                        return HFTMode.SHARP_FOLLOWING
                except Exception:
                    pass
            
            # High volume → Liquidity provision
            if volume_24h >= HFTConfig.LIQUIDITY_MIN_VOLUME:
                return HFTMode.LIQUIDITY_PROVISION
            
            # Default: Delta-neutral market making
            return HFTMode.DELTA_NEUTRAL
            
        except Exception as e:
            logger.debug(f"[HFT V2] Mode selection error: {e}")
            return HFTMode.DELTA_NEUTRAL
    
    async def _check_sharp_activity(self, market_id: str) -> bool:
        """Check if there's significant sharp trader activity"""
        try:
            if not self.sharp_detector:
                return False
            
            # Check if sharp detector has method
            if hasattr(self.sharp_detector, 'is_sharp_active'):
                return await self.sharp_detector.is_sharp_active(market_id)
            elif hasattr(self.sharp_detector, 'detect_sharp_movement'):
                result = await self.sharp_detector.detect_sharp_movement(market_id)
                return result.get('z_score', 0) >= HFTConfig.SHARP_MIN_ZSCORE
            
            return False
        except Exception:
            return False
    
    async def _build_trade_params(
        self,
        hft_mode: HFTMode,
        market_id: str,
        market_data: Dict,
        multipliers: Dict[str, float],
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Build trade parameters respecting ALL constraints.
        
        Constraints:
        - Kelly Criterion (0.25 fractional sizing)
        - 3% max position cap
        - Available capital limits
        - Strategy-specific allocations
        
        Returns:
            Trade params dict or None if constraints not met
        """
        try:
            # Get available capital
            available_capital = await self._get_available_capital()
            if available_capital <= 0:
                return None
            
            # Get HFT lane allocation (35% of total)
            hft_capital = available_capital * HFTConfig.HFT_LANE_ALLOCATION
            
            # Get strategy-specific allocation
            strategy_allocation = HFTConfig.SUB_STRATEGY_ALLOCATION.get(hft_mode.value, 0.20)
            base_capital = hft_capital * strategy_allocation
            
            # Apply Kelly criterion
            confidence = signal.get('confidence', 0.65) if signal else 0.65
            kelly_sized = base_capital * HFTConfig.KELLY_FRACTION * confidence
            
            # Apply news multiplier
            position_mult = multipliers.get('position_mult', 1.0)
            adjusted_position = kelly_sized * position_mult
            
            # Enforce 3% max position cap
            initial_capital = getattr(self.paper_trader, 'INITIAL_CAPITAL', 10000)
            max_position = initial_capital * HFTConfig.MAX_POSITION_PCT
            final_position = min(adjusted_position, max_position)
            
            # Minimum position check
            if final_position < 5:  # $5 minimum
                return None
            
            # Get spread parameters
            spread_mult = multipliers.get('spread_mult', 1.0)
            base_spread = self._get_base_spread(hft_mode, market_data)
            adjusted_spread = base_spread * spread_mult
            
            # Get direction from signal or default
            direction = 'YES'
            if signal:
                direction = signal.get('direction', 'YES')
            
            return {
                'position_size': round(final_position, 2),
                'spread': adjusted_spread,
                'direction': direction,
                'confidence': confidence,
                'hft_mode': hft_mode.value,
                'spread_mult': spread_mult,
                'position_mult': position_mult
            }
            
        except Exception as e:
            logger.debug(f"[HFT V2] Build params error: {e}")
            return None
    
    def _get_base_spread(self, hft_mode: HFTMode, market_data: Dict) -> float:
        """Get base spread for the given HFT mode"""
        if hft_mode == HFTMode.DELTA_NEUTRAL:
            return HFTConfig.DELTA_NEUTRAL_BASE_SPREAD
        elif hft_mode == HFTMode.EXTREME_SPREAD:
            return HFTConfig.EXTREME_SPREAD_BASE * HFTConfig.EXTREME_SPREAD_MULTIPLIER
        elif hft_mode == HFTMode.LIQUIDITY_PROVISION:
            return HFTConfig.LIQUIDITY_BASE_SPREAD
        else:
            return 0.02  # Default 2%
    
    async def _get_available_capital(self) -> float:
        """Get available capital from position manager or paper trader"""
        try:
            if self.position_manager and hasattr(self.position_manager, 'get_available_capital'):
                return await self.position_manager.get_available_capital()
            elif self.paper_trader:
                if hasattr(self.paper_trader, 'current_capital'):
                    return self.paper_trader.current_capital
                elif hasattr(self.paper_trader, 'deployed_capital'):
                    return self.paper_trader.deployed_capital
            return 0
        except Exception:
            return 0
    
    async def _execute_strategy(
        self,
        hft_mode: HFTMode,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Execute the selected HFT strategy.
        
        Delegates to strategy-specific methods.
        """
        try:
            if hft_mode == HFTMode.DELTA_NEUTRAL:
                return await self._execute_delta_neutral(market_id, market_data, trade_params, signal)
            elif hft_mode == HFTMode.VOLATILITY_EXPLOIT:
                return await self._execute_volatility_exploit(market_id, market_data, trade_params, signal)
            elif hft_mode == HFTMode.EXTREME_SPREAD:
                return await self._execute_extreme_spread(market_id, market_data, trade_params, signal)
            elif hft_mode == HFTMode.SHARP_FOLLOWING:
                return await self._execute_sharp_following(market_id, market_data, trade_params, signal)
            elif hft_mode == HFTMode.LIQUIDITY_PROVISION:
                return await self._execute_liquidity_provision(market_id, market_data, trade_params, signal)
            else:
                return None
        except Exception as e:
            logger.error(f"[HFT V2] Strategy execution error: {e}")
            return None
    
    # =========================================================================
    # STRATEGY 1: DELTA-NEUTRAL MARKET MAKING (35% allocation)
    # =========================================================================
    async def _execute_delta_neutral(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Delta-Neutral Market Making
        
        Purpose: Quote YES bid/ask + NO bid/ask simultaneously, capture spreads
        Zone: Standard prices (0.10 - 0.90)
        Base Spread: 2% (via spread_calibrator if available)
        Target: 0.5-2% per trade
        """
        try:
            yes_price = float(market_data.get('yes_price', 0.5))
            spread = trade_params['spread']
            position_size = trade_params['position_size']
            
            # Calculate bid/ask prices (used for logging/future order placement)
            half_spread = spread / 2
            _ = max(0.001, yes_price - half_spread)  # yes_bid - for future order placement
            _ = min(0.999, yes_price + half_spread)  # yes_ask - for future order placement
            
            # Check if spread is profitable
            if self.spread_calibrator:
                try:
                    optimal = await self.spread_calibrator.calculate_optimal_spread(market_data)
                    if spread < optimal.get('optimal_spread', 0):
                        return None  # Spread too tight
                except Exception:
                    pass
            
            # Execute via paper_trader
            result = await self._execute_paper_trade(
                market_id=market_id,
                market_data=market_data,
                side='YES',  # Primary side
                size=position_size / 2,  # Split between YES and NO
                strategy='hft_delta_neutral',
                entry_price=yes_price
            )
            
            return result
            
        except Exception as e:
            logger.debug(f"[HFT V2] Delta-neutral error: {e}")
            return None
    
    # =========================================================================
    # STRATEGY 2: VOLATILITY EXPLOITATION (10% allocation)
    # =========================================================================
    async def _execute_volatility_exploit(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Volatility Exploitation
        
        Purpose: Buy at extreme prices betting on mean reversion
        Zone: 0.05-0.10 (low) or 0.90-0.99 (high)
        Frequency: 30-second assessment
        Target: 30-100x multipliers on winners
        """
        try:
            yes_price = float(market_data.get('yes_price', 0.5))
            position_size = trade_params['position_size']
            
            # Determine direction based on price zone
            if yes_price <= 0.10:
                # Low price → bet on YES (mean reversion up)
                direction = 'YES'
                side = 'YES'
                expected_value = yes_price + (0.20 * (1 - yes_price))
                
                # Check expected gain
                if expected_value <= yes_price * 1.5:
                    return None  # Not enough expected gain
                    
            elif yes_price >= 0.90:
                # High price → bet on NO (mean reversion down)
                side = 'NO'
                expected_value = (1 - yes_price) + (0.10 * yes_price)
                
                # Check expected gain
                if expected_value <= (1 - yes_price) * 1.3:
                    return None
            else:
                return None  # Not in extreme zone
            
            # Check volatility if predictor available
            if self.volatility_predictor:
                try:
                    vol_score = await self.volatility_predictor.predict(market_data)
                    if vol_score < HFTConfig.VOLATILITY_MIN_SCORE:
                        return None  # Volatility too low
                except Exception:
                    pass
            
            # Execute trade
            result = await self._execute_paper_trade(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=min(position_size, HFTConfig.VOLATILITY_BASE_POSITION * trade_params['position_mult']),
                strategy='hft_volatility_exploit',
                entry_price=yes_price if side == 'YES' else (1 - yes_price)
            )
            
            return result
            
        except Exception as e:
            logger.debug(f"[HFT V2] Volatility exploit error: {e}")
            return None
    
    # =========================================================================
    # STRATEGY 3: EXTREME SPREAD CAPTURE (15% allocation)
    # =========================================================================
    async def _execute_extreme_spread(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Extreme Spread Capture
        
        Purpose: Quote very wide spreads (5-15x normal) at price extremes
        Zone: 0.05-0.10 or 0.90-0.99
        Target: Compensate for volatility with wide spreads
        """
        try:
            yes_price = float(market_data.get('yes_price', 0.5))
            spread_mult = trade_params.get('spread_mult', 1.0)
            position_mult = trade_params.get('position_mult', 1.0)
            
            # Calculate extreme spread
            base_spread = HFTConfig.EXTREME_SPREAD_BASE
            extreme_multiplier = HFTConfig.EXTREME_SPREAD_MULTIPLIER * spread_mult
            adjusted_spread = min(base_spread * extreme_multiplier, HFTConfig.EXTREME_SPREAD_MAX)
            
            # Calculate bid/ask with clamping (for future order placement)
            half_spread = adjusted_spread / 2
            _ = max(0.001, yes_price - half_spread)  # yes_bid
            _ = min(0.999, yes_price + half_spread)  # yes_ask
            
            # Smaller position for risk management
            position_size = min(
                trade_params['position_size'],
                HFTConfig.EXTREME_SPREAD_BASE_POSITION * position_mult
            )
            
            if position_size < 5:
                return None
            
            # Execute trade
            result = await self._execute_paper_trade(
                market_id=market_id,
                market_data=market_data,
                side='YES',
                size=position_size,
                strategy='hft_extreme_spread',
                entry_price=yes_price
            )
            
            return result
            
        except Exception as e:
            logger.debug(f"[HFT V2] Extreme spread error: {e}")
            return None
    
    # =========================================================================
    # STRATEGY 4: SHARP TRADER FOLLOWING (20% allocation)
    # =========================================================================
    async def _execute_sharp_following(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Sharp Trader Following
        
        Purpose: Detect sharp traders, position 30-50% of their size
        Frequency: 75-100ms (faster than normal)
        Uses: Existing sharp_detector module
        """
        try:
            if not self.sharp_detector:
                return None
            
            # Get sharp activity
            sharp_activity = None
            if hasattr(self.sharp_detector, 'get_sharp_activity'):
                sharp_activity = await self.sharp_detector.get_sharp_activity(market_id)
            elif hasattr(self.sharp_detector, 'detect_sharp_movement'):
                sharp_activity = await self.sharp_detector.detect_sharp_movement(market_id)
            
            if not sharp_activity:
                return None
            
            z_score = sharp_activity.get('z_score', 0)
            if z_score < HFTConfig.SHARP_MIN_ZSCORE:
                return None  # Not significant
            
            sharp_direction = sharp_activity.get('direction', 'YES')
            sharp_size = sharp_activity.get('size', 100)
            
            # Follow at 50% scale
            our_size = min(
                sharp_size * HFTConfig.SHARP_FOLLOW_SCALE * trade_params.get('position_mult', 1.0),
                trade_params['position_size']
            )
            
            if our_size < 5:
                return None
            
            # Determine side
            side = sharp_direction
            yes_price = float(market_data.get('yes_price', 0.5))
            entry_price = yes_price if side == 'YES' else (1 - yes_price)
            
            # Execute trade
            result = await self._execute_paper_trade(
                market_id=market_id,
                market_data=market_data,
                side=side,
                size=our_size,
                strategy='hft_sharp_following',
                entry_price=entry_price
            )
            
            return result
            
        except Exception as e:
            logger.debug(f"[HFT V2] Sharp following error: {e}")
            return None
    
    # =========================================================================
    # STRATEGY 5: LIQUIDITY PROVISION (20% allocation)
    # =========================================================================
    async def _execute_liquidity_provision(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Liquidity Provision
        
        Purpose: Maintain standing quotes on high-volume markets
        Requirement: daily_volume > $50,000
        Target: 0.5-1% per trade, high frequency (100+ fills/day)
        """
        try:
            volume_24h = float(market_data.get('volume_24h', market_data.get('volume', 0)) or 0)
            
            # Only execute on high-liquidity markets
            if volume_24h < HFTConfig.LIQUIDITY_MIN_VOLUME:
                return None
            
            yes_price = float(market_data.get('yes_price', 0.5))
            spread_mult = trade_params.get('spread_mult', 1.0)
            position_mult = trade_params.get('position_mult', 1.0)
            
            # Tight spreads for high-volume (spread used for future order placement)
            _ = HFTConfig.LIQUIDITY_BASE_SPREAD * spread_mult  # base_spread
            size_per_level = HFTConfig.LIQUIDITY_SIZE_PER_LEVEL * position_mult
            
            # Execute at primary level only (simplified)
            result = await self._execute_paper_trade(
                market_id=market_id,
                market_data=market_data,
                side='YES',
                size=min(size_per_level, trade_params['position_size']),
                strategy='hft_liquidity_provision',
                entry_price=yes_price
            )
            
            return result
            
        except Exception as e:
            logger.debug(f"[HFT V2] Liquidity provision error: {e}")
            return None
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _execute_paper_trade(
        self,
        market_id: str,
        market_data: Dict,
        side: str,
        size: float,
        strategy: str,
        entry_price: float
    ) -> Optional[Dict]:
        """
        Execute trade via paper_trader.
        
        Uses existing paper_trader infrastructure.
        """
        try:
            if not self.paper_trader:
                return None
            
            # Use paper_trader's execute method
            if hasattr(self.paper_trader, '_execute_paper_trade'):
                result = await self.paper_trader._execute_paper_trade(
                    market_data=market_data,
                    side=side,
                    size=size,
                    strategy=strategy,
                    confidence=0.65,
                    sentiment_score=0.5,
                    signal_source='hft_v2'
                )
                return {'success': True, 'result': result}
            elif hasattr(self.paper_trader, 'execute_trade'):
                result = await self.paper_trader.execute_trade(
                    market_id=market_id,
                    direction=side,
                    outcome=side,
                    position_size=size,
                    strategy=strategy
                )
                return result
            else:
                logger.warning("[HFT V2] No suitable execute method on paper_trader")
                return None
                
        except Exception as e:
            logger.debug(f"[HFT V2] Paper trade error: {e}")
            return None
    
    async def _get_active_markets(self) -> List[Dict]:
        """Get list of active markets to process"""
        try:
            if self.market_data_svc:
                if hasattr(self.market_data_svc, 'get_active_markets'):
                    return await self.market_data_svc.get_active_markets(limit=100)
                elif hasattr(self.market_data_svc, 'get_markets'):
                    return await self.market_data_svc.get_markets(limit=100)
            
            # Fallback: use paper_trader's market service
            if self.paper_trader and hasattr(self.paper_trader, 'market_data_svc'):
                svc = self.paper_trader.market_data_svc
                if hasattr(svc, 'get_active_markets'):
                    return await svc.get_active_markets(limit=100)
            
            return []
        except Exception as e:
            logger.debug(f"[HFT V2] Get markets error: {e}")
            return []
    
    async def _log_hft_trade(
        self,
        market_id: str,
        hft_mode: HFTMode,
        trade_params: Dict,
        result: Dict,
        bayes_factor: float,
        news_strength: NewsStrength
    ):
        """Log HFT trade to analytics"""
        try:
            if self.performance_analytics and hasattr(self.performance_analytics, 'log_trade'):
                await self.performance_analytics.log_trade({
                    'market_id': market_id,
                    'strategy': f'hft_{hft_mode.value}',
                    'position_size': trade_params.get('position_size', 0),
                    'has_news': bayes_factor > 0,
                    'bayes_factor': bayes_factor,
                    'news_strength': news_strength.value,
                    'spread_mult': trade_params.get('spread_mult', 1.0),
                    'position_mult': trade_params.get('position_mult', 1.0),
                    'timestamp': datetime.now(timezone.utc)
                })
        except Exception as e:
            logger.debug(f"[HFT V2] Log trade error: {e}")
    
    def get_stats(self) -> Dict:
        """Return HFT engine statistics"""
        return {
            **self.stats,
            'running': self._running,
            'last_cycle_time_ms': self._last_cycle_time
        }
    
    def get_hft_metrics(self) -> Dict:
        """Return HFT performance metrics"""
        return {
            'cycles_executed': self.stats['cycles_executed'],
            'trades_executed': self.stats['trades_executed'],
            'mode_distribution': self.stats['trades_by_mode'],
            'path_a_hits': self.stats['path_a_hits'],
            'path_b_hits': self.stats['path_b_hits'],
            'paused_cycles': self.stats['paused_cycles'],
            'errors': self.stats['errors'],
            'running': self._running
        }


# Singleton instance
_hft_engine_instance: Optional[HighFrequencyTradingEngine] = None


def get_hft_engine() -> Optional[HighFrequencyTradingEngine]:
    """Get the singleton HFT engine instance"""
    return _hft_engine_instance


async def init_hft_engine(dependencies: Dict[str, Any]) -> HighFrequencyTradingEngine:
    """Initialize and return the HFT Engine V2"""
    global _hft_engine_instance
    _hft_engine_instance = HighFrequencyTradingEngine(dependencies)
    return _hft_engine_instance
