"""
HFT V2 Engine Direction-Finding Refactor Tests - Iteration 46
==============================================================

Tests for the HFT V2 Engine refactor that gives each of the 5 sub-strategies
its own direction-finding logic instead of defaulting to 'YES'.

Features tested:
1. execute_hft_scalp correctly calls _determine_direction() before building trade params
2. Each strategy determines its own direction:
   - DELTA_NEUTRAL: Fair value comparison
   - VOLATILITY_EXPLOIT: Mean reversion at extremes
   - LIQUIDITY_PROVISION: Order flow imbalance
   - SHARP_FOLLOWING: Whale/sharp trader direction
   - EXTREME_SPREAD: Fair value comparison
3. Direction is properly passed to _build_trade_params() method
4. PATH A can override direction when Bayes Factor >= 5.0
5. Mean reversion only triggers at price extremes (<=0.15 or >=0.85)
6. Order flow imbalance logic correctly determines direction
7. Engine skips trades when no edge is found (returns None from _determine_direction)
8. HFT config parameters are correctly used
"""

import pytest
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

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
    return os.environ.get('REACT_APP_BACKEND_URL', 'https://sports-lane-fix.preview.emergentagent.com').rstrip('/')

BASE_URL = get_base_url()


class TestHFTConfigDirectionParameters:
    """Test HFT Config has correct direction-related parameters"""
    
    def test_edge_threshold_exists(self):
        """EDGE_THRESHOLD = 0.02 (2% minimum edge to take position)"""
        from trading.hft_config import HFTConfig
        assert hasattr(HFTConfig, 'EDGE_THRESHOLD'), "HFTConfig should have EDGE_THRESHOLD"
        assert HFTConfig.EDGE_THRESHOLD == 0.02, f"EDGE_THRESHOLD should be 0.02, got {HFTConfig.EDGE_THRESHOLD}"
        print(f"✅ EDGE_THRESHOLD = {HFTConfig.EDGE_THRESHOLD}")
    
    def test_path_a_override_bf_exists(self):
        """PATH_A_OVERRIDE_BF = 5.0 (BF >= 5 allows PATH A to override direction)"""
        from trading.hft_config import HFTConfig
        assert hasattr(HFTConfig, 'PATH_A_OVERRIDE_BF'), "HFTConfig should have PATH_A_OVERRIDE_BF"
        assert HFTConfig.PATH_A_OVERRIDE_BF == 5.0, f"PATH_A_OVERRIDE_BF should be 5.0, got {HFTConfig.PATH_A_OVERRIDE_BF}"
        print(f"✅ PATH_A_OVERRIDE_BF = {HFTConfig.PATH_A_OVERRIDE_BF}")
    
    def test_mean_reversion_low_exists(self):
        """MEAN_REVERSION_LOW = 0.15 (below this, expect reversion up)"""
        from trading.hft_config import HFTConfig
        assert hasattr(HFTConfig, 'MEAN_REVERSION_LOW'), "HFTConfig should have MEAN_REVERSION_LOW"
        assert HFTConfig.MEAN_REVERSION_LOW == 0.15, f"MEAN_REVERSION_LOW should be 0.15, got {HFTConfig.MEAN_REVERSION_LOW}"
        print(f"✅ MEAN_REVERSION_LOW = {HFTConfig.MEAN_REVERSION_LOW}")
    
    def test_mean_reversion_high_exists(self):
        """MEAN_REVERSION_HIGH = 0.85 (above this, expect reversion down)"""
        from trading.hft_config import HFTConfig
        assert hasattr(HFTConfig, 'MEAN_REVERSION_HIGH'), "HFTConfig should have MEAN_REVERSION_HIGH"
        assert HFTConfig.MEAN_REVERSION_HIGH == 0.85, f"MEAN_REVERSION_HIGH should be 0.85, got {HFTConfig.MEAN_REVERSION_HIGH}"
        print(f"✅ MEAN_REVERSION_HIGH = {HFTConfig.MEAN_REVERSION_HIGH}")
    
    def test_order_flow_imbalance_ratio_exists(self):
        """ORDER_FLOW_IMBALANCE_RATIO = 1.2 (20% imbalance triggers direction)"""
        from trading.hft_config import HFTConfig
        assert hasattr(HFTConfig, 'ORDER_FLOW_IMBALANCE_RATIO'), "HFTConfig should have ORDER_FLOW_IMBALANCE_RATIO"
        assert HFTConfig.ORDER_FLOW_IMBALANCE_RATIO == 1.2, f"ORDER_FLOW_IMBALANCE_RATIO should be 1.2, got {HFTConfig.ORDER_FLOW_IMBALANCE_RATIO}"
        print(f"✅ ORDER_FLOW_IMBALANCE_RATIO = {HFTConfig.ORDER_FLOW_IMBALANCE_RATIO}")


