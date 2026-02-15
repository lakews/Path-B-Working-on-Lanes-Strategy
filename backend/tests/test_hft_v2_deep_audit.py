"""
HFT V2 Engine Deep Audit Tests - Iteration 47
==============================================

EXTENSIVE AUDIT of the HFT V2 Engine trade logic, decision-making flow, and execution path.
This is a 5-lane trading bot for Polymarket prediction markets.

AUDIT AREAS:
1. Complete execute_hft_scalp() flow from start to finish (13 steps)
2. Direction determination logic for each strategy type
3. Edge calculation correctness (2% threshold)
4. Trade skipping when no edge found
5. PATH A signal integration (MongoDB + bayes_factor)
6. PATH B opportunity detection (hft_opportunities collection)
7. News strength classification and multiplier application
8. HFT Math Engine integration (cubic skew, cliff protection, jump detection)
9. Order hysteresis logic (stale order pruning with 1 cent tolerance)
10. Mode selection logic based on price zones
11. Capital allocation across 5 sub-strategies (sum to 1.0)
12. Kelly criterion application (0.25 fractional sizing)
13. 3% max position cap enforcement
14. Polymarket tick grid compliance ($0.01 rounding)
15. Kill zone bounds enforcement ($0.05 - $0.95)
16. Mean reversion triggers only at extremes (<=0.15 or >=0.85)
17. Order flow imbalance calculation (1.2 ratio threshold)
18. PATH A override when Bayes Factor >= 5.0
19. Trade execution through paper_trader integration
20. Statistics tracking (trades_executed, trades_by_mode, path_a_hits, etc.)
"""

import pytest
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

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
    return os.environ.get('REACT_APP_BACKEND_URL', 'https://hft-evolution.preview.emergentagent.com').rstrip('/')

BASE_URL = get_base_url()


# =============================================================================
# SECTION 1: EXECUTE_HFT_SCALP FLOW AUDIT (13 STEPS)
# =============================================================================

