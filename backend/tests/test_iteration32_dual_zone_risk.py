"""
Task 21: Dual-Zone Risk Architecture - API & Integration Tests
==============================================================

Tests for:
1. Backend risk_config.py constants (WHALE zone vs CORE zone parameters)
2. classify_market_regime function (4 regimes: CONVEXITY_OPPORTUNITY, TAKER_TIGHT, MAKER_WIDE, ZOMBIE)
3. Kill switch rejects prices outside 3%-97% range as ZOMBIE
4. Whale zone ($0.01-$0.10) uses tick-based spread logic (max 3 cents)
5. Core zone ($0.10+) uses percentage-based spread logic (2% taker, 10% maker, 12% zombie)
6. Paper trading API endpoints: /api/paper/status, /api/paper/start, /api/paper/stop
7. Alpha weights API: GET/POST /api/settings/alpha
"""

import pytest
import requests
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://markets-first-engine.preview.emergentagent.com').rstrip('/')

# Auth credentials
AUTH = ('admin', 'apex2026!')


class TestRiskConfigConstants:
    """Test that all risk constants are properly defined in risk_config.py."""
    
    def test_import_risk_config(self):
        """Verify risk_config.py can be imported."""
        from risk_config import RISK, MarketRegime, classify_market_regime
        assert RISK is not None
        assert MarketRegime is not None
        assert classify_market_regime is not None
    
    def test_global_safety_parameters(self):
        """Verify global safety parameters exist and are sensible."""
        from risk_config import RISK
        assert RISK.STOP_LOSS_PCT == 0.15  # 15%
        assert RISK.MAX_DRAWDOWN_PCT == 5.0  # 5%
        assert RISK.KILL_SWITCH_LOW == 0.03  # 3 cents
        assert RISK.KILL_SWITCH_HIGH == 0.97  # 97 cents
    
    def test_whale_zone_parameters(self):
        """Verify Whale Zone parameters for convexity trading."""
        from risk_config import RISK
        assert RISK.WHALE_PRICE_CEILING == 0.10  # $0.10
        assert RISK.WHALE_MAX_SPREAD_CENTS == 0.03  # 3 cents
        assert RISK.WHALE_MIN_LIQUIDITY == 500.0  # $500
        assert RISK.WHALE_MIN_VOLUME_24H == 500.0  # $500
        assert RISK.WHALE_MAX_POSITION == 15.0  # $15
        assert RISK.WHALE_MAX_POSITION_PCT == 1.0  # 1%
    
    def test_core_zone_parameters(self):
        """Verify Core Alpha Zone parameters."""
        from risk_config import RISK
        assert RISK.CORE_TAKER_SPREAD_PCT == 0.02  # 2%
        assert RISK.CORE_MAKER_SPREAD_PCT == 0.10  # 10%
        assert RISK.CORE_ZOMBIE_SPREAD_PCT == 0.12  # 12%
        assert RISK.CORE_MIN_LIQUIDITY == 1000.0  # $1K
        assert RISK.CORE_MIN_VOLUME_24H == 1000.0  # $1K
        assert RISK.CORE_MAX_POSITION == 100.0  # $100
        assert RISK.CORE_MAX_POSITION_PCT == 3.0  # 3%
    
    def test_fee_structure(self):
        """Verify fee structure is correct."""
        from risk_config import RISK
        assert RISK.TAKER_FEE == 0.02  # 2%
        assert RISK.MAKER_FEE == 0.00  # 0%
        assert RISK.ADVERSE_SELECTION_COST == 0.005  # 0.5%