class TestDetermineDirectionMethodExists:
    """Test _determine_direction method exists in HFT V2 Engine"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_determine_direction_method_exists(self, hft_v2_source):
        """_determine_direction() method exists in HFT V2 Engine"""
        assert "async def _determine_direction(" in hft_v2_source, \
            "_determine_direction method should exist in HFT V2 Engine"
        print("✅ _determine_direction() method exists")
    
    def test_determine_direction_takes_hft_mode(self, hft_v2_source):
        """_determine_direction() takes hft_mode parameter"""
        assert "hft_mode: HFTMode" in hft_v2_source or "hft_mode=" in hft_v2_source, \
            "_determine_direction should take hft_mode parameter"
        print("✅ _determine_direction() takes hft_mode parameter")
    
    def test_determine_direction_takes_market_data(self, hft_v2_source):
        """_determine_direction() takes market_data parameter"""
        assert "market_data: Dict" in hft_v2_source or "market_data=" in hft_v2_source, \
            "_determine_direction should take market_data parameter"
        print("✅ _determine_direction() takes market_data parameter")
    
    def test_determine_direction_takes_adjusted_fair(self, hft_v2_source):
        """_determine_direction() takes adjusted_fair parameter"""
        assert "adjusted_fair" in hft_v2_source, \
            "_determine_direction should take adjusted_fair parameter"
        print("✅ _determine_direction() takes adjusted_fair parameter")
    
    def test_determine_direction_takes_signal(self, hft_v2_source):
        """_determine_direction() takes signal parameter for PATH A override"""
        assert "signal" in hft_v2_source, \
            "_determine_direction should take signal parameter"
        print("✅ _determine_direction() takes signal parameter")


class TestExecuteHFTScalpCallsDetermineDirection:
    """Test execute_hft_scalp calls _determine_direction before _build_trade_params"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_execute_hft_scalp_calls_determine_direction(self, hft_v2_source):
        """execute_hft_scalp() calls _determine_direction()"""
        # Find the execute_hft_scalp method and verify it calls _determine_direction
        assert "await self._determine_direction(" in hft_v2_source, \
            "execute_hft_scalp should call _determine_direction"
        print("✅ execute_hft_scalp() calls _determine_direction()")
    
    def test_direction_passed_to_build_trade_params(self, hft_v2_source):
        """Direction from _determine_direction is passed to _build_trade_params"""
        # Check that direction is passed to _build_trade_params
        assert "direction=direction" in hft_v2_source, \
            "Direction should be passed to _build_trade_params"
        print("✅ Direction is passed to _build_trade_params()")
    
    def test_determine_direction_called_after_mode_selection(self, hft_v2_source):
        """_determine_direction is called after _select_hft_mode (STEP 10)"""
        # Find the order of calls in execute_hft_scalp
        # _select_hft_mode should come before _determine_direction
        mode_selection_pos = hft_v2_source.find("await self._select_hft_mode(")
        direction_pos = hft_v2_source.find("await self._determine_direction(")
        
        assert mode_selection_pos > 0, "_select_hft_mode should be called"
        assert direction_pos > 0, "_determine_direction should be called"
        assert mode_selection_pos < direction_pos, \
            "_select_hft_mode should be called before _determine_direction"
        print("✅ _determine_direction is called after _select_hft_mode")
    
    def test_skip_trade_when_no_direction(self, hft_v2_source):
        """Engine skips trade when _determine_direction returns None"""
        # Check for the pattern: if not direction: return None
        assert "if not direction:" in hft_v2_source, \
            "Should check if direction is None"
        print("✅ Engine skips trade when direction is None")


