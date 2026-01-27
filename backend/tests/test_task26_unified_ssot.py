"""
Task 26: Unified Strategy-Based SSOT Tests
==========================================
Tests for the refactored trading engine with unified liquidity/volume filters
based on Three-Speed model (HFT, Alpha, Gamma).

Key test areas:
1. RiskConfig.get_thresholds() - Returns correct thresholds based on strategy + price
2. RiskConfig.get_strategy_path() - Maps strategy names to paths
3. API endpoint returns new parameters
4. ML modules use RISK for thresholds
"""

import pytest
import requests
import os
import sys

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

from tests.conftest import API_BASE_URL as BASE_URL


class TestRiskConfigGetThresholds:
    """Test RiskConfig.get_thresholds() method - Strategy + Price based threshold lookup"""
    
    def test_hft_thresholds_high_price(self):
        """HFT strategy at $0.50 should return (10000, 5000)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('HFT', 0.5)
        
        assert min_liq == 10000.0, f"HFT min_liquidity should be 10000, got {min_liq}"
        assert min_vol == 5000.0, f"HFT min_volume should be 5000, got {min_vol}"
    
    def test_gamma_thresholds_low_price(self):
        """GAMMA strategy at $0.05 should return (250, 250)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('GAMMA', 0.05)
        
        assert min_liq == 250.0, f"GAMMA min_liquidity should be 250, got {min_liq}"
        assert min_vol == 250.0, f"GAMMA min_volume should be 250, got {min_vol}"
    
    def test_alpha_core_thresholds(self):
        """ALPHA strategy at $0.50 (core zone) should return (1000, 1000)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('ALPHA', 0.5)
        
        assert min_liq == 1000.0, f"ALPHA core min_liquidity should be 1000, got {min_liq}"
        assert min_vol == 1000.0, f"ALPHA core min_volume should be 1000, got {min_vol}"
    
    def test_alpha_whale_thresholds(self):
        """ALPHA strategy at $0.05 (whale zone) should return (500, 500)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('ALPHA', 0.05)
        
        assert min_liq == 500.0, f"ALPHA whale min_liquidity should be 500, got {min_liq}"
        assert min_vol == 500.0, f"ALPHA whale min_volume should be 500, got {min_vol}"
    
    def test_arbitrage_maps_to_hft(self):
        """'arbitrage' strategy should map to HFT path and return (10000, 5000)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('arbitrage', 0.5)
        
        assert min_liq == 10000.0, f"arbitrage should use HFT thresholds (10000), got {min_liq}"
        assert min_vol == 5000.0, f"arbitrage should use HFT thresholds (5000), got {min_vol}"
    
    def test_gamma_scalp_maps_to_gamma(self):
        """'gamma_scalp' strategy should map to GAMMA path and return (250, 250)"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('gamma_scalp', 0.05)
        
        assert min_liq == 250.0, f"gamma_scalp should use GAMMA thresholds (250), got {min_liq}"
        assert min_vol == 250.0, f"gamma_scalp should use GAMMA thresholds (250), got {min_vol}"
    
    def test_delta_neutral_maps_to_hft(self):
        """'delta_neutral' strategy should map to HFT path"""
        from risk_config import RISK
        
        min_liq, min_vol = RISK.get_thresholds('delta_neutral', 0.5)
        
        assert min_liq == 10000.0, f"delta_neutral should use HFT thresholds, got {min_liq}"
        assert min_vol == 5000.0, f"delta_neutral should use HFT thresholds, got {min_vol}"
    
    def test_alpha_directional_maps_to_alpha(self):
        """'alpha_directional' strategy should map to ALPHA path"""
        from risk_config import RISK
        
        # Core zone price
        min_liq, min_vol = RISK.get_thresholds('alpha_directional', 0.5)
        assert min_liq == 1000.0, f"alpha_directional core should be 1000, got {min_liq}"
        
        # Whale zone price
        min_liq, min_vol = RISK.get_thresholds('alpha_directional', 0.05)
        assert min_liq == 500.0, f"alpha_directional whale should be 500, got {min_liq}"


