"""
HFT ENGINE V2 - HIGH-FREQUENCY TRADING ENGINE (ENHANCED)
=========================================================

Merges all legacy HFT features with the new 5 sub-strategy architecture.

LEGACY FEATURES INTEGRATED:
1. Alpha Target Integration - Uses strategy_context.get_target() for fair value
2. HFT Math Engine - Cubic skew, jump detection, cliff protection
3. Active Order Tracking - Manages active_orders dict for Polymarket compliance
4. Hysteresis Logic - Anti-churn with HYSTERESIS_THRESHOLD
5. Tick Grid Compliance - Uses TICK_SIZE = 0.01 for Polymarket

NEW V2 FEATURES:
1. 5 HFT Sub-Strategies with capital allocation
2. News Strength Classification (PAUSE/EXTREME/CAUTION/NORMAL)
3. MongoDB Signal Integration (PATH A + PATH B)
4. Spread & Position Multipliers based on news

CRITICAL CONSTRAINTS (MUST RESPECT):
- Kelly Criterion (0.25 fractional sizing)
- 3% max position cap
- Polymarket tick grid ($0.01)
- Kill zone bounds ($0.05 - $0.95)
- Never bypass existing capital management
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from threading import Lock

from trading.hft_config import (
    HFTConfig, HFTMode, NewsStrength,
    get_news_strength, get_multipliers, get_price_zone
)

# Import HFT Math Engine components
from strategies.hft_math import (
    HFTMathEngine, HFTMathConfig,
    CubicInventorySkew, AdaptiveSignalSmoother, CliffProtection
)

logger = logging.getLogger(__name__)


# =============================================================================
# POLYMARKET COMPLIANCE CONSTANTS
# =============================================================================
TICK_SIZE = 0.01           # Polymarket tick grid ($0.01)
MIN_PRICE = 0.05           # Kill zone lower bound
MAX_PRICE = 0.95           # Kill zone upper bound
MIN_SPREAD_TICKS = 2       # Minimum 2 cents spread
ORDER_STALE_SECONDS = 120  # Refresh orders after 2 minutes
HYSTERESIS_THRESHOLD = 0.01  # 1 cent drift tolerance (anti-churn)


class HighFrequencyTradingEngineV2:
    """
    Enhanced HFT Engine V2 - Merges Legacy + New Architecture
    
    Features:
    - 5 distinct HFT sub-strategies with proper capital allocation
    - Alpha target integration via strategy_context
    - HFT Math Engine (cubic skew, jump detection, cliff protection)
    - Active order tracking with hysteresis (anti-churn)
    - Polymarket tick grid compliance
    - News signals from MongoDB (PATH A intelligence + PATH B speed)
    - Respects ALL constraints (Kelly, 3% cap, capital limits)
    """
    
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Initialize HFT Engine V2 with injected dependencies.
        
        Args:
            dependencies: Dict containing:
                - db: MongoDB database connection
                - market_data_svc: Market data service
                - paper_trader: Paper trading instance
                - strategy_context: Alpha/HFT shared state bridge
                - position_manager: Position management (optional)
                - sharp_detector: Sharp trader detection (optional)
                - gamma_trader: Gamma trading strategy (optional)
                - performance_analytics: Analytics logging (optional)
        """
        # Required dependencies
        self.db = dependencies.get('db')
        self.market_data_svc = dependencies.get('market_data_svc')
        self.paper_trader = dependencies.get('paper_trader')
        self.strategy_context = dependencies.get('strategy_context')
        
        # Optional dependencies (graceful degradation)
        self.sharp_detector = dependencies.get('sharp_detector')
        self.gamma_trader = dependencies.get('gamma_trader')
        self.volatility_predictor = dependencies.get('volatility_predictor')
        self.performance_analytics = dependencies.get('performance_analytics')
        
        # HFT Math Engine (Cubic Skew, Jump Detection, Cliff Protection)
        self.hft_math_config = HFTMathConfig(
            max_position_limit=1000,
            skew_intensity=0.05,
            ema_alpha=0.2,
            jump_threshold=0.03,
            cliff_zone_threshold=0.15,
            cliff_spread_multiplier=2.0,
            extreme_zone_threshold=0.05,
            extreme_spread_multiplier=3.0,
        )
        self.hft_math_engine = HFTMathEngine(self.hft_math_config)
        
        # Active Order Tracking (Polymarket Compliance)
        self._orders_lock = Lock()
        self.active_orders: Dict[str, Dict] = {}
        
        # Engine state
        self._running = False
        self._last_cycle_time = None
        self._cycle_count = 0
        
        # Statistics
        self.stats = {
            'cycles_executed': 0,
            'trades_executed': 0,
            'trades_by_mode': {mode.value: 0 for mode in HFTMode},
            'paused_cycles': 0,
            'path_a_hits': 0,
            'path_b_hits': 0,
            'alpha_hits': 0,
            'alpha_misses': 0,
            'orders_kept_hysteresis': 0,
            'orders_cancelled_drift': 0,
            'orders_cancelled_stale': 0,
            'total_pnl': 0.0,
            'errors': 0
        }
        
        logger.info("[HFT V2 ENHANCED] Engine initialized")
        logger.info("  ├─ HFT Math Engine: Cubic Skew + Jump Detection + Cliff Protection")
        logger.info("  ├─ Polymarket Compliance: Tick Grid + Hysteresis + Kill Zones")
        logger.info("  ├─ Alpha Integration: strategy_context bridge")
        logger.info("  └─ Signal Sources: MongoDB PATH A + PATH B")
    
    async def start_hft_loop(self):
        """
        Main HFT background loop.
        Runs continuously, executing HFT strategies every 500ms.
        """
        logger.info("[HFT V2] Starting enhanced HFT loop...")
        self._running = True
        
        while self._running:
            try:
                cycle_start = time.time()
                self._cycle_count += 1
                
                # Skip if paper_trader in graceful stop mode
                if self.paper_trader and getattr(self.paper_trader, 'graceful_stop', False):
                    await asyncio.sleep(0.5)
                    continue
                
                # Get active markets
                markets = await self._get_active_markets()
                
                evaluated = 0
                triggered = 0
                
                if markets:
                    for market in markets[:50]:  # Process top 50 for speed
                        try:
                            result = await self.execute_hft_scalp(market)
                            evaluated += 1
                            if result and result.get('success'):
                                triggered += 1
                        except Exception as e:
                            logger.debug(f"[HFT V2] Market error: {e}")
                            continue
                
                self.stats['cycles_executed'] += 1
                
                # Calculate cycle time
                cycle_time_ms = (time.time() - cycle_start) * 1000
                self._last_cycle_time = cycle_time_ms
                
                # Log every 20 cycles
                if self._cycle_count % 20 == 0:
                    alpha_hit_rate = self.stats['alpha_hits'] / max(1, self.stats['alpha_hits'] + self.stats['alpha_misses'])
                    logger.info(
                        f"[HFT V2 #{self._cycle_count}] Evaluated: {evaluated}, "
                        f"Triggered: {triggered}, Cycle: {cycle_time_ms:.0f}ms, "
                        f"Alpha Hits: {alpha_hit_rate:.1%}"
                    )
                
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
        
        logger.info("[HFT V2] Enhanced HFT loop stopped")
    
    async def stop(self):
        """Stop the HFT engine"""
        self._running = False
        logger.info("[HFT V2] Stop requested")
    
    async def execute_hft_scalp(self, market_data: Dict) -> Optional[Dict]:
        """
        Main entry point for HFT execution on a single market.
        
        Enhanced Flow:
        1. Check if we already have a position (skip)
        2. Get Alpha target from strategy_context (smart mode)
        3. Check PATH B for fresh news broadcast (speed)
        4. Get PATH A analysis for bayes_factor (intelligence)
        5. Classify news strength and get multipliers
        6. If PAUSE mode, skip cycle
        7. Apply HFT Math Engine (skew, smoothing, cliff protection)
        8. Prune stale orders with hysteresis
        9. Select appropriate HFT mode based on price zone
        10. Build trade parameters (respecting all constraints)
        11. Execute via paper_trader with tick grid compliance
        12. Log to analytics
        """
        try:
            market_id = market_data.get('id', market_data.get('condition_id', ''))
            if not market_id:
                return None
            
            # STEP 1: Skip if we already have a position
            if self.paper_trader and market_id in getattr(self.paper_trader, 'paper_positions', {}):
                return None
            
            # Get current price
            yes_price = float(market_data.get('yes_price', market_data.get('price', 0.5)))
            
            # STEP 2: Check Alpha target (strategy_context bridge)
            alpha_target = None
            fair_value = yes_price  # Default to market price
            alpha_confidence = 0.5
            
            if self.strategy_context:
                alpha_target = self.strategy_context.get_target(market_id)
                if alpha_target and not alpha_target.get('stale'):
                    fair_value = alpha_target['fair_value']
                    # regime stored in alpha_target, used in _select_hft_mode
                    alpha_confidence = alpha_target.get('confidence', 0.7)
                    self.stats['alpha_hits'] += 1
                else:
                    self.stats['alpha_misses'] += 1
            
            # STEP 3: Check PATH B for fresh news broadcast (speed)
            has_news, opportunity = await self._check_path_b_opportunity(market_id)
            
            # STEP 4: Get PATH A analysis for bayes_factor (intelligence)
            signal = None
            bayes_factor = 0.0
            if has_news:
                signal = await self._read_path_a_signal(market_id)
                if signal:
                    bayes_factor = signal.get('bayes_factor', 0.0)
                    self.stats['path_a_hits'] += 1
            
            # STEP 5: Classify news strength and get multipliers
            news_strength = get_news_strength(bayes_factor)
            multipliers = get_multipliers(news_strength)
            
            # STEP 6: If PAUSE mode, skip entire cycle
            if news_strength == NewsStrength.PAUSE:
                self.stats['paused_cycles'] += 1
                logger.debug(f"[HFT V2] PAUSE: {market_id[:16]}... BF={bayes_factor:.1f}")
                return None
            
            # STEP 7: Apply HFT Math Engine
            current_position = self._get_current_position(market_id)
            quote_result = self.hft_math_engine.calculate_quote(
                market_id=market_id,
                raw_fair_value=fair_value,
                raw_signal=yes_price,
                current_position=current_position,
                base_spread=HFTConfig.DELTA_NEUTRAL_BASE_SPREAD
            )
            
            # Extract adjusted values
            adjusted_fair = quote_result['fair_value']
            adjusted_spread = quote_result['spread']
            cliff_zone = quote_result['cliff_zone']
            # signal_action available in quote_result for future use (jump detection)
            
            # STEP 8: Prune stale orders with hysteresis
            prune_stats = self._prune_stale_orders(market_id, adjusted_fair)
            self.stats['orders_kept_hysteresis'] += prune_stats.get('orders_kept_hysteresis', 0)
            self.stats['orders_cancelled_drift'] += prune_stats.get('orders_cancelled_drift', 0)
            self.stats['orders_cancelled_stale'] += prune_stats.get('orders_cancelled_stale', 0)
            
            # STEP 9: Select HFT mode based on price zone and conditions
            hft_mode = await self._select_hft_mode(
                market_id, market_data, yes_price, 
                alpha_target=alpha_target, cliff_zone=cliff_zone
            )
            
            if not hft_mode:
                return None
            
            # STEP 10: Build trade parameters (respecting ALL constraints)
            trade_params = await self._build_trade_params(
                hft_mode=hft_mode,
                market_id=market_id,
                market_data=market_data,
                multipliers=multipliers,
                signal=signal,
                alpha_confidence=alpha_confidence,
                adjusted_fair=adjusted_fair,
                adjusted_spread=adjusted_spread,
                cliff_zone=cliff_zone
            )
            
            if not trade_params:
                return None
            
            # STEP 11: Execute via appropriate strategy method with tick grid compliance
            result = await self._execute_strategy(
                hft_mode=hft_mode,
                market_id=market_id,
                market_data=market_data,
                trade_params=trade_params,
                signal=signal,
                alpha_target=alpha_target
            )
            
            if result and result.get('success'):
                self.stats['trades_executed'] += 1
                self.stats['trades_by_mode'][hft_mode.value] += 1
                
                # Update active orders
                self._update_active_order(market_id, trade_params)
                
                # STEP 12: Log to analytics
                await self._log_hft_trade(
                    market_id=market_id,
                    hft_mode=hft_mode,
                    trade_params=trade_params,
                    result=result,
                    bayes_factor=bayes_factor,
                    news_strength=news_strength,
                    alpha_target=alpha_target
                )
            
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[HFT V2] Execute error: {e}")
            return None
    
    # =========================================================================
    # ALPHA TARGET INTEGRATION
    # =========================================================================
    
    def _get_current_position(self, market_id: str) -> float:
        """Get current position size for a market (for inventory skew)"""
        try:
            if self.paper_trader:
                positions = getattr(self.paper_trader, 'paper_positions', {})
                if market_id in positions:
                    return positions[market_id].get('size', 0)
            return 0.0
        except Exception:
            return 0.0
    
    # =========================================================================
    # POLYMARKET COMPLIANCE: TICK GRID & HYSTERESIS
    # =========================================================================
    
    def _round_to_tick(self, price: float) -> float:
        """Round price to Polymarket tick grid ($0.01)."""
        return round(price, 2)
    
    def _clamp_to_bounds(self, price: float) -> float:
        """Clamp price to kill zone bounds [$0.05, $0.95]."""
        return max(MIN_PRICE, min(MAX_PRICE, price))
    
    def _enforce_min_spread(self, bid: float, ask: float) -> Tuple[float, float]:
        """
        Enforce minimum spread of 2 ticks ($0.02).
        If spread is too tight, widen symmetrically around mid-point.
        """
        min_spread = MIN_SPREAD_TICKS * TICK_SIZE
        current_spread = ask - bid
        
        if current_spread >= min_spread:
            return bid, ask
        
        mid = (bid + ask) / 2
        half_spread = min_spread / 2
        
        new_bid = self._round_to_tick(mid - half_spread)
        new_ask = self._round_to_tick(mid + half_spread)
        
        new_bid = self._clamp_to_bounds(new_bid)
        new_ask = self._clamp_to_bounds(new_ask)
        
        if new_ask <= new_bid:
            new_ask = new_bid + min_spread
            new_ask = self._clamp_to_bounds(new_ask)
        
        return new_bid, new_ask
    
    def _prune_stale_orders(self, market_id: str, current_ai_price: float) -> Dict:
        """
        Prune stale or drifted orders with hysteresis (anti-churn) logic.
        
        Logic:
        1. If drift <= HYSTERESIS_THRESHOLD (1 cent): KEEP order (anti-churn)
        2. If drift > HYSTERESIS_THRESHOLD: CANCEL (AI changed mind)
        3. If age > ORDER_STALE_SECONDS (120s): CANCEL (refresh liquidity)
        4. If price outside kill zones: CANCEL (safety)
        """
        now = datetime.now(timezone.utc)
        stats = {
            'orders_checked': 0,
            'orders_kept_hysteresis': 0,
            'orders_cancelled_drift': 0,
            'orders_cancelled_stale': 0,
            'orders_cancelled_bounds': 0,
            'total_cancelled': 0,
        }
        
        with self._orders_lock:
            order = self.active_orders.get(market_id)
            if not order:
                return stats
            
            stats['orders_checked'] = 1
            order_price = order.get('price', 0)
            order_time = order.get('timestamp')
            should_cancel = False
            cancel_reason = ""
            
            # CHECK 1: BOUNDS VIOLATION (Safety First)
            if order_price < MIN_PRICE or order_price > MAX_PRICE:
                should_cancel = True
                cancel_reason = f"BOUNDS_VIOLATION (price={order_price:.2f})"
                stats['orders_cancelled_bounds'] += 1
            
            # CHECK 2: STALENESS (Refresh Liquidity)
            elif order_time:
                age_seconds = (now - order_time).total_seconds()
                if age_seconds > ORDER_STALE_SECONDS:
                    should_cancel = True
                    cancel_reason = f"STALE ({age_seconds:.0f}s > {ORDER_STALE_SECONDS}s)"
                    stats['orders_cancelled_stale'] += 1
            
            # CHECK 3: DRIFT vs HYSTERESIS (Anti-Churn)
            if not should_cancel:
                raw_drift = abs(order_price - current_ai_price)
                clean_drift = round(raw_drift, 4)
                
                if clean_drift <= HYSTERESIS_THRESHOLD:
                    stats['orders_kept_hysteresis'] += 1
                    logger.debug(
                        f"[HFT V2] Keeping {market_id[:16]}... order "
                        f"(drift={clean_drift:.4f} <= {HYSTERESIS_THRESHOLD})"
                    )
                else:
                    should_cancel = True
                    cancel_reason = f"DRIFT ({clean_drift:.4f} > {HYSTERESIS_THRESHOLD})"
                    stats['orders_cancelled_drift'] += 1
            
            # EXECUTE CANCELLATION
            if should_cancel:
                del self.active_orders[market_id]
                stats['total_cancelled'] += 1
                logger.info(
                    f"[HFT V2] ❌ Cancelled {market_id[:16]}... | "
                    f"Reason: {cancel_reason} | "
                    f"Old Price: ${order_price:.2f} → AI Price: ${current_ai_price:.2f}"
                )
        
        return stats
    
    def _update_active_order(self, market_id: str, trade_params: Dict):
        """Track active order for lifecycle management"""
        with self._orders_lock:
            self.active_orders[market_id] = {
                'price': trade_params.get('entry_price', 0),
                'size': trade_params.get('position_size', 0),
                'side': trade_params.get('direction', 'YES'),
                'timestamp': datetime.now(timezone.utc),
                'hft_mode': trade_params.get('hft_mode', 'unknown'),
                'ai_price': trade_params.get('adjusted_fair', 0),
            }
    
    # =========================================================================
    # PATH A/B SIGNAL INTEGRATION
    # =========================================================================
    
    async def _check_path_b_opportunity(self, market_id: str) -> Tuple[bool, Optional[Dict]]:
        """Check PATH B (hft_opportunities) for fresh news broadcast."""
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
        """Read PATH A signal from MongoDB signals collection."""
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
    
    # =========================================================================
    # MODE SELECTION
    # =========================================================================
    
    async def _select_hft_mode(
        self, market_id: str, market_data: Dict, price: float,
        alpha_target: Optional[Dict] = None, cliff_zone: str = "SAFE"
    ) -> Optional[HFTMode]:
        """
        Select the appropriate HFT mode based on market conditions.
        
        Enhanced logic considers:
        - Alpha target regime (ZOMBIE, MAKER_WIDE, TAKER_TIGHT)
        - Cliff zone (EXTREME, CLIFF, SAFE)
        - Price zone (extreme_low, standard, extreme_high)
        - Volume and sharp activity
        """
        try:
            zone = get_price_zone(price)
            volume_24h = float(market_data.get('volume_24h', market_data.get('volume', 0)) or 0)
            
            # Check Alpha regime for ZOMBIE markets
            if alpha_target:
                regime = alpha_target.get('regime', '')
                if regime == 'ZOMBIE':
                    return None  # Skip zombie markets
            
            # EXTREME ZONES or CLIFF zones: Volatility/Extreme spread strategies
            if zone in ['extreme_low', 'extreme_high'] or cliff_zone in ['EXTREME', 'CLIFF']:
                vol_score = market_data.get('volatility', 0.5)
                
                if vol_score >= HFTConfig.VOLATILITY_MIN_SCORE:
                    return HFTMode.VOLATILITY_EXPLOIT
                else:
                    return HFTMode.EXTREME_SPREAD
            
            # STANDARD ZONE: Multiple strategies possible
            
            # Check for sharp trader activity (highest priority in standard zone)
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
            
            # Check Alpha regime for maker/taker preference
            if alpha_target:
                regime = alpha_target.get('regime', '')
                if regime == 'MAKER_WIDE':
                    return HFTMode.DELTA_NEUTRAL  # Market making with wide spreads
            
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
            
            if hasattr(self.sharp_detector, 'is_sharp_active'):
                return await self.sharp_detector.is_sharp_active(market_id)
            elif hasattr(self.sharp_detector, 'detect_sharp_movement'):
                result = await self.sharp_detector.detect_sharp_movement(market_id)
                return result.get('z_score', 0) >= HFTConfig.SHARP_MIN_ZSCORE
            
            return False
        except Exception:
            return False
    
    # =========================================================================
    # TRADE PARAMETER BUILDING
    # =========================================================================
    
    async def _build_trade_params(
        self,
        hft_mode: HFTMode,
        market_id: str,
        market_data: Dict,
        multipliers: Dict[str, float],
        signal: Optional[Dict],
        alpha_confidence: float,
        adjusted_fair: float,
        adjusted_spread: float,
        cliff_zone: str
    ) -> Optional[Dict]:
        """
        Build trade parameters respecting ALL constraints.
        
        Enhanced with:
        - Tick grid compliance
        - Kill zone bounds
        - Alpha confidence weighting
        - Cliff zone spread multipliers
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
            
            # Apply Kelly criterion with Alpha confidence
            confidence = max(alpha_confidence, signal.get('confidence', 0.5) if signal else 0.5)
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
            
            # Get spread parameters with cliff zone adjustment
            spread_mult = multipliers.get('spread_mult', 1.0)
            cliff_mult = 1.0
            if cliff_zone == 'EXTREME':
                cliff_mult = 3.0
            elif cliff_zone == 'CLIFF':
                cliff_mult = 2.0
            
            final_spread = adjusted_spread * spread_mult * cliff_mult
            
            # Apply tick grid compliance
            half_spread = final_spread / 2
            
            bid = self._round_to_tick(adjusted_fair - half_spread)
            ask = self._round_to_tick(adjusted_fair + half_spread)
            
            bid = self._clamp_to_bounds(bid)
            ask = self._clamp_to_bounds(ask)
            
            bid, ask = self._enforce_min_spread(bid, ask)
            
            # Get direction from signal or Alpha target
            direction = 'YES'
            if signal:
                direction = signal.get('direction', 'YES')
            
            entry_price = bid if direction == 'YES' else ask
            
            return {
                'position_size': round(final_position, 2),
                'spread': round(ask - bid, 2),
                'direction': direction,
                'confidence': confidence,
                'hft_mode': hft_mode.value,
                'spread_mult': spread_mult,
                'position_mult': position_mult,
                'cliff_mult': cliff_mult,
                'cliff_zone': cliff_zone,
                'bid': bid,
                'ask': ask,
                'entry_price': entry_price,
                'adjusted_fair': adjusted_fair,
            }
            
        except Exception as e:
            logger.debug(f"[HFT V2] Build params error: {e}")
            return None
    
    async def _get_available_capital(self) -> float:
        """Get available capital from paper trader"""
        try:
            if self.paper_trader:
                if hasattr(self.paper_trader, 'current_capital'):
                    return self.paper_trader.current_capital
                elif hasattr(self.paper_trader, 'deployed_capital'):
                    return self.paper_trader.deployed_capital
            return 0
        except Exception:
            return 0
    
    # =========================================================================
    # STRATEGY EXECUTION
    # =========================================================================
    
    async def _execute_strategy(
        self,
        hft_mode: HFTMode,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        signal: Optional[Dict],
        alpha_target: Optional[Dict]
    ) -> Optional[Dict]:
        """Execute the selected HFT strategy with Polymarket compliance."""
        try:
            # All strategies use the same execution path with tick-grid compliant params
            return await self._execute_compliant_trade(
                market_id=market_id,
                market_data=market_data,
                trade_params=trade_params,
                hft_mode=hft_mode
            )
        except Exception as e:
            logger.error(f"[HFT V2] Strategy execution error: {e}")
            return None
    
    async def _execute_compliant_trade(
        self,
        market_id: str,
        market_data: Dict,
        trade_params: Dict,
        hft_mode: HFTMode
    ) -> Optional[Dict]:
        """
        Execute trade via paper_trader with full Polymarket compliance.
        Uses tick-grid aligned prices from trade_params.
        """
        try:
            if not self.paper_trader:
                return None
            
            strategy_name = f'hft_{hft_mode.value}'
            
            # Use paper_trader's execute method
            if hasattr(self.paper_trader, '_execute_paper_entry'):
                # Prepare signals dict for the entry method
                signals = {
                    'hft_mode': hft_mode.value,
                    'path_a_signal': trade_params.get('path_a_signal'),
                    'path_b_opportunity': trade_params.get('path_b_opportunity'),
                    'edge': trade_params.get('edge', 0),
                    'confidence': trade_params.get('confidence', 0.65),
                }
                
                result = await self.paper_trader._execute_paper_entry(
                    market_id=market_id,
                    market_data=market_data,
                    side=trade_params['direction'],
                    size=trade_params['position_size'],
                    strategy=strategy_name,
                    signals=signals,
                    rl_action='BUY' if trade_params['direction'] == 'YES' else 'SELL',
                    rl_confidence=trade_params.get('confidence', 0.65),
                    sizing_breakdown={'source': 'hft_v2', 'kelly': 0.15}
                )
                return {'success': True, 'result': result}
            elif hasattr(self.paper_trader, 'execute_trade'):
                result = await self.paper_trader.execute_trade(
                    market_id=market_id,
                    direction=trade_params['direction'],
                    outcome=trade_params['direction'],
                    position_size=trade_params['position_size'],
                    strategy=strategy_name
                )
                return result
            else:
                logger.warning("[HFT V2] No suitable execute method on paper_trader")
                return None
                
        except Exception as e:
            logger.debug(f"[HFT V2] Compliant trade error: {e}")
            return None
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
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
        news_strength: NewsStrength,
        alpha_target: Optional[Dict]
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
                    'cliff_zone': trade_params.get('cliff_zone', 'SAFE'),
                    'has_alpha_target': alpha_target is not None,
                    'alpha_regime': alpha_target.get('regime') if alpha_target else None,
                    'tick_compliant': True,
                    'timestamp': datetime.now(timezone.utc)
                })
        except Exception as e:
            logger.debug(f"[HFT V2] Log trade error: {e}")
    
    def get_stats(self) -> Dict:
        """Return HFT engine statistics"""
        return {
            **self.stats,
            'running': self._running,
            'last_cycle_time_ms': self._last_cycle_time,
            'cycle_count': self._cycle_count,
            'active_orders': len(self.active_orders),
        }
    
    def get_hft_metrics(self) -> Dict:
        """Return HFT performance metrics"""
        alpha_total = self.stats['alpha_hits'] + self.stats['alpha_misses']
        alpha_hit_rate = self.stats['alpha_hits'] / max(1, alpha_total)
        
        return {
            'cycles_executed': self.stats['cycles_executed'],
            'trades_executed': self.stats['trades_executed'],
            'mode_distribution': self.stats['trades_by_mode'],
            'path_a_hits': self.stats['path_a_hits'],
            'path_b_hits': self.stats['path_b_hits'],
            'alpha_hits': self.stats['alpha_hits'],
            'alpha_misses': self.stats['alpha_misses'],
            'alpha_hit_rate': round(alpha_hit_rate, 3),
            'paused_cycles': self.stats['paused_cycles'],
            'orders_kept_hysteresis': self.stats['orders_kept_hysteresis'],
            'orders_cancelled_drift': self.stats['orders_cancelled_drift'],
            'orders_cancelled_stale': self.stats['orders_cancelled_stale'],
            'active_orders': len(self.active_orders),
            'errors': self.stats['errors'],
            'running': self._running
        }


# Singleton instance
_hft_engine_v2_instance: Optional[HighFrequencyTradingEngineV2] = None


def get_hft_engine_v2() -> Optional[HighFrequencyTradingEngineV2]:
    """Get the singleton HFT engine V2 instance"""
    return _hft_engine_v2_instance


async def init_hft_engine_v2(dependencies: Dict[str, Any]) -> HighFrequencyTradingEngineV2:
    """Initialize and return the enhanced HFT Engine V2"""
    global _hft_engine_v2_instance
    _hft_engine_v2_instance = HighFrequencyTradingEngineV2(dependencies)
    return _hft_engine_v2_instance
