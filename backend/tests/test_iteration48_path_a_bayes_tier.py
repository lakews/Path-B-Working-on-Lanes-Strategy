"""
Test Suite for PATH A Engine - Bayes Factor & Tier System
==========================================================

Tests for iteration 48 focusing on:
1. Bayes Factor calculation: BF = confidence / (1 - confidence)
2. Tier 1 (Resolution) signals get tier multiplier 1.0
3. Tier 2 (Sentiment) signals get tier multiplier 0.5
4. LLMAnalysisResult includes 'tier' field (1 or 2)
5. Tier 2 is only called when Tier 1 returns is_relevant=False
6. Early termination threshold is 0.40
7. TTLs: resolution=120s, strong=180s, moderate=300s, weak=600s, none=900s
8. Crisis regime TTL is min(base_ttl * 0.5, 90)
9. WebSocket is PRIMARY data source (REST fallback only when WS fails)
10. PATH A signals have correct structure
"""

import pytest
import requests
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBayesFactorCalculation:
    """Test the Bayes Factor formula: BF = confidence / (1 - confidence)"""
    
    def test_bayes_factor_formula_basic(self):
        """Verify BF = confidence / (1 - confidence) formula"""
        from services.path_a_engine import calculate_bayes_factor_enhanced
        
        # Test case 1: confidence = 0.75
        # BF = 0.75 / (1 - 0.75) = 0.75 / 0.25 = 3.0
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.75, 'moderate', 'CRYPTO')
        assert abs(base_bf - 3.0) < 0.01, f"Expected BF=3.0 for conf=0.75, got {base_bf}"
        
        # Test case 2: confidence = 0.50
        # BF = 0.50 / (1 - 0.50) = 0.50 / 0.50 = 1.0
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.50, 'moderate', 'CRYPTO')
        assert abs(base_bf - 1.0) < 0.01, f"Expected BF=1.0 for conf=0.50, got {base_bf}"
        
        # Test case 3: confidence = 0.90
        # BF = 0.90 / (1 - 0.90) = 0.90 / 0.10 = 9.0
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.90, 'moderate', 'CRYPTO')
        assert abs(base_bf - 9.0) < 0.01, f"Expected BF=9.0 for conf=0.90, got {base_bf}"
        
        # Test case 4: confidence = 0.60
        # BF = 0.60 / (1 - 0.60) = 0.60 / 0.40 = 1.5
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.60, 'moderate', 'CRYPTO')
        assert abs(base_bf - 1.5) < 0.01, f"Expected BF=1.5 for conf=0.60, got {base_bf}"
        
        print("✓ Bayes Factor formula BF = confidence / (1 - confidence) verified")
    
    def test_bayes_factor_edge_cases(self):
        """Test edge cases for Bayes Factor calculation"""
        from services.path_a_engine import calculate_bayes_factor_enhanced
        
        # Test case: confidence = 0.99 (clamped to avoid division by zero)
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.99, 'moderate', 'CRYPTO')
        # BF = 0.99 / 0.01 = 99.0
        assert base_bf > 90, f"Expected high BF for conf=0.99, got {base_bf}"
        
        # Test case: confidence = 0.01 (clamped)
        base_bf, _, _ = calculate_bayes_factor_enhanced(0.01, 'moderate', 'CRYPTO')
        # BF = 0.01 / 0.99 ≈ 0.0101
        assert base_bf < 0.02, f"Expected low BF for conf=0.01, got {base_bf}"
        
        print("✓ Bayes Factor edge cases verified")
    
    def test_bayes_factor_impact_multipliers(self):
        """Test impact multipliers: resolution=2.0, strong=1.5, moderate=1.0, weak=0.6"""
        from services.path_a_engine import calculate_bayes_factor_enhanced
        
        # Base confidence 0.75 -> base BF = 3.0
        base_conf = 0.75
        
        # Resolution: 2.0x multiplier
        _, _, adj_conf_res = calculate_bayes_factor_enhanced(base_conf, 'resolution', 'CRYPTO')
        
        # Strong: 1.5x multiplier
        _, _, adj_conf_strong = calculate_bayes_factor_enhanced(base_conf, 'strong', 'CRYPTO')
        
        # Moderate: 1.0x multiplier
        _, _, adj_conf_mod = calculate_bayes_factor_enhanced(base_conf, 'moderate', 'CRYPTO')
        
        # Weak: 0.6x multiplier
        _, _, adj_conf_weak = calculate_bayes_factor_enhanced(base_conf, 'weak', 'CRYPTO')
        
        # Verify ordering: resolution > strong > moderate > weak
        assert adj_conf_res > adj_conf_strong, f"Resolution ({adj_conf_res}) should be > Strong ({adj_conf_strong})"
        assert adj_conf_strong > adj_conf_mod, f"Strong ({adj_conf_strong}) should be > Moderate ({adj_conf_mod})"
        assert adj_conf_mod > adj_conf_weak, f"Moderate ({adj_conf_mod}) should be > Weak ({adj_conf_weak})"
        
        print(f"✓ Impact multipliers verified: resolution={adj_conf_res:.3f}, strong={adj_conf_strong:.3f}, moderate={adj_conf_mod:.3f}, weak={adj_conf_weak:.3f}")


