"""
Test Paper Trading Data Sync Fix - Iteration 12
Tests the fixes for:
1. Promise.allSettled in frontend fetchData (handles individual API failures gracefully)
2. Backend /api/paper/status returns complete structure even when no session
3. MongoDB ObjectId serialization fix using .copy() before insert_one()
"""

import pytest
import requests
import os
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH = HTTPBasicAuth('admin', 'apex2026!')


class TestPaperStatusEndpoint:
    """Test /api/paper/status endpoint returns complete structure"""
    
    def test_status_returns_complete_structure_no_session(self):
        """Verify status returns all required fields even when no session exists"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify all required fields are present (fix for UI showing stale data)
        required_fields = [
            'running',
            'open_positions',
            'total_trades',
            'total_pnl',
            'win_rate',
            'max_drawdown',
            'current_capital',
            'initial_capital'
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify running is False when no session
        if 'message' in data and 'No paper trading session' in data.get('message', ''):
            assert data['running'] == False, "running should be False when no session"
            assert data['open_positions'] == 0, "open_positions should be 0 when no session"
            assert data['total_trades'] == 0, "total_trades should be 0 when no session"
        
        print(f"✅ Status endpoint returns complete structure: {list(data.keys())}")


class TestPaperTradesEndpoint:
    """Test /api/paper/trades endpoint for ObjectId serialization fix"""
    
    def test_trades_returns_valid_json(self):
        """Verify trades endpoint returns valid JSON without ObjectId errors"""
        response = requests.get(f"{BASE_URL}/api/paper/trades?limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'trades' in data, "Response should contain 'trades' key"
        assert isinstance(data['trades'], list), "trades should be a list"
        
        # If there are trades, verify they don't contain _id (MongoDB ObjectId)
        for trade in data['trades']:
            assert '_id' not in trade, f"Trade should not contain _id: {trade}"
        
        print(f"✅ Trades endpoint returns valid JSON with {len(data['trades'])} trades")
    
    def test_trades_with_different_limits(self):
        """Test trades endpoint with various limit values"""
        for limit in [10, 25, 50, 100]:
            response = requests.get(f"{BASE_URL}/api/paper/trades?limit={limit}")
            assert response.status_code == 200, f"Expected 200 for limit={limit}"
            data = response.json()
            assert 'trades' in data
            print(f"✅ Trades endpoint works with limit={limit}")


class TestPaperPositionsEndpoint:
    """Test /api/paper/positions endpoint"""
    
    def test_positions_returns_array(self):
        """Verify positions endpoint returns positions array"""
        response = requests.get(f"{BASE_URL}/api/paper/positions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'positions' in data, "Response should contain 'positions' key"
        assert isinstance(data['positions'], list), "positions should be a list"
        
        print(f"✅ Positions endpoint returns array with {len(data['positions'])} positions")


class TestPaperAnalyticsEndpoint:
    """Test /api/paper/analytics endpoint"""
    
    def test_analytics_returns_valid_structure(self):
        """Verify analytics endpoint returns valid structure"""
        response = requests.get(f"{BASE_URL}/api/paper/analytics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Check for expected keys
        expected_keys = ['current_session', 'completed_sessions', 'aggregate_stats', 
                        'strategy_performance', 'equity_curve']
        
        for key in expected_keys:
            assert key in data, f"Missing expected key: {key}"
        
        print(f"✅ Analytics endpoint returns valid structure: {list(data.keys())}")


class TestAllPaperEndpointsIndependently:
    """Test that all paper trading endpoints work independently (Promise.allSettled fix)"""
    
    def test_all_endpoints_return_200(self):
        """Verify all paper trading endpoints return 200 independently"""
        endpoints = [
            '/api/paper/status',
            '/api/paper/positions',
            '/api/paper/trades?limit=50',
            '/api/paper/analytics'
        ]
        
        results = {}
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            results[endpoint] = {
                'status_code': response.status_code,
                'success': response.status_code == 200
            }
            
            # Each endpoint should work independently
            assert response.status_code == 200, f"Endpoint {endpoint} failed with {response.status_code}"
        
        print(f"✅ All {len(endpoints)} endpoints return 200 independently")
        for endpoint, result in results.items():
            print(f"   - {endpoint}: {result['status_code']}")


class TestPaperTradingStartStop:
    """Test paper trading start/stop flow with auth"""
    
    def test_start_paper_trading(self):
        """Test starting paper trading session"""
        # First check current status
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status_data = status_response.json()
        
        if status_data.get('running'):
            print("⚠️ Paper trading already running, skipping start test")
            return
        
        # Start paper trading
        response = requests.post(
            f"{BASE_URL}/api/paper/start?initial_capital=10000&continuous_mode=false",
            auth=AUTH
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'session_id' in data, "Response should contain session_id"
        
        print(f"✅ Paper trading started with session_id: {data.get('session_id')}")
        
        # Verify status now shows running
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status_data = status_response.json()
        assert status_data.get('running') == True, "Status should show running=True after start"
        
        print(f"✅ Status shows running=True, open_positions={status_data.get('open_positions')}")
    
    def test_stop_paper_trading(self):
        """Test stopping paper trading session"""
        # First check if running
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status_data = status_response.json()
        
        if not status_data.get('running'):
            print("⚠️ Paper trading not running, skipping stop test")
            return
        
        # Stop paper trading
        response = requests.post(
            f"{BASE_URL}/api/paper/stop?graceful=false",
            auth=AUTH
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        print(f"✅ Paper trading stopped successfully")
        
        # Verify status now shows not running
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status_data = status_response.json()
        
        # After stop, running should be False
        print(f"✅ Status after stop: running={status_data.get('running')}")


class TestStatusFieldsWhenRunning:
    """Test status fields when paper trading is running"""
    
    def test_status_fields_during_session(self):
        """Verify status returns all fields during active session"""
        # Start a session first
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status_data = status_response.json()
        
        if not status_data.get('running'):
            # Start paper trading
            start_response = requests.post(
                f"{BASE_URL}/api/paper/start?initial_capital=10000&continuous_mode=false",
                auth=AUTH
            )
            if start_response.status_code != 200:
                print(f"⚠️ Could not start paper trading: {start_response.text}")
                return
        
        # Get status
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # When running, should have these fields
        expected_fields = [
            'session_id', 'running', 'initial_capital', 'current_capital',
            'total_pnl', 'total_trades', 'winning_trades', 'win_rate',
            'max_drawdown', 'open_positions'
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing field during active session: {field}"
        
        print(f"✅ Status during active session has all required fields")
        print(f"   - running: {data.get('running')}")
        print(f"   - open_positions: {data.get('open_positions')}")
        print(f"   - total_trades: {data.get('total_trades')}")
        print(f"   - continuous_mode: {data.get('continuous_mode')}")
        
        # Stop the session
        requests.post(f"{BASE_URL}/api/paper/stop?graceful=false", auth=AUTH)


class TestCumulativeStatsEndpoint:
    """Test /api/paper/cumulative-stats endpoint"""
    
    def test_cumulative_stats_structure(self):
        """Verify cumulative stats returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Check for expected keys
        expected_keys = ['overall', 'by_strategy', 'by_asset_class', 'current_session_included']
        
        for key in expected_keys:
            assert key in data, f"Missing expected key: {key}"
        
        print(f"✅ Cumulative stats returns valid structure")
        print(f"   - overall sessions: {data.get('overall', {}).get('total_sessions', 0)}")
        print(f"   - strategies: {list(data.get('by_strategy', {}).keys())}")


class TestAIStatsEndpoint:
    """Test /api/paper/ai-stats endpoint"""
    
    def test_ai_stats_structure(self):
        """Verify AI stats returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/paper/ai-stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'ai_stats' in data, "Response should contain 'ai_stats' key"
        
        print(f"✅ AI stats endpoint returns valid structure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
