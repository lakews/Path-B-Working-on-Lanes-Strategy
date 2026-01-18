"""
Unit tests for the Polymarket Position Sizer.

Tests cover:
- Binary Kelly Criterion calculation
- Utilization Brake
- Time/Duration Penalty
- Oracle Risk Multiplier  
- Correlation Dampening
- Liquidity Caps
- Sector Caps
- Full end-to-end sizing
"""

import pytest
from datetime import datetime, timezone, timedelta

# Import the sizer
import sys
sys.path.insert(0, '/app/backend')
from ml.polymarket_position_sizer import PolymarketPositionSizer
from ml.market_classifier import classify_market, get_oracle_risk_multiplier, AMBIGUITY_MATRIX, get_default_ambiguity_matrix


@pytest.fixture
def sizer():
    """Create a fresh sizer instance for each test."""
    return PolymarketPositionSizer()


@pytest.fixture
def sample_order_book():
    """Sample order book with asks."""
    return [
        {"price": 0.45, "size": 5000},
        {"price": 0.46, "size": 3000},
        {"price": 0.47, "size": 2000},
    ]


class TestBinaryKellyCalculation:
    """Tests for Binary Kelly Criterion."""
    
    def test_kelly_positive_edge(self, sizer):
        """Kelly should be positive when edge is positive."""
        edge = 0.10
        effective_price = 0.45
        
        kelly = sizer._calculate_binary_kelly(edge, effective_price)
        expected = edge / (1 - effective_price)
        
        assert kelly > 0
        assert abs(kelly - expected) < 0.01
    
    def test_kelly_zero_edge(self, sizer):
        """Kelly should be zero when edge is zero."""
        kelly = sizer._calculate_binary_kelly(0.0, 0.45)
        assert kelly == 0.0
    
    def test_kelly_negative_edge(self, sizer):
        """Kelly should be zero when edge is negative."""
        kelly = sizer._calculate_binary_kelly(-0.05, 0.45)
        assert kelly == 0.0


class TestEffectivePrice:
    """Tests for fee-adjusted effective price."""
    
    def test_effective_price_with_default_fee(self, sizer):
        """Effective price includes 2% exit fee by default."""
        ask_price = 0.50
        effective = sizer._calculate_effective_price(ask_price)
        expected = 0.50 * 1.02  # 2% fee
        assert abs(effective - expected) < 0.001
    
    def test_effective_price_zero(self, sizer):
        """Zero ask price."""
        effective = sizer._calculate_effective_price(0.0)
        assert effective == 0.0


class TestUtilizationBrake:
    """Tests for utilization-based position reduction."""
    
    def test_zero_utilization_full_size(self, sizer):
        """At 0% utilization, multiplier = 1.0."""
        mult = sizer._calculate_utilization_brake(0.0)
        assert mult == 1.0
    
    def test_full_utilization_zero_size(self, sizer):
        """At 100% utilization, multiplier = 0."""
        mult = sizer._calculate_utilization_brake(1.0)
        assert mult == 0.0
    
    def test_half_utilization(self, sizer):
        """At 50% utilization, mult = (1-0.5)^2 = 0.25."""
        mult = sizer._calculate_utilization_brake(0.5)
        # Allow small tolerance
        assert 0.20 < mult < 0.30


class TestTimePenalty:
    """Tests for time-to-expiry penalties."""
    
    def test_far_expiry_minimal_penalty(self, sizer):
        """30+ days = minimal penalty."""
        penalty = sizer._calculate_time_penalty(30.0)
        assert penalty >= 0.9
    
    def test_short_expiry_high_penalty(self, sizer):
        """<1 day = high penalty."""
        penalty = sizer._calculate_time_penalty(0.5)
        assert penalty < 0.6
    
    def test_none_expiry_no_penalty(self, sizer):
        """None = no penalty."""
        penalty = sizer._calculate_time_penalty(None)
        assert penalty == 1.0


class TestOracleRiskMultiplier:
    """Tests for the Oracle/Ambiguity Matrix."""
    
    def test_sports_low_risk(self):
        """Sports = 1.0 (binary, clear resolution)."""
        assert AMBIGUITY_MATRIX['sports'] == 1.0
    
    def test_crypto_low_risk(self):
        """Crypto = 1.0 (oracle-resolvable)."""
        assert AMBIGUITY_MATRIX['crypto'] == 1.0
    
    def test_conflict_high_risk(self):
        """Conflict = 0.4 (vague definitions)."""
        assert AMBIGUITY_MATRIX['conflict'] == 0.4
    
    def test_social_high_risk(self):
        """Social = 0.5 (linguistic ambiguity)."""
        assert AMBIGUITY_MATRIX['social'] == 0.5
    
    def test_unknown_conservative(self):
        """Unknown = 0.6 (conservative default)."""
        assert AMBIGUITY_MATRIX['unknown'] == 0.6
    
    def test_classify_market_function(self):
        """Test market classifier returns expected fields."""
        result = classify_market({
            'question': 'Lakers win NBA Finals?',
            'category': 'sports'
        })
        
        assert 'category' in result
        assert 'oracle_multiplier' in result
        assert result['oracle_multiplier'] == 1.0
    
    def test_get_oracle_risk_multiplier(self):
        """Test oracle risk multiplier function."""
        mult = get_oracle_risk_multiplier('sports', 'Lakers win?', None)
        assert mult == 1.0
        
        mult = get_oracle_risk_multiplier('conflict', 'Ceasefire?', None)
        assert mult <= 0.5


