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
- Edge cases and boundary conditions
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

# Import the sizer
import sys
sys.path.insert(0, '/app/backend')
from ml.polymarket_position_sizer import PolymarketPositionSizer
from ml.market_classifier import classify_market, get_oracle_risk_multiplier, AMBIGUITY_MATRIX


@pytest.fixture
def sizer():
    """Create a fresh sizer instance for each test."""
    return PolymarketPositionSizer()


@pytest.fixture
def sample_market():
    """Sample market data for tests."""
    return {
        'question': 'Will the Fed cut rates in March 2026?',
        'condition_id': 'test_market_123',
        'tokens': [
            {'outcome': 'Yes', 'price': 0.45},
            {'outcome': 'No', 'price': 0.55}
        ],
        'category': 'finance',
        'end_date_iso': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        'volume_24h': 50000,
        'liquidity': 100000
    }


class TestBinaryKellyCalculation:
    """Tests for Binary Kelly Criterion."""
    
    def test_kelly_positive_edge(self, sizer):
        """Kelly should be positive when edge is positive."""
        edge = 0.10  # 10% edge
        effective_price = 0.45
        
        kelly = sizer._calculate_binary_kelly(edge, effective_price)
        
        # Binary Kelly = edge / (1 - effective_price)
        expected = edge / (1 - effective_price)  # 0.10 / 0.55 = 0.182
        
        assert kelly > 0, "Kelly should be positive"
        assert abs(kelly - expected) < 0.01, "Kelly calculation mismatch"
    
    def test_kelly_zero_edge(self, sizer):
        """Kelly should be zero when edge is zero."""
        edge = 0.0
        effective_price = 0.45
        
        kelly = sizer._calculate_binary_kelly(edge, effective_price)
        assert kelly == 0.0
    
    def test_kelly_negative_edge(self, sizer):
        """Kelly should be zero when edge is negative."""
        edge = -0.05
        effective_price = 0.45
        
        kelly = sizer._calculate_binary_kelly(edge, effective_price)
        assert kelly == 0.0
    
    def test_kelly_high_effective_price(self, sizer):
        """Kelly with high effective price (near 1)."""
        edge = 0.05
        effective_price = 0.95
        
        kelly = sizer._calculate_binary_kelly(edge, effective_price)
        # edge / (1 - 0.95) = 0.05 / 0.05 = 1.0
        assert kelly == 1.0


class TestEffectivePrice:
    """Tests for fee-adjusted effective price."""
    
    def test_effective_price_with_fee(self, sizer):
        """Effective price should include exit fee."""
        ask_price = 0.50
        
        effective = sizer._calculate_effective_price(ask_price)
        
        # Default fee is 2%, so effective = 0.50 * 1.02 = 0.51
        expected = ask_price * (1 + sizer.config.get('polymarket_fee_pct', 0.02))
        assert abs(effective - expected) < 0.001
    
    def test_effective_price_zero(self, sizer):
        """Effective price of zero."""
        effective = sizer._calculate_effective_price(0.0)
        assert effective == 0.0


class TestUtilizationBrake:
    """Tests for utilization-based position reduction."""
    
    def test_zero_utilization(self, sizer):
        """At 0% utilization, multiplier should be 1.0 (full size)."""
        mult = sizer._calculate_utilization_brake(0.0)
        assert mult == 1.0
    
    def test_fifty_percent_utilization(self, sizer):
        """At 50% utilization, multiplier should be 0.25."""
        mult = sizer._calculate_utilization_brake(0.50)
        # Formula: (1 - 0.5)^2 = 0.25
        assert abs(mult - 0.25) < 0.01
    
    def test_eighty_percent_utilization(self, sizer):
        """At 80% utilization, multiplier should be very low."""
        mult = sizer._calculate_utilization_brake(0.80)
        # (1 - 0.8)^2 = 0.04
        assert abs(mult - 0.04) < 0.01
    
    def test_ninety_percent_utilization(self, sizer):
        """At 90% utilization, multiplier should be near zero."""
        mult = sizer._calculate_utilization_brake(0.90)
        # (1 - 0.9)^2 = 0.01
        assert mult < 0.02
    
    def test_full_utilization(self, sizer):
        """At 100% utilization, multiplier should be 0."""
        mult = sizer._calculate_utilization_brake(1.0)
        assert mult == 0.0
    
    def test_over_utilization(self, sizer):
        """Above 100% utilization (edge case)."""
        mult = sizer._calculate_utilization_brake(1.2)
        # Should clamp or handle gracefully
        assert mult >= 0.0


