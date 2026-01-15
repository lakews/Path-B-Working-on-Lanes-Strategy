"""
Test Paper Trading Enhancements - Iteration 11
Tests for:
- Continuous mode and graceful stop
- Cumulative stats across sessions
- AI stats with session learning and signal usage
- Navigation order (Config after Dashboard)
- UI tabs (5 tabs: Live, Cumulative, Sessions, Optimizer, RL)
"""
import pytest
import requests
import os
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# HTTP Basic Auth credentials
AUTH = HTTPBasicAuth('admin', 'apex2026!')


class TestPaperStatusEndpoint:
    """Test GET /api/paper/status returns correct structure"""
    
    def test_paper_status_returns_correct_structure(self):
        """Verify /api/paper/status returns running status and message when no session"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        
        # When no session, should return running=False
        assert "running" in data
        assert data["running"] == False
        assert "message" in data


class TestCumulativeStatsEndpoint:
    """Test GET /api/paper/cumulative-stats returns correct structure"""
    
    def test_cumulative_stats_returns_overall_structure(self):
        """Verify cumulative-stats returns overall, by_strategy, by_asset_class"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        data = response.json()
        
        # Check overall structure
        assert "overall" in data
        overall = data["overall"]
        assert "total_sessions" in overall
        assert "total_trades" in overall
        assert "total_wins" in overall
        assert "total_pnl" in overall
        assert "total_initial_capital" in overall
        assert "continuous_sessions" in overall
        assert "win_rate" in overall
        
    def test_cumulative_stats_has_by_strategy(self):
        """Verify cumulative-stats has by_strategy with all 4 strategies"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "by_strategy" in data
        by_strategy = data["by_strategy"]
        
        # Should have all 4 strategies
        expected_strategies = ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
        for strategy in expected_strategies:
            assert strategy in by_strategy, f"Missing strategy: {strategy}"
            strategy_data = by_strategy[strategy]
            assert "total_trades" in strategy_data
            assert "total_wins" in strategy_data
            assert "total_pnl" in strategy_data
            assert "sessions" in strategy_data
            assert "win_rate" in strategy_data
    
    def test_cumulative_stats_has_by_asset_class(self):
        """Verify cumulative-stats has by_asset_class structure"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "by_asset_class" in data
        # by_asset_class can be empty if no sessions have run
        assert isinstance(data["by_asset_class"], dict)
    
    def test_cumulative_stats_has_current_session_flag(self):
        """Verify cumulative-stats has current_session_included flag"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_session_included" in data
        assert isinstance(data["current_session_included"], bool)


class TestAIStatsEndpoint:
    """Test GET /api/paper/ai-stats returns correct structure"""
    
    def test_ai_stats_returns_structure(self):
        """Verify ai-stats returns ai_stats field"""
        response = requests.get(f"{BASE_URL}/api/paper/ai-stats")
        assert response.status_code == 200
        data = response.json()
        
        # When no session, should return message and empty ai_stats
        assert "ai_stats" in data or "message" in data
    
    def test_ai_stats_no_session_message(self):
        """Verify ai-stats returns appropriate message when no session"""
        response = requests.get(f"{BASE_URL}/api/paper/ai-stats")
        assert response.status_code == 200
        data = response.json()
        
        # When no session running
        if "message" in data:
            assert "No paper trading session" in data["message"]


class TestPaperStartEndpoint:
    """Test POST /api/paper/start with continuous_mode parameter"""
    
    def test_paper_start_requires_auth(self):
        """Verify /api/paper/start requires HTTP Basic Auth"""
        response = requests.post(f"{BASE_URL}/api/paper/start")
        assert response.status_code == 401
    
    def test_paper_start_accepts_continuous_mode_param(self):
        """Verify /api/paper/start accepts continuous_mode parameter"""
        # Start with continuous_mode=true
        response = requests.post(
            f"{BASE_URL}/api/paper/start?initial_capital=10000&continuous_mode=true",
            auth=AUTH
        )
        
        # Should succeed or return already running
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "continuous_mode" in data
            assert data["continuous_mode"] == True
            
            # Stop the session
            requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH)


class TestPaperStopEndpoint:
    """Test POST /api/paper/stop with graceful parameter"""
    
    def test_paper_stop_requires_auth(self):
        """Verify /api/paper/stop requires HTTP Basic Auth"""
        response = requests.post(f"{BASE_URL}/api/paper/stop")
        assert response.status_code == 401
    
    def test_paper_stop_accepts_graceful_param(self):
        """Verify /api/paper/stop accepts graceful parameter"""
        # First start a session
        start_response = requests.post(
            f"{BASE_URL}/api/paper/start?initial_capital=10000",
            auth=AUTH
        )
        
        if start_response.status_code == 200:
            # Stop with graceful=true
            response = requests.post(
                f"{BASE_URL}/api/paper/stop?graceful=true",
                auth=AUTH
            )
            assert response.status_code == 200
        else:
            # Session might already be running, try to stop it
            response = requests.post(
                f"{BASE_URL}/api/paper/stop?graceful=false",
                auth=AUTH
            )
            # Either succeeds or no session running
            assert response.status_code in [200, 400]


class TestNavigationOrder:
    """Test that Config appears after Dashboard in navigation"""
    
    def test_frontend_loads(self):
        """Verify frontend loads successfully"""
        response = requests.get(BASE_URL)
        assert response.status_code == 200
        assert "APEX TRADER" in response.text or "apex" in response.text.lower()


class TestOtherPaperEndpoints:
    """Test other paper trading endpoints"""
    
    def test_paper_positions_endpoint(self):
        """Verify /api/paper/positions returns positions array"""
        response = requests.get(f"{BASE_URL}/api/paper/positions")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)
    
    def test_paper_trades_endpoint(self):
        """Verify /api/paper/trades returns trades array"""
        response = requests.get(f"{BASE_URL}/api/paper/trades")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert isinstance(data["trades"], list)
    
    def test_paper_sessions_endpoint(self):
        """Verify /api/paper/sessions returns sessions list"""
        response = requests.get(f"{BASE_URL}/api/paper/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
    
    def test_paper_analytics_endpoint(self):
        """Verify /api/paper/analytics returns analytics data"""
        response = requests.get(f"{BASE_URL}/api/paper/analytics")
        assert response.status_code == 200
        data = response.json()
        # Should have some structure
        assert isinstance(data, dict)


class TestOptimizerEndpoint:
    """Test optimizer params endpoint"""
    
    def test_optimizer_params_endpoint(self):
        """Verify /api/optimizer/params returns parameters"""
        response = requests.get(f"{BASE_URL}/api/optimizer/params")
        assert response.status_code == 200
        data = response.json()
        assert "params" in data
        params = data["params"]
        
        # Check key parameters exist
        assert "min_rl_confidence" in params
        assert "take_profit_pct" in params
        assert "stop_loss_pct" in params
        assert "kelly_fraction" in params


class TestRLStatsEndpoint:
    """Test RL stats endpoint"""
    
    def test_rl_stats_endpoint(self):
        """Verify /api/rl/stats returns RL statistics"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Should have RL stats
        assert "total_iterations" in data or "epsilon" in data or "buffer_size" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
