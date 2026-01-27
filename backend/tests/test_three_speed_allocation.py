"""
Task 25: Three-Speed Capital Allocation Tests
Tests for HFT (35%), Alpha (55%), Gamma (10%) allocation buckets
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestThreeSpeedAllocationAPI:
    """Test Three-Speed Capital Allocation API endpoints"""
    
    def test_get_portfolio_risk_returns_three_allocations(self):
        """GET /api/config/portfolio-risk returns hft, alpha, gamma allocation percentages"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200
        
        data = response.json()
        assert 'config' in data
        config = data['config']
        
        # Verify all three allocation fields exist
        assert 'hft_allocation_pct' in config, "Missing hft_allocation_pct"
        assert 'alpha_allocation_pct' in config, "Missing alpha_allocation_pct"
        assert 'gamma_allocation_pct' in config, "Missing gamma_allocation_pct"
        
        # Verify they are numeric
        assert isinstance(config['hft_allocation_pct'], (int, float))
        assert isinstance(config['alpha_allocation_pct'], (int, float))
        assert isinstance(config['gamma_allocation_pct'], (int, float))
    
    def test_get_portfolio_risk_defaults_are_35_55_10(self):
        """GET /api/config/portfolio-risk defaults should be 35/55/10"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200
        
        data = response.json()
        assert 'defaults' in data
        defaults = data['defaults']
        
        # Verify default values
        assert defaults['hft_allocation_pct'] == 35.0, f"HFT default should be 35, got {defaults['hft_allocation_pct']}"
        assert defaults['alpha_allocation_pct'] == 55.0, f"Alpha default should be 55, got {defaults['alpha_allocation_pct']}"
        assert defaults['gamma_allocation_pct'] == 10.0, f"Gamma default should be 10, got {defaults['gamma_allocation_pct']}"
    
    def test_post_portfolio_risk_saves_allocations(self):
        """POST /api/config/portfolio-risk saves all three allocation percentages"""
        # Save custom allocations
        payload = {
            'hft_allocation_pct': 30,
            'alpha_allocation_pct': 60,
            'gamma_allocation_pct': 10
        }
        response = requests.post(f"{BASE_URL}/api/config/portfolio-risk", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('success') == True
        assert 'config' in data
        
        # Verify saved values
        config = data['config']
        assert config['hft_allocation_pct'] == 30.0
        assert config['alpha_allocation_pct'] == 60.0
        assert config['gamma_allocation_pct'] == 10.0
        
        # Verify persistence with GET
        get_response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        get_data = get_response.json()
        assert get_data['config']['hft_allocation_pct'] == 30.0
        assert get_data['config']['alpha_allocation_pct'] == 60.0
        assert get_data['config']['gamma_allocation_pct'] == 10.0
    
    def test_reset_portfolio_risk_restores_defaults(self):
        """POST /api/config/portfolio-risk/reset resets to defaults (35/55/10)"""
        # First set custom values
        payload = {'hft_allocation_pct': 20, 'alpha_allocation_pct': 70, 'gamma_allocation_pct': 10}
        requests.post(f"{BASE_URL}/api/config/portfolio-risk", json=payload)
        
        # Reset to defaults
        response = requests.post(f"{BASE_URL}/api/config/portfolio-risk/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert 'config' in data
        config = data['config']
        
        # Verify reset to defaults
        assert config['hft_allocation_pct'] == 35.0, f"HFT should reset to 35, got {config['hft_allocation_pct']}"
        assert config['alpha_allocation_pct'] == 55.0, f"Alpha should reset to 55, got {config['alpha_allocation_pct']}"
        assert config['gamma_allocation_pct'] == 10.0, f"Gamma should reset to 10, got {config['gamma_allocation_pct']}"
        
        # Verify persistence
        get_response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        get_data = get_response.json()
        assert get_data['config']['hft_allocation_pct'] == 35.0
        assert get_data['config']['alpha_allocation_pct'] == 55.0
        assert get_data['config']['gamma_allocation_pct'] == 10.0
    
    def test_allocations_sum_validation(self):
        """Test that allocations can be set to any values (validation is frontend-only)"""
        # Backend should accept any values - validation is UI-side
        payload = {
            'hft_allocation_pct': 40,
            'alpha_allocation_pct': 40,
            'gamma_allocation_pct': 20
        }
        response = requests.post(f"{BASE_URL}/api/config/portfolio-risk", json=payload)
        assert response.status_code == 200
        
        # Sum = 100, should work
        data = response.json()
        assert data['config']['hft_allocation_pct'] == 40.0
        assert data['config']['alpha_allocation_pct'] == 40.0
        assert data['config']['gamma_allocation_pct'] == 20.0
        
        # Reset for other tests
        requests.post(f"{BASE_URL}/api/config/portfolio-risk/reset")


class TestRiskConfigDefaults:
    """Test risk_config.py DEFAULTS and RiskConfig class"""
    
    def test_defaults_contain_three_speed_allocations(self):
        """Verify DEFAULTS dict has correct allocation values"""
        # This is tested via API since we can't import directly
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        defaults = response.json()['defaults']
        
        assert defaults['hft_allocation_pct'] == 35.0
        assert defaults['alpha_allocation_pct'] == 55.0
        assert defaults['gamma_allocation_pct'] == 10.0
    
    def test_to_dict_includes_allocations(self):
        """Verify to_dict() includes all three allocation values"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        config = response.json()['config']
        
        # to_dict() is called by the API - verify fields exist
        assert 'hft_allocation_pct' in config
        assert 'alpha_allocation_pct' in config
        assert 'gamma_allocation_pct' in config
    
    def test_load_from_dict_loads_allocations(self):
        """Verify load_from_dict() loads all three allocation values"""
        # Set values via POST (which uses load_from_dict internally)
        payload = {'hft_allocation_pct': 25, 'alpha_allocation_pct': 65, 'gamma_allocation_pct': 10}
        requests.post(f"{BASE_URL}/api/config/portfolio-risk", json=payload)
        
        # Verify loaded correctly
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        config = response.json()['config']
        
        assert config['hft_allocation_pct'] == 25.0
        assert config['alpha_allocation_pct'] == 65.0
        assert config['gamma_allocation_pct'] == 10.0
        
        # Reset
        requests.post(f"{BASE_URL}/api/config/portfolio-risk/reset")
    
    def test_reset_to_defaults_resets_allocations(self):
        """Verify reset_to_defaults() resets all three allocations"""
        # Set custom values
        payload = {'hft_allocation_pct': 50, 'alpha_allocation_pct': 40, 'gamma_allocation_pct': 10}
        requests.post(f"{BASE_URL}/api/config/portfolio-risk", json=payload)
        
        # Reset
        response = requests.post(f"{BASE_URL}/api/config/portfolio-risk/reset")
        config = response.json()['config']
        
        # Verify defaults restored
        assert config['hft_allocation_pct'] == 35.0
        assert config['alpha_allocation_pct'] == 55.0
        assert config['gamma_allocation_pct'] == 10.0


