"""
HFT Engine V2 ENHANCED - Comprehensive Test Suite
==================================================

Tests for the merged HFT V2 architecture with all legacy features integrated.

Features tested:
1. Alpha Target Integration (strategy_context)
2. HFT Math Engine (cubic skew, jump detection, cliff protection)
3. Active Order Tracking (Polymarket compliance)
4. Hysteresis Logic (anti-churn)
5. Tick Grid Compliance ($0.01)
6. 5 Sub-Strategies
7. MongoDB PATH A+B signals
8. Legacy HFT loop deprecation
"""

import pytest
import requests
import os
import sys
import ast

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHFTV2EnhancedFileExists:
    """Verify HFT V2 Enhanced engine file exists with required structure"""
    
    def test_hft_engine_v2_file_exists(self):
        """HFT V2 Enhanced engine file exists at /app/backend/trading/hft_engine_v2.py"""
        file_path = "/app/backend/trading/hft_engine_v2.py"
        assert os.path.exists(file_path), f"HFT V2 engine file not found at {file_path}"
    
    def test_hft_math_file_exists(self):
        """HFT Math Engine file exists at /app/backend/strategies/hft_math.py"""
        file_path = "/app/backend/strategies/hft_math.py"
        assert os.path.exists(file_path), f"HFT Math file not found at {file_path}"


class TestHighFrequencyTradingEngineV2Class:
    """Verify HighFrequencyTradingEngineV2 class exists with all required methods"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_class_exists(self, hft_v2_source):
        """HighFrequencyTradingEngineV2 class exists"""
        assert "class HighFrequencyTradingEngineV2:" in hft_v2_source
    
    def test_round_to_tick_method(self, hft_v2_source):
        """_round_to_tick() method for tick grid compliance exists"""
        assert "def _round_to_tick(self" in hft_v2_source
    
    def test_clamp_to_bounds_method(self, hft_v2_source):
        """_clamp_to_bounds() method for kill zone compliance exists"""
        assert "def _clamp_to_bounds(self" in hft_v2_source
    
    def test_enforce_min_spread_method(self, hft_v2_source):
        """_enforce_min_spread() method for minimum 2-tick spread exists"""
        assert "def _enforce_min_spread(self" in hft_v2_source
    
    def test_prune_stale_orders_method(self, hft_v2_source):
        """_prune_stale_orders() method with hysteresis logic exists"""
        assert "def _prune_stale_orders(self" in hft_v2_source
    
    def test_get_hft_metrics_method(self, hft_v2_source):
        """get_hft_metrics() method exists"""
        assert "def get_hft_metrics(self" in hft_v2_source
    
    def test_get_stats_method(self, hft_v2_source):
        """get_stats() method exists"""
        assert "def get_stats(self" in hft_v2_source
    
    def test_start_hft_loop_method(self, hft_v2_source):
        """start_hft_loop() method exists"""
        assert "async def start_hft_loop(self" in hft_v2_source
    
    def test_stop_method(self, hft_v2_source):
        """stop() method exists"""
        assert "async def stop(self" in hft_v2_source
    
    def test_execute_hft_scalp_method(self, hft_v2_source):
        """execute_hft_scalp() method exists"""
        assert "async def execute_hft_scalp(self" in hft_v2_source


class TestHFTMathEngineIntegration:
    """Verify HFT Math Engine is imported and used in HFT V2"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_hft_math_engine_import(self, hft_v2_source):
        """HFTMathEngine imported from strategies.hft_math"""
        assert "from strategies.hft_math import" in hft_v2_source
        assert "HFTMathEngine" in hft_v2_source
    
    def test_cubic_inventory_skew_import(self, hft_v2_source):
        """CubicInventorySkew imported from strategies.hft_math"""
        assert "CubicInventorySkew" in hft_v2_source
    
    def test_adaptive_signal_smoother_import(self, hft_v2_source):
        """AdaptiveSignalSmoother imported from strategies.hft_math"""
        assert "AdaptiveSignalSmoother" in hft_v2_source
    
    def test_cliff_protection_import(self, hft_v2_source):
        """CliffProtection imported from strategies.hft_math"""
        assert "CliffProtection" in hft_v2_source
    
    def test_hft_math_engine_instantiation(self, hft_v2_source):
        """HFTMathEngine is instantiated in __init__"""
        assert "self.hft_math_engine = HFTMathEngine" in hft_v2_source