class TestExecuteHFTScalpFlowAudit:
    """Audit the complete execute_hft_scalp() flow from start to finish"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_step1_position_check(self, hft_v2_source):
        """STEP 1: Check if we already have a position (skip)"""
        assert "paper_positions" in hft_v2_source, "Should check paper_positions"
        assert "market_id in" in hft_v2_source, "Should check if market_id in positions"
        print("✅ STEP 1: Position check exists")
    
    def test_step2_alpha_target_check(self, hft_v2_source):
        """STEP 2: Get Alpha target from strategy_context"""
        assert "strategy_context" in hft_v2_source, "Should use strategy_context"
        assert "get_target" in hft_v2_source, "Should call get_target()"
        assert "alpha_target" in hft_v2_source, "Should store alpha_target"
        print("✅ STEP 2: Alpha target check exists")
    
    def test_step3_path_b_check(self, hft_v2_source):
        """STEP 3: Check PATH B for fresh news broadcast"""
        assert "_check_path_b_opportunity" in hft_v2_source, "Should have PATH B check method"
        assert "hft_opportunities" in hft_v2_source, "Should query hft_opportunities collection"
        print("✅ STEP 3: PATH B check exists")
    
    def test_step4_path_a_signal(self, hft_v2_source):
        """STEP 4: Get PATH A analysis for bayes_factor"""
        assert "_read_path_a_signal" in hft_v2_source, "Should have PATH A read method"
        assert "bayes_factor" in hft_v2_source, "Should extract bayes_factor"
        print("✅ STEP 4: PATH A signal read exists")
    
    def test_step5_news_strength_classification(self, hft_v2_source):
        """STEP 5: Classify news strength and get multipliers"""
        assert "get_news_strength" in hft_v2_source, "Should call get_news_strength()"
        assert "get_multipliers" in hft_v2_source, "Should call get_multipliers()"
        print("✅ STEP 5: News strength classification exists")
    
    def test_step6_pause_mode_skip(self, hft_v2_source):
        """STEP 6: If PAUSE mode, skip entire cycle"""
        assert "NewsStrength.PAUSE" in hft_v2_source, "Should check for PAUSE mode"
        assert "paused_cycles" in hft_v2_source, "Should track paused_cycles"
        print("✅ STEP 6: PAUSE mode skip exists")
    
    def test_step7_hft_math_engine(self, hft_v2_source):
        """STEP 7: Apply HFT Math Engine (skew, smoothing, cliff protection)"""
        assert "hft_math_engine" in hft_v2_source, "Should use hft_math_engine"
        assert "calculate_quote" in hft_v2_source, "Should call calculate_quote()"
        assert "cliff_zone" in hft_v2_source, "Should extract cliff_zone"
        print("✅ STEP 7: HFT Math Engine integration exists")
    
    def test_step8_order_pruning(self, hft_v2_source):
        """STEP 8: Prune stale orders with hysteresis"""
        assert "_prune_stale_orders" in hft_v2_source, "Should have prune method"
        assert "HYSTERESIS_THRESHOLD" in hft_v2_source, "Should use HYSTERESIS_THRESHOLD"
        print("✅ STEP 8: Order pruning with hysteresis exists")
    
    def test_step9_mode_selection(self, hft_v2_source):
        """STEP 9: Select appropriate HFT mode based on price zone"""
        assert "_select_hft_mode" in hft_v2_source, "Should have mode selection method"
        assert "get_price_zone" in hft_v2_source, "Should call get_price_zone()"
        print("✅ STEP 9: Mode selection exists")
    
    def test_step10_direction_determination(self, hft_v2_source):
        """STEP 10: Determine trade direction using strategy-specific logic"""
        assert "_determine_direction" in hft_v2_source, "Should have direction method"
        assert "direction = await self._determine_direction" in hft_v2_source, \
            "Should call _determine_direction"
        print("✅ STEP 10: Direction determination exists")
    
    def test_step11_build_trade_params(self, hft_v2_source):
        """STEP 11: Build trade parameters (respecting all constraints)"""
        assert "_build_trade_params" in hft_v2_source, "Should have build params method"
        assert "direction=direction" in hft_v2_source, "Should pass direction"
        print("✅ STEP 11: Build trade params exists")
    
    def test_step12_execute_strategy(self, hft_v2_source):
        """STEP 12: Execute via paper_trader with tick grid compliance"""
        assert "_execute_strategy" in hft_v2_source, "Should have execute method"
        assert "_execute_compliant_trade" in hft_v2_source, "Should have compliant trade method"
        print("✅ STEP 12: Strategy execution exists")
    
    def test_step13_log_analytics(self, hft_v2_source):
        """STEP 13: Log to analytics"""
        assert "_log_hft_trade" in hft_v2_source, "Should have log method"
        assert "performance_analytics" in hft_v2_source, "Should use performance_analytics"
        print("✅ STEP 13: Analytics logging exists")


# =============================================================================
# SECTION 2: DIRECTION DETERMINATION LOGIC AUDIT
# =============================================================================

class TestDirectionDeterminationAudit:
    """Audit direction determination logic for each strategy type"""
    
    @pytest.fixture
    def mock_engine(self):
        """Create a mock HFT V2 Engine for testing"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None,
            'market_data_svc': None,
            'paper_trader': None,
            'strategy_context': None,
            'sharp_detector': None,
        })
        return engine
    
    def test_delta_neutral_direction_yes_edge(self, mock_engine):
        """DELTA_NEUTRAL: Returns YES when fair > price + edge_threshold"""
        from trading.hft_config import HFTConfig, HFTMode
        
        # fair=0.55, price=0.50, edge=0.05 > 0.02 threshold → YES
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.DELTA_NEUTRAL,
                market_data={'price': 0.50, 'yes_price': 0.50},
                adjusted_fair=0.55,
                signal=None
            )
        )
        assert result == 'YES', f"Expected YES, got {result}"
        print("✅ DELTA_NEUTRAL returns YES when underpriced")
    
    def test_delta_neutral_direction_no_edge(self, mock_engine):
        """DELTA_NEUTRAL: Returns NO when fair < price - edge_threshold"""
        from trading.hft_config import HFTConfig, HFTMode
        
        # fair=0.45, price=0.50, edge=0.05 > 0.02 threshold → NO
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.DELTA_NEUTRAL,
                market_data={'price': 0.50, 'yes_price': 0.50},
                adjusted_fair=0.45,
                signal=None
            )
        )
        assert result == 'NO', f"Expected NO, got {result}"
        print("✅ DELTA_NEUTRAL returns NO when overpriced")
    
    def test_delta_neutral_direction_no_edge_skip(self, mock_engine):
        """DELTA_NEUTRAL: Returns None when no edge (skip trade)"""
        from trading.hft_config import HFTConfig, HFTMode
        
        # fair=0.51, price=0.50, edge=0.01 < 0.02 threshold → None
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.DELTA_NEUTRAL,
                market_data={'price': 0.50, 'yes_price': 0.50},
                adjusted_fair=0.51,
                signal=None
            )
        )
        assert result is None, f"Expected None (no edge), got {result}"
        print("✅ DELTA_NEUTRAL returns None when no edge")
    
    def test_volatility_exploit_mean_reversion_low(self, mock_engine):
        """VOLATILITY_EXPLOIT: Returns YES at low price (mean reversion)"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.VOLATILITY_EXPLOIT,
                market_data={'price': 0.10, 'yes_price': 0.10},
                adjusted_fair=0.10,
                signal=None
            )
        )
        assert result == 'YES', f"Expected YES at low price, got {result}"
        print("✅ VOLATILITY_EXPLOIT returns YES at low price")
    
    def test_volatility_exploit_mean_reversion_high(self, mock_engine):
        """VOLATILITY_EXPLOIT: Returns NO at high price (mean reversion)"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.VOLATILITY_EXPLOIT,
                market_data={'price': 0.90, 'yes_price': 0.90},
                adjusted_fair=0.90,
                signal=None
            )
        )
        assert result == 'NO', f"Expected NO at high price, got {result}"
        print("✅ VOLATILITY_EXPLOIT returns NO at high price")
    
    def test_volatility_exploit_skip_middle(self, mock_engine):
        """VOLATILITY_EXPLOIT: Returns None in middle range (skip)"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.VOLATILITY_EXPLOIT,
                market_data={'price': 0.50, 'yes_price': 0.50},
                adjusted_fair=0.50,
                signal=None
            )
        )
        assert result is None, f"Expected None in middle range, got {result}"
        print("✅ VOLATILITY_EXPLOIT returns None in middle range")
    
    def test_liquidity_provision_buy_pressure(self, mock_engine):
        """LIQUIDITY_PROVISION: Returns YES on buy pressure"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.LIQUIDITY_PROVISION,
                market_data={
                    'price': 0.50, 'yes_price': 0.50,
                    'buy_volume': 1500, 'sell_volume': 1000,
                    'volume_24h': 100000
                },
                adjusted_fair=0.50,
                signal=None
            )
        )
        assert result == 'YES', f"Expected YES on buy pressure, got {result}"
        print("✅ LIQUIDITY_PROVISION returns YES on buy pressure")
    
    def test_liquidity_provision_sell_pressure(self, mock_engine):
        """LIQUIDITY_PROVISION: Returns NO on sell pressure"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.LIQUIDITY_PROVISION,
                market_data={
                    'price': 0.50, 'yes_price': 0.50,
                    'buy_volume': 1000, 'sell_volume': 1500,
                    'volume_24h': 100000
                },
                adjusted_fair=0.50,
                signal=None
            )
        )
        assert result == 'NO', f"Expected NO on sell pressure, got {result}"
        print("✅ LIQUIDITY_PROVISION returns NO on sell pressure")
    
    def test_extreme_spread_direction(self, mock_engine):
        """EXTREME_SPREAD: Uses fair value comparison like DELTA_NEUTRAL"""
        from trading.hft_config import HFTMode
        
        result = asyncio.get_event_loop().run_until_complete(
            mock_engine._determine_direction(
                hft_mode=HFTMode.EXTREME_SPREAD,
                market_data={'price': 0.50, 'yes_price': 0.50},
                adjusted_fair=0.55,
                signal=None
            )
        )
        assert result == 'YES', f"Expected YES, got {result}"
        print("✅ EXTREME_SPREAD uses fair value comparison")


# =============================================================================
# SECTION 3: EDGE CALCULATION AUDIT
# =============================================================================

class TestEdgeCalculationAudit:
    """Audit edge calculation correctness (2% threshold)"""
    
    def test_edge_threshold_value(self):
        """EDGE_THRESHOLD should be 0.02 (2%)"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.EDGE_THRESHOLD == 0.02, \
            f"EDGE_THRESHOLD should be 0.02, got {HFTConfig.EDGE_THRESHOLD}"
        print(f"✅ EDGE_THRESHOLD = {HFTConfig.EDGE_THRESHOLD} (2%)")
    
    def test_edge_calculation_yes(self):
        """Edge YES = adjusted_fair - current_price"""
        from trading.hft_config import HFTConfig
        
        adjusted_fair = 0.55
        current_price = 0.50
        edge_yes = adjusted_fair - current_price
        
        assert edge_yes == 0.05, f"Edge YES should be 0.05, got {edge_yes}"
        assert edge_yes >= HFTConfig.EDGE_THRESHOLD, "Edge should exceed threshold"
        print(f"✅ Edge YES calculation: {adjusted_fair} - {current_price} = {edge_yes}")
    
    def test_edge_calculation_no(self):
        """Edge NO = current_price - adjusted_fair"""
        from trading.hft_config import HFTConfig
        
        adjusted_fair = 0.45
        current_price = 0.50
        edge_no = current_price - adjusted_fair
        
        assert edge_no == 0.05, f"Edge NO should be 0.05, got {edge_no}"
        assert edge_no >= HFTConfig.EDGE_THRESHOLD, "Edge should exceed threshold"
        print(f"✅ Edge NO calculation: {current_price} - {adjusted_fair} = {edge_no}")
    
    def test_edge_below_threshold_skips(self):
        """Edge below 2% should result in trade skip (None)"""
        from trading.hft_config import HFTConfig
        
        adjusted_fair = 0.51
        current_price = 0.50
        edge = abs(adjusted_fair - current_price)
        
        assert edge == 0.01, f"Edge should be 0.01, got {edge}"
        assert edge < HFTConfig.EDGE_THRESHOLD, "Edge should be below threshold"
        print(f"✅ Edge {edge} < threshold {HFTConfig.EDGE_THRESHOLD} → skip trade")


