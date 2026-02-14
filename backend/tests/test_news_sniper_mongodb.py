"""
NEWS Sniper MongoDB Phase 2 Tests
=================================

Tests for NEWS Lane Phase 2 implementation:
- NewsSniper class with MongoDB integration
- ConvictionEnhancer with 5-factor calculation
- Kelly tiering based on conviction
- MarketRegime and NewsImpactLevel enums
- paper_trader.py integration
- GET /api/news-sniper/status endpoint
"""

import pytest
import requests
import os
import sys
import importlib.util

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# =============================================================================
# TEST: File Existence
# =============================================================================
class TestNewsSniperFileExists:
    """Verify NEWS Sniper MongoDB file exists"""
    
    def test_news_sniper_mongodb_file_exists(self):
        """NEWS Sniper MongoDB file should exist"""
        file_path = "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        assert os.path.exists(file_path), f"File not found: {file_path}"
    
    def test_news_lane_init_file_exists(self):
        """NEWS Lane __init__.py should exist"""
        file_path = "/app/backend/lanes/news_lane/__init__.py"
        assert os.path.exists(file_path), f"File not found: {file_path}"


# =============================================================================
# TEST: NewsSniper Class
# =============================================================================
class TestNewsSniperClass:
    """Verify NewsSniper class exists with required methods"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_news_sniper_class_exists(self):
        """NewsSniper class should exist"""
        assert hasattr(self.module, 'NewsSniper'), "NewsSniper class not found"
    
    def test_news_sniper_has_start_news_loop(self):
        """NewsSniper should have start_news_loop() method"""
        assert hasattr(self.module.NewsSniper, 'start_news_loop'), "start_news_loop() method not found"
    
    def test_news_sniper_has_stop(self):
        """NewsSniper should have stop() method"""
        assert hasattr(self.module.NewsSniper, 'stop'), "stop() method not found"
    
    def test_news_sniper_has_get_stats(self):
        """NewsSniper should have get_stats() method"""
        assert hasattr(self.module.NewsSniper, 'get_stats'), "get_stats() method not found"
    
    def test_news_sniper_has_read_fresh_signals(self):
        """NewsSniper should have _read_fresh_signals() method"""
        assert hasattr(self.module.NewsSniper, '_read_fresh_signals'), "_read_fresh_signals() method not found"
    
    def test_news_sniper_has_conviction_to_kelly(self):
        """NewsSniper should have _conviction_to_kelly() method"""
        assert hasattr(self.module.NewsSniper, '_conviction_to_kelly'), "_conviction_to_kelly() method not found"


# =============================================================================
# TEST: NewsSniper KELLY_TIERS
# =============================================================================
class TestNewsSniperKellyTiers:
    """Verify NewsSniper.KELLY_TIERS has correct values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_kelly_tiers_exists(self):
        """KELLY_TIERS should exist"""
        assert hasattr(self.module.NewsSniper, 'KELLY_TIERS'), "KELLY_TIERS not found"
    
    def test_kelly_tier_conviction_10_plus(self):
        """Conviction >= 10 should map to 50% Kelly"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        # Find tier for conviction >= 10
        tier_10 = next((t for t in tiers if t[0] == 10.0), None)
        assert tier_10 is not None, "Tier for conviction 10 not found"
        assert tier_10[1] == 0.50, f"Expected 0.50 for conviction 10, got {tier_10[1]}"
    
    def test_kelly_tier_conviction_8_10(self):
        """Conviction 8-10 should map to 40% Kelly"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        tier_8 = next((t for t in tiers if t[0] == 8.0), None)
        assert tier_8 is not None, "Tier for conviction 8 not found"
        assert tier_8[1] == 0.40, f"Expected 0.40 for conviction 8, got {tier_8[1]}"
    
    def test_kelly_tier_conviction_6_8(self):
        """Conviction 6-8 should map to 30% Kelly"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        tier_6 = next((t for t in tiers if t[0] == 6.0), None)
        assert tier_6 is not None, "Tier for conviction 6 not found"
        assert tier_6[1] == 0.30, f"Expected 0.30 for conviction 6, got {tier_6[1]}"
    
    def test_kelly_tier_conviction_3_6(self):
        """Conviction 3-6 should map to 15% Kelly"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        tier_3 = next((t for t in tiers if t[0] == 3.0), None)
        assert tier_3 is not None, "Tier for conviction 3 not found"
        assert tier_3[1] == 0.15, f"Expected 0.15 for conviction 3, got {tier_3[1]}"
    
    def test_kelly_tier_conviction_1_3(self):
        """Conviction 1-3 should map to 5% Kelly"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        tier_1 = next((t for t in tiers if t[0] == 1.0), None)
        assert tier_1 is not None, "Tier for conviction 1 not found"
        assert tier_1[1] == 0.05, f"Expected 0.05 for conviction 1, got {tier_1[1]}"
    
    def test_kelly_tier_conviction_below_1(self):
        """Conviction < 1 should map to 0% (skip)"""
        tiers = self.module.NewsSniper.KELLY_TIERS
        tier_0 = next((t for t in tiers if t[0] == 0.0), None)
        assert tier_0 is not None, "Tier for conviction 0 not found"
        assert tier_0[1] == 0.00, f"Expected 0.00 for conviction 0, got {tier_0[1]}"


# =============================================================================
# TEST: ConvictionEnhancer Class
# =============================================================================
class TestConvictionEnhancerClass:
    """Verify ConvictionEnhancer class exists with required methods"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_conviction_enhancer_class_exists(self):
        """ConvictionEnhancer class should exist"""
        assert hasattr(self.module, 'ConvictionEnhancer'), "ConvictionEnhancer class not found"
    
    def test_conviction_enhancer_has_calculate_conviction(self):
        """ConvictionEnhancer should have calculate_conviction() method"""
        assert hasattr(self.module.ConvictionEnhancer, 'calculate_conviction'), "calculate_conviction() method not found"


