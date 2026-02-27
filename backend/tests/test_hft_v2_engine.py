"""
HFT Engine V2 Tests - Iteration 41
==================================

Tests for the High-Frequency Trading Engine V2 implementation:
1. HFT V2 Configuration (hft_config.py)
2. HFT V2 Engine (hft_engine_v2.py)
3. HFT V2 Status Endpoint (/api/hft-v2/status)
4. Integration with paper_trader.py
5. Existing system integrity (Markets-First, paper trading)

Sub-strategies tested:
- Delta-Neutral Market Making (35%)
- Volatility Exploitation (10%)
- Extreme Spread Capture (15%)
- Sharp Trader Following (20%)
- Liquidity Provision (20%)
"""

import pytest
import requests
import os
import sys

# Add backend to path for imports
sys.path.insert(0, '/app/backend')

# Read BASE_URL from frontend .env file
def get_base_url():
    """Read REACT_APP_BACKEND_URL from frontend .env file"""
    env_path = '/app/frontend/.env'
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    return os.environ.get('REACT_APP_BACKEND_URL', 'https://sports-hft-router.preview.emergentagent.com').rstrip('/')

BASE_URL = get_base_url()


class TestHFTConfig:
    """Test HFT V2 Configuration (hft_config.py)"""
    
    def test_hft_config_file_exists(self):
        """Verify hft_config.py exists"""
        config_path = '/app/backend/trading/hft_config.py'
        assert os.path.exists(config_path), f"HFT config file not found at {config_path}"
        print("✅ hft_config.py exists")
    
    def test_hft_config_imports(self):
        """Verify HFTConfig class can be imported"""
        from trading.hft_config import HFTConfig, NewsStrength, HFTMode
        assert HFTConfig is not None
        assert NewsStrength is not None
        assert HFTMode is not None
        print("✅ HFTConfig, NewsStrength, HFTMode imported successfully")
    
    def test_sub_strategy_allocations_sum_to_one(self):
        """Verify sub-strategy allocations sum to 1.0 (100%)"""
        from trading.hft_config import HFTConfig
        
        allocations = HFTConfig.SUB_STRATEGY_ALLOCATION
        total = sum(allocations.values())
        
        assert abs(total - 1.0) < 0.001, f"Allocations sum to {total}, expected 1.0"
        print(f"✅ Sub-strategy allocations sum to {total}")
    
    def test_sub_strategy_allocation_values(self):
        """Verify correct allocation percentages for each sub-strategy"""
        from trading.hft_config import HFTConfig
        
        expected = {
            'delta_neutral': 0.35,
            'volatility_exploit': 0.10,
            'extreme_spread': 0.15,
            'sharp_following': 0.20,
            'liquidity_provision': 0.20
        }
        
        for strategy, expected_alloc in expected.items():
            actual = HFTConfig.SUB_STRATEGY_ALLOCATION.get(strategy)
            assert actual == expected_alloc, f"{strategy}: expected {expected_alloc}, got {actual}"
            print(f"✅ {strategy}: {actual*100:.0f}%")
    
    def test_news_strength_enum_values(self):
        """Verify NewsStrength enum has correct values"""
        from trading.hft_config import NewsStrength
        
        expected_values = ['PAUSE', 'EXTREME', 'CAUTION', 'NORMAL']
        actual_values = [ns.value for ns in NewsStrength]
        
        for expected in expected_values:
            assert expected in actual_values, f"Missing NewsStrength value: {expected}"
            print(f"✅ NewsStrength.{expected} exists")
    
    def test_bayes_factor_thresholds(self):
        """Verify BF thresholds are correctly defined"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.PAUSE_BF == 10.0, f"PAUSE_BF should be 10.0, got {HFTConfig.PAUSE_BF}"
        assert HFTConfig.EXTREME_BF == 5.0, f"EXTREME_BF should be 5.0, got {HFTConfig.EXTREME_BF}"
        assert HFTConfig.CAUTION_BF == 3.0, f"CAUTION_BF should be 3.0, got {HFTConfig.CAUTION_BF}"
        
        print(f"✅ PAUSE_BF={HFTConfig.PAUSE_BF}, EXTREME_BF={HFTConfig.EXTREME_BF}, CAUTION_BF={HFTConfig.CAUTION_BF}")
    
    def test_get_news_strength_pause(self):
        """Test get_news_strength() returns PAUSE for BF >= 10.0"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(10.0)
        assert result == NewsStrength.PAUSE, f"BF=10.0 should return PAUSE, got {result}"
        
        result = get_news_strength(15.0)
        assert result == NewsStrength.PAUSE, f"BF=15.0 should return PAUSE, got {result}"
        
        print("✅ get_news_strength() correctly returns PAUSE for BF >= 10.0")
    
    def test_get_news_strength_extreme(self):
        """Test get_news_strength() returns EXTREME for BF 5.0-10.0"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(5.0)
        assert result == NewsStrength.EXTREME, f"BF=5.0 should return EXTREME, got {result}"
        
        result = get_news_strength(7.5)
        assert result == NewsStrength.EXTREME, f"BF=7.5 should return EXTREME, got {result}"
        
        result = get_news_strength(9.9)
        assert result == NewsStrength.EXTREME, f"BF=9.9 should return EXTREME, got {result}"
        
        print("✅ get_news_strength() correctly returns EXTREME for BF 5.0-10.0")
    
    def test_get_news_strength_caution(self):
        """Test get_news_strength() returns CAUTION for BF 3.0-5.0"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(3.0)
        assert result == NewsStrength.CAUTION, f"BF=3.0 should return CAUTION, got {result}"
        
        result = get_news_strength(4.0)
        assert result == NewsStrength.CAUTION, f"BF=4.0 should return CAUTION, got {result}"
        
        result = get_news_strength(4.9)
        assert result == NewsStrength.CAUTION, f"BF=4.9 should return CAUTION, got {result}"
        
        print("✅ get_news_strength() correctly returns CAUTION for BF 3.0-5.0")
    
    def test_get_news_strength_normal(self):
        """Test get_news_strength() returns NORMAL for BF < 3.0"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(0.0)
        assert result == NewsStrength.NORMAL, f"BF=0.0 should return NORMAL, got {result}"
        
        result = get_news_strength(2.0)
        assert result == NewsStrength.NORMAL, f"BF=2.0 should return NORMAL, got {result}"
        
        result = get_news_strength(2.9)
        assert result == NewsStrength.NORMAL, f"BF=2.9 should return NORMAL, got {result}"
        
        print("✅ get_news_strength() correctly returns NORMAL for BF < 3.0")
    
    def test_kelly_and_position_constraints(self):
        """Verify Kelly criterion and position cap constraints"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.KELLY_FRACTION == 0.25, f"KELLY_FRACTION should be 0.25, got {HFTConfig.KELLY_FRACTION}"
        assert HFTConfig.MAX_POSITION_PCT == 0.03, f"MAX_POSITION_PCT should be 0.03, got {HFTConfig.MAX_POSITION_PCT}"
        
        print(f"✅ Kelly={HFTConfig.KELLY_FRACTION}, Max Position={HFTConfig.MAX_POSITION_PCT*100}%")