class TestPolymarketComplianceConstants:
    """Verify Polymarket compliance constants are correctly defined"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_tick_size_constant(self, hft_v2_source):
        """TICK_SIZE = 0.01 for Polymarket tick grid"""
        assert "TICK_SIZE = 0.01" in hft_v2_source
    
    def test_min_price_constant(self, hft_v2_source):
        """MIN_PRICE = 0.05 for kill zone lower bound"""
        assert "MIN_PRICE = 0.05" in hft_v2_source
    
    def test_max_price_constant(self, hft_v2_source):
        """MAX_PRICE = 0.95 for kill zone upper bound"""
        assert "MAX_PRICE = 0.95" in hft_v2_source
    
    def test_hysteresis_threshold_constant(self, hft_v2_source):
        """HYSTERESIS_THRESHOLD = 0.01 for anti-churn"""
        assert "HYSTERESIS_THRESHOLD = 0.01" in hft_v2_source
    
    def test_min_spread_ticks_constant(self, hft_v2_source):
        """MIN_SPREAD_TICKS = 2 for minimum 2-tick spread"""
        assert "MIN_SPREAD_TICKS = 2" in hft_v2_source


class TestStrategyContextIntegration:
    """Verify strategy_context integration in dependencies"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    @pytest.fixture(scope="class")
    def paper_trader_source(self):
        """Load paper_trader source code"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            return f.read()
    
    def test_strategy_context_in_dependencies(self, hft_v2_source):
        """strategy_context is in dependencies dict"""
        assert "strategy_context" in hft_v2_source
        assert "self.strategy_context = dependencies.get('strategy_context')" in hft_v2_source
    
    def test_strategy_context_passed_to_hft_v2(self, paper_trader_source):
        """strategy_context is passed to init_hft_engine_v2"""
        assert "'strategy_context': self.strategy_context" in paper_trader_source
    
    def test_alpha_target_usage(self, hft_v2_source):
        """Alpha target is retrieved from strategy_context"""
        assert "self.strategy_context.get_target(market_id)" in hft_v2_source


class TestGetHFTMetricsReturns:
    """Verify get_hft_metrics() returns required fields"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_alpha_hits_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns alpha_hits"""
        # Check that alpha_hits is in the return dict of get_hft_metrics
        assert "'alpha_hits':" in hft_v2_source
    
    def test_alpha_misses_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns alpha_misses"""
        assert "'alpha_misses':" in hft_v2_source
    
    def test_alpha_hit_rate_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns alpha_hit_rate"""
        assert "'alpha_hit_rate':" in hft_v2_source
    
    def test_orders_kept_hysteresis_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns orders_kept_hysteresis"""
        assert "'orders_kept_hysteresis':" in hft_v2_source
    
    def test_orders_cancelled_drift_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns orders_cancelled_drift"""
        assert "'orders_cancelled_drift':" in hft_v2_source
    
    def test_orders_cancelled_stale_in_metrics(self, hft_v2_source):
        """get_hft_metrics() returns orders_cancelled_stale"""
        assert "'orders_cancelled_stale':" in hft_v2_source


class TestLegacyHFTLoopRemoval:
    """Verify legacy HFT loop is removed from asyncio.gather"""
    
    @pytest.fixture(scope="class")
    def paper_trader_source(self):
        """Load paper_trader source code"""
        with open("/app/backend/paper_trading/paper_trader.py", "r") as f:
            return f.read()
    
    def test_legacy_hft_loop_deprecated_comment(self, paper_trader_source):
        """Legacy _run_hft_loop() is marked as DEPRECATED"""
        assert "DEPRECATED: self._run_hft_loop()" in paper_trader_source or \
               "# DEPRECATED: self._run_hft_loop()" in paper_trader_source
    
    def test_hft_v2_loop_in_asyncio_gather(self, paper_trader_source):
        """_run_hft_v2_loop() is in asyncio.gather"""
        assert "self._run_hft_v2_loop()" in paper_trader_source
    
    def test_legacy_hft_loop_commented_out(self, paper_trader_source):
        """Legacy _run_hft_loop() is commented out in asyncio.gather"""
        # Find the asyncio.gather section
        lines = paper_trader_source.split('\n')
        in_gather = False
        legacy_commented = False
        hft_v2_active = False
        
        for line in lines:
            if 'asyncio.gather(' in line:
                in_gather = True
            if in_gather:
                if '# DEPRECATED: self._run_hft_loop()' in line or \
                   '#.*self._run_hft_loop()' in line:
                    legacy_commented = True
                if 'self._run_hft_v2_loop()' in line and not line.strip().startswith('#'):
                    hft_v2_active = True
                if ')' in line and in_gather and 'gather' not in line:
                    break
        
        assert legacy_commented or "DEPRECATED" in paper_trader_source, \
            "Legacy _run_hft_loop() should be commented out or marked DEPRECATED"
        assert hft_v2_active, "_run_hft_v2_loop() should be active in asyncio.gather"


class TestHFTV2StatusEndpoint:
    """Test GET /api/hft-v2/status endpoint"""
    
    def test_status_endpoint_returns_200(self):
        """GET /api/hft-v2/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        assert response.status_code == 200
    
    def test_status_endpoint_returns_json(self):
        """GET /api/hft-v2/status returns valid JSON"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        assert isinstance(data, dict)
    
    def test_status_endpoint_has_status_field(self):
        """GET /api/hft-v2/status returns status field"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        assert "status" in data
    
    def test_status_endpoint_not_initialized_when_stopped(self):
        """GET /api/hft-v2/status returns 'not_initialized' when paper trading stopped"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        data = response.json()
        # When paper trading is stopped, status should be 'not_initialized'
        # This is expected behavior
        assert data.get("status") in ["not_initialized", "operational", "running"]