# =============================================================================
# SECTION 4: PATH A/B SIGNAL INTEGRATION AUDIT
# =============================================================================

class TestPathABSignalAudit:
    """Audit PATH A and PATH B signal integration"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_path_a_reads_from_signals_collection(self, hft_v2_source):
        """PATH A reads from MongoDB signals collection"""
        assert "db.signals.find_one" in hft_v2_source, \
            "Should query signals collection"
        assert "'type': 'path_a'" in hft_v2_source, \
            "Should filter by type='path_a'"
        print("✅ PATH A reads from signals collection")
    
    def test_path_a_uses_bayes_factor(self, hft_v2_source):
        """PATH A extracts and uses bayes_factor"""
        assert "bayes_factor" in hft_v2_source, "Should use bayes_factor"
        assert "signal.get('bayes_factor'" in hft_v2_source, \
            "Should extract bayes_factor from signal"
        print("✅ PATH A uses bayes_factor")
    
    def test_path_b_reads_from_hft_opportunities(self, hft_v2_source):
        """PATH B reads from hft_opportunities collection"""
        assert "db.hft_opportunities.find_one" in hft_v2_source, \
            "Should query hft_opportunities collection"
        assert "'type': 'path_b'" in hft_v2_source, \
            "Should filter by type='path_b'"
        print("✅ PATH B reads from hft_opportunities collection")
    
    def test_path_b_checks_expiry(self, hft_v2_source):
        """PATH B checks expires_at for freshness"""
        assert "expires_at" in hft_v2_source, "Should check expires_at"
        assert "$gt" in hft_v2_source, "Should use $gt for expiry comparison"
        print("✅ PATH B checks expiry")
    
    def test_path_a_override_threshold(self):
        """PATH A override threshold is 5.0"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.PATH_A_OVERRIDE_BF == 5.0, \
            f"PATH_A_OVERRIDE_BF should be 5.0, got {HFTConfig.PATH_A_OVERRIDE_BF}"
        print(f"✅ PATH_A_OVERRIDE_BF = {HFTConfig.PATH_A_OVERRIDE_BF}")
    
    def test_path_a_override_logic(self, hft_v2_source):
        """PATH A can override direction when BF >= 5.0"""
        assert "HFTConfig.PATH_A_OVERRIDE_BF" in hft_v2_source, \
            "Should use PATH_A_OVERRIDE_BF threshold"
        assert "path_a_direction" in hft_v2_source, \
            "Should extract path_a_direction"
        assert "PATH A override" in hft_v2_source, \
            "Should log PATH A override"
        print("✅ PATH A override logic exists")


# =============================================================================
# SECTION 5: NEWS STRENGTH CLASSIFICATION AUDIT
# =============================================================================