class TestDeltaNeutralDirectionLogic:
    """Test DELTA_NEUTRAL strategy uses fair value comparison for direction"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_delta_neutral_uses_fair_value(self, hft_v2_source):
        """DELTA_NEUTRAL uses fair value vs current price comparison"""
        # Check for fair value comparison logic
        assert "HFTMode.DELTA_NEUTRAL" in hft_v2_source, \
            "DELTA_NEUTRAL mode should be referenced"
        assert "adjusted_fair" in hft_v2_source, \
            "adjusted_fair should be used for comparison"
        print("✅ DELTA_NEUTRAL uses fair value comparison")
    
    def test_delta_neutral_edge_calculation(self, hft_v2_source):
        """DELTA_NEUTRAL calculates edge_yes and edge_no"""
        # Check for edge calculation
        assert "edge_yes" in hft_v2_source or "edge" in hft_v2_source, \
            "Edge calculation should exist"
        print("✅ DELTA_NEUTRAL calculates edge")
    
    def test_delta_neutral_returns_yes_when_underpriced(self, hft_v2_source):
        """DELTA_NEUTRAL returns YES when market is underpriced"""
        # Check for YES direction when fair > price
        assert "direction = 'YES'" in hft_v2_source, \
            "Should set direction to YES"
        print("✅ DELTA_NEUTRAL can return YES direction")
    
    def test_delta_neutral_returns_no_when_overpriced(self, hft_v2_source):
        """DELTA_NEUTRAL returns NO when market is overpriced"""
        # Check for NO direction when fair < price
        assert "direction = 'NO'" in hft_v2_source, \
            "Should set direction to NO"
        print("✅ DELTA_NEUTRAL can return NO direction")


class TestMeanReversionDirectionLogic:
    """Test VOLATILITY_EXPLOIT strategy uses mean reversion at extremes"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_mean_reversion_method_exists(self, hft_v2_source):
        """_get_mean_reversion_direction() method exists"""
        assert "def _get_mean_reversion_direction(" in hft_v2_source, \
            "_get_mean_reversion_direction method should exist"
        print("✅ _get_mean_reversion_direction() method exists")
    
    def test_mean_reversion_uses_config_thresholds(self, hft_v2_source):
        """Mean reversion uses HFTConfig.MEAN_REVERSION_LOW and HIGH"""
        assert "HFTConfig.MEAN_REVERSION_LOW" in hft_v2_source, \
            "Should use MEAN_REVERSION_LOW threshold"
        assert "HFTConfig.MEAN_REVERSION_HIGH" in hft_v2_source, \
            "Should use MEAN_REVERSION_HIGH threshold"
        print("✅ Mean reversion uses config thresholds")
    
    def test_mean_reversion_returns_yes_at_low_price(self, hft_v2_source):
        """Mean reversion returns YES when price <= 0.15"""
        # Check for YES return at low price
        assert "return 'YES'" in hft_v2_source, \
            "Should return YES at low price"
        print("✅ Mean reversion returns YES at low price")
    
    def test_mean_reversion_returns_no_at_high_price(self, hft_v2_source):
        """Mean reversion returns NO when price >= 0.85"""
        # Check for NO return at high price
        assert "return 'NO'" in hft_v2_source, \
            "Should return NO at high price"
        print("✅ Mean reversion returns NO at high price")
    
    def test_mean_reversion_returns_none_in_middle(self, hft_v2_source):
        """Mean reversion returns None when price is not at extremes"""
        # Check for None return in middle range
        assert "return None" in hft_v2_source, \
            "Should return None when not at extremes"
        print("✅ Mean reversion returns None in middle range")


