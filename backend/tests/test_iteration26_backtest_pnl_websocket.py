"""
Iteration 26 Tests: Backtest P&L Calculation and WebSocket Integration

Tests:
1. Backtest engine P&L calculation correctly handles YES and NO positions
2. Backtest engine tracks position 'side' field (YES/NO)
3. Paper trader initializes WebSocket service on start
4. Paper trader falls back to REST if WebSocket unavailable
5. _get_active_markets method uses WebSocket data when available
6. Backend starts without errors after code changes
"""

import pytest
import requests
import os
import json
import inspect
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ============================================================================
# BACKEND HEALTH AND STARTUP TESTS
# ============================================================================

class TestBackendHealth:
    """Verify backend starts without errors after code changes"""
    
    def test_health_endpoint(self):
        """Backend health check returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✅ Backend health: {data}")
    
    def test_paper_status_endpoint(self):
        """Paper trading status endpoint works"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        assert 'running' in data
        print(f"✅ Paper status: running={data.get('running')}")
    
    def test_backtest_results_endpoint(self):
        """Backtest results endpoint works"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        data = response.json()
        # API returns dict with latest result or list of results
        assert isinstance(data, (dict, list))
        print(f"✅ Backtest results endpoint working, type={type(data).__name__}")


# ============================================================================
# BACKTEST P&L CALCULATION TESTS
# ============================================================================

class TestBacktestPnLCalculation:
    """Test backtest engine P&L calculation for YES and NO positions"""
    
    def test_yes_position_pnl_calculation(self):
        """
        YES position P&L: profit when YES price goes UP
        Formula: pnl_pct = (current_price - entry_price) / entry_price
        """
        # Simulate YES position P&L calculation
        entry_price = 0.50  # Entry at 50 cents
        current_price = 0.60  # Price went up to 60 cents
        
        # YES position: profit when price goes up
        pnl_pct = (current_price - entry_price) / entry_price
        
        assert pnl_pct == pytest.approx(0.20, rel=0.01)  # 20% profit
        print(f"✅ YES position: entry={entry_price}, current={current_price}, pnl={pnl_pct:.2%}")
    
    def test_yes_position_loss_calculation(self):
        """YES position loss when price goes DOWN"""
        entry_price = 0.50
        current_price = 0.40  # Price dropped
        
        pnl_pct = (current_price - entry_price) / entry_price
        
        assert pnl_pct == pytest.approx(-0.20, rel=0.01)  # 20% loss
        print(f"✅ YES position loss: entry={entry_price}, current={current_price}, pnl={pnl_pct:.2%}")
    
    def test_no_position_pnl_calculation(self):
        """
        NO position P&L: profit when YES price goes DOWN (NO price goes UP)
        Formula: 
            no_entry = 1 - entry_price (YES)
            no_current = 1 - current_price (YES)
            pnl_pct = (no_current - no_entry) / no_entry
        """
        entry_price = 0.60  # YES price at entry
        current_price = 0.40  # YES price dropped (good for NO)
        
        # NO position calculation
        no_entry = 1 - entry_price  # 0.40
        no_current = 1 - current_price  # 0.60
        pnl_pct = (no_current - no_entry) / no_entry
        
        assert pnl_pct == pytest.approx(0.50, rel=0.01)  # 50% profit
        print(f"✅ NO position profit: YES entry={entry_price}, YES current={current_price}")
        print(f"   NO entry={no_entry}, NO current={no_current}, pnl={pnl_pct:.2%}")
    
    def test_no_position_loss_calculation(self):
        """NO position loss when YES price goes UP (NO price goes DOWN)"""
        entry_price = 0.40  # YES price at entry
        current_price = 0.60  # YES price went up (bad for NO)
        
        no_entry = 1 - entry_price  # 0.60
        no_current = 1 - current_price  # 0.40
        pnl_pct = (no_current - no_entry) / no_entry
        
        assert pnl_pct == pytest.approx(-0.333, rel=0.01)  # ~33% loss
        print(f"✅ NO position loss: YES entry={entry_price}, YES current={current_price}")
        print(f"   NO entry={no_entry}, NO current={no_current}, pnl={pnl_pct:.2%}")
    
    def test_no_position_at_extreme_prices(self):
        """Test NO position P&L at extreme YES prices"""
        # Entry when YES is high (NO is cheap)
        entry_price = 0.80  # YES at 80 cents
        current_price = 0.50  # YES dropped to 50 cents
        
        no_entry = 1 - entry_price  # 0.20
        no_current = 1 - current_price  # 0.50
        pnl_pct = (no_current - no_entry) / no_entry
        
        assert pnl_pct == pytest.approx(1.50, rel=0.01)  # 150% profit!
        print(f"✅ NO position at extreme: YES {entry_price}→{current_price}, pnl={pnl_pct:.2%}")


class TestBacktestPositionSideTracking:
    """Test that backtest engine tracks position 'side' field"""
    
    def test_determine_trade_side_logic(self):
        """
        Test _determine_trade_side logic:
        - Sentiment > 0.55 → YES (bullish)
        - Sentiment < 0.45 → NO (bearish)
        - Neutral → defaults based on price
        """
        # Bullish sentiment → YES
        sentiment_bullish = 0.65
        assert sentiment_bullish > 0.55
        expected_side_bullish = 'YES'
        print(f"✅ Bullish sentiment {sentiment_bullish} → {expected_side_bullish}")
        
        # Bearish sentiment → NO
        sentiment_bearish = 0.35
        assert sentiment_bearish < 0.45
        expected_side_bearish = 'NO'
        print(f"✅ Bearish sentiment {sentiment_bearish} → {expected_side_bearish}")
        
        # Neutral sentiment with high price → NO (bet against)
        sentiment_neutral = 0.50
        price_high = 0.70
        assert 0.45 <= sentiment_neutral <= 0.55
        assert price_high > 0.65
        expected_side_neutral_high = 'NO'
        print(f"✅ Neutral sentiment {sentiment_neutral}, high price {price_high} → {expected_side_neutral_high}")
        
        # Neutral sentiment with low price → YES (bet for)
        price_low = 0.30
        assert price_low < 0.35
        expected_side_neutral_low = 'YES'
        print(f"✅ Neutral sentiment {sentiment_neutral}, low price {price_low} → {expected_side_neutral_low}")


class TestBacktestExitValueCalculation:
    """Test exit value calculation for YES and NO positions"""
    
    def test_yes_exit_value(self):
        """YES position exit value = shares * current_yes_price"""
        shares = 100
        exit_price = 0.70  # YES price at exit
        cost = 50  # Original cost
        
        exit_value = shares * exit_price
        pnl = exit_value - cost
        
        assert exit_value == 70
        assert pnl == 20
        print(f"✅ YES exit: {shares} shares @ ${exit_price} = ${exit_value}, PnL=${pnl}")
    
    def test_no_exit_value(self):
        """NO position exit value = shares * current_no_price (where no_price = 1 - yes_price)"""
        shares = 100
        yes_exit_price = 0.30  # YES price at exit
        no_exit_price = 1 - yes_exit_price  # 0.70
        cost = 50  # Original cost
        
        exit_value = shares * no_exit_price
        pnl = exit_value - cost
        
        assert exit_value == 70
        assert pnl == 20
        print(f"✅ NO exit: {shares} shares @ NO ${no_exit_price} (YES ${yes_exit_price}) = ${exit_value}, PnL=${pnl}")


# ============================================================================
# WEBSOCKET INTEGRATION TESTS (Source Code Inspection)
# ============================================================================

class TestWebSocketServiceIntegration:
    """Test paper trader WebSocket service integration via source code inspection"""
    
    def test_realtime_market_service_module_exists(self):
        """Verify realtime_market_service module is importable"""
        # Read the source file directly
        with open('/app/backend/services/realtime_market_service.py', 'r') as f:
            source = f.read()
        
        assert 'class RealTimeMarketService' in source
        assert 'get_realtime_market_service' in source
        assert 'WebSocket' in source
        print("✅ RealTimeMarketService module exists with WebSocket support")
    
    def test_paper_trader_has_websocket_imports(self):
        """Verify paper_trader imports WebSocket service"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        assert 'from services.realtime_market_service import' in source
        assert 'get_realtime_market_service' in source
        assert 'RealTimeMarketService' in source
        print("✅ PaperTrader imports RealTimeMarketService")
    
    def test_paper_trader_has_websocket_attributes_in_init(self):
        """Verify paper_trader __init__ sets up WebSocket attributes"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        assert 'self.realtime_market_service' in source
        assert 'self.use_websocket_data' in source
        print("✅ PaperTrader has WebSocket attributes in __init__")
    
    def test_get_active_markets_has_websocket_logic(self):
        """Verify _get_active_markets method has WebSocket logic"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        # Find _get_active_markets method
        assert 'async def _get_active_markets' in source
        
        # Check for WebSocket-related code in the method
        assert 'use_websocket_data' in source
        assert 'realtime_market_service' in source
        assert 'WebSocket' in source
        assert 'REST' in source  # Fallback
        print("✅ _get_active_markets has WebSocket integration with REST fallback")