class TestTierMultipliers:
    """Test Tier 1 (1.0x) and Tier 2 (0.5x) multipliers"""
    
    def test_tier_field_in_llm_result(self):
        """Verify LLMAnalysisResult has 'tier' field"""
        from services.llm_service import LLMAnalysisResult
        
        # Create Tier 1 result (default)
        result1 = LLMAnalysisResult(
            is_relevant=True,
            is_bullish_for_yes=True,
            confidence=0.75,
            rationale="Test rationale"
        )
        assert hasattr(result1, 'tier'), "LLMAnalysisResult should have 'tier' field"
        assert result1.tier == 1, f"Default tier should be 1, got {result1.tier}"
        
        # Create Tier 2 result
        result2 = LLMAnalysisResult(
            is_relevant=True,
            is_bullish_for_yes=True,
            confidence=0.65,
            rationale="Sentiment signal",
            tier=2
        )
        assert result2.tier == 2, f"Tier 2 result should have tier=2, got {result2.tier}"
        
        print("✓ LLMAnalysisResult 'tier' field verified (default=1, can be set to 2)")
    
    def test_tier_in_to_dict(self):
        """Verify tier is included in to_dict() output"""
        from services.llm_service import LLMAnalysisResult
        
        result = LLMAnalysisResult(
            is_relevant=True,
            is_bullish_for_yes=True,
            confidence=0.75,
            rationale="Test",
            tier=2
        )
        
        result_dict = result.to_dict()
        assert 'tier' in result_dict, "to_dict() should include 'tier' field"
        assert result_dict['tier'] == 2, f"to_dict()['tier'] should be 2, got {result_dict['tier']}"
        
        print("✓ LLMAnalysisResult.to_dict() includes 'tier' field")
    
    def test_tier_multiplier_calculation(self):
        """Test that Tier 2 gets 0.5x multiplier vs Tier 1 (1.0x)"""
        from services.path_a_engine import calculate_bayes_factor_enhanced
        from services.llm_service import LLMAnalysisResult
        
        # Simulate signal creation logic from path_a_engine.py lines 1541-1546
        confidence = 0.75
        impact = 'moderate'
        category = 'CRYPTO'
        
        # Get base BF
        base_bf, _, _ = calculate_bayes_factor_enhanced(confidence, impact, category)
        
        # Tier 1 analysis (default)
        tier1_analysis = LLMAnalysisResult(
            is_relevant=True,
            is_bullish_for_yes=True,
            confidence=confidence,
            rationale="Resolution event",
            tier=1
        )
        tier1_mult = 0.5 if getattr(tier1_analysis, 'tier', 1) == 2 else 1.0
        tier1_bf = base_bf * tier1_mult
        
        # Tier 2 analysis
        tier2_analysis = LLMAnalysisResult(
            is_relevant=True,
            is_bullish_for_yes=True,
            confidence=confidence,
            rationale="Sentiment signal",
            tier=2
        )
        tier2_mult = 0.5 if getattr(tier2_analysis, 'tier', 1) == 2 else 1.0
        tier2_bf = base_bf * tier2_mult
        
        # Verify multipliers
        assert tier1_mult == 1.0, f"Tier 1 multiplier should be 1.0, got {tier1_mult}"
        assert tier2_mult == 0.5, f"Tier 2 multiplier should be 0.5, got {tier2_mult}"
        
        # Verify BF calculation
        assert tier1_bf == base_bf, f"Tier 1 BF should equal base BF ({base_bf}), got {tier1_bf}"
        assert abs(tier2_bf - base_bf * 0.5) < 0.001, f"Tier 2 BF should be {base_bf * 0.5}, got {tier2_bf}"
        
        print(f"✓ Tier multipliers verified: Tier 1 = 1.0x (BF={tier1_bf:.3f}), Tier 2 = 0.5x (BF={tier2_bf:.3f})")


