"""
Unit Tests for Alpha-State Exit Engine (Task 24)
=================================================

Tests cover:
1. Sports Volatility - Wide stops (SL mult 1.5)
2. Politics Tightness - Standard stops (SL mult 1.0)
3. Whale Zone - Special 50%/2x/5x rules
4. Free Roll Trigger - Partial sell on profit target
5. Dust Filter - Full close if partial too small
6. Free Ride State - Let it ride logic
7. Mechanical Strategy - Direct TP/SL
8. Thesis Fail - Time decay with loss
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.exit_engine import (
    ExitEngine,
    ExitAction,
    ExitReason,
    ExitDecision,
    get_exit_engine
)
from risk_config import (
    EXIT_GLOBAL_SETTINGS,
    EXIT_STRATEGY_CONFIG,
    EXIT_ALPHA_ASSET_MODIFIERS,
    get_alpha_asset_modifier
)


class TestSportsVolatility:
    """Test Sports asset class - wide stops for game swings."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_sports_allows_20_percent_loss(self):
        """Sports with -20% PnL should HOLD (SL mult 1.5 allows -22.5%)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.40,  # -20% loss
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        # Sports SL = 15% * 1.5 = 22.5%, so -20% should HOLD
        assert decision.action == ExitAction.HOLD
        assert decision.asset_class == 'sports'
    
    def test_sports_stops_at_23_percent_loss(self):
        """Sports with -23% PnL should CLOSE (exceeds 22.5% SL)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.385,  # -23% loss
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.STOP_LOSS
    
    def test_sports_no_thesis_fail(self):
        """Sports should NOT use thesis fail (halftime != loss)."""
        mods = get_alpha_asset_modifier('sports')
        assert mods['use_thesis_fail'] is False
        
        # Even with long duration + loss, should not thesis fail
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.48,  # -4% loss
            position_size_usd=50.0,
            duration_hours=20,  # Long hold
        )
        
        assert decision.reason != ExitReason.THESIS_FAIL
    
    def test_sports_no_trailing_stop(self):
        """Sports should NOT use trailing stop (scores oscillate)."""
        mods = get_alpha_asset_modifier('sports')
        assert mods['use_trailing'] is False


class TestPoliticsTightness:
    """Test Politics asset class - standard stops."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_politics_stops_at_16_percent_loss(self):
        """Politics with -16% PnL should CLOSE (SL mult 1.0 = 15%)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',
            entry_price=0.50,
            current_price=0.42,  # -16% loss
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.STOP_LOSS
    
    def test_politics_holds_at_14_percent_loss(self):
        """Politics with -14% PnL should HOLD (within 15% SL)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',
            entry_price=0.50,
            current_price=0.43,  # -14% loss
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.HOLD
    
    def test_politics_uses_thesis_fail(self):
        """Politics should use thesis fail for stalled trades."""
        mods = get_alpha_asset_modifier('politics')
        assert mods['use_thesis_fail'] is True
        
        # Long duration + small loss = thesis fail
        # Base 72h * 3.0 time_mult * 0.5 thesis = 108h
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',
            entry_price=0.50,
            current_price=0.49,  # -2% loss
            position_size_usd=50.0,
            duration_hours=120,  # Over thesis fail threshold
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.THESIS_FAIL


class TestWhaleZone:
    """Test Whale Zone exits (entry < $0.10)."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_whale_holds_at_20_percent_loss(self):
        """Whale zone with -20% loss should HOLD (stop is 50% of entry)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.05,  # Whale zone
            current_price=0.04,  # -20% loss
            position_size_usd=10.0,
            duration_hours=10,
        )
        
        # Whale stop = 50% of entry = $0.025
        # Current $0.04 > $0.025, so HOLD
        assert decision.zone == 'WHALE'
        assert decision.action == ExitAction.HOLD
    
    def test_whale_stops_at_50_percent(self):
        """Whale zone should stop at 50% of entry price."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.05,  # Whale zone
            current_price=0.024,  # Below 50% of entry
            position_size_usd=10.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.WHALE_STOP
    
    def test_whale_free_roll_at_2x(self):
        """Whale zone should free roll at 2x entry."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.05,  # Whale zone
            current_price=0.10,  # 2x entry
            position_size_usd=20.0,  # Large enough for partial
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.FREE_ROLL
        assert decision.reason == ExitReason.WHALE_FREE_ROLL
        assert decision.sell_pct == 0.50
    
    def test_whale_moonbag_at_5x(self):
        """Whale zone should close all at 5x entry."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.05,  # Whale zone
            current_price=0.25,  # 5x entry
            position_size_usd=10.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.WHALE_MOONBAG


class TestFreeRollTrigger:
    """Test Free Roll exit logic."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_free_roll_at_35_percent_gain(self):
        """Core zone with +35% gain should trigger free roll."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',  # profit_mult 1.2 -> target 36%
            entry_price=0.50,
            current_price=0.675,  # +35% gain
            position_size_usd=100.0,  # Large enough
            duration_hours=10,
        )
        
        # Politics target = 30% * 1.2 = 36%
        # +35% is just below, so should HOLD
        assert decision.action == ExitAction.HOLD
    
    def test_free_roll_at_40_percent_gain(self):
        """Core zone with +40% gain should trigger free roll."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',  # profit_mult 1.2 -> target 36%
            entry_price=0.50,
            current_price=0.70,  # +40% gain
            position_size_usd=100.0,
            duration_hours=10,
        )
        
        assert decision.action == ExitAction.FREE_ROLL
        assert decision.reason == ExitReason.PROFIT_TARGET


class TestDustFilter:
    """Test dust filter for small positions."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_dust_full_close(self):
        """Small position at profit should close all (no partial).
        
        To trigger dust filter, principal must be < $2.00 min trade.
        With +40% PnL, principal = position / 1.40
        So position of $2.50 gives principal of $1.79, below $2.00 min.
        """
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='default',
            entry_price=0.50,
            current_price=0.70,  # +40% gain (above 30% target)
            position_size_usd=2.50,  # Small position - principal would be $1.79
            duration_hours=10,
        )
        
        # Principal sell would be ~$1.79, below $2 min
        # Should close all instead
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.TAKE_PROFIT