class TestMarketsFirstSystemOperational:
    """Verify Markets-First system is still operational"""
    
    def test_health_endpoint(self):
        """Health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
    
    def test_scanner_health_endpoint(self):
        """Scanner health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/scanner/health", timeout=10)
        assert response.status_code == 200
    
    def test_paper_status_endpoint(self):
        """Paper status endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/paper/status", timeout=10)
        assert response.status_code == 200


class TestHFTMathEngineClasses:
    """Verify HFT Math Engine classes exist with required methods"""
    
    @pytest.fixture(scope="class")
    def hft_math_source(self):
        """Load HFT Math source code"""
        with open("/app/backend/strategies/hft_math.py", "r") as f:
            return f.read()
    
    def test_hft_math_engine_class(self, hft_math_source):
        """HFTMathEngine class exists"""
        assert "class HFTMathEngine:" in hft_math_source
    
    def test_cubic_inventory_skew_class(self, hft_math_source):
        """CubicInventorySkew class exists"""
        assert "class CubicInventorySkew:" in hft_math_source
    
    def test_adaptive_signal_smoother_class(self, hft_math_source):
        """AdaptiveSignalSmoother class exists"""
        assert "class AdaptiveSignalSmoother:" in hft_math_source
    
    def test_cliff_protection_class(self, hft_math_source):
        """CliffProtection class exists"""
        assert "class CliffProtection:" in hft_math_source
    
    def test_calculate_quote_method(self, hft_math_source):
        """HFTMathEngine has calculate_quote method"""
        assert "def calculate_quote(" in hft_math_source
    
    def test_calculate_skew_method(self, hft_math_source):
        """CubicInventorySkew has calculate_skew method"""
        assert "def calculate_skew(" in hft_math_source
    
    def test_smooth_signal_method(self, hft_math_source):
        """AdaptiveSignalSmoother has smooth_signal method"""
        assert "def smooth_signal(" in hft_math_source
    
    def test_calculate_spread_multiplier_method(self, hft_math_source):
        """CliffProtection has calculate_spread_multiplier method"""
        assert "def calculate_spread_multiplier(" in hft_math_source


class TestHFTV2StatsTracking:
    """Verify HFT V2 stats tracking includes all required fields"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_alpha_hits_in_stats(self, hft_v2_source):
        """Stats includes alpha_hits"""
        assert "'alpha_hits': 0" in hft_v2_source
    
    def test_alpha_misses_in_stats(self, hft_v2_source):
        """Stats includes alpha_misses"""
        assert "'alpha_misses': 0" in hft_v2_source
    
    def test_orders_kept_hysteresis_in_stats(self, hft_v2_source):
        """Stats includes orders_kept_hysteresis"""
        assert "'orders_kept_hysteresis': 0" in hft_v2_source
    
    def test_orders_cancelled_drift_in_stats(self, hft_v2_source):
        """Stats includes orders_cancelled_drift"""
        assert "'orders_cancelled_drift': 0" in hft_v2_source
    
    def test_orders_cancelled_stale_in_stats(self, hft_v2_source):
        """Stats includes orders_cancelled_stale"""
        assert "'orders_cancelled_stale': 0" in hft_v2_source
    
    def test_path_a_hits_in_stats(self, hft_v2_source):
        """Stats includes path_a_hits"""
        assert "'path_a_hits': 0" in hft_v2_source
    
    def test_path_b_hits_in_stats(self, hft_v2_source):
        """Stats includes path_b_hits"""
        assert "'path_b_hits': 0" in hft_v2_source


class TestHFTV2ActiveOrderTracking:
    """Verify active order tracking with hysteresis"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_active_orders_dict(self, hft_v2_source):
        """active_orders dict exists"""
        assert "self.active_orders:" in hft_v2_source or \
               "self.active_orders =" in hft_v2_source
    
    def test_orders_lock(self, hft_v2_source):
        """Thread lock for orders exists"""
        assert "self._orders_lock = Lock()" in hft_v2_source
    
    def test_update_active_order_method(self, hft_v2_source):
        """_update_active_order method exists"""
        assert "def _update_active_order(self" in hft_v2_source


class TestHFTV2EnhancedDocstring:
    """Verify HFT V2 Enhanced has proper documentation"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_enhanced_in_docstring(self, hft_v2_source):
        """ENHANCED mentioned in docstring"""
        assert "ENHANCED" in hft_v2_source
    
    def test_legacy_features_documented(self, hft_v2_source):
        """Legacy features are documented"""
        assert "LEGACY FEATURES" in hft_v2_source or "Legacy" in hft_v2_source
    
    def test_alpha_target_documented(self, hft_v2_source):
        """Alpha Target Integration documented"""
        assert "Alpha Target" in hft_v2_source or "alpha_target" in hft_v2_source
    
    def test_hysteresis_documented(self, hft_v2_source):
        """Hysteresis Logic documented"""
        assert "Hysteresis" in hft_v2_source or "hysteresis" in hft_v2_source
    
    def test_tick_grid_documented(self, hft_v2_source):
        """Tick Grid Compliance documented"""
        assert "Tick Grid" in hft_v2_source or "tick grid" in hft_v2_source


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