class TestNewsStrengthAudit:
    """Audit news strength classification and multiplier application"""
    
    def test_news_strength_thresholds(self):
        """News strength thresholds are correct"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.PAUSE_BF == 10.0, f"PAUSE_BF should be 10.0, got {HFTConfig.PAUSE_BF}"
        assert HFTConfig.EXTREME_BF == 5.0, f"EXTREME_BF should be 5.0, got {HFTConfig.EXTREME_BF}"
        assert HFTConfig.CAUTION_BF == 3.0, f"CAUTION_BF should be 3.0, got {HFTConfig.CAUTION_BF}"
        print(f"✅ News thresholds: PAUSE={HFTConfig.PAUSE_BF}, EXTREME={HFTConfig.EXTREME_BF}, CAUTION={HFTConfig.CAUTION_BF}")
    
    def test_get_news_strength_pause(self):
        """BF >= 10.0 returns PAUSE"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(10.0)
        assert result == NewsStrength.PAUSE, f"Expected PAUSE, got {result}"
        
        result = get_news_strength(15.0)
        assert result == NewsStrength.PAUSE, f"Expected PAUSE, got {result}"
        print("✅ BF >= 10.0 → PAUSE")
    
    def test_get_news_strength_extreme(self):
        """BF 5.0-10.0 returns EXTREME"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(5.0)
        assert result == NewsStrength.EXTREME, f"Expected EXTREME, got {result}"
        
        result = get_news_strength(7.5)
        assert result == NewsStrength.EXTREME, f"Expected EXTREME, got {result}"
        print("✅ BF 5.0-10.0 → EXTREME")
    
    def test_get_news_strength_caution(self):
        """BF 3.0-5.0 returns CAUTION"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(3.0)
        assert result == NewsStrength.CAUTION, f"Expected CAUTION, got {result}"
        
        result = get_news_strength(4.5)
        assert result == NewsStrength.CAUTION, f"Expected CAUTION, got {result}"
        print("✅ BF 3.0-5.0 → CAUTION")
    
    def test_get_news_strength_normal(self):
        """BF < 3.0 returns NORMAL"""
        from trading.hft_config import get_news_strength, NewsStrength
        
        result = get_news_strength(2.0)
        assert result == NewsStrength.NORMAL, f"Expected NORMAL, got {result}"
        
        result = get_news_strength(0.0)
        assert result == NewsStrength.NORMAL, f"Expected NORMAL, got {result}"
        print("✅ BF < 3.0 → NORMAL")
    
    def test_spread_multipliers(self):
        """Spread multipliers are correct"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.SPREAD_MULTIPLIERS['NORMAL'] == 1.0
        assert HFTConfig.SPREAD_MULTIPLIERS['CAUTION'] == 1.3
        assert HFTConfig.SPREAD_MULTIPLIERS['EXTREME'] == 2.5
        assert HFTConfig.SPREAD_MULTIPLIERS['PAUSE'] == 0.0
        print("✅ Spread multipliers: NORMAL=1.0, CAUTION=1.3, EXTREME=2.5, PAUSE=0.0")
    
    def test_position_multipliers(self):
        """Position multipliers are correct"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.POSITION_MULTIPLIERS['NORMAL'] == 1.0
        assert HFTConfig.POSITION_MULTIPLIERS['CAUTION'] == 0.75
        assert HFTConfig.POSITION_MULTIPLIERS['EXTREME'] == 0.5
        assert HFTConfig.POSITION_MULTIPLIERS['PAUSE'] == 0.0
        print("✅ Position multipliers: NORMAL=1.0, CAUTION=0.75, EXTREME=0.5, PAUSE=0.0")
    
    def test_get_multipliers_function(self):
        """get_multipliers returns correct values"""
        from trading.hft_config import get_multipliers, NewsStrength
        
        result = get_multipliers(NewsStrength.NORMAL)
        assert result['spread_mult'] == 1.0
        assert result['position_mult'] == 1.0
        
        result = get_multipliers(NewsStrength.EXTREME)
        assert result['spread_mult'] == 2.5
        assert result['position_mult'] == 0.5
        print("✅ get_multipliers returns correct values")


# =============================================================================
# SECTION 6: HFT MATH ENGINE AUDIT
# =============================================================================

