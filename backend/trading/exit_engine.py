"""
APEX TRADER - Alpha-State Exit Engine (Task 24)
================================================

Hierarchical Exit Engine that respects:
1. STATE: Is the trade Active or "Free Ride" (House Money)?
2. STRATEGY: Is it Mechanical (Math-based) or Alpha (Opinion-based)?
3. ASSET CLASS: Does it need wide stops (Sports) or tight stops (Science)?
4. ZONE: Is it a "Whale" trade (<$0.10) or Core trade?

Exit Decision Flow (Strict Order):
1. Free Ride State → Let it ride (floor $0.02, ceiling $0.98)
2. Global Safety → Wick filter, Expiry guard
3. Whale Zone → Special gamma exit rules
4. Mechanical Strategy → Direct TP/SL check
5. Alpha Strategy → Asset-modified exits with trailing/thesis fail

Usage:
    from trading.exit_engine import ExitEngine, ExitDecision
    
    engine = ExitEngine()
    decision = engine.check_exit(trade_data)
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

from risk_config import (
    EXIT_GLOBAL_SETTINGS,
    EXIT_STRATEGY_CONFIG,
    EXIT_ALPHA_ASSET_MODIFIERS,
    EXIT_WHALE_ZONE,
    get_alpha_asset_modifier,
)

logger = logging.getLogger(__name__)


class ExitAction(Enum):
    """Exit action to take."""
    HOLD = "HOLD"                     # No action, keep position
    CLOSE_ALL = "CLOSE_ALL"           # Close entire position
    FREE_ROLL = "FREE_ROLL"           # Sell principal, keep profits
    PARTIAL_CLOSE = "PARTIAL_CLOSE"   # Partial position close


class ExitReason(Enum):
    """Reason for exit decision."""
    # Hold reasons
    WICK_PROTECTION = "wick_protection"       # Spread too wide
    WITHIN_BOUNDS = "within_bounds"           # Normal operation
    FREE_RIDE_ACTIVE = "free_ride_active"     # House money, let it ride
    
    # Close reasons
    TAKE_PROFIT = "take_profit"               # Hit profit target
    STOP_LOSS = "stop_loss"                   # Hit stop loss
    TIME_DECAY = "time_decay"                 # Max hold time exceeded
    THESIS_FAIL = "thesis_fail"               # Stalled trade (time + loss)
    EXPIRY_GUARD = "expiry_guard"             # Force close near expiry
    TRAILING_STOP = "trailing_stop"           # Trailing stop triggered
    ZOMBIE_EXIT = "zombie_exit"               # Dead market exit
    FREE_RIDE_FLOOR = "free_ride_floor"       # Free ride hit floor
    FREE_RIDE_CEILING = "free_ride_ceiling"   # Free ride hit ceiling
    
    # Whale zone reasons
    WHALE_STOP = "whale_stop"                 # Whale zone stop (50% of entry)
    WHALE_FREE_ROLL = "whale_free_roll"       # Whale 2x free roll
    WHALE_MOONBAG = "whale_moonbag"           # Whale 5x moonbag
    
    # Free roll trigger
    PROFIT_TARGET = "profit_target"           # Hit free roll profit target


@dataclass
class ExitDecision:
    """Result of exit engine check."""
    action: ExitAction
    reason: ExitReason
    
    # Trade context
    strategy: str
    asset_class: str
    zone: str                         # 'WHALE' or 'CORE'
    state: str                        # 'ACTIVE' or 'FREE_RIDE'
    
    # Current metrics
    pnl_pct: float
    duration_hours: float
    current_price: float
    entry_price: float
    
    # Thresholds used
    take_profit_threshold: float
    stop_loss_threshold: float
    max_hours: float
    
    # Sell details (for partial exits)
    sell_pct: float = 1.0             # Percentage to sell
    sell_amount_usd: float = 0.0      # USD amount to sell
    
    # Modifiers applied
    modifiers_applied: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/API."""
        return {
            'action': self.action.value,
            'reason': self.reason.value,
            'strategy': self.strategy,
            'asset_class': self.asset_class,
            'zone': self.zone,
            'state': self.state,
            'pnl_pct': round(self.pnl_pct, 4),
            'duration_hours': round(self.duration_hours, 2),
            'current_price': round(self.current_price, 4),
            'entry_price': round(self.entry_price, 4),
            'take_profit_threshold': round(self.take_profit_threshold, 4),
            'stop_loss_threshold': round(self.stop_loss_threshold, 4),
            'max_hours': round(self.max_hours, 2),
            'sell_pct': round(self.sell_pct, 2),
            'sell_amount_usd': round(self.sell_amount_usd, 2),
        }


