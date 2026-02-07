"""
Test Sports Arbitrage Exit Engine - Iteration 38

Tests the fix for sports arbitrage positions not closing correctly.
The fix adds a Universal Exit Engine in _position_monitoring_loop that
evaluates ALL positions (including sports) using the ExitEngine SSOT.

Test Scenarios:
1. TAKE_PROFIT: 10% gain > 5% TP threshold → CLOSE_ALL
2. STOP_LOSS: 10% loss > 5% SL threshold → CLOSE_ALL
3. TIME_DECAY: 15h > 12h max hours → CLOSE_ALL
4. HOLD: 2.5% gain < 5% TP threshold → HOLD

Configuration from EXIT_STRATEGY_CONFIG['sports_arbitrage']:
- tp_pct: 0.05 (5% take profit)
- sl_pct: 0.05 (5% stop loss)
- max_hours: 12 (12 hours max hold)
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, '/app/backend')

from trading.exit_engine import ExitEngine, ExitAction, ExitReason
from risk_config import EXIT_STRATEGY_CONFIG


class TestSportsArbitrageExitConfig:
    """Test that sports_arbitrage is correctly configured in EXIT_STRATEGY_CONFIG."""
    
    def test_sports_arbitrage_exists_in_config(self):
        """Verify sports_arbitrage strategy exists in EXIT_STRATEGY_CONFIG."""
        assert 'sports_arbitrage' in EXIT_STRATEGY_CONFIG, \
            "sports_arbitrage should be in EXIT_STRATEGY_CONFIG"
        print("✅ sports_arbitrage exists in EXIT_STRATEGY_CONFIG")
    
    def test_sports_arbitrage_is_mechanical(self):
        """Verify sports_arbitrage is a mechanical strategy type."""
        config = EXIT_STRATEGY_CONFIG['sports_arbitrage']
        assert config['type'] == 'mechanical', \
            f"sports_arbitrage should be 'mechanical', got '{config['type']}'"
        print(f"✅ sports_arbitrage type is 'mechanical'")
    
    def test_sports_arbitrage_tp_pct(self):
        """Verify sports_arbitrage take profit is 5%."""
        config = EXIT_STRATEGY_CONFIG['sports_arbitrage']
        assert config['tp_pct'] == 0.05, \
            f"sports_arbitrage tp_pct should be 0.05, got {config['tp_pct']}"
        print(f"✅ sports_arbitrage tp_pct = {config['tp_pct']} (5%)")
    
    def test_sports_arbitrage_sl_pct(self):
        """Verify sports_arbitrage stop loss is 5%."""
        config = EXIT_STRATEGY_CONFIG['sports_arbitrage']
        assert config['sl_pct'] == 0.05, \
            f"sports_arbitrage sl_pct should be 0.05, got {config['sl_pct']}"
        print(f"✅ sports_arbitrage sl_pct = {config['sl_pct']} (5%)")
    
    def test_sports_arbitrage_max_hours(self):
        """Verify sports_arbitrage max hold time is 12 hours."""
        config = EXIT_STRATEGY_CONFIG['sports_arbitrage']
        assert config['max_hours'] == 12, \
            f"sports_arbitrage max_hours should be 12, got {config['max_hours']}"
        print(f"✅ sports_arbitrage max_hours = {config['max_hours']} hours")


class TestSportsArbitrageExitScenarios:
    """Test ExitEngine.check_exit() for sports_arbitrage scenarios."""
    
    @pytest.fixture
    def exit_engine(self):
        """Create a fresh ExitEngine instance."""
        return ExitEngine()
    
    def test_take_profit_scenario(self, exit_engine):
        """
        TAKE_PROFIT: 10% gain > 5% TP threshold → CLOSE_ALL
        
        Entry: $0.50, Current: $0.55 (10% gain)
        Expected: CLOSE_ALL with reason TAKE_PROFIT
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.55,  # 10% gain
            position_size_usd=100.0,
            duration_hours=2.0,  # Within time limit
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.55,
            side='YES'
        )
        
        # Verify decision
        assert decision.action == ExitAction.CLOSE_ALL, \
            f"Expected CLOSE_ALL, got {decision.action}"
        assert decision.reason == ExitReason.TAKE_PROFIT, \
            f"Expected TAKE_PROFIT, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(0.10, rel=0.01), \
            f"Expected ~10% P&L, got {decision.pnl_pct:.2%}"
        
        print(f"✅ TAKE_PROFIT scenario: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")
    
    def test_stop_loss_scenario(self, exit_engine):
        """
        STOP_LOSS: 10% loss > 5% SL threshold → CLOSE_ALL
        
        Entry: $0.50, Current: $0.45 (10% loss)
        Expected: CLOSE_ALL with reason STOP_LOSS
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.45,  # 10% loss
            position_size_usd=100.0,
            duration_hours=2.0,  # Within time limit
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.50,
            side='YES'
        )
        
        # Verify decision
        assert decision.action == ExitAction.CLOSE_ALL, \
            f"Expected CLOSE_ALL, got {decision.action}"
        assert decision.reason == ExitReason.STOP_LOSS, \
            f"Expected STOP_LOSS, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(-0.10, rel=0.01), \
            f"Expected ~-10% P&L, got {decision.pnl_pct:.2%}"
        
        print(f"✅ STOP_LOSS scenario: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")
    
    def test_time_decay_scenario(self, exit_engine):
        """
        TIME_DECAY: 15h > 12h max hours → CLOSE_ALL
        
        Entry: $0.50, Current: $0.51 (2% gain, within TP/SL)
        Duration: 15 hours (exceeds 12h max)
        Expected: CLOSE_ALL with reason TIME_DECAY
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.51,  # 2% gain (within bounds)
            position_size_usd=100.0,
            duration_hours=15.0,  # Exceeds 12h max
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.51,
            side='YES'
        )
        
        # Verify decision
        assert decision.action == ExitAction.CLOSE_ALL, \
            f"Expected CLOSE_ALL, got {decision.action}"
        assert decision.reason == ExitReason.TIME_DECAY, \
            f"Expected TIME_DECAY, got {decision.reason}"
        assert decision.duration_hours == 15.0, \
            f"Expected duration 15h, got {decision.duration_hours}"
        
        print(f"✅ TIME_DECAY scenario: action={decision.action.value}, "
              f"reason={decision.reason.value}, duration={decision.duration_hours}h")
    
    def test_hold_scenario(self, exit_engine):
        """
        HOLD: 2.5% gain < 5% TP threshold → HOLD
        
        Entry: $0.50, Current: $0.5125 (2.5% gain)
        Duration: 5 hours (within 12h max)
        Expected: HOLD with reason WITHIN_BOUNDS
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.5125,  # 2.5% gain (below 5% TP)
            position_size_usd=100.0,
            duration_hours=5.0,  # Within time limit
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.5125,
            side='YES'
        )
        
        # Verify decision
        assert decision.action == ExitAction.HOLD, \
            f"Expected HOLD, got {decision.action}"
        assert decision.reason == ExitReason.WITHIN_BOUNDS, \
            f"Expected WITHIN_BOUNDS, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(0.025, rel=0.01), \
            f"Expected ~2.5% P&L, got {decision.pnl_pct:.2%}"
        
        print(f"✅ HOLD scenario: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")
    
    def test_hold_small_loss_scenario(self, exit_engine):
        """
        HOLD: 2% loss < 5% SL threshold → HOLD
        
        Entry: $0.50, Current: $0.49 (2% loss)
        Duration: 5 hours (within 12h max)
        Expected: HOLD with reason WITHIN_BOUNDS
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.49,  # 2% loss (below 5% SL)
            position_size_usd=100.0,
            duration_hours=5.0,  # Within time limit
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.50,
            side='YES'
        )
        
        # Verify decision
        assert decision.action == ExitAction.HOLD, \
            f"Expected HOLD, got {decision.action}"
        assert decision.reason == ExitReason.WITHIN_BOUNDS, \
            f"Expected WITHIN_BOUNDS, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(-0.02, rel=0.01), \
            f"Expected ~-2% P&L, got {decision.pnl_pct:.2%}"
        
        print(f"✅ HOLD (small loss) scenario: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")