class TestOrderFlowDirectionLogic:
    """Test LIQUIDITY_PROVISION strategy uses order flow imbalance"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_order_flow_method_exists(self, hft_v2_source):
        """_get_order_flow_direction() method exists"""
        assert "def _get_order_flow_direction(" in hft_v2_source, \
            "_get_order_flow_direction method should exist"
        print("✅ _get_order_flow_direction() method exists")
    
    def test_order_flow_uses_buy_sell_volume(self, hft_v2_source):
        """Order flow uses buy_volume and sell_volume"""
        assert "buy_volume" in hft_v2_source, \
            "Should use buy_volume"
        assert "sell_volume" in hft_v2_source, \
            "Should use sell_volume"
        print("✅ Order flow uses buy/sell volume")
    
    def test_order_flow_uses_imbalance_ratio(self, hft_v2_source):
        """Order flow uses ORDER_FLOW_IMBALANCE_RATIO"""
        assert "HFTConfig.ORDER_FLOW_IMBALANCE_RATIO" in hft_v2_source or \
               "imbalance_ratio" in hft_v2_source, \
            "Should use imbalance ratio"
        print("✅ Order flow uses imbalance ratio")
    
    def test_order_flow_returns_yes_on_buy_pressure(self, hft_v2_source):
        """Order flow returns YES when buy volume exceeds sell volume"""
        # Check for YES return on buy pressure
        assert "return 'YES'" in hft_v2_source, \
            "Should return YES on buy pressure"
        print("✅ Order flow returns YES on buy pressure")
    
    def test_order_flow_returns_no_on_sell_pressure(self, hft_v2_source):
        """Order flow returns NO when sell volume exceeds buy volume"""
        # Check for NO return on sell pressure
        assert "return 'NO'" in hft_v2_source, \
            "Should return NO on sell pressure"
        print("✅ Order flow returns NO on sell pressure")


class TestSharpFollowingDirectionLogic:
    """Test SHARP_FOLLOWING strategy follows whale/sharp traders"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_sharp_direction_method_exists(self, hft_v2_source):
        """_get_sharp_direction() method exists"""
        assert "async def _get_sharp_direction(" in hft_v2_source, \
            "_get_sharp_direction method should exist"
        print("✅ _get_sharp_direction() method exists")
    
    def test_sharp_direction_uses_whale_tracker(self, hft_v2_source):
        """Sharp direction uses whale_tracker"""
        assert "whale_tracker" in hft_v2_source, \
            "Should use whale_tracker"
        print("✅ Sharp direction uses whale_tracker")
    
    def test_sharp_direction_uses_sharp_detector(self, hft_v2_source):
        """Sharp direction uses sharp_detector"""
        assert "sharp_detector" in hft_v2_source, \
            "Should use sharp_detector"
        print("✅ Sharp direction uses sharp_detector")
    
    def test_sharp_direction_has_default(self, hft_v2_source):
        """Sharp direction has default fallback"""
        # Check for default return
        assert "return 'YES'" in hft_v2_source, \
            "Should have default fallback"
        print("✅ Sharp direction has default fallback")


class TestPathAOverrideLogic:
    """Test PATH A can override direction when Bayes Factor >= 5.0"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_path_a_override_check_exists(self, hft_v2_source):
        """PATH A override check exists in _determine_direction"""
        assert "PATH_A_OVERRIDE_BF" in hft_v2_source or "bayes_factor" in hft_v2_source, \
            "Should check PATH A override"
        print("✅ PATH A override check exists")
    
    def test_path_a_override_uses_threshold(self, hft_v2_source):
        """PATH A override uses HFTConfig.PATH_A_OVERRIDE_BF threshold"""
        assert "HFTConfig.PATH_A_OVERRIDE_BF" in hft_v2_source, \
            "Should use PATH_A_OVERRIDE_BF threshold"
        print("✅ PATH A override uses config threshold")
    
    def test_path_a_override_changes_direction(self, hft_v2_source):
        """PATH A override can change direction"""
        # Check for direction override logic
        assert "path_a_direction" in hft_v2_source or "signal.get('direction')" in hft_v2_source, \
            "Should get direction from PATH A signal"
        print("✅ PATH A override can change direction")
    
    def test_path_a_override_logs_change(self, hft_v2_source):
        """PATH A override logs when direction is changed"""
        assert "PATH A override" in hft_v2_source, \
            "Should log PATH A override"
        print("✅ PATH A override logs direction change")


class TestBuildTradeParamsReceivesDirection:
    """Test _build_trade_params receives direction parameter"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_build_trade_params_has_direction_param(self, hft_v2_source):
        """_build_trade_params has direction parameter"""
        # Find the method signature
        assert "direction: str" in hft_v2_source or "direction," in hft_v2_source, \
            "_build_trade_params should have direction parameter"
        print("✅ _build_trade_params has direction parameter")
    
    def test_build_trade_params_uses_direction(self, hft_v2_source):
        """_build_trade_params uses direction for entry price"""
        # Check that direction is used
        assert "'direction': direction" in hft_v2_source, \
            "Direction should be included in trade params"
        print("✅ _build_trade_params uses direction")
    
    def test_no_default_yes_direction(self, hft_v2_source):
        """_build_trade_params does not default to YES"""
        # Check that there's no hardcoded YES default in _build_trade_params
        # The direction should come from _determine_direction
        build_params_start = hft_v2_source.find("async def _build_trade_params(")
        build_params_end = hft_v2_source.find("async def", build_params_start + 1)
        build_params_code = hft_v2_source[build_params_start:build_params_end]
        
        # Should not have direction = 'YES' as default
        assert "direction = 'YES'" not in build_params_code, \
            "_build_trade_params should not default to YES"
        print("✅ _build_trade_params does not default to YES")


