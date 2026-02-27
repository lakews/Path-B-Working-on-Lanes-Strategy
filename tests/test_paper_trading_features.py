"""
Test Paper Trading API Endpoints and Strategy Optimizer
Tests for new Paper Trading engine with RL integration
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://markets-first-ai.preview.emergentagent.com').rstrip('/')

class TestPaperTradingAPI:
    """Paper Trading API endpoint tests"""
    
    def test_paper_status_endpoint(self):
        """Test GET /api/paper/status returns correct response"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        # Should return status even when not running
        assert "running" in data or "message" in data
        print(f"✅ Paper status: {data}")
    
    def test_paper_analytics_endpoint(self):
        """Test GET /api/paper/analytics returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/paper/analytics")
        assert response.status_code == 200
        
        data = response.json()
        # Should have analytics structure
        assert "aggregate_stats" in data or "current_session" in data or "completed_sessions" in data
        print(f"✅ Paper analytics keys: {list(data.keys())}")
    
    def test_paper_positions_endpoint(self):
        """Test GET /api/paper/positions returns empty array when no session"""
        response = requests.get(f"{BASE_URL}/api/paper/positions")
        assert response.status_code == 200
        
        data = response.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)
        print(f"✅ Paper positions: {len(data['positions'])} positions")
    
    def test_paper_sessions_endpoint(self):
        """Test GET /api/paper/sessions returns sessions list"""
        response = requests.get(f"{BASE_URL}/api/paper/sessions?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        print(f"✅ Paper sessions: {len(data['sessions'])} sessions")
    
    def test_paper_trades_endpoint(self):
        """Test GET /api/paper/trades returns trades list"""
        response = requests.get(f"{BASE_URL}/api/paper/trades?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert "trades" in data
        assert isinstance(data["trades"], list)
        print(f"✅ Paper trades: {len(data['trades'])} trades")


class TestOptimizerAPI:
    """Strategy Optimizer API endpoint tests"""
    
    def test_optimizer_params_endpoint(self):
        """Test GET /api/optimizer/params returns optimizable parameters"""
        response = requests.get(f"{BASE_URL}/api/optimizer/params")
        assert response.status_code == 200
        
        data = response.json()
        assert "params" in data
        
        params = data["params"]
        # Check for expected parameter categories
        expected_params = [
            "min_rl_confidence",
            "take_profit_pct",
            "stop_loss_pct",
            "kelly_fraction",
            "max_position_pct",
            "strategy_weights"
        ]
        
        for param in expected_params:
            assert param in params, f"Missing parameter: {param}"
        
        print(f"✅ Optimizer params: {list(params.keys())}")
    
    def test_optimizer_stats_endpoint(self):
        """Test GET /api/optimizer/stats returns optimization statistics"""
        response = requests.get(f"{BASE_URL}/api/optimizer/stats")
        assert response.status_code == 200
        
        data = response.json()
        # Should have current_params and recent_optimizations
        assert "current_params" in data or "error" not in data
        print(f"✅ Optimizer stats keys: {list(data.keys())}")


class TestRLIntegration:
    """RL Engine integration tests for paper trading"""
    
    def test_rl_detailed_stats_endpoint(self):
        """Test GET /api/rl/detailed-stats returns RL training statistics"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        assert response.status_code == 200
        
        data = response.json()
        # Should have rl_stats or model_status
        assert "rl_stats" in data or "model_status" in data
        print(f"✅ RL detailed stats: {list(data.keys())}")
    
    def test_rl_stats_endpoint(self):
        """Test GET /api/rl/stats returns basic RL statistics"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        # Should return stats structure
        print(f"✅ RL stats: {data}")


class TestHealthAndStatus:
    """Basic health and status checks"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✅ Health check passed")
    
    def test_status_endpoint(self):
        """Test /api/status returns system status"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "trading_mode" in data
        assert "configuration" in data
        print(f"✅ System status: mode={data.get('trading_mode')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