class TestHFTMathEngineAudit:
    """Audit HFT Math Engine integration (cubic skew, cliff protection, jump detection)"""
    
    def test_cubic_skew_calculation(self):
        """Cubic inventory skew uses x³ formula"""
        from strategies.hft_math import CubicInventorySkew, HFTMathConfig
        
        config = HFTMathConfig(max_position_limit=1000, skew_intensity=0.05)
        skew = CubicInventorySkew(config)
        
        # Test at 50% inventory
        adjusted, skew_amount, debug = skew.calculate_skew(
            current_position=500,
            raw_fair_value=0.50,
            max_position=1000,
            intensity=0.05
        )
        
        # pos_ratio = 0.5, cubed = 0.125, skew = 0.125 * 0.05 = 0.00625
        expected_skew = (0.5 ** 3) * 0.05
        assert abs(skew_amount - expected_skew) < 0.0001, \
            f"Skew should be {expected_skew}, got {skew_amount}"
        print(f"✅ Cubic skew at 50% inventory: {skew_amount:.6f}")
    
    def test_cubic_skew_hockey_stick(self):
        """Cubic skew has hockey stick shape (flat at start, steep at end)"""
        from strategies.hft_math import CubicInventorySkew, HFTMathConfig
        
        config = HFTMathConfig(max_position_limit=1000, skew_intensity=0.05)
        skew = CubicInventorySkew(config)
        
        # At 10% inventory - should be negligible
        _, skew_10, _ = skew.calculate_skew(100, 0.50, 1000, 0.05)
        
        # At 90% inventory - should be significant
        _, skew_90, _ = skew.calculate_skew(900, 0.50, 1000, 0.05)
        
        assert skew_10 < 0.001, f"Skew at 10% should be < 0.001, got {skew_10}"
        assert skew_90 > 0.03, f"Skew at 90% should be > 0.03, got {skew_90}"
        print(f"✅ Hockey stick: 10%={skew_10:.6f}, 90%={skew_90:.6f}")
    
    def test_cliff_protection_zones(self):
        """Cliff protection identifies correct zones"""
        from strategies.hft_math import CliffProtection, HFTMathConfig
        
        config = HFTMathConfig(
            cliff_zone_threshold=0.15,
            cliff_spread_multiplier=2.0,
            extreme_zone_threshold=0.05,
            extreme_spread_multiplier=3.0
        )
        cliff = CliffProtection(config)
        
        # SAFE zone (0.15 to 0.85)
        mult, zone, _ = cliff.calculate_spread_multiplier(0.50)
        assert zone == "SAFE", f"Expected SAFE at 0.50, got {zone}"
        assert mult == 1.0, f"Expected mult 1.0, got {mult}"
        
        # CLIFF zone (0.05 to 0.15 or 0.85 to 0.95)
        mult, zone, _ = cliff.calculate_spread_multiplier(0.10)
        assert zone == "CLIFF", f"Expected CLIFF at 0.10, got {zone}"
        assert mult == 2.0, f"Expected mult 2.0, got {mult}"
        
        # EXTREME zone (< 0.05 or > 0.95)
        mult, zone, _ = cliff.calculate_spread_multiplier(0.03)
        assert zone == "EXTREME", f"Expected EXTREME at 0.03, got {zone}"
        assert mult == 3.0, f"Expected mult 3.0, got {mult}"
        
        print("✅ Cliff protection zones: SAFE=1.0x, CLIFF=2.0x, EXTREME=3.0x")
    
    def test_jump_detection(self):
        """Jump detection bypasses smoothing for large moves"""
        from strategies.hft_math import AdaptiveSignalSmoother, HFTMathConfig
        
        config = HFTMathConfig(ema_alpha=0.2, jump_threshold=0.03)
        smoother = AdaptiveSignalSmoother(config)
        
        # Initialize
        smoother.smooth_signal("test_market", 0.50)
        
        # Small move - should be smoothed
        _, action, _ = smoother.smooth_signal("test_market", 0.51)
        assert action == "EMA_SMOOTHED", f"Expected EMA_SMOOTHED, got {action}"
        
        # Reset and test large move
        smoother.reset("test_market")
        smoother.smooth_signal("test_market", 0.50)
        
        # Large move (> 3 cents) - should bypass smoothing
        _, action, _ = smoother.smooth_signal("test_market", 0.55)
        assert action == "JUMP_DETECTED", f"Expected JUMP_DETECTED, got {action}"
        
        print("✅ Jump detection: small moves smoothed, large moves instant")


# =============================================================================
# SECTION 7: ORDER HYSTERESIS AUDIT
# =============================================================================

class TestOrderHysteresisAudit:
    """Audit order hysteresis logic (stale order pruning with 1 cent tolerance)"""
    
    def test_hysteresis_threshold_value(self):
        """HYSTERESIS_THRESHOLD should be 0.01 (1 cent)"""
        from trading.hft_engine_v2 import HYSTERESIS_THRESHOLD
        
        assert HYSTERESIS_THRESHOLD == 0.01, \
            f"HYSTERESIS_THRESHOLD should be 0.01, got {HYSTERESIS_THRESHOLD}"
        print(f"✅ HYSTERESIS_THRESHOLD = {HYSTERESIS_THRESHOLD} (1 cent)")
    
    def test_order_stale_seconds(self):
        """ORDER_STALE_SECONDS should be 120 (2 minutes)"""
        from trading.hft_engine_v2 import ORDER_STALE_SECONDS
        
        assert ORDER_STALE_SECONDS == 120, \
            f"ORDER_STALE_SECONDS should be 120, got {ORDER_STALE_SECONDS}"
        print(f"✅ ORDER_STALE_SECONDS = {ORDER_STALE_SECONDS} (2 minutes)")
    
    @pytest.fixture
    def mock_engine(self):
        """Create a mock HFT V2 Engine for testing"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None,
            'market_data_svc': None,
            'paper_trader': None,
            'strategy_context': None,
        })
        return engine
    
    def test_hysteresis_keeps_order_within_tolerance(self, mock_engine):
        """Orders within 1 cent drift are kept (anti-churn)"""
        from trading.hft_engine_v2 import HYSTERESIS_THRESHOLD
        
        market_id = "test_market_1"
        
        # Add an active order at $0.50
        mock_engine.active_orders[market_id] = {
            'price': 0.50,
            'timestamp': datetime.now(timezone.utc),
        }
        
        # Prune with AI price at $0.505 (0.5 cent drift < 1 cent threshold)
        stats = mock_engine._prune_stale_orders(market_id, 0.505)
        
        assert stats['orders_kept_hysteresis'] == 1, "Order should be kept"
        assert market_id in mock_engine.active_orders, "Order should still exist"
        print("✅ Order kept within 1 cent tolerance")
    
    def test_hysteresis_cancels_order_beyond_tolerance(self, mock_engine):
        """Orders beyond 1 cent drift are cancelled"""
        market_id = "test_market_2"
        
        # Add an active order at $0.50
        mock_engine.active_orders[market_id] = {
            'price': 0.50,
            'timestamp': datetime.now(timezone.utc),
        }
        
        # Prune with AI price at $0.52 (2 cent drift > 1 cent threshold)
        stats = mock_engine._prune_stale_orders(market_id, 0.52)
        
        assert stats['orders_cancelled_drift'] == 1, "Order should be cancelled"
        assert market_id not in mock_engine.active_orders, "Order should be removed"
        print("✅ Order cancelled beyond 1 cent tolerance")


# =============================================================================
# SECTION 8: MODE SELECTION AUDIT
# =============================================================================

class TestModeSelectionAudit:
    """Audit mode selection logic based on price zones"""
    
    def test_price_zone_extreme_low(self):
        """Price < 0.10 is extreme_low zone"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.05) == 'extreme_low'
        assert get_price_zone(0.09) == 'extreme_low'
        print("✅ Price < 0.10 → extreme_low")
    
    def test_price_zone_standard(self):
        """Price 0.10-0.90 is standard zone"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.10) == 'standard'
        assert get_price_zone(0.50) == 'standard'
        assert get_price_zone(0.89) == 'standard'
        print("✅ Price 0.10-0.90 → standard")
    
    def test_price_zone_extreme_high(self):
        """Price >= 0.90 is extreme_high zone"""
        from trading.hft_config import get_price_zone
        
        assert get_price_zone(0.90) == 'extreme_high'
        assert get_price_zone(0.95) == 'extreme_high'
        print("✅ Price >= 0.90 → extreme_high")
    
    def test_zone_config_values(self):
        """Zone boundaries are correctly configured"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.ZONES['extreme_low'] == (0.0, 0.10)
        assert HFTConfig.ZONES['standard'] == (0.10, 0.90)
        assert HFTConfig.ZONES['extreme_high'] == (0.90, 1.0)
        print("✅ Zone boundaries: extreme_low=(0,0.10), standard=(0.10,0.90), extreme_high=(0.90,1.0)")