class TestRiskConfigGetStrategyPath:
    """Test RiskConfig.get_strategy_path() method - Strategy name to path mapping"""
    
    def test_arbitrage_returns_hft(self):
        """'arbitrage' should return 'HFT'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('arbitrage')
        assert path == 'HFT', f"arbitrage should map to HFT, got {path}"
    
    def test_gamma_scalp_returns_gamma(self):
        """'gamma_scalp' should return 'GAMMA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('gamma_scalp')
        assert path == 'GAMMA', f"gamma_scalp should map to GAMMA, got {path}"
    
    def test_alpha_directional_returns_alpha(self):
        """'alpha_directional' should return 'ALPHA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('alpha_directional')
        assert path == 'ALPHA', f"alpha_directional should map to ALPHA, got {path}"
    
    def test_delta_neutral_returns_hft(self):
        """'delta_neutral' should return 'HFT'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('delta_neutral')
        assert path == 'HFT', f"delta_neutral should map to HFT, got {path}"
    
    def test_market_making_returns_hft(self):
        """'market_making' should return 'HFT'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('market_making')
        assert path == 'HFT', f"market_making should map to HFT, got {path}"
    
    def test_whale_returns_gamma(self):
        """'whale' should return 'GAMMA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('whale')
        assert path == 'GAMMA', f"whale should map to GAMMA, got {path}"
    
    def test_moonshot_returns_gamma(self):
        """'moonshot' should return 'GAMMA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('moonshot')
        assert path == 'GAMMA', f"moonshot should map to GAMMA, got {path}"
    
    def test_unknown_strategy_defaults_to_alpha(self):
        """Unknown strategy should default to 'ALPHA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path('unknown_strategy')
        assert path == 'ALPHA', f"unknown strategy should default to ALPHA, got {path}"
    
    def test_none_strategy_defaults_to_alpha(self):
        """None strategy should default to 'ALPHA'"""
        from risk_config import RISK
        
        path = RISK.get_strategy_path(None)
        assert path == 'ALPHA', f"None strategy should default to ALPHA, got {path}"


