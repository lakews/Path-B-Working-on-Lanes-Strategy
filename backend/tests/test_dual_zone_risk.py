"""
Task 21: Dual-Zone Risk Architecture Tests
==========================================

Tests to verify the centralized risk_config.py is working correctly
and all market classification logic handles both zones properly.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from risk_config import (
    RISK, 
    MarketRegime, 
    classify_market_regime,
    get_zone_parameters,
    is_spread_acceptable
)


class TestRiskConfigConstants:
    """Test that all risk constants are properly defined."""
    
    def test_global_safety_parameters(self):
        """Verify global safety parameters exist and are sensible."""
        assert RISK.STOP_LOSS_PCT == 0.15  # 15%
        assert RISK.MAX_DRAWDOWN_PCT == 5.0  # 5%
        assert RISK.KILL_SWITCH_LOW == 0.03  # 3 cents
        assert RISK.KILL_SWITCH_HIGH == 0.97  # 97 cents
    
    def test_whale_zone_parameters(self):
        """Verify Whale Zone parameters for convexity trading."""
        assert RISK.WHALE_PRICE_CEILING == 0.10  # $0.10
        assert RISK.WHALE_MAX_SPREAD_CENTS == 0.03  # 3 cents
        assert RISK.WHALE_MIN_LIQUIDITY == 500.0  # $500
        assert RISK.WHALE_MIN_VOLUME_24H == 500.0  # $500
        assert RISK.WHALE_MAX_POSITION == 15.0  # $15
        assert RISK.WHALE_MAX_POSITION_PCT == 1.0  # 1%
    
    def test_core_zone_parameters(self):
        """Verify Core Alpha Zone parameters."""
        assert RISK.CORE_TAKER_SPREAD_PCT == 0.02  # 2%
        assert RISK.CORE_MAKER_SPREAD_PCT == 0.10  # 10%
        assert RISK.CORE_ZOMBIE_SPREAD_PCT == 0.12  # 12%
        assert RISK.CORE_MIN_LIQUIDITY == 1000.0  # $1K
        assert RISK.CORE_MIN_VOLUME_24H == 1000.0  # $1K
        assert RISK.CORE_MAX_POSITION == 100.0  # $100
        assert RISK.CORE_MAX_POSITION_PCT == 3.0  # 3%
    
    def test_fee_structure(self):
        """Verify fee structure is correct."""
        assert RISK.TAKER_FEE == 0.02  # 2%
        assert RISK.MAKER_FEE == 0.00  # 0%
        assert RISK.ADVERSE_SELECTION_COST == 0.005  # 0.5%


class TestMarketRegimeClassification:
    """Test the classify_market_regime function."""
    
    # =========================================================================
    # KILL SWITCH TESTS
    # =========================================================================
    
    def test_kill_switch_extreme_low(self):
        """Price below 3 cents should be ZOMBIE."""
        regime, diag = classify_market_regime(
            best_bid=0.01, 
            best_ask=0.02, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'kill switch' in diag.get('reject_reason', '').lower()
    
    def test_kill_switch_extreme_high(self):
        """Price above 97 cents should be ZOMBIE."""
        regime, diag = classify_market_regime(
            best_bid=0.98, 
            best_ask=0.99, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'kill switch' in diag.get('reject_reason', '').lower()
    
    # =========================================================================
    # WHALE ZONE TESTS (Price < $0.10)
    # =========================================================================
    
    def test_whale_zone_convexity_opportunity(self):
        """Cheap asset with tight tick spread = CONVEXITY_OPPORTUNITY."""
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
    
    def test_whale_zone_wide_tick_spread(self):
        """Cheap asset with wide tick spread = ZOMBIE (too risky)."""
        # Price: $0.05, Spread: 5 cents (too wide)
        regime, diag = classify_market_regime(
            best_bid=0.02, 
            best_ask=0.07, 
            volume_24h=1000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'tick spread' in diag.get('reject_reason', '').lower()
    
    def test_whale_zone_low_volume(self):
        """Cheap asset with low volume = ZOMBIE."""
        regime, diag = classify_market_regime(
            best_bid=0.04, 
            best_ask=0.05, 
            volume_24h=100.0  # Below $500 minimum
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'volume' in diag.get('reject_reason', '').lower()
    
    # =========================================================================
    # CORE ZONE TESTS (Price >= $0.10)
    # =========================================================================
    
    def test_core_zone_taker_tight(self):
        """Standard asset with tight % spread = TAKER_TIGHT (< 2%)."""
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
        # Price: $0.50, Spread: 15% (dead)
        regime, diag = classify_market_regime(
            best_bid=0.4625, 
            best_ask=0.5375, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'spread' in diag.get('reject_reason', '').lower()
    
    def test_core_zone_boundary_taker_maker(self):
        """Exactly 2% spread should be MAKER_WIDE (boundary case)."""
        # Price: $0.50, Spread: 2% exactly
        regime, diag = classify_market_regime(
            best_bid=0.495, 
            best_ask=0.505, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.MAKER_WIDE  # 2% is >= threshold
    
    def test_core_zone_boundary_maker_zombie(self):
        """Exactly 12% spread should be MAKER_WIDE (boundary case)."""
        # Price: $0.50, Spread: 12% exactly
        regime, diag = classify_market_regime(
            best_bid=0.47, 
            best_ask=0.53, 
            volume_24h=5000.0
        )
        assert regime == MarketRegime.MAKER_WIDE  # 12% is NOT > zombie threshold
    
    def test_core_zone_low_volume(self):
        """Standard asset with low volume = ZOMBIE."""
        regime, diag = classify_market_regime(
            best_bid=0.495, 
            best_ask=0.505, 
            volume_24h=500.0  # Below $1K minimum for core zone
        )
        assert regime == MarketRegime.ZOMBIE
        assert 'volume' in diag.get('reject_reason', '').lower()
    
    # =========================================================================
    # BOUNDARY TESTS
    # =========================================================================
    
    def test_boundary_at_whale_ceiling(self):
        """Price exactly at $0.10 should be CORE zone."""
        regime, diag = classify_market_regime(
            best_bid=0.099, 
            best_ask=0.101, 
            volume_24h=2000.0
        )
        # Mid price = 0.10, so it's exactly at the boundary
        assert diag['zone'] == 'CORE'
    
    def test_boundary_just_below_whale_ceiling(self):
        """Price just below $0.10 should be WHALE zone."""
        regime, diag = classify_market_regime(
            best_bid=0.089, 
            best_ask=0.099, 
            volume_24h=1000.0
        )
        assert diag['zone'] == 'WHALE'


class TestZoneParameters:
    """Test the get_zone_parameters helper function."""
    
    def test_whale_zone_parameters(self):
        """Low price should return Whale zone parameters."""
        params = get_zone_parameters(mid_price=0.05)
        assert params['zone'] == 'WHALE'
        assert params['spread_type'] == 'absolute_cents'
        assert params['max_spread'] == RISK.WHALE_MAX_SPREAD_CENTS
        assert params['max_position'] == RISK.WHALE_MAX_POSITION
    
    def test_core_zone_parameters(self):
        """Higher price should return Core zone parameters."""
        params = get_zone_parameters(mid_price=0.50)
        assert params['zone'] == 'CORE'
        assert params['spread_type'] == 'percentage'
        assert params['max_spread'] == RISK.CORE_MAKER_SPREAD_PCT
        assert params['max_position'] == RISK.CORE_MAX_POSITION


class TestSpreadAcceptability:
    """Test the is_spread_acceptable helper function."""
    
    def test_whale_zone_tight_spread_acceptable(self):
        """Tight tick spread in whale zone should be acceptable."""
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.02,  # 2 cents (within 3 cent limit)
            spread_pct=0.40,    # 40% (ignored in whale zone)
            mid_price=0.05
        )
        assert acceptable is True
        assert 'whale_zone' in reason.lower()
    
    def test_whale_zone_wide_spread_rejected(self):
        """Wide tick spread in whale zone should be rejected."""
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.05,  # 5 cents (exceeds 3 cent limit)
            spread_pct=1.0,     # 100% (ignored in whale zone)
            mid_price=0.05
        )
        assert acceptable is False
        assert 'whale_zone' in reason.lower()
    
    def test_core_zone_tight_spread_acceptable(self):
        """Tight % spread in core zone should be acceptable."""
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.01,
            spread_pct=0.02,  # 2% (within limit)
            mid_price=0.50
        )
        assert acceptable is True
        assert 'core_zone' in reason.lower()
    
    def test_core_zone_wide_spread_hft_acceptable(self):
        """Wide % spread should be acceptable for HFT (maker)."""
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.06,
            spread_pct=0.12,  # 12% (at zombie threshold)
            mid_price=0.50,
            is_hft=True
        )
        assert acceptable is True  # HFT has higher tolerance
    
    def test_core_zone_wide_spread_alpha_rejected(self):
        """Wide % spread should be rejected for Alpha (taker)."""
        acceptable, reason = is_spread_acceptable(
            spread_cents=0.06,
            spread_pct=0.12,  # 12% (exceeds 10% maker limit)
            mid_price=0.50,
            is_hft=False
        )
        assert acceptable is False


class TestMarketRegimeEnum:
    """Test MarketRegime enum values."""
    
    def test_regime_values(self):
        """Verify all regime values are correct strings."""
        assert MarketRegime.CONVEXITY_OPPORTUNITY == "CONVEXITY_OPPORTUNITY"
        assert MarketRegime.TAKER_TIGHT == "TAKER_TIGHT"
        assert MarketRegime.MAKER_WIDE == "MAKER_WIDE"
        assert MarketRegime.ZOMBIE == "ZOMBIE"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
