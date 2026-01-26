"""
APEX TRADER New Features Tests - Iteration 6
Tests for:
1. RL detailed stats endpoint GET /api/rl/detailed-stats (action_distribution, q_table analysis)
2. RL learn from backtest POST /api/rl/learn-from-backtest/{backtest_id}
3. Alerts config endpoint GET /api/alerts/config (thresholds and cooldowns)
4. Alerts history endpoint GET /api/alerts/history
5. Backtest with data_source parameter (auto, real, snapshots, hybrid)
6. Backtest results include data_quality.data_source_mode field
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://hysteresis-trader.preview.emergentagent.com')


class TestRLDetailedStats:
    """Tests for /api/rl/detailed-stats endpoint"""
    
    def test_detailed_stats_endpoint_returns_200(self):
        """Test /api/rl/detailed-stats returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_detailed_stats_has_rl_stats(self):
        """Test response contains rl_stats object"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        assert "rl_stats" in data, f"Missing rl_stats in response: {data}"
        assert isinstance(data["rl_stats"], dict), "rl_stats should be a dict"
    
    def test_detailed_stats_has_model_status(self):
        """Test response contains model_status field"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        assert "model_status" in data, f"Missing model_status in response: {data}"
        assert data["model_status"] in ["loaded", "fresh"], f"Invalid model_status: {data['model_status']}"
    
    def test_detailed_stats_has_action_distribution(self):
        """Test rl_stats contains action_distribution"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        rl_stats = data.get("rl_stats", {})
        assert "action_distribution" in rl_stats, f"Missing action_distribution in rl_stats: {rl_stats}"
        
        # Verify action_distribution has expected actions
        action_dist = rl_stats["action_distribution"]
        expected_actions = ["WAIT", "BUY_SMALL", "BUY_MEDIUM", "BUY_LARGE", "SELL_SMALL", "SELL_MEDIUM", "SELL_LARGE"]
        for action in expected_actions:
            assert action in action_dist, f"Missing action {action} in action_distribution"
    
    def test_detailed_stats_has_q_table_analysis(self):
        """Test rl_stats contains Q-table analysis fields"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        rl_stats = data.get("rl_stats", {})
        
        # Check for Q-table analysis fields
        assert "q_table_size" in rl_stats, "Missing q_table_size"
        assert "q_table_nonzero_pct" in rl_stats, "Missing q_table_nonzero_pct"
        assert "q_table_mean" in rl_stats, "Missing q_table_mean"
        assert "q_table_max" in rl_stats, "Missing q_table_max"
    
    def test_detailed_stats_has_learning_params(self):
        """Test rl_stats contains learning parameters"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        rl_stats = data.get("rl_stats", {})
        
        assert "learning_rate" in rl_stats, "Missing learning_rate"
        assert "discount_factor" in rl_stats, "Missing discount_factor"
        assert "epsilon" in rl_stats, "Missing epsilon"
    
    def test_detailed_stats_has_reward_metrics(self):
        """Test rl_stats contains reward metrics"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        data = response.json()
        
        rl_stats = data.get("rl_stats", {})
        
        assert "avg_reward_100" in rl_stats, "Missing avg_reward_100"
        assert "max_reward_100" in rl_stats, "Missing max_reward_100"
        assert "min_reward_100" in rl_stats, "Missing min_reward_100"
        assert "std_reward_100" in rl_stats, "Missing std_reward_100"
        assert "positive_rate" in rl_stats, "Missing positive_rate"


class TestRLLearnFromBacktest:
    """Tests for /api/rl/learn-from-backtest/{backtest_id} endpoint"""
    
    @pytest.fixture
    def existing_backtest_id(self):
        """Get an existing backtest ID from history"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=1")
        if response.status_code == 200:
            history = response.json().get("history", [])
            if history:
                return history[0].get("backtest_id")
        return None
    
    def test_learn_from_backtest_with_valid_id(self, existing_backtest_id):
        """Test learning from a valid backtest ID"""
        if not existing_backtest_id:
            pytest.skip("No existing backtest found to test with")
        
        response = requests.post(f"{BASE_URL}/api/rl/learn-from-backtest/{existing_backtest_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Missing message in response"
        assert existing_backtest_id in data["message"], "Backtest ID not in message"
    
    def test_learn_from_backtest_returns_stats(self, existing_backtest_id):
        """Test that learning returns updated RL stats"""
        if not existing_backtest_id:
            pytest.skip("No existing backtest found to test with")
        
        response = requests.post(f"{BASE_URL}/api/rl/learn-from-backtest/{existing_backtest_id}")
        data = response.json()
        
        assert "rl_stats" in data, "Missing rl_stats in response"
        assert "backtest_return" in data, "Missing backtest_return in response"
        assert "strategies_learned" in data, "Missing strategies_learned in response"
    
    def test_learn_from_backtest_invalid_id(self):
        """Test learning from non-existent backtest returns 404"""
        response = requests.post(f"{BASE_URL}/api/rl/learn-from-backtest/invalid-backtest-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "message" in data or "detail" in data, "Missing error message"


class TestAlertsConfig:
    """Tests for /api/alerts/config endpoint"""
    
    def test_alerts_config_returns_200(self):
        """Test /api/alerts/config returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_alerts_config_has_enabled_field(self):
        """Test config contains enabled field"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        data = response.json()
        
        assert "enabled" in data, f"Missing enabled field: {data}"
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
    
    def test_alerts_config_has_thresholds(self):
        """Test config contains thresholds"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        data = response.json()
        
        assert "thresholds" in data, f"Missing thresholds: {data}"
        thresholds = data["thresholds"]
        
        # Check expected threshold fields
        assert "whale_activity_min" in thresholds, "Missing whale_activity_min threshold"
        assert "sentiment_shift_min" in thresholds, "Missing sentiment_shift_min threshold"
        assert "drawdown_max" in thresholds, "Missing drawdown_max threshold"
        assert "profit_notification_min" in thresholds, "Missing profit_notification_min threshold"
    
    def test_alerts_config_has_cooldowns(self):
        """Test config contains cooldowns"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        data = response.json()
        
        assert "cooldowns_minutes" in data, f"Missing cooldowns_minutes: {data}"
        cooldowns = data["cooldowns_minutes"]
        
        # Check expected cooldown types
        expected_types = ["whale_activity", "sentiment_shift", "drawdown_alert", "trade_executed", "backtest_complete", "risk_threshold"]
        for alert_type in expected_types:
            assert alert_type in cooldowns, f"Missing cooldown for {alert_type}"
    
    def test_alerts_config_sender_email(self):
        """Test config contains sender_email"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        data = response.json()
        
        assert "sender_email" in data, f"Missing sender_email: {data}"