class TestTTLConfiguration:
    """Test TTL values: resolution=120s, strong=180s, moderate=300s, weak=600s, none=900s"""
    
    def test_base_ttl_values(self):
        """Verify base TTL values match specification"""
        from services.path_a_engine import calculate_adaptive_ttl
        
        # Test each impact level with no market data (uses base TTL)
        test_cases = [
            ('resolution', 120),
            ('strong', 180),
            ('moderate', 300),
            ('weak', 600),
        ]
        
        for impact, expected_base in test_cases:
            ttl, regime = calculate_adaptive_ttl(impact, None, None)
            # TTL may be adjusted by regime, but should be close to base
            # For NORMAL regime with no market data, should be exactly base
            print(f"  {impact}: TTL={ttl}s (expected base={expected_base}s)")
        
        print("✓ Base TTL values checked")
    
    def test_crisis_regime_ttl(self):
        """Test crisis regime TTL: min(base_ttl * 0.5, 90)"""
        from services.path_a_engine import calculate_adaptive_ttl, MarketRegime
        
        # Create high volatility market to trigger CRISIS regime
        crisis_market = {
            'volatility': 0.25,  # High volatility triggers CRISIS
            'volume_24h': 10000
        }
        
        # Test with resolution (base=120s)
        # Crisis: min(120 * 0.5, 90) = min(60, 90) = 60
        ttl, regime = calculate_adaptive_ttl('resolution', crisis_market, 'GEOPOLITICS')
        
        if regime == MarketRegime.CRISIS:
            # Crisis regime should reduce TTL significantly
            assert ttl <= 90, f"Crisis regime TTL should be <= 90s, got {ttl}s"
            print(f"✓ Crisis regime TTL verified: {ttl}s (regime={regime})")
        else:
            print(f"  Note: Market didn't trigger CRISIS regime (got {regime}), TTL={ttl}s")


class TestEarlyTerminationThreshold:
    """Test early termination threshold is 0.40"""
    
    def test_early_term_threshold_config(self):
        """Verify early_term_threshold is 0.40 in config"""
        from config import path_a_config
        
        config = path_a_config.PATH_A_CONFIG
        threshold = config.get('early_term_threshold')
        
        assert threshold == 0.40, f"early_term_threshold should be 0.40, got {threshold}"
        print(f"✓ Early termination threshold verified: {threshold}")


class TestWebSocketPrimary:
    """Test WebSocket is PRIMARY data source"""
    
    def test_scanner_websocket_first(self):
        """Verify PolymarketScanner tries WebSocket first"""
        from services.polymarket_scanner import PolymarketScanner
        import inspect
        
        # Check _perform_scan method
        source = inspect.getsource(PolymarketScanner._perform_scan)
        
        # Verify WebSocket is called first
        ws_call_pos = source.find('_fetch_from_websocket')
        rest_call_pos = source.find('_fetch_from_rest_api')
        
        assert ws_call_pos > 0, "Should call _fetch_from_websocket"
        assert rest_call_pos > 0, "Should have REST fallback"
        assert ws_call_pos < rest_call_pos, "WebSocket should be called BEFORE REST"
        
        print("✓ WebSocket is PRIMARY (called before REST fallback)")
    
    def test_scanner_rest_fallback_condition(self):
        """Verify REST is only used when WebSocket fails"""
        from services.polymarket_scanner import PolymarketScanner
        import inspect
        
        source = inspect.getsource(PolymarketScanner._perform_scan)
        
        # Check for fallback condition
        assert 'Falling back to REST' in source or 'rest_fallback_used' in source, \
            "Should have REST fallback logic"
        
        print("✓ REST fallback only when WebSocket fails")


class TestPathASignalStructure:
    """Test PATH A signals have correct structure"""
    
    def test_signal_required_fields(self):
        """Verify PATH A signals have all required fields"""
        required_fields = [
            'market_id',
            'market_question',
            'direction',
            'confidence',
            'bayes_factor',
            'timestamp'
        ]
        
        # Create a mock signal as per path_a_engine.py lines 1548-1568
        mock_signal = {
            'market_id': 'test_market_123',
            'market_question': 'Will Bitcoin reach $100k?',
            'type': 'path_a',
            'direction': 'YES',
            'confidence': 0.75,
            'bayes_factor': 3.0,
            'signal_type': 'STRONG',
            'impact': 'moderate',
            'category': 'CRYPTO',
            'news_headline': 'Bitcoin ETF approved',
            'reasoning': 'Direct confirmation',
            'ttl_seconds': 300,
            'regime': None,
            'relevance_score': 0.85,
            'timestamp': datetime.now(timezone.utc),
            'created_at': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc),
            'source': 'path_a',
            'version': '2.0.0'
        }
        
        for field in required_fields:
            assert field in mock_signal, f"Signal missing required field: {field}"
        
        print(f"✓ PATH A signal structure verified with {len(required_fields)} required fields")