class ExitEngine:
    """
    Alpha-State Exit Engine - Hierarchical exit logic.
    
    Respects: State > Strategy > Asset Class > Zone
    """
    
    def __init__(self):
        """Initialize Exit Engine with config."""
        self.global_settings = dict(EXIT_GLOBAL_SETTINGS)
        self.strategy_config = dict(EXIT_STRATEGY_CONFIG)
        self.alpha_modifiers = dict(EXIT_ALPHA_ASSET_MODIFIERS)
        self.whale_zone = dict(EXIT_WHALE_ZONE)
        
        # Statistics
        self.stats = {
            'total_checks': 0,
            'holds': 0,
            'close_all': 0,
            'free_rolls': 0,
            'whale_exits': 0,
            'thesis_fails': 0,
            'trailing_stops': 0,
        }
        
        logger.info("🎯 ExitEngine initialized (Alpha-State)")
    
    def check_exit(
        self,
        strategy: str,
        asset_class: str,
        entry_price: float,
        current_price: float,
        position_size_usd: float,
        duration_hours: float,
        current_spread_pct: float = 0.0,
        hours_to_expiry: float = None,
        trade_status: str = 'ACTIVE',
        peak_price: float = None,
        side: str = 'YES',
    ) -> ExitDecision:
        """
        Check if a trade should exit.
        
        Args:
            strategy: Trade strategy (e.g., 'alpha_directional')
            asset_class: Asset category (e.g., 'politics', 'sports')
            entry_price: Original entry price (YES price, 0-1)
            current_price: Current market price (YES price, 0-1)
            position_size_usd: Current position size in USD
            duration_hours: How long position has been held
            current_spread_pct: Current bid-ask spread as percentage
            hours_to_expiry: Hours until market expires (None if unknown)
            trade_status: 'ACTIVE' or 'FREE_RIDE'
            peak_price: Highest price seen (for trailing stops)
            side: 'YES' or 'NO' - CRITICAL for correct P&L calculation
            
        Returns:
            ExitDecision with action and full context
        """
        self.stats['total_checks'] += 1
        
        # =================================================================
        # SIDE-AWARE P&L CALCULATION (Critical Fix - Jan 2026)
        # =================================================================
        # For YES positions: P&L = (current - entry) / entry
        # For NO positions: P&L = ((1 - current) - (1 - entry)) / (1 - entry)
        #                       = (entry - current) / (1 - entry)
        # This is because NO positions GAIN when YES price FALLS.
        
        if side.upper() == 'YES':
            # YES position: profits when price goes UP
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            # Peak tracking for trailing stops (YES wants high prices)
            effective_peak = peak_price if peak_price else current_price
        else:
            # NO position: profits when YES price goes DOWN (NO price goes UP)
            no_entry = 1 - entry_price
            no_current = 1 - current_price
            pnl_pct = (no_current - no_entry) / no_entry if no_entry > 0 else 0
            # Peak tracking for NO positions (NO wants low YES prices = high NO prices)
            # For trailing stops, we track the HIGHEST NO price seen (lowest YES price)
            if peak_price:
                # peak_price stores YES price, convert to NO for comparison
                no_peak = 1 - peak_price
                effective_peak = 1 - no_peak  # Back to YES for internal logic
            else:
                effective_peak = current_price
        
        # Determine zone (based on YES entry price)
        zone = 'WHALE' if entry_price < self.global_settings['whale_threshold_price'] else 'CORE'
        
        # Get strategy config
        strat_config = self.strategy_config.get(
            strategy, 
            self.strategy_config.get('alpha_directional')
        )
        
        # =====================================================================
        # 1. FREE RIDE STATE CHECK
        # =====================================================================
        if trade_status == 'FREE_RIDE':
            decision = self._check_free_ride_exit(
                entry_price, current_price, pnl_pct, duration_hours,
                strategy, asset_class, zone, strat_config
            )
            if decision:
                return decision
        
        # =====================================================================
        # 2. GLOBAL SAFETY (PRE-FLIGHT)
        # =====================================================================
        
        # Wick Filter: Don't exit into wide spreads
        if current_spread_pct > self.global_settings['max_spread_pct']:
            self.stats['holds'] += 1
            return ExitDecision(
                action=ExitAction.HOLD,
                reason=ExitReason.WICK_PROTECTION,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=0, stop_loss_threshold=0, max_hours=0,
            )
        
        # Expiry Guard: Force close losing trades near expiry
        if hours_to_expiry is not None and hours_to_expiry < self.global_settings['expiry_guard_hours']:
            if pnl_pct < 0:
                self.stats['close_all'] += 1
                return ExitDecision(
                    action=ExitAction.CLOSE_ALL,
                    reason=ExitReason.EXPIRY_GUARD,
                    strategy=strategy, asset_class=asset_class,
                    zone=zone, state=trade_status,
                    pnl_pct=pnl_pct, duration_hours=duration_hours,
                    current_price=current_price, entry_price=entry_price,
                    take_profit_threshold=0, stop_loss_threshold=0,
                    max_hours=self.global_settings['expiry_guard_hours'],
                )
        
        # =====================================================================
        # 3. WHALE ZONE CHECK (< $0.10 Entry)
        # =====================================================================
        if zone == 'WHALE':
            decision = self._check_whale_exit(
                entry_price, current_price, pnl_pct, duration_hours,
                position_size_usd, strategy, asset_class, trade_status
            )
            if decision.action != ExitAction.HOLD:
                return decision
        
        # =====================================================================
        # 4. MECHANICAL STRATEGY CHECK
        # =====================================================================
        if strat_config.get('type') == 'mechanical':
            return self._check_mechanical_exit(
                strat_config, entry_price, current_price, pnl_pct,
                duration_hours, strategy, asset_class, zone, trade_status
            )
        
        # =====================================================================
        # 5. ALPHA STRATEGY CHECK (Complex)
        # =====================================================================
        return self._check_alpha_exit(
            strat_config, entry_price, current_price, pnl_pct,
            duration_hours, position_size_usd, strategy, asset_class,
            zone, trade_status, peak_price
        )
    
    def _check_free_ride_exit(
        self, entry_price, current_price, pnl_pct, duration_hours,
        strategy, asset_class, zone, strat_config
    ) -> Optional[ExitDecision]:
        """
        Check exit for FREE_RIDE state (House Money).
        
        Free ride rules are simple:
        - Floor: Exit if price drops to $0.02
        - Ceiling: Exit if price rises to $0.98
        - Otherwise: Let it ride
        """
        floor = self.global_settings['free_ride_floor']
        ceiling = self.global_settings['free_ride_ceiling']
        
        # Hit floor - cleanup
        if current_price <= floor:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.FREE_RIDE_FLOOR,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state='FREE_RIDE',
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=ceiling, stop_loss_threshold=floor,
                max_hours=float('inf'),
            )
        
        # Hit ceiling - capture full value
        if current_price >= ceiling:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.FREE_RIDE_CEILING,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state='FREE_RIDE',
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=ceiling, stop_loss_threshold=floor,
                max_hours=float('inf'),
            )
        
        # Let it ride
        self.stats['holds'] += 1
        return ExitDecision(
            action=ExitAction.HOLD,
            reason=ExitReason.FREE_RIDE_ACTIVE,
            strategy=strategy, asset_class=asset_class,
            zone=zone, state='FREE_RIDE',
            pnl_pct=pnl_pct, duration_hours=duration_hours,
            current_price=current_price, entry_price=entry_price,
            take_profit_threshold=ceiling, stop_loss_threshold=floor,
            max_hours=float('inf'),
        )
    
    def _check_whale_exit(
        self, entry_price, current_price, pnl_pct, duration_hours,
        position_size_usd, strategy, asset_class, trade_status
    ) -> ExitDecision:
        """
        Check exit for Whale Zone trades (entry < $0.10).
        
        Uses PRICE MULTIPLES, not percentages:
        - Stop: 50% of entry (0.5x)
        - Free Roll: 2x entry (sell 50%)
        - Moonbag: 5x entry (sell 100%)
        """
        price_multiple = current_price / entry_price if entry_price > 0 else 0
        
        # MOONBAG: 5x exit
        if price_multiple >= self.whale_zone['moonbag_multiple']:
            self.stats['whale_exits'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.WHALE_MOONBAG,
                strategy=strategy, asset_class=asset_class,
                zone='WHALE', state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=entry_price * self.whale_zone['moonbag_multiple'],
                stop_loss_threshold=entry_price * self.whale_zone['stop_loss_multiple'],
                max_hours=168,
            )
        
        # FREE ROLL: 2x exit (sell 50%)
        if price_multiple >= self.whale_zone['free_roll_multiple'] and trade_status != 'FREE_RIDE':
            sell_pct = self.whale_zone['free_roll_sell_pct']
            sell_amount = position_size_usd * sell_pct
            
            # Dust check
            if sell_amount < self.global_settings['min_trade_size_usd']:
                # Too small to partial sell, take full profit
                self.stats['whale_exits'] += 1
                return ExitDecision(
                    action=ExitAction.CLOSE_ALL,
                    reason=ExitReason.WHALE_FREE_ROLL,
                    strategy=strategy, asset_class=asset_class,
                    zone='WHALE', state=trade_status,
                    pnl_pct=pnl_pct, duration_hours=duration_hours,
                    current_price=current_price, entry_price=entry_price,
                    take_profit_threshold=entry_price * self.whale_zone['free_roll_multiple'],
                    stop_loss_threshold=entry_price * self.whale_zone['stop_loss_multiple'],
                    max_hours=168,
                )
            
            self.stats['free_rolls'] += 1
            return ExitDecision(
                action=ExitAction.FREE_ROLL,
                reason=ExitReason.WHALE_FREE_ROLL,
                strategy=strategy, asset_class=asset_class,
                zone='WHALE', state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=entry_price * self.whale_zone['free_roll_multiple'],
                stop_loss_threshold=entry_price * self.whale_zone['stop_loss_multiple'],
                max_hours=168,
                sell_pct=sell_pct,
                sell_amount_usd=sell_amount,
            )
        
        # STOP LOSS: 50% of entry
        if price_multiple <= self.whale_zone['stop_loss_multiple']:
            self.stats['whale_exits'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.WHALE_STOP,
                strategy=strategy, asset_class=asset_class,
                zone='WHALE', state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=entry_price * self.whale_zone['free_roll_multiple'],
                stop_loss_threshold=entry_price * self.whale_zone['stop_loss_multiple'],
                max_hours=168,
            )
        
        # HOLD
        return ExitDecision(
            action=ExitAction.HOLD,
            reason=ExitReason.WITHIN_BOUNDS,
            strategy=strategy, asset_class=asset_class,
            zone='WHALE', state=trade_status,
            pnl_pct=pnl_pct, duration_hours=duration_hours,
            current_price=current_price, entry_price=entry_price,
            take_profit_threshold=entry_price * self.whale_zone['free_roll_multiple'],
            stop_loss_threshold=entry_price * self.whale_zone['stop_loss_multiple'],
            max_hours=168,
        )
    
    def _check_mechanical_exit(
        self, strat_config, entry_price, current_price, pnl_pct,
        duration_hours, strategy, asset_class, zone, trade_status
    ) -> ExitDecision:
        """
        Check exit for Mechanical strategies (Arb, Delta Neutral).
        
        Simple TP/SL/Time checks - no asset modifiers.
        """
        tp_pct = strat_config['tp_pct']
        sl_pct = strat_config['sl_pct']
        max_hours = strat_config['max_hours']
        
        # TAKE PROFIT
        if pnl_pct >= tp_pct:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.TAKE_PROFIT,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=tp_pct,
                stop_loss_threshold=-sl_pct,
                max_hours=max_hours,
            )
        
        # STOP LOSS
        if pnl_pct <= -sl_pct:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.STOP_LOSS,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=tp_pct,
                stop_loss_threshold=-sl_pct,
                max_hours=max_hours,
            )
        
        # TIME DECAY
        if duration_hours >= max_hours:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.TIME_DECAY,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=tp_pct,
                stop_loss_threshold=-sl_pct,
                max_hours=max_hours,
            )
        
        # HOLD
        self.stats['holds'] += 1
        return ExitDecision(
            action=ExitAction.HOLD,
            reason=ExitReason.WITHIN_BOUNDS,
            strategy=strategy, asset_class=asset_class,
            zone=zone, state=trade_status,
            pnl_pct=pnl_pct, duration_hours=duration_hours,
            current_price=current_price, entry_price=entry_price,
            take_profit_threshold=tp_pct,
            stop_loss_threshold=-sl_pct,
            max_hours=max_hours,
        )
    
    def _check_alpha_exit(
        self, strat_config, entry_price, current_price, pnl_pct,
        duration_hours, position_size_usd, strategy, asset_class,
        zone, trade_status, peak_price
    ) -> ExitDecision:
        """
        Check exit for Alpha (Complex) strategies.
        
        Uses asset-class modifiers for:
        - Profit target (Free Roll trigger)
        - Stop loss
        - Max hold time
        - Trailing stop
        - Thesis fail
        - Zombie detection
        """
        # Get asset modifiers
        mods = get_alpha_asset_modifier(asset_class)
        
        # Calculate modified thresholds
        base_profit = strat_config.get('profit_trigger_pct', 0.30)
        base_sl = strat_config.get('base_sl_pct', 0.15)
        base_max_hours = strat_config.get('base_max_hours', 72)
        
        profit_target = base_profit * mods['profit_mult']
        stop_limit = base_sl * mods['sl_mult']
        max_hours = base_max_hours * mods['time_mult']
        
        # =====================================================================
        # A. THESIS FAIL (Time Decay with Loss)
        # =====================================================================
        if mods['use_thesis_fail']:
            thesis_fail_time = max_hours * 0.5  # 50% of max hold time
            if duration_hours > thesis_fail_time and pnl_pct < 0:
                self.stats['thesis_fails'] += 1
                return ExitDecision(
                    action=ExitAction.CLOSE_ALL,
                    reason=ExitReason.THESIS_FAIL,
                    strategy=strategy, asset_class=asset_class,
                    zone=zone, state=trade_status,
                    pnl_pct=pnl_pct, duration_hours=duration_hours,
                    current_price=current_price, entry_price=entry_price,
                    take_profit_threshold=profit_target,
                    stop_loss_threshold=-stop_limit,
                    max_hours=max_hours,
                    modifiers_applied=mods,
                )
        
        # =====================================================================
        # B. HARD STOP (Asset Adjusted)
        # =====================================================================
        if pnl_pct <= -stop_limit:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.STOP_LOSS,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=profit_target,
                stop_loss_threshold=-stop_limit,
                max_hours=max_hours,
                modifiers_applied=mods,
            )
        
        # =====================================================================
        # C. TRAILING STOP (Ratchet)
        # =====================================================================
        if mods['use_trailing'] and peak_price is not None:
            # Calculate trailing stop
            peak_pnl = (peak_price - entry_price) / entry_price if entry_price > 0 else 0
            
            # If we've been up >15%, move stop to breakeven
            if peak_pnl >= 0.15:
                # Trail 10% behind peak
                trail_stop = peak_price * 0.90
                
                if current_price < trail_stop and current_price < entry_price:
                    self.stats['trailing_stops'] += 1
                    return ExitDecision(
                        action=ExitAction.CLOSE_ALL,
                        reason=ExitReason.TRAILING_STOP,
                        strategy=strategy, asset_class=asset_class,
                        zone=zone, state=trade_status,
                        pnl_pct=pnl_pct, duration_hours=duration_hours,
                        current_price=current_price, entry_price=entry_price,
                        take_profit_threshold=profit_target,
                        stop_loss_threshold=-stop_limit,
                        max_hours=max_hours,
                        modifiers_applied=mods,
                    )
        
        # =====================================================================
        # D. FREE ROLL TRIGGER (Sell Principal)
        # =====================================================================
        if pnl_pct >= profit_target:
            # Calculate principal to sell
            # Principal = original investment, profit = gains
            current_value = position_size_usd
            original_value = current_value / (1 + pnl_pct)
            sell_amount = original_value  # Sell the principal
            
            # Dust check
            if sell_amount < self.global_settings['min_trade_size_usd']:
                # Too small, take full profit
                self.stats['close_all'] += 1
                return ExitDecision(
                    action=ExitAction.CLOSE_ALL,
                    reason=ExitReason.TAKE_PROFIT,
                    strategy=strategy, asset_class=asset_class,
                    zone=zone, state=trade_status,
                    pnl_pct=pnl_pct, duration_hours=duration_hours,
                    current_price=current_price, entry_price=entry_price,
                    take_profit_threshold=profit_target,
                    stop_loss_threshold=-stop_limit,
                    max_hours=max_hours,
                    modifiers_applied=mods,
                )
            
            sell_pct = sell_amount / current_value if current_value > 0 else 0.5
            self.stats['free_rolls'] += 1
            return ExitDecision(
                action=ExitAction.FREE_ROLL,
                reason=ExitReason.PROFIT_TARGET,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=profit_target,
                stop_loss_threshold=-stop_limit,
                max_hours=max_hours,
                sell_pct=sell_pct,
                sell_amount_usd=sell_amount,
                modifiers_applied=mods,
            )
        
        # =====================================================================
        # E. ZOMBIE CHECK
        # =====================================================================
        if not mods['allow_zombie']:
            # After 24h with <1% change = zombie
            if duration_hours > 24 and abs(pnl_pct) < 0.01:
                self.stats['close_all'] += 1
                return ExitDecision(
                    action=ExitAction.CLOSE_ALL,
                    reason=ExitReason.ZOMBIE_EXIT,
                    strategy=strategy, asset_class=asset_class,
                    zone=zone, state=trade_status,
                    pnl_pct=pnl_pct, duration_hours=duration_hours,
                    current_price=current_price, entry_price=entry_price,
                    take_profit_threshold=profit_target,
                    stop_loss_threshold=-stop_limit,
                    max_hours=max_hours,
                    modifiers_applied=mods,
                )
        
        # =====================================================================
        # F. TIME DECAY (Max Hold)
        # =====================================================================
        if duration_hours >= max_hours:
            self.stats['close_all'] += 1
            return ExitDecision(
                action=ExitAction.CLOSE_ALL,
                reason=ExitReason.TIME_DECAY,
                strategy=strategy, asset_class=asset_class,
                zone=zone, state=trade_status,
                pnl_pct=pnl_pct, duration_hours=duration_hours,
                current_price=current_price, entry_price=entry_price,
                take_profit_threshold=profit_target,
                stop_loss_threshold=-stop_limit,
                max_hours=max_hours,
                modifiers_applied=mods,
            )
        
        # =====================================================================
        # HOLD
        # =====================================================================
        self.stats['holds'] += 1
        return ExitDecision(
            action=ExitAction.HOLD,
            reason=ExitReason.WITHIN_BOUNDS,
            strategy=strategy, asset_class=asset_class,
            zone=zone, state=trade_status,
            pnl_pct=pnl_pct, duration_hours=duration_hours,
            current_price=current_price, entry_price=entry_price,
            take_profit_threshold=profit_target,
            stop_loss_threshold=-stop_limit,
            max_hours=max_hours,
            modifiers_applied=mods,
        )
    
    def get_stats(self) -> Dict:
        """Get exit engine statistics."""
        return {
            **self.stats,
            'config': {
                'whale_threshold': self.global_settings['whale_threshold_price'],
                'max_spread_pct': self.global_settings['max_spread_pct'],
                'strategies': list(self.strategy_config.keys()),
                'asset_classes': list(self.alpha_modifiers.keys()),
            }
        }
    
    def reset_stats(self):
        """Reset statistics."""
        for key in self.stats:
            self.stats[key] = 0


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_exit_engine: Optional[ExitEngine] = None

def get_exit_engine() -> ExitEngine:
    """Get or create the singleton ExitEngine instance."""
    global _exit_engine
    if _exit_engine is None:
        _exit_engine = ExitEngine()
    return _exit_engine