class TestAPIPortfolioRiskEndpoint:
    """Test GET /api/config/portfolio-risk returns all new Task 26 parameters"""
    
    def test_api_returns_hft_liquidity_params(self):
        """API should return hft_min_liquidity and hft_min_volume_24h in config"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200, f"API returned {response.status_code}"
        
        data = response.json()
        # API returns nested structure with 'config' and 'defaults' keys
        config = data.get('config', data)  # Fallback to data if no 'config' key
        
        assert 'hft_min_liquidity' in config, "Missing hft_min_liquidity in API response"
        assert 'hft_min_volume_24h' in config, "Missing hft_min_volume_24h in API response"
        assert config['hft_min_liquidity'] == 10000.0, f"hft_min_liquidity should be 10000, got {config['hft_min_liquidity']}"
        assert config['hft_min_volume_24h'] == 5000.0, f"hft_min_volume_24h should be 5000, got {config['hft_min_volume_24h']}"
    
    def test_api_returns_alpha_liquidity_params(self):
        """API should return alpha_core_liquidity, alpha_whale_liquidity, etc."""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200
        
        data = response.json()
        config = data.get('config', data)
        
        assert 'alpha_core_liquidity' in config, "Missing alpha_core_liquidity"
        assert 'alpha_whale_liquidity' in config, "Missing alpha_whale_liquidity"
        assert 'alpha_core_volume' in config, "Missing alpha_core_volume"
        assert 'alpha_whale_volume' in config, "Missing alpha_whale_volume"
        
        assert config['alpha_core_liquidity'] == 1000.0
        assert config['alpha_whale_liquidity'] == 500.0
        assert config['alpha_core_volume'] == 1000.0
        assert config['alpha_whale_volume'] == 500.0
    
    def test_api_returns_gamma_liquidity_params(self):
        """API should return gamma_min_liquidity and gamma_min_volume_24h"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200
        
        data = response.json()
        config = data.get('config', data)
        
        assert 'gamma_min_liquidity' in config, "Missing gamma_min_liquidity"
        assert 'gamma_min_volume_24h' in config, "Missing gamma_min_volume_24h"
        
        assert config['gamma_min_liquidity'] == 250.0
        assert config['gamma_min_volume_24h'] == 250.0
    
    def test_api_returns_analysis_thresholds(self):
        """API should return analysis thresholds (sharp_detection, hot_market, norm_anchors)"""
        response = requests.get(f"{BASE_URL}/api/config/portfolio-risk")
        assert response.status_code == 200
        
        data = response.json()
        config = data.get('config', data)
        
        # Data cleaning thresholds
        assert 'data_cleaning_min_liquidity' in config, "Missing data_cleaning_min_liquidity"
        assert 'data_cleaning_min_volume' in config, "Missing data_cleaning_min_volume"
        assert config['data_cleaning_min_liquidity'] == 250.0
        assert config['data_cleaning_min_volume'] == 250.0
        
        # Feature triggers
        assert 'sharp_detection_min_volume' in config, "Missing sharp_detection_min_volume"
        assert 'hot_market_volume_threshold' in config, "Missing hot_market_volume_threshold"
        assert config['sharp_detection_min_volume'] == 25000.0
        assert config['hot_market_volume_threshold'] == 50000.0
        
        # Normalization anchors
        assert 'norm_liquidity_anchor' in config, "Missing norm_liquidity_anchor"
        assert 'norm_volume_anchor' in config, "Missing norm_volume_anchor"
        assert config['norm_liquidity_anchor'] == 50000.0
        assert config['norm_volume_anchor'] == 50000.0


class TestDefaultsValues:
    """Test that DEFAULTS dict has all Task 26 parameters with correct values"""
    
    def test_defaults_hft_values(self):
        """DEFAULTS should have HFT values: 10000/5000"""
        from risk_config import DEFAULTS
        
        assert DEFAULTS['HFT_MIN_LIQUIDITY'] == 10000.0
        assert DEFAULTS['HFT_MIN_VOLUME_24H'] == 5000.0
    
    def test_defaults_alpha_values(self):
        """DEFAULTS should have ALPHA values: core 1000/1000, whale 500/500"""
        from risk_config import DEFAULTS
        
        assert DEFAULTS['ALPHA_CORE_LIQUIDITY'] == 1000.0
        assert DEFAULTS['ALPHA_WHALE_LIQUIDITY'] == 500.0
        assert DEFAULTS['ALPHA_CORE_VOLUME'] == 1000.0
        assert DEFAULTS['ALPHA_WHALE_VOLUME'] == 500.0
    
    def test_defaults_gamma_values(self):
        """DEFAULTS should have GAMMA values: 250/250"""
        from risk_config import DEFAULTS
        
        assert DEFAULTS['GAMMA_MIN_LIQUIDITY'] == 250.0
        assert DEFAULTS['GAMMA_MIN_VOLUME_24H'] == 250.0
    
    def test_defaults_analysis_values(self):
        """DEFAULTS should have analysis thresholds"""
        from risk_config import DEFAULTS
        
        assert DEFAULTS['DATA_CLEANING_MIN_LIQUIDITY'] == 250.0
        assert DEFAULTS['DATA_CLEANING_MIN_VOLUME'] == 250.0
        assert DEFAULTS['SHARP_DETECTION_MIN_VOLUME'] == 25000.0
        assert DEFAULTS['HOT_MARKET_VOLUME_THRESHOLD'] == 50000.0
        assert DEFAULTS['NORM_LIQUIDITY_ANCHOR'] == 50000.0
        assert DEFAULTS['NORM_VOLUME_ANCHOR'] == 50000.0