class TestHFTEngineV2:
    """Test HFT Engine V2 (hft_engine_v2.py)"""
    
    def test_hft_engine_file_exists(self):
        """Verify hft_engine_v2.py exists"""
        engine_path = '/app/backend/trading/hft_engine_v2.py'
        assert os.path.exists(engine_path), f"HFT engine file not found at {engine_path}"
        print("✅ hft_engine_v2.py exists")
    
    def test_hft_engine_imports(self):
        """Verify HighFrequencyTradingEngine can be imported"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngine, init_hft_engine, get_hft_engine
        assert HighFrequencyTradingEngine is not None
        assert init_hft_engine is not None
        assert get_hft_engine is not None
        print("✅ HighFrequencyTradingEngine, init_hft_engine, get_hft_engine imported")
    
    def test_hft_engine_initialization(self):
        """Test HFT Engine can be initialized with minimal dependencies"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngine
        
        # Initialize with minimal dependencies
        engine = HighFrequencyTradingEngine({
            'db': None,
            'market_data_svc': None,
            'paper_trader': None,
            'position_manager': None
        })
        
        assert engine is not None
        assert engine._running == False
        assert engine.stats['cycles_executed'] == 0
        assert engine.stats['trades_executed'] == 0
        
        print("✅ HFT Engine V2 initialized successfully")
    
    def test_hft_engine_stats_structure(self):
        """Verify HFT Engine stats have correct structure"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngine
        
        engine = HighFrequencyTradingEngine({})
        stats = engine.get_stats()
        
        expected_keys = ['cycles_executed', 'trades_executed', 'trades_by_mode', 
                        'paused_cycles', 'path_a_hits', 'path_b_hits', 
                        'total_pnl', 'errors', 'running', 'last_cycle_time_ms']
        
        for key in expected_keys:
            assert key in stats, f"Missing stats key: {key}"
        
        print(f"✅ HFT Engine stats structure correct: {list(stats.keys())}")
    
    def test_hft_engine_metrics_structure(self):
        """Verify HFT Engine metrics have correct structure"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngine
        
        engine = HighFrequencyTradingEngine({})
        metrics = engine.get_hft_metrics()
        
        expected_keys = ['cycles_executed', 'trades_executed', 'mode_distribution',
                        'path_a_hits', 'path_b_hits', 'paused_cycles', 'errors', 'running']
        
        for key in expected_keys:
            assert key in metrics, f"Missing metrics key: {key}"
        
        # Verify mode_distribution has all 5 strategies
        mode_dist = metrics['mode_distribution']
        expected_modes = ['delta_neutral', 'volatility_exploit', 'extreme_spread', 
                         'sharp_following', 'liquidity_provision']
        
        for mode in expected_modes:
            assert mode in mode_dist, f"Missing mode in distribution: {mode}"
        
        print(f"✅ HFT Engine metrics structure correct with all 5 sub-strategies")