class TestAlertsHistory:
    """Tests for /api/alerts/history endpoint"""
    
    def test_alerts_history_returns_200(self):
        """Test /api/alerts/history returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/alerts/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_alerts_history_returns_list(self):
        """Test history returns a list"""
        response = requests.get(f"{BASE_URL}/api/alerts/history")
        data = response.json()
        
        assert "history" in data, f"Missing history field: {data}"
        assert isinstance(data["history"], list), "history should be a list"
    
    def test_alerts_history_with_limit(self):
        """Test history respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/alerts/history?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["history"]) <= 5, "History should respect limit"


class TestBacktestDataSource:
    """Tests for backtest data_source parameter"""
    
    def test_backtest_start_with_auto_data_source(self):
        """Test starting backtest with auto data source"""
        params = {
            "start_date": "2026-01-01T00:00:00Z",
            "end_date": "2026-01-07T23:59:59Z",
            "data_source": "auto"
        }
        response = requests.post(f"{BASE_URL}/api/backtest/start", params=params)
        
        # Should either start successfully or indicate already running
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "data_source" in data, "Missing data_source in response"
            assert data["data_source"] == "auto", f"Expected auto, got {data['data_source']}"
            
            # Stop the backtest
            requests.post(f"{BASE_URL}/api/backtest/stop")
    
    def test_backtest_results_include_data_source_mode(self):
        """Test that backtest results include data_quality.data_source_mode"""
        # Get latest backtest results
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        
        if response.status_code == 200:
            data = response.json()
            if data and "data_quality" in data:
                # New backtests should have data_source_mode
                # Older backtests may not have it (backward compatibility)
                if "data_source_mode" in data["data_quality"]:
                    # Verify valid data source mode
                    valid_modes = ["auto", "real", "snapshots", "live", "hybrid"]
                    assert data["data_quality"]["data_source_mode"] in valid_modes, f"Invalid data_source_mode: {data['data_quality']['data_source_mode']}"
                else:
                    # Old backtest without data_source_mode - this is acceptable
                    print(f"Note: Backtest result missing data_source_mode (older backtest)")
    
    def test_backtest_history_includes_data_source_mode(self):
        """Test that backtest history items may include data_source_mode (new backtests)"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=5")
        
        if response.status_code == 200:
            data = response.json()
            history = data.get("history", [])
            
            # Count how many have data_source_mode
            with_mode = 0
            for bt in history:
                if "data_quality" in bt and "data_source_mode" in bt["data_quality"]:
                    with_mode += 1
            
            # At least some recent backtests should have the field (if any exist)
            print(f"Backtests with data_source_mode: {with_mode}/{len(history)}")


class TestBacktestDataSourceOptions:
    """Tests for different data source options"""
    
    def test_data_source_options_in_results(self):
        """Test that data_quality includes data_source_options (new backtests)"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        
        if response.status_code == 200:
            data = response.json()
            if data and "data_quality" in data:
                # New backtests should have data_source_options
                if "data_source_options" in data["data_quality"]:
                    options = data["data_quality"]["data_source_options"]
                    expected_options = ["auto", "real", "snapshots", "live", "hybrid"]
                    assert options == expected_options, f"Unexpected options: {options}"
                else:
                    # Old backtest without data_source_options - acceptable
                    print("Note: Backtest result missing data_source_options (older backtest)")


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after new features"""
    
    def test_health_endpoint(self):
        """Test /api/health still works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_status_endpoint(self):
        """Test /api/status still works"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "trading_mode" in data
        assert "configuration" in data
    
    def test_rl_stats_endpoint(self):
        """Test /api/rl/stats still works"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_iterations" in data
        assert "epsilon" in data
    
    def test_backtest_history_endpoint(self):
        """Test /api/backtest/history still works"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
    
    def test_backtest_results_endpoint(self):
        """Test /api/backtest/results still works"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        # May return 404 if no results, or 200 with results
        assert response.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