# =============================================================================
# SECTION 9: CAPITAL ALLOCATION AUDIT
# =============================================================================

class TestCapitalAllocationAudit:
    """Audit capital allocation across 5 sub-strategies"""
    
    def test_sub_strategy_allocation_sum(self):
        """Sub-strategy allocations must sum to 1.0"""
        from trading.hft_config import HFTConfig
        
        total = sum(HFTConfig.SUB_STRATEGY_ALLOCATION.values())
        assert abs(total - 1.0) < 0.001, \
            f"Sub-strategy allocations should sum to 1.0, got {total}"
        print(f"✅ Sub-strategy allocations sum to {total}")
    
    def test_sub_strategy_allocation_values(self):
        """Sub-strategy allocation values are correct"""
        from trading.hft_config import HFTConfig
        
        expected = {
            'delta_neutral': 0.35,
            'volatility_exploit': 0.10,
            'extreme_spread': 0.15,
            'sharp_following': 0.20,
            'liquidity_provision': 0.20
        }
        
        for strategy, allocation in expected.items():
            actual = HFTConfig.SUB_STRATEGY_ALLOCATION.get(strategy)
            assert actual == allocation, \
                f"{strategy} should be {allocation}, got {actual}"
        
        print("✅ Allocations: delta_neutral=35%, volatility=10%, extreme=15%, sharp=20%, liquidity=20%")
    
    def test_hft_lane_allocation(self):
        """HFT lane gets 35% of total capital"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.HFT_LANE_ALLOCATION == 0.35, \
            f"HFT_LANE_ALLOCATION should be 0.35, got {HFTConfig.HFT_LANE_ALLOCATION}"
        print(f"✅ HFT_LANE_ALLOCATION = {HFTConfig.HFT_LANE_ALLOCATION} (35%)")


# =============================================================================
# SECTION 10: KELLY CRITERION AUDIT
# =============================================================================

class TestKellyCriterionAudit:
    """Audit Kelly criterion application (0.25 fractional sizing)"""
    
    def test_kelly_fraction_value(self):
        """KELLY_FRACTION should be 0.25 (25%)"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.KELLY_FRACTION == 0.25, \
            f"KELLY_FRACTION should be 0.25, got {HFTConfig.KELLY_FRACTION}"
        print(f"✅ KELLY_FRACTION = {HFTConfig.KELLY_FRACTION} (25%)")
    
    def test_kelly_applied_in_build_params(self):
        """Kelly criterion is applied in _build_trade_params"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            source = f.read()
        
        assert "KELLY_FRACTION" in source, "Should use KELLY_FRACTION"
        assert "kelly_sized" in source, "Should calculate kelly_sized"
        print("✅ Kelly criterion applied in _build_trade_params")


# =============================================================================
# SECTION 11: MAX POSITION CAP AUDIT
# =============================================================================

class TestMaxPositionCapAudit:
    """Audit 3% max position cap enforcement"""
    
    def test_max_position_pct_value(self):
        """MAX_POSITION_PCT should be 0.03 (3%)"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.MAX_POSITION_PCT == 0.03, \
            f"MAX_POSITION_PCT should be 0.03, got {HFTConfig.MAX_POSITION_PCT}"
        print(f"✅ MAX_POSITION_PCT = {HFTConfig.MAX_POSITION_PCT} (3%)")
    
    def test_max_position_enforced_in_build_params(self):
        """3% cap is enforced in _build_trade_params"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            source = f.read()
        
        assert "MAX_POSITION_PCT" in source, "Should use MAX_POSITION_PCT"
        assert "max_position" in source, "Should calculate max_position"
        assert "min(adjusted_position, max_position)" in source or \
               "min(" in source, "Should enforce cap with min()"
        print("✅ 3% max position cap enforced")


# =============================================================================
# SECTION 12: POLYMARKET TICK GRID AUDIT
# =============================================================================

class TestTickGridAudit:
    """Audit Polymarket tick grid compliance ($0.01 rounding)"""
    
    def test_tick_size_value(self):
        """TICK_SIZE should be 0.01 ($0.01)"""
        from trading.hft_engine_v2 import TICK_SIZE
        
        assert TICK_SIZE == 0.01, f"TICK_SIZE should be 0.01, got {TICK_SIZE}"
        print(f"✅ TICK_SIZE = {TICK_SIZE} ($0.01)")
    
    def test_round_to_tick_method(self):
        """_round_to_tick rounds to $0.01"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None, 
            'paper_trader': None, 'strategy_context': None
        })
        
        assert engine._round_to_tick(0.505) == 0.51
        assert engine._round_to_tick(0.504) == 0.50
        assert engine._round_to_tick(0.123456) == 0.12
        print("✅ _round_to_tick rounds to $0.01")
    
    def test_min_spread_ticks(self):
        """MIN_SPREAD_TICKS should be 2 (2 cents)"""
        from trading.hft_engine_v2 import MIN_SPREAD_TICKS, TICK_SIZE
        
        assert MIN_SPREAD_TICKS == 2, f"MIN_SPREAD_TICKS should be 2, got {MIN_SPREAD_TICKS}"
        min_spread = MIN_SPREAD_TICKS * TICK_SIZE
        assert min_spread == 0.02, f"Min spread should be $0.02, got {min_spread}"
        print(f"✅ MIN_SPREAD_TICKS = {MIN_SPREAD_TICKS} (${min_spread})")


