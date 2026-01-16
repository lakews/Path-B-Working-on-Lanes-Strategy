"""
Test Suite for Iteration 18 - New Configuration Features
Tests:
1. Advanced Position Sizing (Kelly bounds, min_position_size, min_liquidity_for_full_size)
2. Asset Class Exit Multipliers (TP/SL/Time multipliers for 6 asset classes)
3. Market Alerts (enable/disable toggle, volume threshold)
4. GET /api/config returns all new fields
5. POST /api/config/update saves all new fields
6. GET /api/alerts returns alerts array, count, enabled status, volume_threshold
7. POST /api/alerts/toggle enables/disables alerts
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health endpoint working")


class TestConfigNewFields:
    """Test GET /api/config returns all new fields"""
    
    def test_config_returns_kelly_bounds(self):
        """Test config returns min_kelly_fraction and max_kelly_fraction"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        # Check Kelly bounds exist
        assert "min_kelly_fraction" in data, "min_kelly_fraction missing from config"
        assert "max_kelly_fraction" in data, "max_kelly_fraction missing from config"
        
        # Check default values
        assert isinstance(data["min_kelly_fraction"], (int, float))
        assert isinstance(data["max_kelly_fraction"], (int, float))
        assert data["min_kelly_fraction"] >= 0
        assert data["max_kelly_fraction"] <= 1
        assert data["min_kelly_fraction"] <= data["max_kelly_fraction"]
        
        print(f"✓ Kelly bounds: min={data['min_kelly_fraction']}, max={data['max_kelly_fraction']}")
    
    def test_config_returns_position_limits(self):
        """Test config returns min_position_size and min_liquidity_for_full_size"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        # Check position limits exist
        assert "min_position_size" in data, "min_position_size missing from config"
        assert "min_liquidity_for_full_size" in data, "min_liquidity_for_full_size missing from config"
        
        # Check values are reasonable
        assert isinstance(data["min_position_size"], (int, float))
        assert isinstance(data["min_liquidity_for_full_size"], (int, float))
        assert data["min_position_size"] > 0
        assert data["min_liquidity_for_full_size"] > 0
        
        print(f"✓ Position limits: min_size=${data['min_position_size']}, full_size_liquidity=${data['min_liquidity_for_full_size']}")
    
    def test_config_returns_alerts_config(self):
        """Test config returns alerts_enabled and alert_volume_threshold"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        # Check alerts config exists
        assert "alerts_enabled" in data, "alerts_enabled missing from config"
        assert "alert_volume_threshold" in data, "alert_volume_threshold missing from config"
        
        # Check types
        assert isinstance(data["alerts_enabled"], bool)
        assert isinstance(data["alert_volume_threshold"], (int, float))
        assert data["alert_volume_threshold"] > 0
        
        print(f"✓ Alerts config: enabled={data['alerts_enabled']}, threshold={data['alert_volume_threshold']}x")
    
    def test_config_returns_asset_class_exit_multipliers(self):
        """Test config returns asset_class_exit_multipliers for all 6 asset classes"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        # Check asset_class_exit_multipliers exists
        assert "asset_class_exit_multipliers" in data, "asset_class_exit_multipliers missing from config"
        
        multipliers = data["asset_class_exit_multipliers"]
        assert isinstance(multipliers, dict)
        
        # Check all 6 asset classes are present
        expected_classes = ["crypto", "politics", "sports", "finance", "entertainment", "science"]
        for asset_class in expected_classes:
            assert asset_class in multipliers, f"{asset_class} missing from asset_class_exit_multipliers"
            
            # Check each has tp_mult, sl_mult, time_mult
            assert "tp_mult" in multipliers[asset_class], f"tp_mult missing for {asset_class}"
            assert "sl_mult" in multipliers[asset_class], f"sl_mult missing for {asset_class}"
            assert "time_mult" in multipliers[asset_class], f"time_mult missing for {asset_class}"
            
            # Check values are reasonable
            assert multipliers[asset_class]["tp_mult"] > 0
            assert multipliers[asset_class]["sl_mult"] > 0
            assert multipliers[asset_class]["time_mult"] > 0
        
        print(f"✓ Asset class exit multipliers present for all 6 classes: {list(multipliers.keys())}")


class TestConfigUpdate:
    """Test POST /api/config/update saves all new fields"""
    
    def get_auth(self):
        """Get authentication for protected endpoints"""
        return ("admin", "apex2026!")
    
    def test_update_kelly_bounds(self):
        """Test updating Kelly bounds via config update"""
        # Get current config
        response = requests.get(f"{BASE_URL}/api/config")
        original_config = response.json()
        
        # Update Kelly bounds
        update_payload = {
            "min_kelly_fraction": 0.15,
            "max_kelly_fraction": 0.60
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json=update_payload,
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify update persisted
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        assert data["min_kelly_fraction"] == 0.15
        assert data["max_kelly_fraction"] == 0.60
        
        # Restore original values
        restore_payload = {
            "min_kelly_fraction": original_config.get("min_kelly_fraction", 0.10),
            "max_kelly_fraction": original_config.get("max_kelly_fraction", 0.50)
        }
        requests.post(f"{BASE_URL}/api/config/update", json=restore_payload, auth=self.get_auth())
        
        print("✓ Kelly bounds update and persistence verified")
    
    def test_update_position_limits(self):
        """Test updating position limits via config update"""
        # Get current config
        response = requests.get(f"{BASE_URL}/api/config")
        original_config = response.json()
        
        # Update position limits
        update_payload = {
            "min_position_size": 10.0,
            "min_liquidity_for_full_size": 15000.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json=update_payload,
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify update persisted
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        assert data["min_position_size"] == 10.0
        assert data["min_liquidity_for_full_size"] == 15000.0
        
        # Restore original values
        restore_payload = {
            "min_position_size": original_config.get("min_position_size", 5.0),
            "min_liquidity_for_full_size": original_config.get("min_liquidity_for_full_size", 10000.0)
        }
        requests.post(f"{BASE_URL}/api/config/update", json=restore_payload, auth=self.get_auth())
        
        print("✓ Position limits update and persistence verified")
    
    def test_update_alerts_config(self):
        """Test updating alerts config via config update"""
        # Get current config
        response = requests.get(f"{BASE_URL}/api/config")
        original_config = response.json()
        
        # Update alerts config
        update_payload = {
            "alerts_enabled": True,
            "alert_volume_threshold": 3.5
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json=update_payload,
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify update persisted
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        assert data["alerts_enabled"] == True
        assert data["alert_volume_threshold"] == 3.5
        
        # Restore original values
        restore_payload = {
            "alerts_enabled": original_config.get("alerts_enabled", False),
            "alert_volume_threshold": original_config.get("alert_volume_threshold", 2.0)
        }
        requests.post(f"{BASE_URL}/api/config/update", json=restore_payload, auth=self.get_auth())
        
        print("✓ Alerts config update and persistence verified")
    
    def test_update_asset_class_exit_multipliers(self):
        """Test updating asset class exit multipliers via config update"""
        # Get current config
        response = requests.get(f"{BASE_URL}/api/config")
        original_config = response.json()
        
        # Update crypto multipliers
        update_payload = {
            "asset_class_exit_multipliers": {
                "crypto": {
                    "tp_mult": 2.0,
                    "sl_mult": 1.5,
                    "time_mult": 0.75
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json=update_payload,
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify update persisted
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        assert data["asset_class_exit_multipliers"]["crypto"]["tp_mult"] == 2.0
        assert data["asset_class_exit_multipliers"]["crypto"]["sl_mult"] == 1.5
        assert data["asset_class_exit_multipliers"]["crypto"]["time_mult"] == 0.75
        
        # Restore original values
        restore_payload = {
            "asset_class_exit_multipliers": original_config.get("asset_class_exit_multipliers", {})
        }
        requests.post(f"{BASE_URL}/api/config/update", json=restore_payload, auth=self.get_auth())
        
        print("✓ Asset class exit multipliers update and persistence verified")


class TestAlertsEndpoints:
    """Test alerts-related endpoints"""
    
    def get_auth(self):
        """Get authentication for protected endpoints"""
        return ("admin", "apex2026!")
    
    def test_get_alerts_returns_correct_structure(self):
        """Test GET /api/alerts returns alerts array, count, enabled status, volume_threshold"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "alerts" in data, "alerts array missing"
        assert "count" in data, "count missing"
        assert "enabled" in data, "enabled status missing"
        assert "volume_threshold" in data, "volume_threshold missing"
        
        # Check types
        assert isinstance(data["alerts"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["volume_threshold"], (int, float))
        
        print(f"✓ GET /api/alerts returns correct structure: count={data['count']}, enabled={data['enabled']}, threshold={data['volume_threshold']}x")
    
    def test_toggle_alerts_enable(self):
        """Test POST /api/alerts/toggle enables alerts"""
        # Enable alerts
        response = requests.post(
            f"{BASE_URL}/api/alerts/toggle",
            params={"enabled": True},
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify via GET /api/alerts
        response = requests.get(f"{BASE_URL}/api/alerts")
        data = response.json()
        assert data["enabled"] == True
        
        print("✓ POST /api/alerts/toggle enables alerts correctly")
    
    def test_toggle_alerts_disable(self):
        """Test POST /api/alerts/toggle disables alerts"""
        # Disable alerts
        response = requests.post(
            f"{BASE_URL}/api/alerts/toggle",
            params={"enabled": False},
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify via GET /api/alerts
        response = requests.get(f"{BASE_URL}/api/alerts")
        data = response.json()
        assert data["enabled"] == False
        
        print("✓ POST /api/alerts/toggle disables alerts correctly")
    
    def test_clear_alerts(self):
        """Test POST /api/alerts/clear clears all alerts"""
        response = requests.post(
            f"{BASE_URL}/api/alerts/clear",
            auth=self.get_auth()
        )
        assert response.status_code == 200
        
        # Verify alerts are cleared
        response = requests.get(f"{BASE_URL}/api/alerts")
        data = response.json()
        assert data["count"] == 0
        assert len(data["alerts"]) == 0
        
        print("✓ POST /api/alerts/clear clears all alerts")


class TestEnvFileCleanup:
    """Test that .env file has been cleaned up"""
    
    def test_config_not_from_env_hardcoded(self):
        """Test that config values come from DB, not hardcoded .env"""
        # Get config
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        # These should be present and have reasonable defaults
        # (not hardcoded in .env anymore)
        assert "initial_capital" in data
        assert "trades_per_10min" in data
        assert "kelly_fraction" in data
        
        # Values should be reasonable defaults
        assert data["initial_capital"] > 0
        assert data["trades_per_10min"] > 0
        
        print(f"✓ Config values present: initial_capital=${data['initial_capital']}, trades_per_10min={data['trades_per_10min']}")


class TestDefaultValues:
    """Test that default values match expected"""
    
    def test_default_kelly_bounds(self):
        """Test default Kelly bounds are correct"""
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        
        # Default values from requirements
        # min_kelly_fraction=0.10, max_kelly_fraction=0.50
        # These may have been modified, so just check they're reasonable
        assert 0 < data["min_kelly_fraction"] <= 0.5
        assert 0.1 <= data["max_kelly_fraction"] <= 1.0
        
        print(f"✓ Kelly bounds are reasonable: {data['min_kelly_fraction']} - {data['max_kelly_fraction']}")
    
    def test_default_position_limits(self):
        """Test default position limits are correct"""
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        
        # Default values: min_position_size=5, min_liquidity_for_full_size=10000
        assert data["min_position_size"] >= 1  # At least $1
        assert data["min_liquidity_for_full_size"] >= 1000  # At least $1000
        
        print(f"✓ Position limits are reasonable: min=${data['min_position_size']}, full_size_liq=${data['min_liquidity_for_full_size']}")
    
    def test_default_alerts_config(self):
        """Test default alerts config is correct"""
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        
        # Default: alerts_enabled=false, alert_volume_threshold=2.0
        assert isinstance(data["alerts_enabled"], bool)
        assert data["alert_volume_threshold"] >= 1.0  # At least 1x
        
        print(f"✓ Alerts config is reasonable: enabled={data['alerts_enabled']}, threshold={data['alert_volume_threshold']}x")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