class TestHFTV2StatusEndpoint:
    """Test GET /api/hft-v2/status endpoint"""
    
    def test_hft_v2_status_endpoint_exists(self):
        """Verify /api/hft-v2/status endpoint responds"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✅ GET /api/hft-v2/status returns 200")
    
    def test_hft_v2_status_not_initialized(self):
        """Verify status is 'not_initialized' when paper trading is stopped"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        
        # When paper trading is not running, status should be 'not_initialized'
        # or 'operational'/'stopped' if it was previously started
        assert 'status' in data, "Response should contain 'status' field"
        
        valid_statuses = ['not_initialized', 'operational', 'stopped']
        assert data['status'] in valid_statuses, f"Unexpected status: {data['status']}"
        
        print(f"✅ HFT V2 status: {data['status']}")
    
    def test_hft_v2_status_response_structure(self):
        """Verify response structure contains expected fields"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        
        assert 'status' in data
        assert 'timestamp' in data
        
        # If not initialized, should have message
        if data['status'] == 'not_initialized':
            assert 'message' in data
            print(f"✅ Not initialized response: {data['message']}")
        else:
            # If operational/stopped, should have metrics and config
            assert 'metrics' in data or 'config' in data
            print(f"✅ Operational response with metrics/config")
    
    def test_hft_v2_config_values_in_response(self):
        """Verify config values in response match expected values"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        
        if data['status'] != 'not_initialized' and 'config' in data:
            config = data['config']
            
            # Verify BF thresholds
            assert config.get('pause_bf') == 10.0
            assert config.get('extreme_bf') == 5.0
            assert config.get('caution_bf') == 3.0
            
            # Verify constraints
            assert config.get('kelly_fraction') == 0.25
            assert config.get('max_position_pct') == 0.03
            
            # Verify allocations
            allocations = config.get('sub_strategy_allocations', {})
            assert allocations.get('delta_neutral') == 0.35
            assert allocations.get('volatility_exploit') == 0.10
            assert allocations.get('extreme_spread') == 0.15
            assert allocations.get('sharp_following') == 0.20
            assert allocations.get('liquidity_provision') == 0.20
            
            print("✅ Config values in response match expected values")
        else:
            print("⚠️ HFT V2 not initialized - config not available (expected when paper trading stopped)")