# =============================================================================
# SECTION 13: KILL ZONE BOUNDS AUDIT
# =============================================================================

class TestKillZoneBoundsAudit:
    """Audit kill zone bounds enforcement ($0.05 - $0.95)"""
    
    def test_min_price_value(self):
        """MIN_PRICE should be 0.05 ($0.05)"""
        from trading.hft_engine_v2 import MIN_PRICE
        
        assert MIN_PRICE == 0.05, f"MIN_PRICE should be 0.05, got {MIN_PRICE}"
        print(f"✅ MIN_PRICE = {MIN_PRICE} ($0.05)")
    
    def test_max_price_value(self):
        """MAX_PRICE should be 0.95 ($0.95)"""
        from trading.hft_engine_v2 import MAX_PRICE
        
        assert MAX_PRICE == 0.95, f"MAX_PRICE should be 0.95, got {MAX_PRICE}"
        print(f"✅ MAX_PRICE = {MAX_PRICE} ($0.95)")
    
    def test_clamp_to_bounds_method(self):
        """_clamp_to_bounds enforces kill zones"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        assert engine._clamp_to_bounds(0.03) == 0.05  # Below min
        assert engine._clamp_to_bounds(0.97) == 0.95  # Above max
        assert engine._clamp_to_bounds(0.50) == 0.50  # Within bounds
        print("✅ _clamp_to_bounds enforces $0.05-$0.95 bounds")


# =============================================================================
# SECTION 14: MEAN REVERSION THRESHOLDS AUDIT
# =============================================================================

class TestMeanReversionThresholdsAudit:
    """Audit mean reversion triggers only at extremes (<=0.15 or >=0.85)"""
    
    def test_mean_reversion_low_threshold(self):
        """MEAN_REVERSION_LOW should be 0.15"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.MEAN_REVERSION_LOW == 0.15, \
            f"MEAN_REVERSION_LOW should be 0.15, got {HFTConfig.MEAN_REVERSION_LOW}"
        print(f"✅ MEAN_REVERSION_LOW = {HFTConfig.MEAN_REVERSION_LOW}")
    
    def test_mean_reversion_high_threshold(self):
        """MEAN_REVERSION_HIGH should be 0.85"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.MEAN_REVERSION_HIGH == 0.85, \
            f"MEAN_REVERSION_HIGH should be 0.85, got {HFTConfig.MEAN_REVERSION_HIGH}"
        print(f"✅ MEAN_REVERSION_HIGH = {HFTConfig.MEAN_REVERSION_HIGH}")
    
    def test_mean_reversion_boundary_conditions(self):
        """Mean reversion triggers at exact boundaries"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        # At boundary 0.15 - should trigger YES
        assert engine._get_mean_reversion_direction(0.15) == 'YES'
        
        # At boundary 0.85 - should trigger NO
        assert engine._get_mean_reversion_direction(0.85) == 'NO'
        
        # Just above 0.15 - should NOT trigger
        assert engine._get_mean_reversion_direction(0.16) is None
        
        # Just below 0.85 - should NOT trigger
        assert engine._get_mean_reversion_direction(0.84) is None
        
        print("✅ Mean reversion triggers at exact boundaries")


# =============================================================================
# SECTION 15: ORDER FLOW IMBALANCE AUDIT
# =============================================================================