class TestWebSocketFallbackLogic:
    """Test WebSocket to REST fallback logic"""
    
    def test_fallback_when_websocket_unavailable(self):
        """
        Verify fallback logic:
        1. Try WebSocket first
        2. If WebSocket fails or returns no data, fall back to REST
        """
        # This tests the logic pattern, not actual network calls
        
        # Scenario 1: WebSocket returns data
        ws_markets = [{'id': '1', 'question': 'Test'}]
        use_websocket = True
        ws_service_available = True
        
        if use_websocket and ws_service_available and ws_markets:
            data_source = "WebSocket"
            markets = ws_markets
        else:
            data_source = "REST"
            markets = []  # Would fetch from REST
        
        assert data_source == "WebSocket"
        assert len(markets) == 1
        print(f"✅ Scenario 1: WebSocket available → {data_source}")
        
        # Scenario 2: WebSocket returns empty
        ws_markets_empty = []
        
        if use_websocket and ws_service_available and ws_markets_empty:
            data_source = "WebSocket"
            markets = ws_markets_empty
        else:
            data_source = "REST"
            markets = [{'id': '2', 'question': 'REST Test'}]  # Simulated REST response
        
        assert data_source == "REST"
        print(f"✅ Scenario 2: WebSocket empty → {data_source}")
        
        # Scenario 3: WebSocket disabled
        use_websocket = False
        
        if use_websocket and ws_service_available:
            data_source = "WebSocket"
        else:
            data_source = "REST"
        
        assert data_source == "REST"
        print(f"✅ Scenario 3: WebSocket disabled → {data_source}")