class TestSportsArbitrageNoSide:
    """Test ExitEngine for NO-side sports positions."""
    
    @pytest.fixture
    def exit_engine(self):
        """Create a fresh ExitEngine instance."""
        return ExitEngine()
    
    def test_no_side_take_profit(self, exit_engine):
        """
        NO-side TAKE_PROFIT: YES price drops → NO position profits
        
        Entry YES: $0.50 (NO entry: $0.50)
        Current YES: $0.45 (NO current: $0.55)
        NO P&L: (0.55 - 0.50) / 0.50 = 10% gain
        Expected: CLOSE_ALL with reason TAKE_PROFIT
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,      # YES entry price
            current_price=0.45,   # YES current price (dropped)
            position_size_usd=100.0,
            duration_hours=2.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.45,
            side='NO'  # NO position
        )
        
        # For NO side: P&L = (NO_current - NO_entry) / NO_entry
        # NO_entry = 1 - 0.50 = 0.50
        # NO_current = 1 - 0.45 = 0.55
        # P&L = (0.55 - 0.50) / 0.50 = 0.10 (10% gain)
        
        assert decision.action == ExitAction.CLOSE_ALL, \
            f"Expected CLOSE_ALL, got {decision.action}"
        assert decision.reason == ExitReason.TAKE_PROFIT, \
            f"Expected TAKE_PROFIT, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(0.10, rel=0.01), \
            f"Expected ~10% P&L for NO side, got {decision.pnl_pct:.2%}"
        
        print(f"✅ NO-side TAKE_PROFIT: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")
    
    def test_no_side_stop_loss(self, exit_engine):
        """
        NO-side STOP_LOSS: YES price rises → NO position loses
        
        Entry YES: $0.50 (NO entry: $0.50)
        Current YES: $0.55 (NO current: $0.45)
        NO P&L: (0.45 - 0.50) / 0.50 = -10% loss
        Expected: CLOSE_ALL with reason STOP_LOSS
        """
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,      # YES entry price
            current_price=0.55,   # YES current price (rose)
            position_size_usd=100.0,
            duration_hours=2.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.50,
            side='NO'  # NO position
        )
        
        # For NO side: P&L = (NO_current - NO_entry) / NO_entry
        # NO_entry = 1 - 0.50 = 0.50
        # NO_current = 1 - 0.55 = 0.45
        # P&L = (0.45 - 0.50) / 0.50 = -0.10 (-10% loss)
        
        assert decision.action == ExitAction.CLOSE_ALL, \
            f"Expected CLOSE_ALL, got {decision.action}"
        assert decision.reason == ExitReason.STOP_LOSS, \
            f"Expected STOP_LOSS, got {decision.reason}"
        assert decision.pnl_pct == pytest.approx(-0.10, rel=0.01), \
            f"Expected ~-10% P&L for NO side, got {decision.pnl_pct:.2%}"
        
        print(f"✅ NO-side STOP_LOSS: action={decision.action.value}, "
              f"reason={decision.reason.value}, pnl={decision.pnl_pct:.2%}")


class TestExitEngineThresholds:
    """Test that ExitEngine uses correct thresholds from config."""
    
    @pytest.fixture
    def exit_engine(self):
        """Create a fresh ExitEngine instance."""
        return ExitEngine()
    
    def test_decision_contains_correct_thresholds(self, exit_engine):
        """Verify ExitDecision contains the correct threshold values."""
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.51,  # Small gain
            position_size_usd=100.0,
            duration_hours=5.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.51,
            side='YES'
        )
        
        # Verify thresholds in decision
        assert decision.take_profit_threshold == 0.05, \
            f"Expected TP threshold 0.05, got {decision.take_profit_threshold}"
        assert decision.stop_loss_threshold == -0.05, \
            f"Expected SL threshold -0.05, got {decision.stop_loss_threshold}"
        assert decision.max_hours == 12, \
            f"Expected max_hours 12, got {decision.max_hours}"
        
        print(f"✅ Thresholds correct: TP={decision.take_profit_threshold}, "
              f"SL={decision.stop_loss_threshold}, max_hours={decision.max_hours}")
    
    def test_decision_to_dict(self, exit_engine):
        """Verify ExitDecision.to_dict() returns correct format."""
        decision = exit_engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.55,  # 10% gain
            position_size_usd=100.0,
            duration_hours=2.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.55,
            side='YES'
        )
        
        d = decision.to_dict()
        
        # Verify dict structure
        assert d['action'] == 'CLOSE_ALL'
        assert d['reason'] == 'take_profit'
        assert d['strategy'] == 'sports_arbitrage'
        assert d['asset_class'] == 'sports'
        assert d['zone'] == 'CORE'  # $0.50 is in CORE zone
        assert d['state'] == 'ACTIVE'
        assert d['pnl_pct'] == pytest.approx(0.10, rel=0.01)
        
        print(f"✅ to_dict() format correct: {d}")


class TestExitEngineStats:
    """Test ExitEngine statistics tracking."""
    
    def test_stats_increment_on_close(self):
        """Verify stats are incremented when positions close."""
        engine = ExitEngine()
        initial_stats = engine.get_stats()
        
        # Trigger a CLOSE_ALL (take profit)
        engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.55,  # 10% gain
            position_size_usd=100.0,
            duration_hours=2.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.55,
            side='YES'
        )
        
        final_stats = engine.get_stats()
        
        assert final_stats['total_checks'] == initial_stats['total_checks'] + 1
        assert final_stats['close_all'] == initial_stats['close_all'] + 1
        
        print(f"✅ Stats incremented: total_checks={final_stats['total_checks']}, "
              f"close_all={final_stats['close_all']}")
    
    def test_stats_increment_on_hold(self):
        """Verify stats are incremented when positions hold."""
        engine = ExitEngine()
        initial_stats = engine.get_stats()
        
        # Trigger a HOLD
        engine.check_exit(
            strategy='sports_arbitrage',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.51,  # 2% gain (within bounds)
            position_size_usd=100.0,
            duration_hours=5.0,
            current_spread_pct=0.01,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.51,
            side='YES'
        )
        
        final_stats = engine.get_stats()
        
        assert final_stats['total_checks'] == initial_stats['total_checks'] + 1
        assert final_stats['holds'] == initial_stats['holds'] + 1
        
        print(f"✅ Stats incremented: total_checks={final_stats['total_checks']}, "
              f"holds={final_stats['holds']}")


class TestUniversalExitEngineIntegration:
    """Test that the Universal Exit Engine code structure is correct."""
    
    def test_paper_trader_has_exit_engine(self):
        """Verify PaperTrader class has exit_engine in __init__."""
        # Instead of instantiating (which requires DB), verify the code structure
        import inspect
        from paper_trading.paper_trader import PaperTrader
        
        # Check that exit_engine is set in __init__
        source = inspect.getsource(PaperTrader.__init__)
        
        assert 'self.exit_engine' in source, \
            "PaperTrader.__init__ should set self.exit_engine"
        assert 'get_exit_engine()' in source, \
            "PaperTrader should use get_exit_engine() to initialize"
        
        print(f"✅ PaperTrader.__init__ sets self.exit_engine via get_exit_engine()")
    
    def test_exit_engine_config_has_sports(self):
        """Verify ExitEngine loads sports_arbitrage config."""
        engine = ExitEngine()
        
        assert 'sports_arbitrage' in engine.strategy_config, \
            "ExitEngine should have sports_arbitrage in strategy_config"
        
        config = engine.strategy_config['sports_arbitrage']
        assert config['type'] == 'mechanical'
        assert config['tp_pct'] == 0.05
        assert config['sl_pct'] == 0.05
        assert config['max_hours'] == 12
        
        print(f"✅ ExitEngine has sports_arbitrage config: {config}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