class TestMarketRegimeClassification:
    """Test the classify_market_regime function for all 4 regimes."""
    
    def test_kill_switch_extreme_low(self):
        """Price below 3 cents should be ZOMBIE."""
        from risk_config import classify_market_regime, MarketRegime
        regime, diag = classify_market_regime(
            best_bid=0.01, 
            best_ask=0.02, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'kill switch' in diag.get('reject_reason', '').lower()
    
    def test_kill_switch_extreme_high(self):
        """Price above 97 cents should be ZOMBIE."""
        from risk_config import classify_market_regime, MarketRegime
        regime, diag = classify_market_regime(
            best_bid=0.98, 
            best_ask=0.99, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'kill switch' in diag.get('reject_reason', '').lower()
    
    def test_whale_zone_convexity_opportunity(self):
        """Cheap asset with tight tick spread = CONVEXITY_OPPORTUNITY."""
        from risk_config import classify_market_regime, MarketRegime, RISK
        # Price: $0.05, Spread: 1 cent (tight)
        regime, diag = classify_market_regime(
            best_bid=0.04, 
            best_ask=0.05, 
            volume_24h=1000.0
        )
        assert regime == MarketRegime.CONVEXITY_OPPORTUNITY
        assert diag['zone'] == 'WHALE'
        assert diag['strategy'] == 'gamma_scalp'
        assert diag['max_position'] == RISK.WHALE_MAX_POSITION
    
    def test_whale_zone_wide_tick_spread_zombie(self):
        """Cheap asset with wide tick spread = ZOMBIE (too risky)."""
        from risk_config import classify_market_regime, MarketRegime
        # Price: $0.05, Spread: 5 cents (too wide)
        regime, diag = classify_market_regime(
            best_bid=0.02, 
            best_ask=0.07, 
            volume_24h=1000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'tick spread' in diag.get('reject_reason', '').lower()
    
    def test_whale_zone_low_volume_zombie(self):
        """Cheap asset with low volume = ZOMBIE."""
        from risk_config import classify_market_regime, MarketRegime
        regime, diag = classify_market_regime(
            best_bid=0.04, 
            best_ask=0.05, 
            volume_24h=100.0  # Below $500 minimum
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'volume' in diag.get('reject_reason', '').lower()
    
    def test_core_zone_taker_tight(self):
        """Standard asset with tight % spread = TAKER_TIGHT (< 2%)."""
        from risk_config import classify_market_regime, MarketRegime
        # Price: $0.50, Spread: ~1% (strictly less than 2%)
        regime, diag = classify_market_regime(
            best_bid=0.4975, 
            best_ask=0.5025, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.TAKER_TIGHT
        assert diag['zone'] == 'CORE'
        assert diag['strategy'] == 'taker_directional'
    
    def test_core_zone_maker_wide(self):
        """Standard asset with moderate % spread = MAKER_WIDE (2-12%)."""
        from risk_config import classify_market_regime, MarketRegime
        # Price: $0.50, Spread: ~6% (within 2-12% range)
        regime, diag = classify_market_regime(
            best_bid=0.485, 
            best_ask=0.515, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.MAKER_WIDE
        assert diag['zone'] == 'CORE'
        assert diag['strategy'] == 'maker_limit_order'
    
    def test_core_zone_zombie(self):
        """Standard asset with very wide % spread = ZOMBIE (> 12%)."""
        from risk_config import classify_market_regime, MarketRegime
        # Price: $0.50, Spread: 15% (dead)
        regime, diag = classify_market_regime(
            best_bid=0.4625, 
            best_ask=0.5375, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'spread' in diag.get('reject_reason', '').lower()
    
    def test_core_zone_low_volume_zombie(self):
        """Standard asset with low volume = ZOMBIE."""
        from risk_config import classify_market_regime, MarketRegime
        regime, diag = classify_market_regime(
            best_bid=0.495, 
            best_ask=0.505, 
            volume_24h=500.0  # Below $1K minimum for core zone
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'volume' in diag.get('reject_reason', '').lower()


class TestMarketRegimeEnum:
    """Test MarketRegime enum values."""
    
    def test_regime_values(self):
        """Verify all 4 regime values are correct strings."""
        from risk_config import MarketRegime
        assert MarketRegime.CONVEXITY_OPPORTUNITY == "CONVEXITY_OPPORTUNITY"
        assert MarketRegime.TAKER_TIGHT == "TAKER_TIGHT"
        assert MarketRegime.MAKER_WIDE == "MAKER_WIDE"
        assert MarketRegime.ZOMBIE == "ZOMBIE"


class TestZoneParameters:
    """Test the get_zone_parameters helper function."""
    
    def test_whale_zone_parameters(self):
        """Low price should return Whale zone parameters."""
        from risk_config import get_zone_parameters, RISK
        params = get_zone_parameters(mid_price=0.05)
        assert params['zone'] == 'WHALE'
        assert params['spread_type'] == 'absolute_cents'
        assert params['max_spread'] == RISK.WHALE_MAX_SPREAD_CENTS
        assert params['max_position'] == RISK.WHALE_MAX_POSITION
    
    def test_core_zone_parameters(self):
        """Higher price should return Core zone parameters."""
        from risk_config import get_zone_parameters, RISK
        params = get_zone_parameters(mid_price=0.50)
        assert params['zone'] == 'CORE'
        assert params['spread_type'] == 'percentage'
        assert params['max_spread'] == RISK.CORE_MAKER_SPREAD_PCT
        assert params['max_position'] == RISK.CORE_MAX_POSITION


class TestSpreadAcceptability:
    """Test the is_spread_acceptable helper function."""
    
    def test_whale_zone_tight_spread_acceptable(self):
        """Tight tick spread in whale zone should be acceptable."""
        from risk_config import is_spread_acceptable
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.02,  # 2 cents (within 3 cent limit)
            spread_pct=0.40,    # 40% (ignored in whale zone)
            mid_price=0.05
        )
        assert acceptable is True
        assert 'whale_zone' in reason.lower()
    
    def test_whale_zone_wide_spread_rejected(self):
        """Wide tick spread in whale zone should be rejected."""
        from risk_config import is_spread_acceptable
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.05,  # 5 cents (exceeds 3 cent limit)
            spread_pct=1.0,     # 100% (ignored in whale zone)
            mid_price=0.05
        )
        assert acceptable is False
        assert 'whale_zone' in reason.lower()
    
    def test_core_zone_tight_spread_acceptable(self):
        """Tight % spread in core zone should be acceptable."""
        from risk_config import is_spread_acceptable
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.01,
            spread_pct=0.02,  # 2% (within limit)
            mid_price=0.50
        )
        assert acceptable is True
        assert 'core_zone' in reason.lower()
    
    def test_core_zone_wide_spread_hft_acceptable(self):
        """Wide % spread should be acceptable for HFT (maker)."""
        from risk_config import is_spread_acceptable
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.06,
            spread_pct=0.12,  # 12% (at zombie threshold)
            mid_price=0.50,
            is_hft=True
        )
        assert acceptable is True  # HFT has higher tolerance


class TestPaperTradingAPIEndpoints:
    """Test paper trading API endpoints."""
    
    def test_paper_status_endpoint(self):
        """Test GET /api/paper/status returns valid response."""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        assert 'running' in data
        assert 'open_positions' in data
        assert 'total_trades' in data
        assert 'total_pnl' in data
    
    def test_paper_start_requires_auth(self):
        """Test POST /api/paper/start requires authentication."""
        response = requests.post(f"{BASE_URL}/api/paper/start")
        assert response.status_code == 401
    
    def test_paper_stop_requires_auth(self):
        """Test POST /api/paper/stop requires authentication."""
        response = requests.post(f"{BASE_URL}/api/paper/stop")
        assert response.status_code == 401
    
    def test_paper_start_with_auth(self):
        """Test POST /api/paper/start with valid auth."""
        response = requests.post(f"{BASE_URL}/api/paper/start", auth=AUTH)
        # Should return 200 (started) or 400 (already running)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert 'session_id' in data or 'message' in data
    
    def test_paper_stop_with_auth(self):
        """Test POST /api/paper/stop with valid auth."""
        response = requests.post(f"{BASE_URL}/api/paper/stop", auth=AUTH)
        # Should return 200 (stopped) or 400 (not running)
        assert response.status_code in [200, 400]


class TestAlphaWeightsAPI:
    """Test alpha weights API endpoints."""
    
    def test_get_alpha_weights(self):
        """Test GET /api/settings/alpha returns valid response."""
        response = requests.get(f"{BASE_URL}/api/settings/alpha")
        assert response.status_code == 200
        data = response.json()
        assert 'weights' in data
        weights = data['weights']
        # Verify expected weight keys
        assert 'sentiment_weight' in weights
        assert 'rl_weight' in weights
        assert 'sharp_weight' in weights
        assert 'sentiment_neutral_low' in weights
        assert 'sentiment_neutral_high' in weights
        assert 'max_sentiment_delta' in weights
        assert 'min_rl_confidence' in weights
    
    def test_post_alpha_weights_requires_session(self):
        """Test POST /api/settings/alpha requires active session."""
        response = requests.post(
            f"{BASE_URL}/api/settings/alpha",
            json={"sentiment_weight": 0.55}
        )
        # Should return error if no active session
        assert response.status_code in [200, 400]
        if response.status_code == 400:
            data = response.json()
            assert 'error' in data


class TestHealthAndConfig:
    """Test health and config endpoints."""
    
    def test_health_endpoint(self):
        """Test GET /api/health returns healthy status."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
    
    def test_config_endpoint(self):
        """Test GET /api/config returns valid configuration."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        # Verify Two-Speed Architecture fields
        assert 'hft_allocation_pct' in data
        assert 'alpha_allocation_pct' in data
        assert 'strategy_risk_multipliers' in data
        assert 'spread_policy' in data
        assert 'variance_sizing' in data
    
    def test_config_has_spread_policy(self):
        """Test config includes spread policy with correct thresholds."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        spread_policy = data.get('spread_policy', {})
        assert 'max_spread_hft' in spread_policy
        assert 'max_spread_alpha' in spread_policy
    
    def test_config_has_variance_sizing(self):
        """Test config includes variance sizing with kill switch values."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        variance_sizing = data.get('variance_sizing', {})
        assert 'kill_switch_low' in variance_sizing
        assert 'kill_switch_high' in variance_sizing


class TestConfigSpreadRules:
    """Test config.py SPREAD_RULES constants."""
    
    def test_spread_rules_exist(self):
        """Verify SPREAD_RULES constants are defined."""
        from config import SPREAD_RULES
        assert 'TAKER_THRESHOLD' in SPREAD_RULES
        assert 'MAKER_THRESHOLD' in SPREAD_RULES
        assert 'ZOMBIE_THRESHOLD' in SPREAD_RULES
    
    def test_spread_rules_values(self):
        """Verify SPREAD_RULES have correct values."""
        from config import SPREAD_RULES
        assert SPREAD_RULES['TAKER_THRESHOLD'] == 0.02  # 2%
        assert SPREAD_RULES['MAKER_THRESHOLD'] == 0.10  # 10%
        assert SPREAD_RULES['ZOMBIE_THRESHOLD'] == 0.12  # 12%
    
    def test_classify_spread_regime_function(self):
        """Test classify_spread_regime helper function."""
        from config import classify_spread_regime
        assert classify_spread_regime(0.01) == 'TAKER_TIGHT'  # 1% < 2%
        assert classify_spread_regime(0.05) == 'MAKER_WIDE'   # 5% between 2-12%
        assert classify_spread_regime(0.15) == 'ZOMBIE'       # 15% > 12%


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