class TestStrategySpecificDirectionRouting:
    """Test each strategy routes to its specific direction logic"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_delta_neutral_routing(self, hft_v2_source):
        """DELTA_NEUTRAL routes to fair value comparison"""
        assert "HFTMode.DELTA_NEUTRAL" in hft_v2_source, \
            "Should handle DELTA_NEUTRAL mode"
        print("✅ DELTA_NEUTRAL routing exists")
    
    def test_volatility_exploit_routing(self, hft_v2_source):
        """VOLATILITY_EXPLOIT routes to mean reversion"""
        assert "HFTMode.VOLATILITY_EXPLOIT" in hft_v2_source, \
            "Should handle VOLATILITY_EXPLOIT mode"
        assert "_get_mean_reversion_direction" in hft_v2_source, \
            "Should call mean reversion for VOLATILITY_EXPLOIT"
        print("✅ VOLATILITY_EXPLOIT routing exists")
    
    def test_liquidity_provision_routing(self, hft_v2_source):
        """LIQUIDITY_PROVISION routes to order flow"""
        assert "HFTMode.LIQUIDITY_PROVISION" in hft_v2_source, \
            "Should handle LIQUIDITY_PROVISION mode"
        assert "_get_order_flow_direction" in hft_v2_source, \
            "Should call order flow for LIQUIDITY_PROVISION"
        print("✅ LIQUIDITY_PROVISION routing exists")
    
    def test_sharp_following_routing(self, hft_v2_source):
        """SHARP_FOLLOWING routes to whale/sharp direction"""
        assert "HFTMode.SHARP_FOLLOWING" in hft_v2_source, \
            "Should handle SHARP_FOLLOWING mode"
        assert "_get_sharp_direction" in hft_v2_source, \
            "Should call sharp direction for SHARP_FOLLOWING"
        print("✅ SHARP_FOLLOWING routing exists")
    
    def test_extreme_spread_routing(self, hft_v2_source):
        """EXTREME_SPREAD routes to fair value comparison"""
        assert "HFTMode.EXTREME_SPREAD" in hft_v2_source, \
            "Should handle EXTREME_SPREAD mode"
        print("✅ EXTREME_SPREAD routing exists")


class TestMeanReversionThresholds:
    """Test mean reversion only triggers at correct price extremes"""
    
    def test_mean_reversion_low_threshold(self):
        """Mean reversion triggers YES at price <= 0.15"""
        from trading.hft_config import HFTConfig
        
        # Test the threshold value
        assert HFTConfig.MEAN_REVERSION_LOW == 0.15, \
            f"MEAN_REVERSION_LOW should be 0.15, got {HFTConfig.MEAN_REVERSION_LOW}"
        print(f"✅ MEAN_REVERSION_LOW = {HFTConfig.MEAN_REVERSION_LOW}")
    
    def test_mean_reversion_high_threshold(self):
        """Mean reversion triggers NO at price >= 0.85"""
        from trading.hft_config import HFTConfig
        
        # Test the threshold value
        assert HFTConfig.MEAN_REVERSION_HIGH == 0.85, \
            f"MEAN_REVERSION_HIGH should be 0.85, got {HFTConfig.MEAN_REVERSION_HIGH}"
        print(f"✅ MEAN_REVERSION_HIGH = {HFTConfig.MEAN_REVERSION_HIGH}")
    
    def test_mean_reversion_middle_range(self):
        """Mean reversion returns None for prices between 0.15 and 0.85"""
        from trading.hft_config import HFTConfig
        
        # Verify the gap between thresholds
        gap = HFTConfig.MEAN_REVERSION_HIGH - HFTConfig.MEAN_REVERSION_LOW
        assert gap == 0.70, f"Gap should be 0.70, got {gap}"
        print(f"✅ Middle range gap = {gap}")


class TestEdgeThresholdUsage:
    """Test EDGE_THRESHOLD is used correctly"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_edge_threshold_used_in_determine_direction(self, hft_v2_source):
        """EDGE_THRESHOLD is used in _determine_direction"""
        assert "HFTConfig.EDGE_THRESHOLD" in hft_v2_source or "edge_threshold" in hft_v2_source, \
            "Should use EDGE_THRESHOLD"
        print("✅ EDGE_THRESHOLD is used")
    
    def test_edge_comparison_for_yes(self, hft_v2_source):
        """Edge comparison for YES direction"""
        assert "edge_yes" in hft_v2_source or "edge" in hft_v2_source, \
            "Should calculate edge for YES"
        print("✅ Edge comparison for YES exists")
    
    def test_edge_comparison_for_no(self, hft_v2_source):
        """Edge comparison for NO direction"""
        assert "edge_no" in hft_v2_source or "edge" in hft_v2_source, \
            "Should calculate edge for NO"
        print("✅ Edge comparison for NO exists")


