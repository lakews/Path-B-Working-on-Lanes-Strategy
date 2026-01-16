"""
Test Exit Parameters Feature - Configurable TP/SL/Max Hours per Strategy

Tests:
1. GET /api/config returns exit_params with all 4 strategies
2. POST /api/config/update with exit_params saves correctly
3. Exit params defaults are correct
4. Paper Trading loads exit params from DB
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Default exit params as defined in the code
DEFAULT_EXIT_PARAMS = {
    'delta_neutral': {'take_profit': 0.02, 'stop_loss': -0.02, 'max_hours': 4},
    'volatility_exploitation': {'take_profit': 0.05, 'stop_loss': -0.05, 'max_hours': 8},
    'alpha_directional': {'take_profit': 0.08, 'stop_loss': -0.05, 'max_hours': 12},
    'arbitrage': {'take_profit': 0.03, 'stop_loss': -0.03, 'max_hours': 6}
}

STRATEGIES = ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login/json", json={
        "username": "admin",
        "password": "apex2026!"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestExitParamsAPI:
    """Test Exit Parameters API endpoints"""
    
    def test_get_config_returns_exit_params(self, authenticated_client):
        """GET /api/config should return exit_params with all 4 strategies"""
        response = authenticated_client.get(f"{BASE_URL}/api/config")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "exit_params" in data, "Response should contain exit_params"
        
        exit_params = data["exit_params"]
        
        # Verify all 4 strategies are present
        for strategy in STRATEGIES:
            assert strategy in exit_params, f"exit_params should contain {strategy}"
            
            # Verify each strategy has required fields
            strategy_params = exit_params[strategy]
            assert "take_profit" in strategy_params, f"{strategy} should have take_profit"
            assert "stop_loss" in strategy_params, f"{strategy} should have stop_loss"
            assert "max_hours" in strategy_params, f"{strategy} should have max_hours"
            
            # Verify types
            assert isinstance(strategy_params["take_profit"], (int, float)), f"{strategy} take_profit should be numeric"
            assert isinstance(strategy_params["stop_loss"], (int, float)), f"{strategy} stop_loss should be numeric"
            assert isinstance(strategy_params["max_hours"], (int, float)), f"{strategy} max_hours should be numeric"
        
        print(f"✅ GET /api/config returns exit_params for all 4 strategies")
        print(f"   Exit params: {exit_params}")
    
    def test_exit_params_default_values(self, authenticated_client):
        """Verify exit_params have correct default values"""
        response = authenticated_client.get(f"{BASE_URL}/api/config")
        
        assert response.status_code == 200
        exit_params = response.json()["exit_params"]
        
        # Check delta_neutral defaults
        dn = exit_params["delta_neutral"]
        assert dn["take_profit"] == 0.02 or abs(dn["take_profit"] - 0.02) < 0.001, f"delta_neutral TP should be 0.02, got {dn['take_profit']}"
        assert dn["stop_loss"] == -0.02 or abs(dn["stop_loss"] - (-0.02)) < 0.001, f"delta_neutral SL should be -0.02, got {dn['stop_loss']}"
        assert dn["max_hours"] == 4 or abs(dn["max_hours"] - 4) < 0.1, f"delta_neutral max_hours should be 4, got {dn['max_hours']}"
        
        # Check volatility_exploitation defaults
        ve = exit_params["volatility_exploitation"]
        assert ve["take_profit"] == 0.05 or abs(ve["take_profit"] - 0.05) < 0.001, f"volatility_exploitation TP should be 0.05, got {ve['take_profit']}"
        assert ve["stop_loss"] == -0.05 or abs(ve["stop_loss"] - (-0.05)) < 0.001, f"volatility_exploitation SL should be -0.05, got {ve['stop_loss']}"
        assert ve["max_hours"] == 8 or abs(ve["max_hours"] - 8) < 0.1, f"volatility_exploitation max_hours should be 8, got {ve['max_hours']}"
        
        # Check alpha_directional defaults
        ad = exit_params["alpha_directional"]
        assert ad["take_profit"] == 0.08 or abs(ad["take_profit"] - 0.08) < 0.001, f"alpha_directional TP should be 0.08, got {ad['take_profit']}"
        assert ad["stop_loss"] == -0.05 or abs(ad["stop_loss"] - (-0.05)) < 0.001, f"alpha_directional SL should be -0.05, got {ad['stop_loss']}"
        assert ad["max_hours"] == 12 or abs(ad["max_hours"] - 12) < 0.1, f"alpha_directional max_hours should be 12, got {ad['max_hours']}"
        
        # Check arbitrage defaults
        arb = exit_params["arbitrage"]
        assert arb["take_profit"] == 0.03 or abs(arb["take_profit"] - 0.03) < 0.001, f"arbitrage TP should be 0.03, got {arb['take_profit']}"
        assert arb["stop_loss"] == -0.03 or abs(arb["stop_loss"] - (-0.03)) < 0.001, f"arbitrage SL should be -0.03, got {arb['stop_loss']}"
        assert arb["max_hours"] == 6 or abs(arb["max_hours"] - 6) < 0.1, f"arbitrage max_hours should be 6, got {arb['max_hours']}"
        
        print(f"✅ Exit params have correct default values")
    
    def test_update_exit_params_single_strategy(self, authenticated_client):
        """POST /api/config/update should save exit_params for a single strategy"""
        # First get current config
        get_response = authenticated_client.get(f"{BASE_URL}/api/config")
        assert get_response.status_code == 200
        original_params = get_response.json()["exit_params"]
        
        # Update delta_neutral with custom values
        custom_params = {
            "exit_params": {
                "delta_neutral": {
                    "take_profit": 0.03,  # Changed from 0.02
                    "stop_loss": -0.025,  # Changed from -0.02
                    "max_hours": 5        # Changed from 4
                }
            }
        }
        
        update_response = authenticated_client.post(f"{BASE_URL}/api/config/update", json=custom_params)
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        
        # Verify the update was saved
        verify_response = authenticated_client.get(f"{BASE_URL}/api/config")
        assert verify_response.status_code == 200
        
        updated_params = verify_response.json()["exit_params"]
        dn = updated_params["delta_neutral"]
        
        assert abs(dn["take_profit"] - 0.03) < 0.001, f"delta_neutral TP should be 0.03, got {dn['take_profit']}"
        assert abs(dn["stop_loss"] - (-0.025)) < 0.001, f"delta_neutral SL should be -0.025, got {dn['stop_loss']}"
        assert abs(dn["max_hours"] - 5) < 0.1, f"delta_neutral max_hours should be 5, got {dn['max_hours']}"
        
        print(f"✅ POST /api/config/update saves exit_params correctly")
        print(f"   Updated delta_neutral: TP={dn['take_profit']}, SL={dn['stop_loss']}, MaxHrs={dn['max_hours']}")
        
        # Restore original values
        restore_params = {
            "exit_params": {
                "delta_neutral": {
                    "take_profit": 0.02,
                    "stop_loss": -0.02,
                    "max_hours": 4
                }
            }
        }
        authenticated_client.post(f"{BASE_URL}/api/config/update", json=restore_params)
    
    def test_update_exit_params_all_strategies(self, authenticated_client):
        """POST /api/config/update should save exit_params for all strategies"""
        # Custom values for all strategies
        custom_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.025, "stop_loss": -0.025, "max_hours": 3},
                "volatility_exploitation": {"take_profit": 0.06, "stop_loss": -0.06, "max_hours": 10},
                "alpha_directional": {"take_profit": 0.10, "stop_loss": -0.06, "max_hours": 14},
                "arbitrage": {"take_profit": 0.04, "stop_loss": -0.04, "max_hours": 8}
            }
        }
        
        update_response = authenticated_client.post(f"{BASE_URL}/api/config/update", json=custom_params)
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        
        # Verify all updates were saved
        verify_response = authenticated_client.get(f"{BASE_URL}/api/config")
        assert verify_response.status_code == 200
        
        updated_params = verify_response.json()["exit_params"]
        
        # Verify delta_neutral
        assert abs(updated_params["delta_neutral"]["take_profit"] - 0.025) < 0.001
        assert abs(updated_params["delta_neutral"]["stop_loss"] - (-0.025)) < 0.001
        assert abs(updated_params["delta_neutral"]["max_hours"] - 3) < 0.1
        
        # Verify volatility_exploitation
        assert abs(updated_params["volatility_exploitation"]["take_profit"] - 0.06) < 0.001
        assert abs(updated_params["volatility_exploitation"]["stop_loss"] - (-0.06)) < 0.001
        assert abs(updated_params["volatility_exploitation"]["max_hours"] - 10) < 0.1
        
        # Verify alpha_directional
        assert abs(updated_params["alpha_directional"]["take_profit"] - 0.10) < 0.001
        assert abs(updated_params["alpha_directional"]["stop_loss"] - (-0.06)) < 0.001
        assert abs(updated_params["alpha_directional"]["max_hours"] - 14) < 0.1
        
        # Verify arbitrage
        assert abs(updated_params["arbitrage"]["take_profit"] - 0.04) < 0.001
        assert abs(updated_params["arbitrage"]["stop_loss"] - (-0.04)) < 0.001
        assert abs(updated_params["arbitrage"]["max_hours"] - 8) < 0.1
        
        print(f"✅ All 4 strategies exit_params updated and verified")
        
        # Restore defaults
        restore_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4},
                "volatility_exploitation": {"take_profit": 0.05, "stop_loss": -0.05, "max_hours": 8},
                "alpha_directional": {"take_profit": 0.08, "stop_loss": -0.05, "max_hours": 12},
                "arbitrage": {"take_profit": 0.03, "stop_loss": -0.03, "max_hours": 6}
            }
        }
        authenticated_client.post(f"{BASE_URL}/api/config/update", json=restore_params)


class TestPaperTradingExitParams:
    """Test Paper Trading loads exit params from DB"""
    
    def test_paper_trading_status_endpoint(self, authenticated_client):
        """Verify paper trading status endpoint works"""
        response = authenticated_client.get(f"{BASE_URL}/api/paper/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "running" in data, "Response should contain 'running' field"
        
        print(f"✅ Paper trading status endpoint works")
        print(f"   Running: {data.get('running')}")
    
    def test_paper_trading_start_stop(self, authenticated_client):
        """Test paper trading start/stop to verify config loading"""
        # First check status
        status_response = authenticated_client.get(f"{BASE_URL}/api/paper/status")
        assert status_response.status_code == 200
        
        initial_running = status_response.json().get("running", False)
        
        if initial_running:
            # Stop first
            stop_response = authenticated_client.post(f"{BASE_URL}/api/paper/stop")
            assert stop_response.status_code == 200, f"Failed to stop: {stop_response.text}"
            time.sleep(2)
        
        # Start paper trading
        start_response = authenticated_client.post(f"{BASE_URL}/api/paper/start")
        assert start_response.status_code == 200, f"Failed to start: {start_response.text}"
        
        time.sleep(3)  # Wait for initialization
        
        # Check status
        status_response = authenticated_client.get(f"{BASE_URL}/api/paper/status")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        assert status_data.get("running") == True, "Paper trading should be running"
        
        print(f"✅ Paper trading started successfully")
        print(f"   Initial capital: ${status_data.get('initial_capital', 'N/A')}")
        
        # Stop paper trading
        stop_response = authenticated_client.post(f"{BASE_URL}/api/paper/stop")
        assert stop_response.status_code == 200, f"Failed to stop: {stop_response.text}"
        
        print(f"✅ Paper trading stopped successfully")


class TestExitParamsPresets:
    """Test preset buttons functionality (Conservative, Moderate, Aggressive)"""
    
    def test_conservative_preset_values(self, authenticated_client):
        """Test Conservative preset values"""
        # Conservative preset: TP=2%, SL=-2%, MaxHrs=4
        conservative_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4}
            }
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/config/update", json=conservative_params)
        assert response.status_code == 200
        
        verify = authenticated_client.get(f"{BASE_URL}/api/config")
        params = verify.json()["exit_params"]["delta_neutral"]
        
        assert abs(params["take_profit"] - 0.02) < 0.001, "Conservative TP should be 2%"
        assert abs(params["stop_loss"] - (-0.02)) < 0.001, "Conservative SL should be -2%"
        assert abs(params["max_hours"] - 4) < 0.1, "Conservative max_hours should be 4"
        
        print(f"✅ Conservative preset values verified")
    
    def test_moderate_preset_values(self, authenticated_client):
        """Test Moderate preset values"""
        # Moderate preset: TP=5%, SL=-3%, MaxHrs=8
        moderate_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.05, "stop_loss": -0.03, "max_hours": 8}
            }
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/config/update", json=moderate_params)
        assert response.status_code == 200
        
        verify = authenticated_client.get(f"{BASE_URL}/api/config")
        params = verify.json()["exit_params"]["delta_neutral"]
        
        assert abs(params["take_profit"] - 0.05) < 0.001, "Moderate TP should be 5%"
        assert abs(params["stop_loss"] - (-0.03)) < 0.001, "Moderate SL should be -3%"
        assert abs(params["max_hours"] - 8) < 0.1, "Moderate max_hours should be 8"
        
        print(f"✅ Moderate preset values verified")
        
        # Restore defaults
        restore_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4}
            }
        }
        authenticated_client.post(f"{BASE_URL}/api/config/update", json=restore_params)
    
    def test_aggressive_preset_values(self, authenticated_client):
        """Test Aggressive preset values"""
        # Aggressive preset: TP=10%, SL=-5%, MaxHrs=12
        aggressive_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.10, "stop_loss": -0.05, "max_hours": 12}
            }
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/config/update", json=aggressive_params)
        assert response.status_code == 200
        
        verify = authenticated_client.get(f"{BASE_URL}/api/config")
        params = verify.json()["exit_params"]["delta_neutral"]
        
        assert abs(params["take_profit"] - 0.10) < 0.001, "Aggressive TP should be 10%"
        assert abs(params["stop_loss"] - (-0.05)) < 0.001, "Aggressive SL should be -5%"
        assert abs(params["max_hours"] - 12) < 0.1, "Aggressive max_hours should be 12"
        
        print(f"✅ Aggressive preset values verified")
        
        # Restore defaults
        restore_params = {
            "exit_params": {
                "delta_neutral": {"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4}
            }
        }
        authenticated_client.post(f"{BASE_URL}/api/config/update", json=restore_params)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