class TestTimePenalty:
    """Tests for time-to-expiry based penalties."""
    
    def test_no_expiry(self, sizer):
        """No penalty if no expiry (None)."""
        penalty = sizer._calculate_time_penalty(None)
        assert penalty == 1.0
    
    def test_far_expiry_30_days(self, sizer):
        """Minimal penalty for 30+ days to expiry."""
        penalty = sizer._calculate_time_penalty(30.0)
        assert penalty > 0.95
    
    def test_two_weeks_expiry(self, sizer):
        """Some penalty for ~14 days."""
        penalty = sizer._calculate_time_penalty(14.0)
        assert 0.8 < penalty <= 1.0
    
    def test_one_week_expiry(self, sizer):
        """Moderate penalty for 7 days."""
        penalty = sizer._calculate_time_penalty(7.0)
        assert 0.7 < penalty < 0.95
    
    def test_three_days_expiry(self, sizer):
        """Higher penalty for 3 days."""
        penalty = sizer._calculate_time_penalty(3.0)
        assert 0.5 < penalty < 0.85
    
    def test_one_day_expiry(self, sizer):
        """Heavy penalty for <24h."""
        penalty = sizer._calculate_time_penalty(1.0)
        assert penalty < 0.7
    
    def test_hours_to_expiry(self, sizer):
        """Very heavy penalty for hours to expiry."""
        penalty = sizer._calculate_time_penalty(0.25)  # 6 hours
        assert penalty < 0.5
    
    def test_zero_days(self, sizer):
        """Near-zero days should give minimum penalty."""
        penalty = sizer._calculate_time_penalty(0.01)
        assert penalty > 0  # Should not be zero, minimum floor


class TestOracleRiskMultiplier:
    """Tests for Oracle/Ambiguity Matrix multipliers using market_classifier."""
    
    def test_sports_market_low_risk(self):
        """Sports markets should have multiplier = 1.0."""
        assert AMBIGUITY_MATRIX['sports'] == 1.0
    
    def test_crypto_market_low_risk(self):
        """Crypto markets should have multiplier = 1.0."""
        assert AMBIGUITY_MATRIX['crypto'] == 1.0
    
    def test_finance_market(self):
        """Finance markets should have multiplier = 0.95."""
        assert AMBIGUITY_MATRIX['finance'] == 0.95
    
    def test_conflict_high_risk(self):
        """Conflict markets should have low multiplier."""
        assert AMBIGUITY_MATRIX['conflict'] <= 0.5
    
    def test_social_high_risk(self):
        """Social/tweet markets should have low multiplier."""
        assert AMBIGUITY_MATRIX['social'] <= 0.5
    
    def test_unknown_category(self):
        """Unknown category should have conservative default."""
        assert AMBIGUITY_MATRIX['unknown'] == 0.60
    
    def test_classify_sports_market(self):
        """Test market classification for sports."""
        result = classify_market({'question': 'Lakers win NBA Finals?', 'category': 'sports'})
        assert result['category'] == 'sports'
        assert result['oracle_multiplier'] == 1.0
    
    def test_classify_conflict_market(self):
        """Test market classification for conflict."""
        result = classify_market({'question': 'Ceasefire in Ukraine?', 'category': 'conflict'})
        assert result['category'] == 'conflict'
        assert result['oracle_multiplier'] <= 0.5


class TestCorrelationDampening:
    """Tests for correlation-based position limits."""
    
    def test_no_positions(self, sizer, sample_market):
        """Full size with no existing positions."""
        mult, count = sizer._calculate_correlation_dampener(sample_market, [])
        assert mult == 1.0
        assert count == 0
    
    def test_one_same_category(self, sizer, sample_market):
        """Reduced size with 1 position in same category."""
        open_positions = [{'category': 'finance', 'market_question': 'Other Fed market'}]
        sample_market['category'] = 'finance'
        
        mult, count = sizer._calculate_correlation_dampener(sample_market, open_positions)
        assert mult < 1.0
        assert count == 1
    
    def test_different_category(self, sizer, sample_market):
        """No reduction for different category."""
        open_positions = [{'category': 'sports', 'market_question': 'Lakers game'}]
        sample_market['category'] = 'finance'
        
        mult, count = sizer._calculate_correlation_dampener(sample_market, open_positions)
        assert mult == 1.0
        assert count == 0
    
    def test_multiple_correlated(self, sizer, sample_market):
        """Heavy reduction with many same-category positions."""
        open_positions = [
            {'category': 'finance', 'market_question': 'Fed March'},
            {'category': 'finance', 'market_question': 'Fed June'},
            {'category': 'finance', 'market_question': 'CPI report'},
        ]
        sample_market['category'] = 'finance'
        
        mult, count = sizer._calculate_correlation_dampener(sample_market, open_positions)
        assert mult < 0.7
        assert count == 3