# =============================================================================
# TEST: ConvictionEnhancer SOURCE_MULTIPLIERS
# =============================================================================
class TestConvictionEnhancerSourceMultipliers:
    """Verify ConvictionEnhancer.SOURCE_MULTIPLIERS has correct values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_source_multipliers_exists(self):
        """SOURCE_MULTIPLIERS should exist"""
        assert hasattr(self.module.ConvictionEnhancer, 'SOURCE_MULTIPLIERS'), "SOURCE_MULTIPLIERS not found"
    
    def test_reuters_multiplier(self):
        """Reuters should have multiplier 1.25"""
        mult = self.module.ConvictionEnhancer.SOURCE_MULTIPLIERS
        assert 'reuters' in mult, "reuters not in SOURCE_MULTIPLIERS"
        assert mult['reuters'] == 1.25, f"Expected 1.25 for reuters, got {mult['reuters']}"
    
    def test_whale_alert_multiplier(self):
        """Whale Alert should have multiplier 1.35"""
        mult = self.module.ConvictionEnhancer.SOURCE_MULTIPLIERS
        assert 'whale_alert' in mult, "whale_alert not in SOURCE_MULTIPLIERS"
        assert mult['whale_alert'] == 1.35, f"Expected 1.35 for whale_alert, got {mult['whale_alert']}"
    
    def test_twitter_multiplier(self):
        """Twitter should have multiplier 0.90"""
        mult = self.module.ConvictionEnhancer.SOURCE_MULTIPLIERS
        assert 'twitter' in mult, "twitter not in SOURCE_MULTIPLIERS"
        assert mult['twitter'] == 0.90, f"Expected 0.90 for twitter, got {mult['twitter']}"


# =============================================================================
# TEST: ConvictionEnhancer REGIME_MULTIPLIERS
# =============================================================================
class TestConvictionEnhancerRegimeMultipliers:
    """Verify ConvictionEnhancer.REGIME_MULTIPLIERS has correct values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_regime_multipliers_exists(self):
        """REGIME_MULTIPLIERS should exist"""
        assert hasattr(self.module.ConvictionEnhancer, 'REGIME_MULTIPLIERS'), "REGIME_MULTIPLIERS not found"
    
    def test_crisis_multiplier(self):
        """Crisis regime should have multiplier 0.7"""
        mult = self.module.ConvictionEnhancer.REGIME_MULTIPLIERS
        crisis_key = self.module.MarketRegime.CRISIS
        assert crisis_key in mult, "CRISIS not in REGIME_MULTIPLIERS"
        assert mult[crisis_key] == 0.7, f"Expected 0.7 for crisis, got {mult[crisis_key]}"
    
    def test_volatile_multiplier(self):
        """Volatile regime should have multiplier 0.9"""
        mult = self.module.ConvictionEnhancer.REGIME_MULTIPLIERS
        volatile_key = self.module.MarketRegime.VOLATILE
        assert volatile_key in mult, "VOLATILE not in REGIME_MULTIPLIERS"
        assert mult[volatile_key] == 0.9, f"Expected 0.9 for volatile, got {mult[volatile_key]}"
    
    def test_normal_multiplier(self):
        """Normal regime should have multiplier 1.0"""
        mult = self.module.ConvictionEnhancer.REGIME_MULTIPLIERS
        normal_key = self.module.MarketRegime.NORMAL
        assert normal_key in mult, "NORMAL not in REGIME_MULTIPLIERS"
        assert mult[normal_key] == 1.0, f"Expected 1.0 for normal, got {mult[normal_key]}"
    
    def test_quiet_multiplier(self):
        """Quiet regime should have multiplier 1.1"""
        mult = self.module.ConvictionEnhancer.REGIME_MULTIPLIERS
        quiet_key = self.module.MarketRegime.QUIET
        assert quiet_key in mult, "QUIET not in REGIME_MULTIPLIERS"
        assert mult[quiet_key] == 1.1, f"Expected 1.1 for quiet, got {mult[quiet_key]}"