class TestDefaultAmbiguityMatrix:
    """Tests for configurable oracle multipliers."""
    
    def test_get_defaults(self):
        """Default matrix should have all expected categories."""
        defaults = get_default_ambiguity_matrix()
        
        assert 'sports' in defaults
        assert 'crypto' in defaults
        assert 'finance' in defaults
        assert 'conflict' in defaults
        assert 'unknown' in defaults
    
    def test_defaults_in_valid_range(self):
        """All multipliers should be 0-1."""
        defaults = get_default_ambiguity_matrix()
        
        for cat, mult in defaults.items():
            assert 0.0 <= mult <= 1.0, f"{cat} multiplier {mult} out of range"


class TestNoTradeResult:
    """Tests for no-trade result structure."""
    
    def test_no_trade_has_should_trade_false(self, sizer):
        """No-trade result has should_trade = False."""
        result = sizer._no_trade_result("test_reason", "test_detail")
        assert result['should_trade'] == False
    
    def test_no_trade_has_breakdown(self, sizer):
        """No-trade result has sizing_breakdown."""
        result = sizer._no_trade_result("test_reason", "test_detail")
        assert 'sizing_breakdown' in result


class TestFullSizingPipeline:
    """Integration tests for full sizing calculation."""
    
    def test_positive_edge_returns_trade(self, sizer, sample_order_book):
        """Positive edge should return a trade."""
        result = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        assert result['should_trade'] == True
        assert result['position_size'] > 0
        assert 'breakdown' in result
    
    def test_negative_edge_no_trade(self, sizer, sample_order_book):
        """Negative edge should return no trade."""
        result = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.40,  # < 0.45 ask = negative edge
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        assert result['should_trade'] == False
    
    def test_high_utilization_reduces_size(self, sizer, sample_order_book):
        """High utilization should reduce position size."""
        # First, get size with low utilization
        result_low = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        # Then with high utilization
        result_high = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=8000,  # 80% utilized
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        if result_high['should_trade'] and result_low['should_trade']:
            assert result_high['position_size'] < result_low['position_size']
    
    def test_conflict_category_reduces_size(self, sizer, sample_order_book):
        """Conflict category should reduce size due to oracle risk."""
        result_finance = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        result_conflict = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='conflict',
            market_age_hours=100,
            market_question='Ceasefire in war?',
            open_positions=[]
        )
        
        if result_conflict['should_trade'] and result_finance['should_trade']:
            assert result_conflict['position_size'] < result_finance['position_size']
    
    def test_short_expiry_reduces_size(self, sizer, sample_order_book):
        """Short expiry should reduce position size."""
        result_long = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        result_short = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=1.0,  # 1 day
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        if result_short['should_trade'] and result_long['should_trade']:
            assert result_short['position_size'] < result_long['position_size']
    
    def test_breakdown_contains_expected_fields(self, sizer, sample_order_book):
        """Breakdown should contain all sizing factors."""
        result = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        if result['should_trade']:
            breakdown = result['breakdown']
            assert 'kelly_base' in breakdown
            assert 'utilization_mult' in breakdown
            assert 'oracle_mult' in breakdown
            assert 'time_penalty' in breakdown
            assert 'final_size' in breakdown


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_zero_equity(self, sizer, sample_order_book):
        """Zero equity should handle gracefully."""
        result = sizer.calculate_position_size(
            equity=0,
            deployed_capital=0,
            model_probability=0.55,
            ask_price=0.45,
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        # Should not crash, either no trade or tiny size
        assert 'should_trade' in result
    
    def test_extreme_edge(self, sizer, sample_order_book):
        """Very high edge should cap Kelly."""
        result = sizer.calculate_position_size(
            equity=10000,
            deployed_capital=0,
            model_probability=0.95,  # Very high probability
            ask_price=0.30,          # Low price = huge edge
            order_book_asks=sample_order_book,
            days_to_expiry=30.0,
            market_category='finance',
            market_age_hours=100,
            market_question='Fed cuts rates?',
            open_positions=[]
        )
        
        if result['should_trade']:
            # Should be capped at some reasonable max
            assert result['position_size'] < 5000  # Less than 50% of equity


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