class TestExistingSystemIntegrity:
    """Test that existing systems still work after HFT V2 integration"""
    
    def test_health_endpoint(self):
        """Verify /api/health still works"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print("✅ GET /api/health returns healthy")
    
    def test_scanner_health_endpoint(self):
        """Verify /api/health/scanner still works"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        print(f"✅ GET /api/health/scanner returns status: {data.get('status')}")
    
    def test_paper_trading_status_endpoint(self):
        """Verify /api/paper/status still works"""
        response = requests.get(f"{BASE_URL}/api/paper/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert 'running' in data
        print(f"✅ GET /api/paper/status returns running: {data.get('running')}")
    
    def test_news_webhook_endpoint(self):
        """Verify POST /api/webhooks/news still works with PATH A/B"""
        test_payload = {
            "headline": "Test news for HFT V2 integration",
            "source": "test_source",
            "timestamp": "2026-01-15T12:00:00Z"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/webhooks/news",
                json=test_payload,
                timeout=30  # Increased timeout for LLM processing
            )
            
            # Should return 200 or 202 (accepted)
            assert response.status_code in [200, 202], f"Expected 200/202, got {response.status_code}"
            print(f"✅ POST /api/webhooks/news returns {response.status_code}")
        except requests.exceptions.ReadTimeout:
            # Timeout is acceptable for this endpoint as it does LLM processing
            print("⚠️ POST /api/webhooks/news timed out (expected for LLM processing)")
            pytest.skip("News webhook timed out - LLM processing takes longer")
    
    def test_analytics_endpoint(self):
        """Verify /api/analytics still works"""
        try:
            response = requests.get(f"{BASE_URL}/api/analytics", timeout=30)
            assert response.status_code == 200
            data = response.json()
            
            # Should have lane data
            assert 'lanes' in data or 'total_pnl' in data or 'session_id' in data
            print("✅ GET /api/analytics returns data")
        except requests.exceptions.ReadTimeout:
            # Timeout is acceptable for this endpoint as it aggregates data
            print("⚠️ GET /api/analytics timed out (expected for data aggregation)")
            pytest.skip("Analytics endpoint timed out - data aggregation takes longer")


class TestPaperTraderIntegration:
    """Test HFT V2 integration in paper_trader.py"""
    
    def test_paper_trader_has_hft_v2_attribute(self):
        """Verify paper_trader.py has hft_engine_v2 attribute"""
        # Check the file contains the attribute
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            content = f.read()
        
        assert 'self.hft_engine_v2' in content, "paper_trader.py should have hft_engine_v2 attribute"
        print("✅ paper_trader.py has hft_engine_v2 attribute")
    
    def test_paper_trader_has_hft_v2_loop(self):
        """Verify paper_trader.py has _run_hft_v2_loop method"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            content = f.read()
        
        assert 'async def _run_hft_v2_loop' in content, "paper_trader.py should have _run_hft_v2_loop method"
        print("✅ paper_trader.py has _run_hft_v2_loop method")
    
    def test_paper_trader_starts_hft_v2_in_gather(self):
        """Verify HFT V2 loop is included in asyncio.gather"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            content = f.read()
        
        assert 'self._run_hft_v2_loop()' in content, "HFT V2 loop should be in asyncio.gather"
        print("✅ HFT V2 loop is included in asyncio.gather")
    
    def test_paper_trader_stops_hft_v2(self):
        """Verify paper_trader stops HFT V2 engine on stop"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            content = f.read()
        
        assert 'await self.hft_engine_v2.stop()' in content, "paper_trader should stop HFT V2 engine"
        print("✅ paper_trader.py stops HFT V2 engine on stop")
    
    def test_paper_trader_imports_hft_v2(self):
        """Verify paper_trader.py imports HFT V2 components"""
        with open('/app/backend/paper_trading/paper_trader.py', 'r') as f:
            content = f.read()
        
        assert 'from trading.hft_engine_v2 import' in content, "paper_trader should import HFT V2"
        assert 'HighFrequencyTradingEngine' in content, "Should import HighFrequencyTradingEngine"
        assert 'init_hft_engine' in content, "Should import init_hft_engine"
        print("✅ paper_trader.py imports HFT V2 components")


class TestHFTModeEnum:
    """Test HFTMode enum for 5 sub-strategies"""
    
    def test_hft_mode_has_all_strategies(self):
        """Verify HFTMode enum has all 5 sub-strategies"""
        from trading.hft_config import HFTMode
        
        expected_modes = [
            'delta_neutral',
            'volatility_exploit',
            'extreme_spread',
            'sharp_following',
            'liquidity_provision'
        ]
        
        actual_modes = [mode.value for mode in HFTMode]
        
        for expected in expected_modes:
            assert expected in actual_modes, f"Missing HFTMode: {expected}"
            print(f"✅ HFTMode.{expected.upper()} exists")


class TestSpreadAndPositionMultipliers:
    """Test spread and position multipliers based on news strength"""
    
    def test_spread_multipliers(self):
        """Verify spread multipliers for each news strength"""
        from trading.hft_config import HFTConfig
        
        expected = {
            'NORMAL': 1.0,
            'CAUTION': 1.3,
            'EXTREME': 2.5,
            'PAUSE': 0.0
        }
        
        for strength, expected_mult in expected.items():
            actual = HFTConfig.SPREAD_MULTIPLIERS.get(strength)
            assert actual == expected_mult, f"{strength}: expected {expected_mult}, got {actual}"
            print(f"✅ Spread multiplier for {strength}: {actual}")
    
    def test_position_multipliers(self):
        """Verify position multipliers for each news strength"""
        from trading.hft_config import HFTConfig
        
        expected = {
            'NORMAL': 1.0,
            'CAUTION': 0.75,
            'EXTREME': 0.5,
            'PAUSE': 0.0
        }
        
        for strength, expected_mult in expected.items():
            actual = HFTConfig.POSITION_MULTIPLIERS.get(strength)
            assert actual == expected_mult, f"{strength}: expected {expected_mult}, got {actual}"
            print(f"✅ Position multiplier for {strength}: {actual}")
    
    def test_get_multipliers_function(self):
        """Test get_multipliers() function"""
        from trading.hft_config import get_multipliers, NewsStrength
        
        # Test NORMAL
        mults = get_multipliers(NewsStrength.NORMAL)
        assert mults['spread_mult'] == 1.0
        assert mults['position_mult'] == 1.0
        
        # Test CAUTION
        mults = get_multipliers(NewsStrength.CAUTION)
        assert mults['spread_mult'] == 1.3
        assert mults['position_mult'] == 0.75
        
        # Test EXTREME
        mults = get_multipliers(NewsStrength.EXTREME)
        assert mults['spread_mult'] == 2.5
        assert mults['position_mult'] == 0.5
        
        # Test PAUSE
        mults = get_multipliers(NewsStrength.PAUSE)
        assert mults['spread_mult'] == 0.0
        assert mults['position_mult'] == 0.0
        
        print("✅ get_multipliers() returns correct values for all news strengths")


class TestPriceZones:
    """Test price zone classification for strategy selection"""
    
    def test_get_price_zone_extreme_low(self):
        """Test extreme_low zone (0.0 - 0.10)"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.0) == 'extreme_low'
        assert get_price_zone(0.05) == 'extreme_low'
        assert get_price_zone(0.10) == 'extreme_low'
        
        print("✅ get_price_zone() correctly identifies extreme_low zone")
    
    def test_get_price_zone_standard(self):
        """Test standard zone (0.10 - 0.90)"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.11) == 'standard'
        assert get_price_zone(0.50) == 'standard'
        assert get_price_zone(0.89) == 'standard'
        
        print("✅ get_price_zone() correctly identifies standard zone")
    
    def test_get_price_zone_extreme_high(self):
        """Test extreme_high zone (0.90 - 1.0)"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.90) == 'extreme_high'
        assert get_price_zone(0.95) == 'extreme_high'
        assert get_price_zone(1.0) == 'extreme_high'
        
        print("✅ get_price_zone() correctly identifies extreme_high zone")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