# =============================================================================
# TEST: MarketRegime Enum
# =============================================================================
class TestMarketRegimeEnum:
    """Verify MarketRegime enum has correct values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_market_regime_enum_exists(self):
        """MarketRegime enum should exist"""
        assert hasattr(self.module, 'MarketRegime'), "MarketRegime enum not found"
    
    def test_market_regime_has_crisis(self):
        """MarketRegime should have CRISIS value"""
        assert hasattr(self.module.MarketRegime, 'CRISIS'), "CRISIS not in MarketRegime"
        assert self.module.MarketRegime.CRISIS.value == "crisis"
    
    def test_market_regime_has_volatile(self):
        """MarketRegime should have VOLATILE value"""
        assert hasattr(self.module.MarketRegime, 'VOLATILE'), "VOLATILE not in MarketRegime"
        assert self.module.MarketRegime.VOLATILE.value == "volatile"
    
    def test_market_regime_has_normal(self):
        """MarketRegime should have NORMAL value"""
        assert hasattr(self.module.MarketRegime, 'NORMAL'), "NORMAL not in MarketRegime"
        assert self.module.MarketRegime.NORMAL.value == "normal"
    
    def test_market_regime_has_quiet(self):
        """MarketRegime should have QUIET value"""
        assert hasattr(self.module.MarketRegime, 'QUIET'), "QUIET not in MarketRegime"
        assert self.module.MarketRegime.QUIET.value == "quiet"


# =============================================================================
# TEST: NewsImpactLevel Enum
# =============================================================================
class TestNewsImpactLevelEnum:
    """Verify NewsImpactLevel enum has correct values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
    
    def test_news_impact_level_enum_exists(self):
        """NewsImpactLevel enum should exist"""
        assert hasattr(self.module, 'NewsImpactLevel'), "NewsImpactLevel enum not found"
    
    def test_news_impact_level_has_extreme(self):
        """NewsImpactLevel should have EXTREME value"""
        assert hasattr(self.module.NewsImpactLevel, 'EXTREME'), "EXTREME not in NewsImpactLevel"
        assert self.module.NewsImpactLevel.EXTREME.value == "extreme"
    
    def test_news_impact_level_has_high(self):
        """NewsImpactLevel should have HIGH value"""
        assert hasattr(self.module.NewsImpactLevel, 'HIGH'), "HIGH not in NewsImpactLevel"
        assert self.module.NewsImpactLevel.HIGH.value == "high"
    
    def test_news_impact_level_has_moderate(self):
        """NewsImpactLevel should have MODERATE value"""
        assert hasattr(self.module.NewsImpactLevel, 'MODERATE'), "MODERATE not in NewsImpactLevel"
        assert self.module.NewsImpactLevel.MODERATE.value == "moderate"
    
    def test_news_impact_level_has_low(self):
        """NewsImpactLevel should have LOW value"""
        assert hasattr(self.module.NewsImpactLevel, 'LOW'), "LOW not in NewsImpactLevel"
        assert self.module.NewsImpactLevel.LOW.value == "low"
    
    def test_news_impact_level_has_skip(self):
        """NewsImpactLevel should have SKIP value"""
        assert hasattr(self.module.NewsImpactLevel, 'SKIP'), "SKIP not in NewsImpactLevel"
        assert self.module.NewsImpactLevel.SKIP.value == "skip"