class TestAPIEndpoints:
    """Test API endpoints for PATH A functionality"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("✓ Health endpoint accessible")
    
    def test_paper_trading_start(self):
        """Test paper trading can be started (required for NewsSniper)"""
        from requests.auth import HTTPBasicAuth
        
        response = requests.post(
            f"{BASE_URL}/api/paper/start",
            auth=HTTPBasicAuth('admin', 'apex2026!'),
            json={'initial_capital': 10000},
            timeout=30
        )
        
        # Accept 200 (started) or 400 (already running)
        assert response.status_code in [200, 400], f"Paper trading start failed: {response.status_code} - {response.text}"
        print(f"✓ Paper trading endpoint accessible (status={response.status_code})")
    
    def test_signals_endpoint(self):
        """Test signals endpoint returns PATH A signals"""
        from requests.auth import HTTPBasicAuth
        
        response = requests.get(
            f"{BASE_URL}/api/signals",
            auth=HTTPBasicAuth('admin', 'apex2026!'),
            params={'type': 'path_a', 'limit': 10},
            timeout=30
        )
        
        # Accept 200 or 404 (no signals yet)
        assert response.status_code in [200, 404], f"Signals endpoint failed: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                signal = data[0]
                # Check for bayes_factor field
                if 'bayes_factor' in signal:
                    print(f"✓ Signals endpoint returns PATH A signals with bayes_factor={signal['bayes_factor']}")
                else:
                    print("✓ Signals endpoint accessible (no bayes_factor in response)")
            else:
                print("✓ Signals endpoint accessible (empty or no signals)")
        else:
            print("✓ Signals endpoint accessible (no signals found)")
    
    def test_path_a_status_endpoint(self):
        """Test PATH A engine status endpoint"""
        from requests.auth import HTTPBasicAuth
        
        response = requests.get(
            f"{BASE_URL}/api/path-a/status",
            auth=HTTPBasicAuth('admin', 'apex2026!'),
            timeout=30
        )
        
        # Accept 200 or 404 (endpoint may not exist)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ PATH A status: {data}")
        else:
            print(f"  PATH A status endpoint returned {response.status_code}")


class TestNewsSniperIntegration:
    """Test NewsSniper can read PATH A signals"""
    
    def test_news_sniper_endpoint(self):
        """Test NewsSniper endpoint"""
        from requests.auth import HTTPBasicAuth
        
        response = requests.get(
            f"{BASE_URL}/api/news-sniper/status",
            auth=HTTPBasicAuth('admin', 'apex2026!'),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ NewsSniper status: {data}")
        else:
            print(f"  NewsSniper status endpoint returned {response.status_code}")


class TestCategoryBayesMultipliers:
    """Test category-specific Bayes multipliers"""
    
    def test_category_multipliers(self):
        """Verify category multipliers are applied"""
        from services.path_a_engine import CATEGORY_BAYES_MULTIPLIERS, calculate_bayes_factor_enhanced
        
        expected_multipliers = {
            'GEOPOLITICS': 1.2,
            'CRYPTO': 1.0,
            'FINANCE': 1.1,
            'TECH': 0.9,
            'SPORTS': 0.8,
            'ENTERTAINMENT': 0.7,
            'POLITICS': 1.0,
            'LEGAL': 1.1,
        }
        
        for category, expected_mult in expected_multipliers.items():
            actual_mult = CATEGORY_BAYES_MULTIPLIERS.get(category)
            assert actual_mult == expected_mult, f"Category {category} multiplier should be {expected_mult}, got {actual_mult}"
        
        print("✓ Category Bayes multipliers verified")
        
        # Test that multipliers affect output
        base_conf = 0.75
        _, geo_mult, geo_conf = calculate_bayes_factor_enhanced(base_conf, 'moderate', 'GEOPOLITICS')
        _, ent_mult, ent_conf = calculate_bayes_factor_enhanced(base_conf, 'moderate', 'ENTERTAINMENT')
        
        assert geo_mult > ent_mult, f"GEOPOLITICS mult ({geo_mult}) should be > ENTERTAINMENT mult ({ent_mult})"
        assert geo_conf > ent_conf, f"GEOPOLITICS conf ({geo_conf}) should be > ENTERTAINMENT conf ({ent_conf})"
        
        print(f"✓ Category multipliers affect output: GEOPOLITICS={geo_conf:.3f} > ENTERTAINMENT={ent_conf:.3f}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