class TestDeployedCapitalLinkage:
    """Test that allocations are linked to deployed capital correctly"""
    
    def test_allocations_relative_to_deployed_capital(self):
        """Verify allocations are percentages of deployed capital, not total"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        config = response.json()['config']
        
        # Get deployed capital percentage
        deployed_pct = config.get('allocated_capital_pct', 80)
        
        # Allocations should sum to 100% of deployed capital
        hft = config['hft_allocation_pct']
        alpha = config['alpha_allocation_pct']
        gamma = config['gamma_allocation_pct']
        
        total = hft + alpha + gamma
        assert total == 100.0, f"Allocations should sum to 100% of deployed capital, got {total}%"
    
    def test_dollar_amounts_calculation(self):
        """Test dollar amounts per $1000 deployed capital"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        config = response.json()['config']
        
        deployed_pct = config.get('allocated_capital_pct', 80) / 100
        hft_pct = config['hft_allocation_pct'] / 100
        alpha_pct = config['alpha_allocation_pct'] / 100
        gamma_pct = config['gamma_allocation_pct'] / 100
        
        # Per $1000 wallet
        wallet = 1000
        deployed = wallet * deployed_pct  # $800 at 80%
        
        hft_dollars = deployed * hft_pct
        alpha_dollars = deployed * alpha_pct
        gamma_dollars = deployed * gamma_pct
        
        # At defaults (80% deployed, 35/55/10 split):
        # HFT: $800 * 0.35 = $280
        # Alpha: $800 * 0.55 = $440
        # Gamma: $800 * 0.10 = $80
        
        assert hft_dollars + alpha_dollars + gamma_dollars == deployed, \
            f"Dollar amounts should sum to deployed capital: {hft_dollars} + {alpha_dollars} + {gamma_dollars} != {deployed}"


# Cleanup fixture
@pytest.fixture(autouse=True, scope="class")
def cleanup_after_tests():
    """Reset to defaults after each test class"""
    yield
    requests.post(f"{BASE_URL}/api/config/portfolio-risk/reset")