class TestMLModulesUseRISK:
    """Test that ML modules import and use RISK for thresholds"""
    
    def test_adaptive_position_sizer_imports_risk(self):
        """adaptive_position_sizer.py should import RISK from risk_config"""
        with open('/app/backend/ml/adaptive_position_sizer.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "adaptive_position_sizer.py should import from risk_config"
        assert 'RISK' in content, "adaptive_position_sizer.py should use RISK"
    
    def test_adaptive_position_sizer_uses_get_thresholds(self):
        """adaptive_position_sizer.py should use RISK.get_thresholds()"""
        with open('/app/backend/ml/adaptive_position_sizer.py', 'r') as f:
            content = f.read()
        
        assert 'get_thresholds' in content, \
            "adaptive_position_sizer.py should use RISK.get_thresholds()"
    
    def test_bayesian_outlier_uses_data_cleaning_thresholds(self):
        """bayesian_outlier.py should use RISK.DATA_CLEANING_* thresholds"""
        with open('/app/backend/ml/bayesian_outlier.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "bayesian_outlier.py should import from risk_config"
        assert 'DATA_CLEANING' in content, \
            "bayesian_outlier.py should use DATA_CLEANING thresholds"
    
    def test_sharp_detector_uses_sharp_detection_threshold(self):
        """sharp_detector.py should use RISK.SHARP_DETECTION_MIN_VOLUME (25000)"""
        with open('/app/backend/ml/sharp_detector.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "sharp_detector.py should import from risk_config"
        assert 'SHARP_DETECTION' in content, \
            "sharp_detector.py should use SHARP_DETECTION threshold"
    
    def test_rl_engine_uses_norm_anchors(self):
        """rl_engine.py should use RISK.NORM_* anchors (50000) for normalization"""
        with open('/app/backend/ml/rl_engine.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "rl_engine.py should import from risk_config"
        assert 'NORM_' in content or 'norm_' in content, \
            "rl_engine.py should use NORM anchors"
    
    def test_signal_fusion_uses_norm_volume_anchor(self):
        """signal_fusion.py should use RISK.NORM_VOLUME_ANCHOR for confidence"""
        with open('/app/backend/ml/signal_fusion.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "signal_fusion.py should import from risk_config"
        assert 'NORM_VOLUME_ANCHOR' in content, \
            "signal_fusion.py should use NORM_VOLUME_ANCHOR"
    
    def test_sentiment_llm_uses_hot_market_threshold(self):
        """sentiment_llm.py should use RISK.HOT_MARKET_VOLUME_THRESHOLD"""
        with open('/app/backend/ml/sentiment_llm.py', 'r') as f:
            content = f.read()
        
        assert 'from risk_config import' in content or 'import risk_config' in content, \
            "sentiment_llm.py should import from risk_config"
        assert 'HOT_MARKET_VOLUME_THRESHOLD' in content, \
            "sentiment_llm.py should use HOT_MARKET_VOLUME_THRESHOLD"


class TestRiskConfigAttributes:
    """Test that RiskConfig class has all Task 26 attributes"""
    
    def test_risk_has_hft_attributes(self):
        """RiskConfig should have HFT_MIN_LIQUIDITY and HFT_MIN_VOLUME_24H"""
        from risk_config import RISK
        
        assert hasattr(RISK, 'HFT_MIN_LIQUIDITY'), "Missing HFT_MIN_LIQUIDITY attribute"
        assert hasattr(RISK, 'HFT_MIN_VOLUME_24H'), "Missing HFT_MIN_VOLUME_24H attribute"
        assert RISK.HFT_MIN_LIQUIDITY == 10000.0
        assert RISK.HFT_MIN_VOLUME_24H == 5000.0
    
    def test_risk_has_alpha_attributes(self):
        """RiskConfig should have ALPHA_CORE_* and ALPHA_WHALE_* attributes"""
        from risk_config import RISK
        
        assert hasattr(RISK, 'ALPHA_CORE_LIQUIDITY'), "Missing ALPHA_CORE_LIQUIDITY"
        assert hasattr(RISK, 'ALPHA_WHALE_LIQUIDITY'), "Missing ALPHA_WHALE_LIQUIDITY"
        assert hasattr(RISK, 'ALPHA_CORE_VOLUME'), "Missing ALPHA_CORE_VOLUME"
        assert hasattr(RISK, 'ALPHA_WHALE_VOLUME'), "Missing ALPHA_WHALE_VOLUME"
    
    def test_risk_has_gamma_attributes(self):
        """RiskConfig should have GAMMA_MIN_LIQUIDITY and GAMMA_MIN_VOLUME_24H"""
        from risk_config import RISK
        
        assert hasattr(RISK, 'GAMMA_MIN_LIQUIDITY'), "Missing GAMMA_MIN_LIQUIDITY"
        assert hasattr(RISK, 'GAMMA_MIN_VOLUME_24H'), "Missing GAMMA_MIN_VOLUME_24H"
        assert RISK.GAMMA_MIN_LIQUIDITY == 250.0
        assert RISK.GAMMA_MIN_VOLUME_24H == 250.0
    
    def test_risk_has_analysis_attributes(self):
        """RiskConfig should have all analysis threshold attributes"""
        from risk_config import RISK
        
        assert hasattr(RISK, 'DATA_CLEANING_MIN_LIQUIDITY')
        assert hasattr(RISK, 'DATA_CLEANING_MIN_VOLUME')
        assert hasattr(RISK, 'SHARP_DETECTION_MIN_VOLUME')
        assert hasattr(RISK, 'HOT_MARKET_VOLUME_THRESHOLD')
        assert hasattr(RISK, 'NORM_LIQUIDITY_ANCHOR')
        assert hasattr(RISK, 'NORM_VOLUME_ANCHOR')
        
        assert RISK.SHARP_DETECTION_MIN_VOLUME == 25000.0
        assert RISK.HOT_MARKET_VOLUME_THRESHOLD == 50000.0
        assert RISK.NORM_LIQUIDITY_ANCHOR == 50000.0
        assert RISK.NORM_VOLUME_ANCHOR == 50000.0


class TestToDictIncludesTask26Params:
    """Test that to_dict() includes all Task 26 parameters"""
    
    def test_to_dict_has_hft_params(self):
        """to_dict() should include hft_min_liquidity and hft_min_volume_24h"""
        from risk_config import RISK
        
        data = RISK.to_dict()
        
        assert 'hft_min_liquidity' in data
        assert 'hft_min_volume_24h' in data
    
    def test_to_dict_has_alpha_params(self):
        """to_dict() should include all alpha liquidity/volume params"""
        from risk_config import RISK
        
        data = RISK.to_dict()
        
        assert 'alpha_core_liquidity' in data
        assert 'alpha_whale_liquidity' in data
        assert 'alpha_core_volume' in data
        assert 'alpha_whale_volume' in data
    
    def test_to_dict_has_gamma_params(self):
        """to_dict() should include gamma_min_liquidity and gamma_min_volume_24h"""
        from risk_config import RISK
        
        data = RISK.to_dict()
        
        assert 'gamma_min_liquidity' in data
        assert 'gamma_min_volume_24h' in data
    
    def test_to_dict_has_analysis_params(self):
        """to_dict() should include all analysis threshold params"""
        from risk_config import RISK
        
        data = RISK.to_dict()
        
        assert 'data_cleaning_min_liquidity' in data
        assert 'data_cleaning_min_volume' in data
        assert 'sharp_detection_min_volume' in data
        assert 'hot_market_volume_threshold' in data
        assert 'norm_liquidity_anchor' in data
        assert 'norm_volume_anchor' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
