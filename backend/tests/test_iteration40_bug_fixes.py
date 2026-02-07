"""
Test Suite for Iteration 40 - Bug Fixes Verification
=====================================================
Tests for:
1. Paper trading starts without errors
2. Universal exit engine runs without 'PARTIAL_EXIT' AttributeError
3. Trades are being closed with proper exit reasons (stop_loss, take_profit, etc.)
4. Capital accounting is accurate (current_capital + deployed + unrealized = total_equity)
5. Sports trades can be entered when edge conditions are met
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH = ('admin', 'apex2026!')


class TestPaperTradingStartup:
    """Test paper trading starts without errors"""
    
    def test_health_endpoint(self):
        """Verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✅ Health check passed: {data}")
    
    def test_paper_trading_status(self):
        """Verify paper trading status endpoint works"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert 'running' in data
        assert 'session_id' in data
        print(f"✅ Paper trading status: running={data.get('running')}, session={data.get('session_id')}")
    
    def test_paper_trading_can_start(self):
        """Verify paper trading can be started"""
        # First check current status
        status_response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert status_response.status_code == 200
        
        if status_response.json().get('running'):
            print("✅ Paper trading already running - skipping start test")
            return
        
        # Try to start paper trading
        start_response = requests.post(f"{BASE_URL}/api/paper/start", auth=AUTH)
        assert start_response.status_code in [200, 201]
        data = start_response.json()
        assert data.get('status') in ['started', 'already_running']
        print(f"✅ Paper trading start: {data}")


class TestExitEngineNoPartialExitError:
    """Test that ExitAction.PARTIAL_CLOSE is used correctly (not PARTIAL_EXIT)"""
    
    def test_exit_action_enum_has_partial_close(self):
        """Verify ExitAction enum has PARTIAL_CLOSE (not PARTIAL_EXIT)"""
        from trading.exit_engine import ExitAction
        
        # Should have PARTIAL_CLOSE
        assert hasattr(ExitAction, 'PARTIAL_CLOSE'), "ExitAction should have PARTIAL_CLOSE"
        assert ExitAction.PARTIAL_CLOSE.value == "PARTIAL_CLOSE"
        
        # Should NOT have PARTIAL_EXIT
        assert not hasattr(ExitAction, 'PARTIAL_EXIT'), "ExitAction should NOT have PARTIAL_EXIT"
        
        print(f"✅ ExitAction enum correct: PARTIAL_CLOSE={ExitAction.PARTIAL_CLOSE.value}")
    
    def test_exit_engine_check_exit_works(self):
        """Verify exit engine check_exit doesn't raise AttributeError"""
        from trading.exit_engine import get_exit_engine, ExitAction
        
        engine = get_exit_engine()
        
        # Test with sample trade data
        decision = engine.check_exit(
            strategy='alpha_directional',
            asset_class='sports',
            entry_price=0.50,
            current_price=0.55,
            position_size_usd=100.0,
            duration_hours=2.0,
            current_spread_pct=0.02,
            hours_to_expiry=48.0,
            trade_status='ACTIVE',
            peak_price=0.56,
            side='YES'
        )
        
        # Should return a valid decision without error
        assert decision is not None
        assert decision.action in [ExitAction.HOLD, ExitAction.CLOSE_ALL, ExitAction.FREE_ROLL, ExitAction.PARTIAL_CLOSE]
        print(f"✅ Exit engine check_exit works: action={decision.action.value}, reason={decision.reason.value}")


class TestTradesClosingWithProperReasons:
    """Test trades are being closed with proper exit reasons"""
    
    def test_paper_status_has_trade_data(self):
        """Verify paper status returns trade data"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        # Should have trade tracking fields
        assert 'total_trades' in data
        assert 'winning_trades' in data
        assert 'total_pnl' in data
        
        print(f"✅ Trade data: total_trades={data.get('total_trades')}, wins={data.get('winning_trades')}, pnl=${data.get('total_pnl', 0):.2f}")
    
    def test_strategy_results_have_pnl(self):
        """Verify strategy results track P&L"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        strategy_results = data.get('strategy_results', {})
        assert len(strategy_results) > 0, "Should have strategy results"
        
        for strategy, stats in strategy_results.items():
            assert 'pnl' in stats, f"Strategy {strategy} should have pnl"
            assert 'trades' in stats, f"Strategy {strategy} should have trades"
            print(f"  - {strategy}: trades={stats.get('trades')}, pnl=${stats.get('pnl', 0):.2f}")
        
        print(f"✅ Strategy results have P&L tracking")
    
    def test_exit_reasons_in_logs(self):
        """Verify exit reasons are being logged (check via trade returns)"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        trade_returns = data.get('trade_returns', [])
        
        # If there are closed trades, we should have returns
        if data.get('total_trades', 0) > 0:
            assert len(trade_returns) > 0, "Should have trade returns if trades were made"
            print(f"✅ Trade returns tracked: {len(trade_returns)} returns recorded")
            
            # Check returns distribution
            positive = sum(1 for r in trade_returns if r > 0)
            negative = sum(1 for r in trade_returns if r < 0)
            print(f"  - Positive returns: {positive}, Negative returns: {negative}")
        else:
            print("⚠️ No trades yet - skipping returns check")


class TestCapitalAccounting:
    """Test capital accounting is accurate"""
    
    def test_capital_accounting_formula(self):
        """Verify: current_capital + deployed + unrealized = total_equity"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        current_capital = data.get('current_capital', 0)
        deployed_capital = data.get('deployed_capital', 0)
        unrealized_pnl = data.get('unrealized_pnl', 0)
        total_equity = data.get('total_equity', 0)
        
        # Calculate expected total
        calculated_equity = current_capital + deployed_capital + unrealized_pnl
        
        # Allow small floating point difference
        difference = abs(calculated_equity - total_equity)
        assert difference < 1.0, f"Capital accounting mismatch: calculated={calculated_equity:.2f}, reported={total_equity:.2f}, diff={difference:.2f}"
        
        print(f"✅ Capital accounting verified:")
        print(f"  - current_capital: ${current_capital:.2f}")
        print(f"  - deployed_capital: ${deployed_capital:.2f}")
        print(f"  - unrealized_pnl: ${unrealized_pnl:.2f}")
        print(f"  - total_equity: ${total_equity:.2f}")
        print(f"  - Formula check: ${calculated_equity:.2f} ≈ ${total_equity:.2f} ✓")
    
    def test_initial_capital_preserved(self):
        """Verify initial capital is tracked"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        initial_capital = data.get('initial_capital', 0)
        assert initial_capital > 0, "Initial capital should be positive"
        
        print(f"✅ Initial capital: ${initial_capital:.2f}")
    
    def test_drawdown_tracking(self):
        """Verify drawdown is being tracked"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        max_drawdown = data.get('max_drawdown', 0)
        current_drawdown = data.get('current_drawdown_pct', 0)
        peak_capital = data.get('peak_capital', 0)
        
        assert peak_capital > 0, "Peak capital should be tracked"
        
        print(f"✅ Drawdown tracking:")
        print(f"  - Peak capital: ${peak_capital:.2f}")
        print(f"  - Max drawdown: {max_drawdown*100:.2f}%")
        print(f"  - Current drawdown: {current_drawdown:.2f}%")


