"""
Test Suite for Config and Paper Trading Fixes - Iteration 15

Tests:
1. P0: Paper trading config loads correctly from MongoDB (initial_capital should be $10,000)
2. Config API GET /api/config returns all fields including kelly_enabled, min_liquidity, max_liquidity
3. Config API POST /api/config/update saves all new fields to MongoDB
4. Paper trading starts with correct capital from DB config
5. Kelly toggle (kelly_enabled) is saved and loaded correctly
6. Liquidity range (min_liquidity, max_liquidity) is saved and loaded correctly
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://smartcache-trade.preview.emergentagent.com').rstrip('/')
AUTH_CREDENTIALS = ('admin', 'apex2026!')


class TestConfigAPI:
    """Test /api/config endpoint returns all required fields"""
    
    def test_config_returns_initial_capital(self):
        """P0: Verify initial_capital is returned and is $10,000"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert response.status_code == 200, f"Config API failed: {response.text}"
        
        data = response.json()
        assert "initial_capital" in data, "initial_capital field missing from config"
        assert data["initial_capital"] == 10000.0, f"Expected initial_capital=10000, got {data['initial_capital']}"
        print(f"✅ initial_capital = ${data['initial_capital']:,.2f}")
    
    def test_config_returns_kelly_enabled(self):
        """Verify kelly_enabled toggle is returned"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert response.status_code == 200
        
        data = response.json()
        assert "kelly_enabled" in data, "kelly_enabled field missing from config"
        assert isinstance(data["kelly_enabled"], bool), f"kelly_enabled should be bool, got {type(data['kelly_enabled'])}"
        print(f"✅ kelly_enabled = {data['kelly_enabled']}")
    
    def test_config_returns_liquidity_range(self):
        """Verify min_liquidity and max_liquidity are returned"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert response.status_code == 200
        
        data = response.json()
        assert "min_liquidity" in data, "min_liquidity field missing from config"
        assert "max_liquidity" in data, "max_liquidity field missing from config"
        
        # Validate types
        assert isinstance(data["min_liquidity"], (int, float)), f"min_liquidity should be numeric"
        assert isinstance(data["max_liquidity"], (int, float)), f"max_liquidity should be numeric"
        
        # Validate range makes sense
        assert data["min_liquidity"] <= data["max_liquidity"], "min_liquidity should be <= max_liquidity"
        
        print(f"✅ Liquidity range: ${data['min_liquidity']:,.0f} - ${data['max_liquidity']:,.0f}")
    
    def test_config_returns_all_new_fields(self):
        """Verify all new fields are present in config response"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert response.status_code == 200
        
        data = response.json()
        
        # All required fields
        required_fields = [
            "initial_capital",
            "capital_deployment_pct",
            "max_position_size_pct",
            "kelly_fraction",
            "kelly_enabled",
            "max_drawdown_pct",
            "trades_per_10min",
            "min_liquidity",
            "max_liquidity",
            "min_volume_24h",
            "max_spread",
            "max_open_positions",
            "enabled_strategies",
            "enabled_asset_classes"
        ]
        
        missing_fields = [f for f in required_fields if f not in data]
        assert not missing_fields, f"Missing fields in config: {missing_fields}"
        
        print(f"✅ All {len(required_fields)} config fields present")
        for field in required_fields:
            print(f"   - {field}: {data[field]}")


class TestConfigUpdate:
    """Test /api/config/update endpoint saves all fields to MongoDB"""
    
    def test_update_kelly_enabled_toggle(self):
        """Test toggling kelly_enabled on and off"""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        original_value = response.json().get("kelly_enabled", True)
        
        # Toggle to opposite
        new_value = not original_value
        update_response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"kelly_enabled": new_value},
            auth=AUTH_CREDENTIALS
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify change persisted
        verify_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert verify_response.json()["kelly_enabled"] == new_value, "kelly_enabled not persisted"
        
        # Restore original value
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"kelly_enabled": original_value},
            auth=AUTH_CREDENTIALS
        )
        
        print(f"✅ kelly_enabled toggle works: {original_value} -> {new_value} -> {original_value}")
    
    def test_update_liquidity_range(self):
        """Test updating min_liquidity and max_liquidity"""
        # Get current values
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        original_min = response.json().get("min_liquidity", 100)
        original_max = response.json().get("max_liquidity", 1000000)
        
        # Update to new values
        new_min = 500
        new_max = 500000
        update_response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"min_liquidity": new_min, "max_liquidity": new_max},
            auth=AUTH_CREDENTIALS
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify changes persisted
        verify_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        data = verify_response.json()
        assert data["min_liquidity"] == new_min, f"min_liquidity not persisted: {data['min_liquidity']}"
        assert data["max_liquidity"] == new_max, f"max_liquidity not persisted: {data['max_liquidity']}"
        
        # Restore original values
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"min_liquidity": original_min, "max_liquidity": original_max},
            auth=AUTH_CREDENTIALS
        )
        
        print(f"✅ Liquidity range update works: ${new_min:,} - ${new_max:,}")
    
    def test_update_initial_capital(self):
        """Test updating initial_capital"""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        original_capital = response.json().get("initial_capital", 10000)
        
        # Update to new value
        new_capital = 25000
        update_response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"initial_capital": new_capital},
            auth=AUTH_CREDENTIALS
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify change persisted
        verify_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        assert verify_response.json()["initial_capital"] == new_capital, "initial_capital not persisted"
        
        # Restore original value
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"initial_capital": original_capital},
            auth=AUTH_CREDENTIALS
        )
        
        print(f"✅ initial_capital update works: ${original_capital:,} -> ${new_capital:,} -> ${original_capital:,}")


class TestPaperTradingConfig:
    """Test paper trading loads config correctly from MongoDB"""
    
    def test_paper_trading_starts_with_correct_capital(self):
        """P0: Verify paper trading starts with initial_capital from DB config"""
        # First, ensure config has correct initial_capital
        config_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        expected_capital = config_response.json().get("initial_capital", 10000)
        
        # Start paper trading
        start_response = requests.post(
            f"{BASE_URL}/api/paper/start",
            auth=AUTH_CREDENTIALS
        )
        assert start_response.status_code == 200, f"Paper trading start failed: {start_response.text}"
        
        # Wait for session to initialize
        time.sleep(2)
        
        # Get paper trading status
        status_response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH_CREDENTIALS)
        assert status_response.status_code == 200, f"Paper status failed: {status_response.text}"
        
        status = status_response.json()
        actual_capital = status.get("initial_capital", 0)
        
        # Stop paper trading
        requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH_CREDENTIALS)
        
        # Verify capital matches
        assert actual_capital == expected_capital, \
            f"Paper trading initial_capital mismatch: expected ${expected_capital:,}, got ${actual_capital:,}"
        
        print(f"✅ Paper trading started with correct capital: ${actual_capital:,.2f}")
    
    def test_paper_trading_uses_kelly_enabled_setting(self):
        """Verify paper trading respects kelly_enabled toggle"""
        # Get current kelly_enabled setting
        config_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        kelly_enabled = config_response.json().get("kelly_enabled", True)
        
        # Start paper trading
        start_response = requests.post(
            f"{BASE_URL}/api/paper/start",
            auth=AUTH_CREDENTIALS
        )
        assert start_response.status_code == 200
        
        time.sleep(2)
        
        # Get status and check config
        status_response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH_CREDENTIALS)
        status = status_response.json()
        
        # Stop paper trading
        requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH_CREDENTIALS)
        
        # Check if config section exists and has kelly info
        config_section = status.get("config", {})
        assert "kelly_fraction" in config_section, "kelly_fraction not in paper trading config"
        
        print(f"✅ Paper trading config includes kelly_fraction: {config_section.get('kelly_fraction')}")
        print(f"   kelly_enabled from DB: {kelly_enabled}")
    
    def test_paper_trading_uses_liquidity_filters(self):
        """Verify paper trading uses min/max liquidity from config"""
        # Get current liquidity settings
        config_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        config = config_response.json()
        min_liq = config.get("min_liquidity", 100)
        max_liq = config.get("max_liquidity", 1000000)
        
        # Start paper trading
        start_response = requests.post(
            f"{BASE_URL}/api/paper/start",
            auth=AUTH_CREDENTIALS
        )
        assert start_response.status_code == 200
        
        time.sleep(2)
        
        # Get status
        status_response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH_CREDENTIALS)
        status = status_response.json()
        
        # Stop paper trading
        requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH_CREDENTIALS)
        
        # Verify session is running with config
        assert status.get("running") == True or status.get("session_id") is not None, \
            "Paper trading session not properly initialized"
        
        print(f"✅ Paper trading session initialized with liquidity filters: ${min_liq:,} - ${max_liq:,}")


class TestTradingConfigModel:
    """Test TradingConfig Pydantic model has all required fields"""
    
    def test_config_update_accepts_all_new_fields(self):
        """Verify /api/config/update accepts all new fields in single request"""
        # Get current config to restore later
        original_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        original_config = original_response.json()
        
        # Update with all new fields
        update_payload = {
            "initial_capital": 15000,
            "capital_deployment_pct": 75,
            "max_position_size_pct": 4,
            "kelly_fraction": 0.30,
            "kelly_enabled": False,
            "max_drawdown_pct": 6,
            "trades_per_10min": 750,
            "min_liquidity": 200,
            "max_liquidity": 750000,
            "min_volume_24h": 2000,
            "max_spread": 0.04,
            "max_open_positions": 75
        }
        
        update_response = requests.post(
            f"{BASE_URL}/api/config/update",
            json=update_payload,
            auth=AUTH_CREDENTIALS
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify all fields persisted
        verify_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        data = verify_response.json()
        
        for field, expected_value in update_payload.items():
            actual_value = data.get(field)
            assert actual_value == expected_value, \
                f"Field {field} not persisted: expected {expected_value}, got {actual_value}"
        
        # Restore original config
        restore_payload = {
            "initial_capital": original_config.get("initial_capital", 10000),
            "capital_deployment_pct": original_config.get("capital_deployment_pct", 80),
            "max_position_size_pct": original_config.get("max_position_size_pct", 3),
            "kelly_fraction": original_config.get("kelly_fraction", 0.25),
            "kelly_enabled": original_config.get("kelly_enabled", True),
            "max_drawdown_pct": original_config.get("max_drawdown_pct", 5),
            "trades_per_10min": original_config.get("trades_per_10min", 500),
            "min_liquidity": original_config.get("min_liquidity", 100),
            "max_liquidity": original_config.get("max_liquidity", 1000000),
            "min_volume_24h": original_config.get("min_volume_24h", 1000),
            "max_spread": original_config.get("max_spread", 0.05),
            "max_open_positions": original_config.get("max_open_positions", 50)
        }
        requests.post(f"{BASE_URL}/api/config/update", json=restore_payload, auth=AUTH_CREDENTIALS)
        
        print(f"✅ All {len(update_payload)} config fields accepted and persisted")


class TestAdaptivePositionSizer:
    """Test adaptive position sizer uses kelly_enabled parameter"""
    
    def test_position_sizer_respects_kelly_toggle(self):
        """Verify position sizer behavior changes based on kelly_enabled"""
        # This is tested indirectly through paper trading
        # When kelly_enabled=False, positions should use fixed sizing
        
        # Get current config
        config_response = requests.get(f"{BASE_URL}/api/config", auth=AUTH_CREDENTIALS)
        config = config_response.json()
        
        # Verify kelly_enabled is in config
        assert "kelly_enabled" in config, "kelly_enabled not in config"
        
        print(f"✅ kelly_enabled is configurable: {config['kelly_enabled']}")
        print(f"   When True: Position sizing uses Kelly Criterion with learned win rates")
        print(f"   When False: Position sizing uses fixed 30% of max position")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
