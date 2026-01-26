"""
APEX TRADER RL Engine API Tests
Tests for RL Engine endpoints: /api/rl/stats, /api/rl/train, /api/rl/save, /api/rl/load
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://hysteresis-trader.preview.emergentagent.com')


class TestRLEngineStats:
    """RL Engine statistics endpoint tests"""
    
    def test_rl_stats_endpoint(self):
        """Test /api/rl/stats returns all required training statistics"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_iterations" in data
        assert "epsilon" in data
        assert "avg_reward_100" in data
        assert "max_reward_100" in data
        assert "min_reward_100" in data
        assert "buffer_size" in data
        assert "q_table_size" in data
        
        # Verify data types
        assert isinstance(data["total_iterations"], int)
        assert isinstance(data["epsilon"], (int, float))
        assert isinstance(data["avg_reward_100"], (int, float))
        assert isinstance(data["buffer_size"], int)
        assert isinstance(data["q_table_size"], list)
    
    def test_rl_stats_epsilon_in_valid_range(self):
        """Verify epsilon is within valid exploration range (0 to 1)"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        data = response.json()
        
        assert 0 <= data["epsilon"] <= 1
    
    def test_rl_stats_q_table_dimensions(self):
        """Verify Q-table has correct dimensions"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        data = response.json()
        
        # Q-table should be 2D: [state_space, action_space]
        assert len(data["q_table_size"]) == 2
        assert data["q_table_size"][0] > 0  # State space
        assert data["q_table_size"][1] == 7  # 7 actions: WAIT, BUY_SMALL, BUY_MEDIUM, BUY_LARGE, SELL_SMALL, SELL_MEDIUM, SELL_LARGE


class TestRLEngineTrain:
    """RL Engine training endpoint tests"""
    
    def test_rl_train_endpoint(self):
        """Test /api/rl/train triggers batch training"""
        response = requests.post(f"{BASE_URL}/api/rl/train")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "message" in data
        assert "stats" in data
        assert data["message"] == "RL batch training completed"
        
        # Verify stats are returned
        stats = data["stats"]
        assert "total_iterations" in stats
        assert "epsilon" in stats
        assert "buffer_size" in stats
    
    def test_rl_train_returns_updated_stats(self):
        """Verify training returns current stats"""
        response = requests.post(f"{BASE_URL}/api/rl/train")
        data = response.json()
        
        # Stats should be present and valid
        assert isinstance(data["stats"]["total_iterations"], int)
        assert isinstance(data["stats"]["epsilon"], (int, float))


class TestRLEngineSaveLoad:
    """RL Engine save/load model endpoint tests"""
    
    def test_rl_save_endpoint(self):
        """Test /api/rl/save saves model successfully"""
        response = requests.post(f"{BASE_URL}/api/rl/save")
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert data["message"] == "RL model saved successfully"
    
    def test_rl_load_endpoint(self):
        """Test /api/rl/load loads model successfully"""
        response = requests.post(f"{BASE_URL}/api/rl/load")
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "stats" in data
        assert data["message"] == "RL model loaded successfully"
        
        # Verify stats are returned after load
        stats = data["stats"]
        assert "total_iterations" in stats
        assert "epsilon" in stats
    
    def test_rl_save_load_preserves_state(self):
        """Test that save/load preserves model state"""
        # Get current stats
        stats_before = requests.get(f"{BASE_URL}/api/rl/stats").json()
        
        # Save model
        save_response = requests.post(f"{BASE_URL}/api/rl/save")
        assert save_response.status_code == 200
        
        # Load model
        load_response = requests.post(f"{BASE_URL}/api/rl/load")
        assert load_response.status_code == 200
        
        # Get stats after load
        stats_after = load_response.json()["stats"]
        
        # Verify key parameters are preserved
        assert stats_before["epsilon"] == stats_after["epsilon"]
        assert stats_before["total_iterations"] == stats_after["total_iterations"]


class TestRLEngineIntegration:
    """Integration tests for RL Engine with other endpoints"""
    
    def test_rl_stats_after_train(self):
        """Verify stats endpoint works after training"""
        # Train
        requests.post(f"{BASE_URL}/api/rl/train")
        
        # Get stats
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        data = response.json()
        
        # All fields should be present
        assert "total_iterations" in data
        assert "epsilon" in data
        assert "buffer_size" in data
    
    def test_rl_full_workflow(self):
        """Test complete RL workflow: stats -> train -> save -> load -> stats"""
        # 1. Get initial stats
        stats1 = requests.get(f"{BASE_URL}/api/rl/stats")
        assert stats1.status_code == 200
        
        # 2. Train
        train = requests.post(f"{BASE_URL}/api/rl/train")
        assert train.status_code == 200
        
        # 3. Save
        save = requests.post(f"{BASE_URL}/api/rl/save")
        assert save.status_code == 200
        
        # 4. Load
        load = requests.post(f"{BASE_URL}/api/rl/load")
        assert load.status_code == 200
        
        # 5. Get final stats
        stats2 = requests.get(f"{BASE_URL}/api/rl/stats")
        assert stats2.status_code == 200


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after RL Engine addition"""
    
    def test_status_endpoint(self):
        """Test /api/status still works"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "trading_mode" in data
        assert "configuration" in data
    
    def test_trades_stats_endpoint(self):
        """Test /api/trades/stats still works"""
        response = requests.get(f"{BASE_URL}/api/trades/stats")
        assert response.status_code == 200
        data = response.json()
        assert "live_trades" in data
        assert "trades_10min" in data
    
    def test_analytics_endpoint(self):
        """Test /api/analytics still works"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        assert response.status_code == 200
        data = response.json()
        assert "total_trades" in data
        assert "strategy_performance" in data
    
    def test_historical_stats_endpoint(self):
        """Test /api/historical/stats still works"""
        response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_snapshots" in data
        assert "unique_markets" in data
    
    def test_performance_endpoint(self):
        """Test /api/performance still works"""
        response = requests.get(f"{BASE_URL}/api/performance")
        assert response.status_code == 200
        data = response.json()
        assert "total_capital" in data
        assert "win_rate" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