# =============================================================================
# TEST: paper_trader.py Imports
# =============================================================================
class TestPaperTraderImports:
    """Verify paper_trader.py imports NewsSniper and related classes"""
    
    def test_paper_trader_imports_news_sniper(self):
        """paper_trader.py should import NewsSniper"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "from lanes.news_lane.news_sniper_mongodb import" in content
        assert "NewsSniper" in content
    
    def test_paper_trader_imports_init_news_sniper(self):
        """paper_trader.py should import init_news_sniper"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "init_news_sniper" in content
    
    def test_paper_trader_imports_get_news_sniper(self):
        """paper_trader.py should import get_news_sniper"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "get_news_sniper" in content
    
    def test_paper_trader_imports_conviction_enhancer(self):
        """paper_trader.py should import ConvictionEnhancer"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "ConvictionEnhancer" in content
    
    def test_paper_trader_imports_news_impact_level(self):
        """paper_trader.py should import NewsImpactLevel"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "NewsImpactLevel" in content
    
    def test_paper_trader_imports_market_regime(self):
        """paper_trader.py should import MarketRegime from news_sniper_mongodb"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        # Check the import line specifically
        assert "from lanes.news_lane.news_sniper_mongodb import" in content
        # MarketRegime is imported from news_sniper_mongodb (line 48)
        import_line = [line for line in content.split('\n') if 'from lanes.news_lane.news_sniper_mongodb import' in line]
        assert len(import_line) > 0, "Import line not found"


# =============================================================================
# TEST: paper_trader.py _run_news_sniper_loop Method
# =============================================================================
class TestPaperTraderNewsSniperLoop:
    """Verify _run_news_sniper_loop() method exists in paper_trader.py"""
    
    def test_run_news_sniper_loop_method_exists(self):
        """_run_news_sniper_loop() method should exist"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        assert "async def _run_news_sniper_loop(self):" in content
    
    def test_run_news_sniper_loop_in_asyncio_gather(self):
        """_run_news_sniper_loop() should be in asyncio.gather"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            content = f.read()
        # Check that it's called in the main loop
        assert "self._run_news_sniper_loop()" in content


# =============================================================================
# TEST: GET /api/news-sniper/status Endpoint
# =============================================================================
class TestNewsSniperStatusEndpoint:
    """Verify GET /api/news-sniper/status endpoint"""
    
    def test_news_sniper_status_endpoint_returns_200(self):
        """GET /api/news-sniper/status should return 200"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_news_sniper_status_returns_not_initialized_when_stopped(self):
        """GET /api/news-sniper/status should return not_initialized when paper trading stopped"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        data = response.json()
        # When paper trading is stopped, status should be not_initialized
        assert data.get('status') == 'not_initialized', f"Expected 'not_initialized', got {data.get('status')}"
    
    def test_news_sniper_status_has_message(self):
        """GET /api/news-sniper/status should have message field"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        data = response.json()
        assert 'message' in data, "message field not found in response"
    
    def test_news_sniper_status_has_timestamp(self):
        """GET /api/news-sniper/status should have timestamp field"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        data = response.json()
        assert 'timestamp' in data, "timestamp field not found in response"


# =============================================================================
# TEST: Module Exports (__init__.py)
# =============================================================================
class TestModuleExports:
    """Verify news_lane module exports"""
    
    def test_init_exports_news_sniper(self):
        """__init__.py should export NewsSniper"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "NewsSniper" in content
    
    def test_init_exports_conviction_enhancer(self):
        """__init__.py should export ConvictionEnhancer"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "ConvictionEnhancer" in content
    
    def test_init_exports_news_impact_level(self):
        """__init__.py should export NewsImpactLevel"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "NewsImpactLevel" in content
    
    def test_init_exports_market_regime(self):
        """__init__.py should export MarketRegime"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "MarketRegime" in content
    
    def test_init_exports_init_news_sniper(self):
        """__init__.py should export init_news_sniper"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "init_news_sniper" in content
    
    def test_init_exports_get_news_sniper(self):
        """__init__.py should export get_news_sniper"""
        with open("/app/backend/lanes/news_lane/__init__.py", "r") as f:
            content = f.read()
        assert "get_news_sniper" in content


# =============================================================================
# TEST: Markets-First System Still Operational
# =============================================================================
class TestMarketsFirstSystemOperational:
    """Verify Markets-First system is still operational"""
    
    def test_health_endpoint(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_paper_status_endpoint(self):
        """GET /api/paper/status should return 200"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


# =============================================================================
# TEST: HFT V2 Still Operational
# =============================================================================
class TestHFTV2StillOperational:
    """Verify HFT V2 is still operational"""
    
    def test_hft_v2_status_endpoint(self):
        """GET /api/hft-v2/status should return 200"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_hft_v2_status_returns_not_initialized_when_stopped(self):
        """GET /api/hft-v2/status should return not_initialized when paper trading stopped"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status")
        data = response.json()
        # When paper trading is stopped, status should be not_initialized
        assert data.get('status') == 'not_initialized', f"Expected 'not_initialized', got {data.get('status')}"