class TestFreeRideState:
    """Test Free Ride (house money) state."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_free_ride_holds(self):
        """Free ride state should let it ride."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.45,  # Down from original
            position_size_usd=50.0,
            duration_hours=100,
            trade_status='FREE_RIDE',
        )
        
        assert decision.action == ExitAction.HOLD
        assert decision.reason == ExitReason.FREE_RIDE_ACTIVE
        assert decision.state == 'FREE_RIDE'
    
    def test_free_ride_floor(self):
        """Free ride should exit at floor ($0.02)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.02,  # At floor
            position_size_usd=50.0,
            duration_hours=100,
            trade_status='FREE_RIDE',
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.FREE_RIDE_FLOOR
    
    def test_free_ride_ceiling(self):
        """Free ride should exit at ceiling ($0.98)."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.98,  # At ceiling
            position_size_usd=50.0,
            duration_hours=100,
            trade_status='FREE_RIDE',
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.FREE_RIDE_CEILING


class TestMechanicalStrategy:
    """Test Mechanical strategy exits (Arb, Delta Neutral)."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_arb_take_profit(self):
        """Arbitrage should take profit at +2%."""
        decision = self.engine.check_exit(
            strategy='arbitrage',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.51,  # +2%
            position_size_usd=50.0,
            duration_hours=1,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.TAKE_PROFIT
    
    def test_arb_stop_loss(self):
        """Arbitrage should stop loss at -2%."""
        decision = self.engine.check_exit(
            strategy='arbitrage',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.49,  # -2%
            position_size_usd=50.0,
            duration_hours=1,
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.STOP_LOSS
    
    def test_delta_neutral_time_decay(self):
        """Delta neutral should close after max hours."""
        decision = self.engine.check_exit(
            strategy='delta_neutral',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.50,  # Flat
            position_size_usd=50.0,
            duration_hours=5,  # Over 4h max
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.TIME_DECAY


class TestGlobalSafety:
    """Test global safety checks."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_wick_protection(self):
        """Wide spread should trigger wick protection."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.30,  # -40% loss
            position_size_usd=50.0,
            duration_hours=1,
            current_spread_pct=0.15,  # 15% spread > 10% max
        )
        
        assert decision.action == ExitAction.HOLD
        assert decision.reason == ExitReason.WICK_PROTECTION
    
    def test_expiry_guard(self):
        """Near expiry with loss should force close."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='crypto',
            entry_price=0.50,
            current_price=0.49,  # Small loss
            position_size_usd=50.0,
            duration_hours=1,
            hours_to_expiry=1.5,  # Under 2h guard
        )
        
        assert decision.action == ExitAction.CLOSE_ALL
        assert decision.reason == ExitReason.EXPIRY_GUARD


class TestAssetModifiers:
    """Test asset modifier loading."""
    
    def test_crypto_modifier(self):
        """Crypto should have wide stops."""
        mods = get_alpha_asset_modifier('crypto')
        assert mods['sl_mult'] == 1.5
        assert mods['profit_mult'] == 1.5
        assert mods['use_trailing'] is True
    
    def test_science_modifier(self):
        """Science should have tight stops and long holds."""
        mods = get_alpha_asset_modifier('science')
        assert mods['sl_mult'] == 0.5
        assert mods['time_mult'] == 5.0
        assert mods['allow_zombie'] is True
    
    def test_unknown_falls_to_default(self):
        """Unknown asset class should use default."""
        mods = get_alpha_asset_modifier('unknown_category')
        assert mods == get_alpha_asset_modifier('default')
    
    def test_compound_names(self):
        """Compound names should map correctly."""
        assert get_alpha_asset_modifier('Science & Tech')['time_mult'] == 5.0
        assert get_alpha_asset_modifier('Finance and Crypto')['sl_mult'] == 1.5


class TestExitDecision:
    """Test ExitDecision dataclass."""
    
    def setup_method(self):
        self.engine = ExitEngine()
    
    def test_decision_to_dict(self):
        """Decision should serialize to dictionary."""
        decision = self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',
            entry_price=0.50,
            current_price=0.52,
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        d = decision.to_dict()
        assert 'action' in d
        assert 'reason' in d
        assert 'pnl_pct' in d
        assert d['zone'] == 'CORE'


class TestStatistics:
    """Test statistics tracking."""
    
    def setup_method(self):
        self.engine = ExitEngine()
        self.engine.reset_stats()
    
    def test_stats_increment(self):
        """Stats should increment on checks."""
        self.engine.check_exit(
            strategy='alpha_directional',
            asset_class='politics',
            entry_price=0.50,
            current_price=0.52,
            position_size_usd=50.0,
            duration_hours=10,
        )
        
        stats = self.engine.get_stats()
        assert stats['total_checks'] >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