class TestLiquidityCap:
    """Tests for liquidity-based position caps."""
    
    def test_high_liquidity_no_cap(self, sizer):
        """High liquidity should not cap small position."""
        cap = sizer._calculate_liquidity_cap(
            kelly_adjusted=500,
            liquidity=100000,
            volume_24h=50000
        )
        assert cap >= 500  # No cap needed
    
    def test_low_liquidity_capped(self, sizer):
        """Low liquidity should cap position."""
        cap = sizer._calculate_liquidity_cap(
            kelly_adjusted=5000,
            liquidity=10000,
            volume_24h=5000
        )
        assert cap < 5000  # Should be capped


class TestSectorCap:
    """Tests for sector-based portfolio caps."""
    
    def test_under_sector_limit(self, sizer):
        """Position allowed when under sector limit."""
        cap = sizer._calculate_sector_cap(
            size_before=500,
            category='crypto',
            equity=10000,
            open_positions=[]
        )
        # Default crypto cap is 20% = $2000
        assert cap >= 500
    
    def test_at_sector_limit(self, sizer):
        """Position reduced when approaching sector limit."""
        # Already have $1800 in crypto, cap is $2000
        open_positions = [
            {'category': 'crypto', 'size': 900},
            {'category': 'crypto', 'size': 900},
        ]
        cap = sizer._calculate_sector_cap(
            size_before=500,
            category='crypto',
            equity=10000,
            open_positions=open_positions
        )
        # Only $200 room left
        assert cap <= 200


class TestNoTradeResult:
    """Tests for no-trade result generation."""
    
    def test_no_trade_structure(self, sizer):
        """No-trade result should have correct structure."""
        result = sizer._no_trade_result("test_reason", "test_detail")
        
        assert result['should_trade'] == False
        assert result['final_size'] == 0
        assert 'sizing_breakdown' in result
        assert result['sizing_breakdown']['rejection_reason'] == "test_reason"


class TestFullSizingPipeline:
    """Integration tests for the full sizing calculation."""
    
    def test_positive_edge_trade(self, sizer, sample_market):
        """Should calculate size for positive edge trade."""
        result = sizer.calculate_position_size(
            market_question=sample_market['question'],
            model_probability=0.55,
            ask_price=0.45,
            trade_side='YES',
            equity=10000,
            deployed=0,
            category='finance',
            end_date_iso=sample_market['end_date_iso'],
            liquidity=sample_market['liquidity'],
            volume_24h=sample_market['volume_24h'],
            open_positions=[]
        )
        
        assert result['should_trade'] == True
        assert result['final_size'] > 0
        assert result['edge'] > 0
    
    def test_negative_edge_no_trade(self, sizer, sample_market):
        """Should not trade with negative edge."""
        result = sizer.calculate_position_size(
            market_question=sample_market['question'],
            model_probability=0.40,  # Model says 40%
            ask_price=0.45,          # Market at 45% - negative edge
            trade_side='YES',
            equity=10000,
            deployed=0,
            category='finance',
            end_date_iso=sample_market['end_date_iso'],
            liquidity=sample_market['liquidity'],
            volume_24h=sample_market['volume_24h'],
            open_positions=[]
        )
        
        assert result['should_trade'] == False
    
    def test_high_utilization_small_size(self, sizer, sample_market):
        """Should reduce size when utilization is high."""
        result = sizer.calculate_position_size(
            market_question=sample_market['question'],
            model_probability=0.55,
            ask_price=0.45,
            trade_side='YES',
            equity=10000,
            deployed=8000,  # 80% utilized
            category='finance',
            end_date_iso=sample_market['end_date_iso'],
            liquidity=sample_market['liquidity'],
            volume_24h=sample_market['volume_24h'],
            open_positions=[]
        )
        
        if result['should_trade']:
            # Should be heavily reduced due to utilization brake
            assert result['sizing_breakdown']['utilization_mult'] < 0.1
    
    def test_conflict_category_reduced(self, sizer, sample_market):
        """Should reduce size for high-risk conflict category."""
        result = sizer.calculate_position_size(
            market_question='Will there be a ceasefire?',
            model_probability=0.60,
            ask_price=0.45,
            trade_side='YES',
            equity=10000,
            deployed=0,
            category='conflict',
            end_date_iso=sample_market['end_date_iso'],
            liquidity=sample_market['liquidity'],
            volume_24h=sample_market['volume_24h'],
            open_positions=[]
        )
        
        if result['should_trade']:
            # Oracle multiplier should be low
            assert result['sizing_breakdown']['oracle_mult'] <= 0.5


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