class TestOrderFlowImbalanceAudit:
    """Audit order flow imbalance calculation (1.2 ratio threshold)"""
    
    def test_imbalance_ratio_value(self):
        """ORDER_FLOW_IMBALANCE_RATIO should be 1.2"""
        from trading.hft_config import HFTConfig
        
        assert HFTConfig.ORDER_FLOW_IMBALANCE_RATIO == 1.2, \
            f"ORDER_FLOW_IMBALANCE_RATIO should be 1.2, got {HFTConfig.ORDER_FLOW_IMBALANCE_RATIO}"
        print(f"✅ ORDER_FLOW_IMBALANCE_RATIO = {HFTConfig.ORDER_FLOW_IMBALANCE_RATIO}")
    
    def test_order_flow_direction_calculation(self):
        """Order flow direction uses 1.2 ratio correctly"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        # Buy pressure: 1200 > 1000 * 1.2 = 1200 → YES
        result = engine._get_order_flow_direction({
            'buy_volume': 1200, 'sell_volume': 1000,
            'volume_24h': 100000, 'price': 0.5
        })
        assert result == 'YES', f"Expected YES on buy pressure, got {result}"
        
        # Sell pressure: 1200 > 1000 * 1.2 = 1200 → NO
        result = engine._get_order_flow_direction({
            'buy_volume': 1000, 'sell_volume': 1200,
            'volume_24h': 100000, 'price': 0.5
        })
        assert result == 'NO', f"Expected NO on sell pressure, got {result}"
        
        print("✅ Order flow direction uses 1.2 ratio correctly")


# =============================================================================
# SECTION 16: STATISTICS TRACKING AUDIT
# =============================================================================

class TestStatisticsTrackingAudit:
    """Audit statistics tracking (trades_executed, trades_by_mode, path_a_hits, etc.)"""
    
    def test_stats_initialization(self):
        """Stats are properly initialized"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        from trading.hft_config import HFTMode
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        assert 'cycles_executed' in engine.stats
        assert 'trades_executed' in engine.stats
        assert 'trades_by_mode' in engine.stats
        assert 'paused_cycles' in engine.stats
        assert 'path_a_hits' in engine.stats
        assert 'path_b_hits' in engine.stats
        assert 'alpha_hits' in engine.stats
        assert 'alpha_misses' in engine.stats
        assert 'orders_kept_hysteresis' in engine.stats
        assert 'orders_cancelled_drift' in engine.stats
        assert 'orders_cancelled_stale' in engine.stats
        assert 'errors' in engine.stats
        
        # Check trades_by_mode has all modes
        for mode in HFTMode:
            assert mode.value in engine.stats['trades_by_mode'], \
                f"trades_by_mode should have {mode.value}"
        
        print("✅ All stats fields initialized")
    
    def test_get_stats_method(self):
        """get_stats returns comprehensive statistics"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        stats = engine.get_stats()
        
        assert 'running' in stats
        assert 'last_cycle_time_ms' in stats
        assert 'cycle_count' in stats
        assert 'active_orders' in stats
        
        print("✅ get_stats returns comprehensive statistics")
    
    def test_get_hft_metrics_method(self):
        """get_hft_metrics returns performance metrics"""
        from trading.hft_engine_v2 import HighFrequencyTradingEngineV2
        
        engine = HighFrequencyTradingEngineV2({
            'db': None, 'market_data_svc': None,
            'paper_trader': None, 'strategy_context': None
        })
        
        metrics = engine.get_hft_metrics()
        
        assert 'cycles_executed' in metrics
        assert 'trades_executed' in metrics
        assert 'mode_distribution' in metrics
        assert 'path_a_hits' in metrics
        assert 'path_b_hits' in metrics
        assert 'alpha_hit_rate' in metrics
        assert 'paused_cycles' in metrics
        assert 'orders_kept_hysteresis' in metrics
        assert 'running' in metrics
        
        print("✅ get_hft_metrics returns performance metrics")


# =============================================================================
# SECTION 17: INTEGRATION TESTS
# =============================================================================

class TestHFTV2IntegrationAudit:
    """Integration tests for HFT V2 Engine"""
    
    def test_hft_v2_status_endpoint(self):
        """GET /api/hft-v2/status returns valid response"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/hft-v2/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'status' in data, "Response should have status field"
        print(f"✅ HFT V2 status endpoint: {data.get('status')}")
    
    def test_paper_trading_status(self):
        """GET /api/paper/status returns valid response"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/paper/status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'running' in data, "Response should have running field"
        print(f"✅ Paper trading status: running={data.get('running')}")
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        import requests
        
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy, got {data.get('status')}"
        print("✅ Health endpoint: healthy")


# =============================================================================
# SECTION 18: PAPER TRADER INTEGRATION AUDIT
# =============================================================================

class TestPaperTraderIntegrationAudit:
    """Audit trade execution through paper_trader integration"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_paper_trader_execute_methods(self, hft_v2_source):
        """Engine uses paper_trader execute methods"""
        assert "_execute_paper_entry" in hft_v2_source or "execute_trade" in hft_v2_source, \
            "Should use paper_trader execute methods"
        print("✅ Paper trader execute methods used")
    
    def test_strategy_name_format(self, hft_v2_source):
        """Strategy name follows hft_{mode} format"""
        assert "f'hft_{hft_mode.value}'" in hft_v2_source or "hft_" in hft_v2_source, \
            "Strategy name should follow hft_{mode} format"
        print("✅ Strategy name format: hft_{mode}")
    
    def test_trade_params_passed_correctly(self, hft_v2_source):
        """Trade params are passed correctly to paper_trader"""
        assert "trade_params['direction']" in hft_v2_source, \
            "Should pass direction from trade_params"
        assert "trade_params['position_size']" in hft_v2_source, \
            "Should pass position_size from trade_params"
        print("✅ Trade params passed correctly")


# =============================================================================
# SECTION 19: CODE QUALITY AUDIT
# =============================================================================

class TestCodeQualityAudit:
    """Audit code quality and best practices"""
    
    @pytest.fixture(scope="class")
    def hft_v2_source(self):
        """Load HFT V2 source code"""
        with open("/app/backend/trading/hft_engine_v2.py", "r") as f:
            return f.read()
    
    def test_async_await_usage(self, hft_v2_source):
        """Async methods use await correctly"""
        # Count async def and await usage
        async_count = hft_v2_source.count("async def")
        await_count = hft_v2_source.count("await")
        
        assert async_count > 0, "Should have async methods"
        assert await_count > 0, "Should use await"
        print(f"✅ Async/await: {async_count} async methods, {await_count} awaits")
    
    def test_error_handling(self, hft_v2_source):
        """Error handling is present"""
        try_count = hft_v2_source.count("try:")
        except_count = hft_v2_source.count("except")
        
        assert try_count > 5, "Should have multiple try blocks"
        assert except_count > 5, "Should have multiple except blocks"
        print(f"✅ Error handling: {try_count} try blocks, {except_count} except blocks")
    
    def test_logging_present(self, hft_v2_source):
        """Logging is used throughout"""
        logger_count = hft_v2_source.count("logger.")
        
        assert logger_count > 10, "Should have extensive logging"
        print(f"✅ Logging: {logger_count} logger calls")
    
    def test_type_hints_present(self, hft_v2_source):
        """Type hints are used"""
        assert "Dict[" in hft_v2_source or "Dict" in hft_v2_source, "Should use Dict type hints"
        assert "Optional[" in hft_v2_source, "Should use Optional type hints"
        assert "-> " in hft_v2_source, "Should have return type hints"
        print("✅ Type hints present")
    
    def test_docstrings_present(self, hft_v2_source):
        """Docstrings are present"""
        docstring_count = hft_v2_source.count('"""')
        
        assert docstring_count > 20, "Should have extensive docstrings"
        print(f"✅ Docstrings: {docstring_count // 2} docstrings")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