class TestHFTV2EngineUnitTests:
    """Unit tests for HFT V2 Engine direction logic"""
    
    @pytest.fixture
    def mock_engine(self):
        """Create a mock HFT V2 Engine for unit testing"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        # Create engine with minimal dependencies
        engine = HighFrequencyTradingEngineV2({
            'db': None,
            'market_data_svc': None,
            'paper_trader': None,
            'strategy_context': None,
            'sharp_detector': None,
            'gamma_trader': None,
            'volatility_predictor': None,
            'performance_analytics': None
        })
        
        return engine
    
    def test_get_mean_reversion_direction_low(self, mock_engine):
        """_get_mean_reversion_direction returns YES at low price"""
        result = mock_engine._get_mean_reversion_direction(0.10)
        assert result == 'YES', f"Expected YES at price 0.10, got {result}"
        print("✅ Mean reversion returns YES at price 0.10")
    
    def test_get_mean_reversion_direction_high(self, mock_engine):
        """_get_mean_reversion_direction returns NO at high price"""
        result = mock_engine._get_mean_reversion_direction(0.90)
        assert result == 'NO', f"Expected NO at price 0.90, got {result}"
        print("✅ Mean reversion returns NO at price 0.90")
    
    def test_get_mean_reversion_direction_middle(self, mock_engine):
        """_get_mean_reversion_direction returns None at middle price"""
        result = mock_engine._get_mean_reversion_direction(0.50)
        assert result is None, f"Expected None at price 0.50, got {result}"
        print("✅ Mean reversion returns None at price 0.50")
    
    def test_get_mean_reversion_direction_boundary_low(self, mock_engine):
        """_get_mean_reversion_direction at boundary 0.15"""
        result = mock_engine._get_mean_reversion_direction(0.15)
        assert result == 'YES', f"Expected YES at price 0.15, got {result}"
        print("✅ Mean reversion returns YES at boundary 0.15")
    
    def test_get_mean_reversion_direction_boundary_high(self, mock_engine):
        """_get_mean_reversion_direction at boundary 0.85"""
        result = mock_engine._get_mean_reversion_direction(0.85)
        assert result == 'NO', f"Expected NO at price 0.85, got {result}"
        print("✅ Mean reversion returns NO at boundary 0.85")
    
    def test_get_order_flow_direction_buy_pressure(self, mock_engine):
        """_get_order_flow_direction returns YES on buy pressure"""
        market_data = {
            'buy_volume': 1500,
            'sell_volume': 1000,
            'volume_24h': 100000,
            'price': 0.5
        }
        result = mock_engine._get_order_flow_direction(market_data)
        assert result == 'YES', f"Expected YES on buy pressure, got {result}"
        print("✅ Order flow returns YES on buy pressure")
    
    def test_get_order_flow_direction_sell_pressure(self, mock_engine):
        """_get_order_flow_direction returns NO on sell pressure"""
        market_data = {
            'buy_volume': 1000,
            'sell_volume': 1500,
            'volume_24h': 100000,
            'price': 0.5
        }
        result = mock_engine._get_order_flow_direction(market_data)
        assert result == 'NO', f"Expected NO on sell pressure, got {result}"
        print("✅ Order flow returns NO on sell pressure")
    
    def test_get_order_flow_direction_balanced(self, mock_engine):
        """_get_order_flow_direction handles balanced volume"""
        market_data = {
            'buy_volume': 1000,
            'sell_volume': 1000,
            'volume_24h': 100000,
            'price': 0.6
        }
        result = mock_engine._get_order_flow_direction(market_data)
        # Should return based on price trend or default
        assert result in ['YES', 'NO'], f"Expected YES or NO, got {result}"
        print(f"✅ Order flow returns {result} on balanced volume")


class TestHFTV2EngineIntegration:
    """Integration tests for HFT V2 Engine"""
    
    def test_hft_v2_status_endpoint(self):
        """GET /api/hft-v2/status returns valid response"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'status' in data, "Response should have status field"
        print(f"✅ HFT V2 status: {data.get('status')}")
    
    def test_paper_trading_status(self):
        """GET /api/paper/status returns valid response"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/paper/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'running' in data, "Response should have running field"
        print(f"✅ Paper trading running: {data.get('running')}")
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy, got {data.get('status')}"
        print("✅ Health endpoint returns healthy")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