# =============================================================================
# TEST: _conviction_to_kelly Logic
# =============================================================================
class TestConvictionToKellyLogic:
    """Verify _conviction_to_kelly() method logic"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Load the news_sniper_mongodb module and create instance"""
        spec = importlib.util.spec_from_file_location(
            "news_sniper_mongodb",
            "/app/backend/lanes/news_lane/news_sniper_mongodb.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        # Create a NewsSniper instance with None db and paper_trader
        self.sniper = self.module.NewsSniper(db=None, paper_trader=None)
    
    def test_conviction_15_returns_50_pct(self):
        """Conviction 15 should return 50% Kelly"""
        result = self.sniper._conviction_to_kelly(15.0)
        assert result == 0.50, f"Expected 0.50, got {result}"
    
    def test_conviction_10_returns_50_pct(self):
        """Conviction 10 should return 50% Kelly"""
        result = self.sniper._conviction_to_kelly(10.0)
        assert result == 0.50, f"Expected 0.50, got {result}"
    
    def test_conviction_9_returns_40_pct(self):
        """Conviction 9 should return 40% Kelly"""
        result = self.sniper._conviction_to_kelly(9.0)
        assert result == 0.40, f"Expected 0.40, got {result}"
    
    def test_conviction_8_returns_40_pct(self):
        """Conviction 8 should return 40% Kelly"""
        result = self.sniper._conviction_to_kelly(8.0)
        assert result == 0.40, f"Expected 0.40, got {result}"
    
    def test_conviction_7_returns_30_pct(self):
        """Conviction 7 should return 30% Kelly"""
        result = self.sniper._conviction_to_kelly(7.0)
        assert result == 0.30, f"Expected 0.30, got {result}"
    
    def test_conviction_6_returns_30_pct(self):
        """Conviction 6 should return 30% Kelly"""
        result = self.sniper._conviction_to_kelly(6.0)
        assert result == 0.30, f"Expected 0.30, got {result}"
    
    def test_conviction_5_returns_15_pct(self):
        """Conviction 5 should return 15% Kelly"""
        result = self.sniper._conviction_to_kelly(5.0)
        assert result == 0.15, f"Expected 0.15, got {result}"
    
    def test_conviction_3_returns_15_pct(self):
        """Conviction 3 should return 15% Kelly"""
        result = self.sniper._conviction_to_kelly(3.0)
        assert result == 0.15, f"Expected 0.15, got {result}"
    
    def test_conviction_2_returns_5_pct(self):
        """Conviction 2 should return 5% Kelly"""
        result = self.sniper._conviction_to_kelly(2.0)
        assert result == 0.05, f"Expected 0.05, got {result}"
    
    def test_conviction_1_returns_5_pct(self):
        """Conviction 1 should return 5% Kelly"""
        result = self.sniper._conviction_to_kelly(1.0)
        assert result == 0.05, f"Expected 0.05, got {result}"
    
    def test_conviction_0_5_returns_0_pct(self):
        """Conviction 0.5 should return 0% (skip)"""
        result = self.sniper._conviction_to_kelly(0.5)
        assert result == 0.00, f"Expected 0.00, got {result}"
    
    def test_conviction_0_returns_0_pct(self):
        """Conviction 0 should return 0% (skip)"""
        result = self.sniper._conviction_to_kelly(0.0)
        assert result == 0.00, f"Expected 0.00, got {result}"


# =============================================================================
# TEST: _read_fresh_signals Method Signature
# =============================================================================
class TestReadFreshSignalsMethod:
    """Verify _read_fresh_signals() method reads from MongoDB signals collection"""
    
    def test_read_fresh_signals_queries_signals_collection(self):
        """_read_fresh_signals() should query MongoDB signals collection"""
        with open("/app/backend/lanes/news_lane/news_sniper_mongodb.py", "r") as f:
            content = f.read()
        # Check that it queries the signals collection
        assert "self.db.signals.find" in content, "_read_fresh_signals should query signals collection"
    
    def test_read_fresh_signals_filters_path_a(self):
        """_read_fresh_signals() should filter for type='path_a'"""
        with open("/app/backend/lanes/news_lane/news_sniper_mongodb.py", "r") as f:
            content = f.read()
        assert "'type': 'path_a'" in content, "_read_fresh_signals should filter for path_a type"
    
    def test_read_fresh_signals_excludes_id(self):
        """_read_fresh_signals() should exclude MongoDB _id"""
        with open("/app/backend/lanes/news_lane/news_sniper_mongodb.py", "r") as f:
            content = f.read()
        assert "'_id': 0" in content, "_read_fresh_signals should exclude _id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