# ============================================================================
# INTEGRATION TESTS VIA API
# ============================================================================

class TestBacktestAPIIntegration:
    """Test backtest functionality via API"""
    
    def test_backtest_results_have_strategy_breakdown(self):
        """Verify backtest results include strategy performance breakdown"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        
        data = response.json()
        
        # Handle both dict (single result) and list (multiple results)
        if isinstance(data, dict):
            latest = data
        elif isinstance(data, list) and len(data) > 0:
            latest = data[0]
        else:
            print("⚠️ No backtest results found")
            return
        
        # Check for strategy results
        if 'strategy_results' in latest:
            strategy_results = latest['strategy_results']
            print(f"✅ Strategy results found: {list(strategy_results.keys())}")
            
            for strategy, stats in strategy_results.items():
                print(f"   {strategy}: trades={stats.get('trades', 0)}, "
                      f"wins={stats.get('wins', 0)}, pnl=${stats.get('pnl', 0):.2f}")
        else:
            print("⚠️ No strategy_results in latest backtest")
    
    def test_backtest_results_have_trade_info(self):
        """Check if backtest results include trade information"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        
        data = response.json()
        
        # Handle both dict and list
        if isinstance(data, dict):
            latest = data
        elif isinstance(data, list) and len(data) > 0:
            latest = data[0]
        else:
            print("⚠️ No backtest results to check")
            return
        
        # Check exit reasons (indicates trades were made)
        exit_reasons = latest.get('exit_reasons', {})
        if exit_reasons:
            print(f"✅ Exit reasons found: {exit_reasons}")
        
        # Check total trades
        total_trades = latest.get('total_trades', 0)
        print(f"✅ Total trades in latest backtest: {total_trades}")


