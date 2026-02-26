"""
Test Iteration 19 Features:
1. Asset Class Equity Breakdown component displays correctly on Paper Trading page
2. Position sizing uses geometric mean instead of direct product for risk_combined
3. Volatility threshold default is now 0.06 (6%) to enable Delta Neutral strategy
4. /api/config endpoint returns volatility_threshold: 0.06
5. /api/paper/status endpoint returns asset_class_equity data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://optimistic-blackburn-2.preview.emergentagent.com').rstrip('/')
AUTH = ('admin', 'apex2026!')


class TestConfigEndpoint:
    """Test /api/config endpoint returns correct volatility_threshold"""
    
    def test_config_returns_volatility_threshold_0_06(self):
        """Verify volatility_threshold default is 0.06 (6%)"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'volatility_threshold' in data, "volatility_threshold should be in config response"
        assert data['volatility_threshold'] == 0.06, f"Expected 0.06, got {data['volatility_threshold']}"
    
    def test_config_returns_delta_neutral_price_range(self):
        """Verify delta neutral price range is 0.35-0.65"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('delta_neutral_price_min') == 0.35, "delta_neutral_price_min should be 0.35"
        assert data.get('delta_neutral_price_max') == 0.65, "delta_neutral_price_max should be 0.65"
    
    def test_config_returns_all_strategy_thresholds(self):
        """Verify all strategy selection thresholds are present"""
        response = requests.get(f"{BASE_URL}/api/config", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        # Check all strategy thresholds exist
        assert 'volatility_threshold' in data
        assert 'sentiment_strength_threshold' in data
        assert 'sharp_alignment_threshold' in data
        assert 'delta_neutral_price_min' in data
        assert 'delta_neutral_price_max' in data
        assert 'bullish_sentiment_threshold' in data
        assert 'bearish_sentiment_threshold' in data


class TestPaperStatusEndpoint:
    """Test /api/paper/status endpoint returns asset_class_equity"""
    
    def test_paper_status_returns_asset_class_equity_field(self):
        """Verify asset_class_equity field exists in paper status response"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        # asset_class_equity should be in response (may be None if not running)
        assert 'asset_class_equity' in data or data.get('running') == False, \
            "asset_class_equity should be in response or paper trading not running"
    
    def test_paper_status_returns_strategy_results(self):
        """Verify strategy_results field exists in paper status response"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        # strategy_results should be in response
        assert 'strategy_results' in data or data.get('running') == False


class TestHealthEndpoint:
    """Test basic health endpoint"""
    
    def test_health_check(self):
        """Verify health endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('status') == 'healthy'


class TestPaperTradingStartStop:
    """Test paper trading start/stop functionality"""
    
    def test_paper_trading_start(self):
        """Test starting paper trading session"""
        response = requests.post(f"{BASE_URL}/api/paper/start", auth=AUTH)
        # May return 200 (started) or 400 (already running)
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert 'session_id' in data
    
    def test_paper_status_after_start(self):
        """Test paper status returns asset_class_equity after start"""
        # First ensure paper trading is started
        requests.post(f"{BASE_URL}/api/paper/start", auth=AUTH)
        
        # Check status
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        # If running, asset_class_equity should be a dict
        if data.get('running'):
            assert 'asset_class_equity' in data
            # Should be a dict with asset class keys
            if data['asset_class_equity']:
                assert isinstance(data['asset_class_equity'], dict)
    
    def test_paper_trading_stop(self):
        """Test stopping paper trading session"""
        response = requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH)
        # May return 200 (stopped) or 400 (not running)
        assert response.status_code in [200, 400]


class TestGeometricMeanCalculation:
    """Test that position sizing uses geometric mean for risk_combined"""
    
    def test_adaptive_position_sizer_code_review(self):
        """Verify geometric mean is used in adaptive_position_sizer.py"""
        # Read the file and check for geometric mean calculation
        import os
        file_path = '/app/backend/ml/adaptive_position_sizer.py'
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for geometric mean calculation
            assert 'risk_product ** (1 / len(risk_factors))' in content, \
                "Geometric mean calculation should be present"
            assert 'Geometric mean' in content or 'geometric mean' in content, \
                "Comment about geometric mean should be present"
        else:
            pytest.skip("File not found - running in test environment")
    
    def test_paper_trader_volatility_threshold_default(self):
        """Verify paper_trader.py has volatility_threshold = 0.06"""
        import os
        file_path = '/app/backend/paper_trading/paper_trader.py'
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for volatility_threshold = 0.06
            assert 'volatility_threshold = 0.06' in content, \
                "volatility_threshold should be set to 0.06 in paper_trader.py"
        else:
            pytest.skip("File not found - running in test environment")


class TestAssetClassEquityInitialization:
    """Test asset_class_equity initialization in paper_trader.py"""
    
    def test_asset_class_equity_initialized_at_zero(self):
        """Verify asset_class_equity is initialized with all asset classes at 0"""
        import os
        file_path = '/app/backend/paper_trading/paper_trader.py'
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for asset_class_equity initialization
            assert 'asset_class_equity' in content
            # Check that it's initialized with 0.0 values
            assert "'finance': 0.0" in content or '"finance": 0.0' in content
            assert "'politics': 0.0" in content or '"politics": 0.0' in content
            assert "'crypto': 0.0" in content or '"crypto": 0.0' in content
        else:
            pytest.skip("File not found - running in test environment")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