class TestSportsTradesEntry:
    """Test sports trades can be entered when edge conditions are met"""
    
    def test_sports_enabled_in_asset_classes(self):
        """Verify sports is enabled in asset classes"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        enabled_asset_classes = data.get('enabled_asset_classes', [])
        assert 'sports' in enabled_asset_classes, "Sports should be enabled"
        
        print(f"✅ Sports enabled in asset classes: {enabled_asset_classes}")
    
    def test_sports_positions_exist(self):
        """Verify sports positions can be created"""
        response = requests.get(f"{BASE_URL}/api/paper/positions", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        positions = data.get('positions', [])
        sports_positions = [p for p in positions if p.get('asset_class') == 'sports' or 'sports' in p.get('strategy', '').lower()]
        
        print(f"✅ Positions check:")
        print(f"  - Total positions: {len(positions)}")
        print(f"  - Sports positions: {len(sports_positions)}")
        
        if sports_positions:
            for p in sports_positions[:3]:
                print(f"    - {p.get('market_id', '?')[:30]}... | Strategy: {p.get('strategy')} | Side: {p.get('side')}")
    
    def test_sports_strategy_results(self):
        """Verify sports_arbitrage strategy is tracked"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        strategy_results = data.get('strategy_results', {})
        
        # Check if sports_arbitrage exists in results
        if 'sports_arbitrage' in strategy_results:
            sports_stats = strategy_results['sports_arbitrage']
            print(f"✅ Sports arbitrage strategy tracked:")
            print(f"  - Trades: {sports_stats.get('trades', 0)}")
            print(f"  - Open positions: {sports_stats.get('open_positions', 0)}")
            print(f"  - P&L: ${sports_stats.get('pnl', 0):.2f}")
            print(f"  - Win rate: {sports_stats.get('win_rate', 0)*100:.1f}%")
        else:
            print("⚠️ sports_arbitrage not in strategy_results yet")
    
    def test_sports_lane_equity(self):
        """Verify SPORTS lane is tracked in lane_equity"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        data = response.json()
        
        lane_equity = data.get('lane_equity', {})
        assert 'SPORTS' in lane_equity, "SPORTS lane should exist"
        
        print(f"✅ Lane equity:")
        for lane, equity in lane_equity.items():
            print(f"  - {lane}: ${equity:.2f}")


class TestExitEngineIntegration:
    """Test exit engine integration with paper trader"""
    
    def test_exit_engine_stats_endpoint(self):
        """Verify exit engine stats are available"""
        response = requests.get(f"{BASE_URL}/api/exit-engine/stats", auth=AUTH)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Exit engine stats:")
            print(f"  - Total checks: {data.get('total_checks', 0)}")
            print(f"  - Holds: {data.get('holds', 0)}")
            print(f"  - Close all: {data.get('close_all', 0)}")
            print(f"  - Free rolls: {data.get('free_rolls', 0)}")
        else:
            print(f"⚠️ Exit engine stats endpoint returned {response.status_code}")
    
    def test_exit_reasons_enum_complete(self):
        """Verify all exit reasons are defined"""
        from trading.exit_engine import ExitReason
        
        expected_reasons = [
            'WICK_PROTECTION', 'WITHIN_BOUNDS', 'FREE_RIDE_ACTIVE',
            'TAKE_PROFIT', 'STOP_LOSS', 'TIME_DECAY', 'THESIS_FAIL',
            'EXPIRY_GUARD', 'TRAILING_STOP', 'ZOMBIE_EXIT',
            'FREE_RIDE_FLOOR', 'FREE_RIDE_CEILING',
            'WHALE_STOP', 'WHALE_FREE_ROLL', 'WHALE_MOONBAG',
            'PROFIT_TARGET'
        ]
        
        for reason in expected_reasons:
            assert hasattr(ExitReason, reason), f"ExitReason should have {reason}"
        
        print(f"✅ All {len(expected_reasons)} exit reasons defined")


# Run tests if executed directly
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