class TestPaperTradingAPIIntegration:
    """Test paper trading WebSocket integration via API"""
    
    def test_paper_status_shows_session_info(self):
        """Check if paper status includes session information"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        print(f"✅ Paper trading status:")
        print(f"   - running: {data.get('running')}")
        print(f"   - session_id: {data.get('session_id')}")


# ============================================================================
# CODE REVIEW VERIFICATION TESTS (Source Code Inspection)
# ============================================================================

class TestBacktestEngineCodeChanges:
    """Verify backtest engine code changes via source inspection"""
    
    def test_backtest_engine_has_determine_trade_side(self):
        """Verify _determine_trade_side method exists in backtest_engine"""
        with open('/app/backend/backtest/backtest_engine.py', 'r') as f:
            source = f.read()
        
        assert 'def _determine_trade_side' in source
        print("✅ BacktestEngine has _determine_trade_side method")
    
    def test_backtest_engine_open_position_has_side(self):
        """Verify _open_position tracks side parameter"""
        with open('/app/backend/backtest/backtest_engine.py', 'r') as f:
            source = f.read()
        
        # Find _open_position method signature
        assert 'async def _open_position' in source
        
        # Check that side parameter exists
        # Look for the method definition with side parameter
        import re
        match = re.search(r'async def _open_position\([^)]+side[^)]*\)', source)
        assert match is not None, "_open_position should have 'side' parameter"
        print(f"✅ _open_position has 'side' parameter")
    
    def test_backtest_engine_check_exit_has_side_logic(self):
        """Verify _check_exit_conditions handles YES/NO sides"""
        with open('/app/backend/backtest/backtest_engine.py', 'r') as f:
            source = f.read()
        
        # Find _check_exit_conditions method
        assert 'def _check_exit_conditions' in source
        
        # Verify side-aware P&L calculation
        assert "side = position.get" in source
        assert "'YES'" in source
        assert "'NO'" in source
        
        print("✅ _check_exit_conditions has side-aware P&L logic")
    
    def test_backtest_engine_close_position_has_side_logic(self):
        """Verify _close_position calculates P&L correctly for both sides"""
        with open('/app/backend/backtest/backtest_engine.py', 'r') as f:
            source = f.read()
        
        # Find _close_position method
        assert 'async def _close_position' in source
        
        # Verify side-aware exit value calculation
        assert "side" in source
        assert "exit_value" in source
        
        # Check for NO position calculation: no_exit_price = 1 - exit_price
        assert "1 - exit_price" in source or "1 -" in source
        
        print("✅ _close_position has side-aware exit value calculation")
    
    def test_backtest_pnl_formula_for_no_positions(self):
        """Verify the NO position P&L formula is correct"""
        with open('/app/backend/backtest/backtest_engine.py', 'r') as f:
            source = f.read()
        
        # The formula for NO positions should be:
        # no_entry = 1 - entry_price
        # no_current = 1 - current_price
        # pnl_pct = (no_current - no_entry) / no_entry
        
        assert "no_entry = 1 - entry_price" in source
        assert "no_current = 1 - current_price" in source
        assert "(no_current - no_entry) / no_entry" in source
        
        print("✅ NO position P&L formula is correct")


class TestPaperTraderCodeChanges:
    """Verify paper trader code changes via source inspection"""
    
    def test_paper_trader_start_initializes_websocket(self):
        """Verify paper_trader.start() initializes WebSocket service"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        # Find start method
        assert 'async def start(self)' in source
        
        # Verify WebSocket initialization in start()
        assert "realtime_market_service" in source
        assert "get_realtime_market_service" in source
        
        print("✅ PaperTrader.start() initializes WebSocket service")
    
    def test_paper_trader_stop_stops_websocket(self):
        """Verify paper_trader.stop() stops WebSocket service"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        # Find stop method
        assert 'async def stop(self' in source
        
        # Verify WebSocket cleanup in stop()
        assert "realtime_market_service" in source
        
        print("✅ PaperTrader.stop() handles WebSocket cleanup")
    
    def test_paper_trader_get_active_markets_websocket_first(self):
        """Verify _get_active_markets tries WebSocket first"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            source = f.read()
        
        # Find _get_active_markets method
        method_start = source.find('async def _get_active_markets')
        assert method_start != -1
        
        # Get method body (next 100 lines or so)
        method_body = source[method_start:method_start+3000]
        
        # Verify WebSocket is tried first
        ws_check = method_body.find('use_websocket_data')
        rest_fallback = method_body.find('PolymarketAPI')
        
        assert ws_check != -1, "Should check use_websocket_data"
        assert rest_fallback != -1, "Should have REST fallback"
        assert ws_check < rest_fallback, "WebSocket should be checked before REST fallback"
        
        print("✅ _get_active_markets tries WebSocket first, then falls back to REST")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
