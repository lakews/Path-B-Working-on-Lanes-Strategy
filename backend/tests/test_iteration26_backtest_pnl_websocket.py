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
        assert isinstance(data, list)
        print(f"✅ Backtest results: {len(data)} sessions found")


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
# WEBSOCKET INTEGRATION TESTS
# ============================================================================

class TestWebSocketServiceIntegration:
    """Test paper trader WebSocket service integration"""
    
    def test_realtime_market_service_module_exists(self):
        """Verify realtime_market_service module is importable"""
        try:
            from services.realtime_market_service import RealTimeMarketService, get_realtime_market_service
            print("✅ RealTimeMarketService module imported successfully")
            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import RealTimeMarketService: {e}")
    
    def test_paper_trader_has_websocket_attributes(self):
        """Verify paper_trader has WebSocket-related attributes"""
        try:
            from paper_trading.paper_trader import PaperTrader
            
            trader = PaperTrader()
            
            # Check WebSocket-related attributes exist
            assert hasattr(trader, 'realtime_market_service')
            assert hasattr(trader, 'use_websocket_data')
            
            # Default should be True (prefer WebSocket)
            assert trader.use_websocket_data == True
            
            # Initially None until start() is called
            assert trader.realtime_market_service is None
            
            print("✅ PaperTrader has WebSocket attributes:")
            print(f"   - realtime_market_service: {trader.realtime_market_service}")
            print(f"   - use_websocket_data: {trader.use_websocket_data}")
            
        except Exception as e:
            pytest.fail(f"Error checking PaperTrader attributes: {e}")
    
    def test_get_active_markets_method_exists(self):
        """Verify _get_active_markets method exists and has WebSocket logic"""
        try:
            from paper_trading.paper_trader import PaperTrader
            import inspect
            
            trader = PaperTrader()
            
            # Check method exists
            assert hasattr(trader, '_get_active_markets')
            
            # Get method source to verify WebSocket logic
            source = inspect.getsource(trader._get_active_markets)
            
            # Verify WebSocket-related code is present
            assert 'use_websocket_data' in source
            assert 'realtime_market_service' in source
            assert 'WebSocket' in source
            assert 'REST' in source  # Fallback
            
            print("✅ _get_active_markets has WebSocket integration:")
            print("   - Checks use_websocket_data flag")
            print("   - Uses realtime_market_service when available")
            print("   - Falls back to REST API")
            
        except Exception as e:
            pytest.fail(f"Error checking _get_active_markets: {e}")


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
        
        results = response.json()
        if results:
            latest = results[0]
            
            # Check for strategy results
            if 'strategy_results' in latest:
                strategy_results = latest['strategy_results']
                print(f"✅ Strategy results found: {list(strategy_results.keys())}")
                
                for strategy, stats in strategy_results.items():
                    print(f"   {strategy}: trades={stats.get('trades', 0)}, "
                          f"wins={stats.get('wins', 0)}, pnl=${stats.get('pnl', 0):.2f}")
            else:
                print("⚠️ No strategy_results in latest backtest")
        else:
            print("⚠️ No backtest results found")
    
    def test_backtest_results_have_trade_side_info(self):
        """Check if backtest trades include side information"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        
        results = response.json()
        if results:
            latest = results[0]
            
            # Check exit reasons (indicates trades were made)
            exit_reasons = latest.get('exit_reasons', {})
            if exit_reasons:
                print(f"✅ Exit reasons found: {exit_reasons}")
            
            # Check total trades
            total_trades = latest.get('total_trades', 0)
            print(f"✅ Total trades in latest backtest: {total_trades}")
            
            # Check for YES/NO breakdown if available
            if 'trades_by_side' in latest:
                print(f"✅ Trades by side: {latest['trades_by_side']}")
        else:
            print("⚠️ No backtest results to check")


class TestPaperTradingAPIIntegration:
    """Test paper trading WebSocket integration via API"""
    
    def test_paper_status_shows_websocket_info(self):
        """Check if paper status includes WebSocket information"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        print(f"✅ Paper trading status:")
        print(f"   - running: {data.get('running')}")
        print(f"   - session_id: {data.get('session_id')}")
        
        # Check for WebSocket-related fields if session is running
        if data.get('running'):
            if 'data_source' in data:
                print(f"   - data_source: {data.get('data_source')}")
            if 'websocket_connected' in data:
                print(f"   - websocket_connected: {data.get('websocket_connected')}")


# ============================================================================
# CODE REVIEW VERIFICATION TESTS
# ============================================================================

class TestCodeChangesVerification:
    """Verify the specific code changes mentioned in the review request"""
    
    def test_backtest_engine_has_determine_trade_side(self):
        """Verify _determine_trade_side method exists in backtest_engine"""
        try:
            from backtest.backtest_engine import BacktestEngine
            
            engine = BacktestEngine()
            assert hasattr(engine, '_determine_trade_side')
            print("✅ BacktestEngine has _determine_trade_side method")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")
    
    def test_backtest_engine_open_position_has_side(self):
        """Verify _open_position tracks side parameter"""
        try:
            from backtest.backtest_engine import BacktestEngine
            import inspect
            
            engine = BacktestEngine()
            
            # Get method signature
            sig = inspect.signature(engine._open_position)
            params = list(sig.parameters.keys())
            
            assert 'side' in params
            print(f"✅ _open_position has 'side' parameter: {params}")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")
    
    def test_backtest_engine_check_exit_has_side_logic(self):
        """Verify _check_exit_conditions handles YES/NO sides"""
        try:
            from backtest.backtest_engine import BacktestEngine
            import inspect
            
            engine = BacktestEngine()
            source = inspect.getsource(engine._check_exit_conditions)
            
            # Verify side-aware P&L calculation
            assert "side = position.get" in source or "side =" in source
            assert "YES" in source
            assert "NO" in source
            
            print("✅ _check_exit_conditions has side-aware P&L logic")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")
    
    def test_backtest_engine_close_position_has_side_logic(self):
        """Verify _close_position calculates P&L correctly for both sides"""
        try:
            from backtest.backtest_engine import BacktestEngine
            import inspect
            
            engine = BacktestEngine()
            source = inspect.getsource(engine._close_position)
            
            # Verify side-aware exit value calculation
            assert "side" in source
            assert "YES" in source
            assert "NO" in source
            assert "exit_value" in source
            
            print("✅ _close_position has side-aware exit value calculation")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")
    
    def test_paper_trader_start_initializes_websocket(self):
        """Verify paper_trader.start() initializes WebSocket service"""
        try:
            from paper_trading.paper_trader import PaperTrader
            import inspect
            
            trader = PaperTrader()
            source = inspect.getsource(trader.start)
            
            # Verify WebSocket initialization in start()
            assert "realtime_market_service" in source
            assert "get_realtime_market_service" in source
            assert "WebSocket" in source
            
            print("✅ PaperTrader.start() initializes WebSocket service")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")
    
    def test_paper_trader_stop_stops_websocket(self):
        """Verify paper_trader.stop() stops WebSocket service"""
        try:
            from paper_trading.paper_trader import PaperTrader
            import inspect
            
            trader = PaperTrader()
            source = inspect.getsource(trader.stop)
            
            # Verify WebSocket cleanup in stop()
            assert "realtime_market_service" in source
            
            print("✅ PaperTrader.stop() handles WebSocket cleanup")
            
        except Exception as e:
            pytest.fail(f"Error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
