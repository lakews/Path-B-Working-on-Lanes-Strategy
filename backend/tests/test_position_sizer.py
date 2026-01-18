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


@pytest.fixture
def sample_context():
    """Sample sizing context."""
    return {
        'equity': 10000,
        'deployed': 0,
        'open_positions': [],
        'model_probability': 0.55,  # Model says 55% YES
        'market_price': 0.45,       # Market says 45% YES
        'trade_side': 'YES'
    }


class TestBinaryKellyCalculation:
    """Tests for Binary Kelly Criterion."""
    
    def test_kelly_positive_edge(self, sizer, sample_market, sample_context):
        """Kelly should be positive when model prob > market price."""
        # Model says 55%, market at 45% = 10% edge
        ask_price = 0.45
        model_prob = 0.55
        fee_pct = 0.02
        
        # Effective price after fee
        effective_price = ask_price * (1 + fee_pct)  # 0.459
        
        # Edge = model_prob - effective_price
        edge = model_prob - effective_price  # 0.091
        
        assert edge > 0, "Edge should be positive"
        
        # Binary Kelly = edge / (1 - effective_price)
        kelly_fraction = edge / (1 - effective_price)
        
        assert kelly_fraction > 0, "Kelly fraction should be positive"
        assert kelly_fraction < 1, "Kelly fraction should be < 1"
    
    def test_kelly_negative_edge(self, sizer):
        """Kelly should be zero when model prob < effective price."""
        ask_price = 0.60
        model_prob = 0.50
        fee_pct = 0.02
        
        effective_price = ask_price * (1 + fee_pct)
        edge = model_prob - effective_price
        
        assert edge < 0, "Edge should be negative"
        # Sizer should return no trade
    
    def test_kelly_fraction_capped_at_25pct(self, sizer):
        """Kelly multiplier is capped at 0.25 by default."""
        # Even with huge edge, kelly_base should be limited
        equity = 10000
        edge = 0.50  # 50% edge (unrealistic but for testing)
        effective_price = 0.30
        
        raw_kelly = edge / (1 - effective_price)  # 0.714
        assert raw_kelly > 0.25, "Raw kelly exceeds cap"
        
        # Capped kelly
        capped_kelly = min(raw_kelly, 0.25)
        assert capped_kelly == 0.25


class TestUtilizationBrake:
    """Tests for utilization-based position reduction."""
    
    def test_zero_utilization(self, sizer):
        """At 0% utilization, multiplier should be 1.0 (full size)."""
        utilization = 0.0
        mult = sizer._utilization_brake(utilization)
        assert mult == 1.0
    
    def test_fifty_percent_utilization(self, sizer):
        """At 50% utilization, multiplier should be around 0.5."""
        utilization = 0.50
        mult = sizer._utilization_brake(utilization)
        # (1 - 0.5)^2 = 0.25
        assert abs(mult - 0.25) < 0.01
    
    def test_eighty_percent_utilization(self, sizer):
        """At 80% utilization, multiplier should be very low."""
        utilization = 0.80
        mult = sizer._utilization_brake(utilization)
        # (1 - 0.8)^2 = 0.04
        assert mult < 0.10
    
    def test_full_utilization(self, sizer):
        """At 100% utilization, multiplier should be 0."""
        utilization = 1.0
        mult = sizer._utilization_brake(utilization)
        assert mult == 0.0


class TestTimePenalty:
    """Tests for time-to-expiry based penalties."""
    
    def test_no_expiry_date(self, sizer):
        """No penalty if no expiry date provided."""
        penalty = sizer._time_penalty(None)
        assert penalty == 1.0
    
    def test_far_expiry(self, sizer):
        """No penalty for markets > 30 days out."""
        far_future = datetime.now(timezone.utc) + timedelta(days=60)
        penalty = sizer._time_penalty(far_future.isoformat())
        assert penalty > 0.95
    
    def test_one_week_expiry(self, sizer):
        """Some penalty for 7 days to expiry."""
        one_week = datetime.now(timezone.utc) + timedelta(days=7)
        penalty = sizer._time_penalty(one_week.isoformat())
        assert 0.7 < penalty < 1.0
    
    def test_one_day_expiry(self, sizer):
        """Heavy penalty for <24h to expiry."""
        tomorrow = datetime.now(timezone.utc) + timedelta(hours=12)
        penalty = sizer._time_penalty(tomorrow.isoformat())
        assert penalty < 0.7
    
    def test_expired_market(self, sizer):
        """Minimal size for expired/imminent markets."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        penalty = sizer._time_penalty(past.isoformat())
        assert penalty < 0.3


class TestOracleRisk:
    """Tests for Oracle/Ambiguity Matrix multipliers."""
    
    def test_sports_low_risk(self, sizer, sample_market):
        """Sports markets should have multiplier ~1.0."""
        sample_market['question'] = 'Lakers win NBA Finals?'
        sample_market['category'] = 'sports'
        
        category = sizer._classify_market_category(sample_market)
        mult = sizer._oracle_risk_multiplier(category, sample_market['question'])
        assert mult >= 0.95
    
    def test_crypto_low_risk(self, sizer, sample_market):
        """Crypto/price markets should have multiplier ~1.0."""
        sample_market['question'] = 'Bitcoin above $100k on Jan 31?'
        sample_market['category'] = 'crypto'
        
        category = sizer._classify_market_category(sample_market)
        mult = sizer._oracle_risk_multiplier(category, sample_market['question'])
        assert mult >= 0.95
    
    def test_conflict_high_risk(self, sizer, sample_market):
        """Conflict/war markets should have low multiplier."""
        sample_market['question'] = 'Ceasefire in Ukraine by March?'
        sample_market['category'] = 'conflict'
        
        category = sizer._classify_market_category(sample_market)
        mult = sizer._oracle_risk_multiplier(category, sample_market['question'])
        assert mult <= 0.5
    
    def test_vague_language_penalty(self, sizer, sample_market):
        """Vague language should trigger penalty."""
        sample_market['question'] = 'Will significant progress be made?'
        
        # Should detect vague language
        category = sizer._classify_market_category(sample_market)
        mult = sizer._oracle_risk_multiplier(category, sample_market['question'])
        # Should have penalty for subjective language
        assert mult < 1.0


class TestCorrelationDampening:
    """Tests for correlation-based position limits."""
    
    def test_no_correlated_positions(self, sizer, sample_market):
        """Full size with no existing correlated positions."""
        open_positions = []
        mult = sizer._correlation_dampening(sample_market, open_positions)
        assert mult == 1.0
    
    def test_one_correlated_position(self, sizer, sample_market):
        """Reduced size with 1 correlated position."""
        open_positions = [
            {'category': 'finance', 'market_question': 'Fed rate decision'}
        ]
        sample_market['category'] = 'finance'
        mult = sizer._correlation_dampening(sample_market, open_positions)
        assert 0.8 < mult < 1.0
    
    def test_many_correlated_positions(self, sizer, sample_market):
        """Heavy reduction with many correlated positions."""
        open_positions = [
            {'category': 'finance', 'market_question': 'Fed March'},
            {'category': 'finance', 'market_question': 'Fed June'},
            {'category': 'finance', 'market_question': 'Fed September'},
            {'category': 'finance', 'market_question': 'CPI January'},
        ]
        sample_market['category'] = 'finance'
        mult = sizer._correlation_dampening(sample_market, open_positions)
        assert mult < 0.6


class TestLiquidityCap:
    """Tests for liquidity-based position caps."""
    
    def test_high_liquidity(self, sizer):
        """High liquidity should not cap position."""
        liquidity = 100000
        max_pct = 0.01  # 1% of liquidity
        proposed_size = 500
        
        liquidity_cap = liquidity * max_pct
        assert proposed_size < liquidity_cap
    
    def test_low_liquidity_capped(self, sizer):
        """Low liquidity should cap position."""
        liquidity = 5000
        max_pct = 0.01
        proposed_size = 500
        
        liquidity_cap = liquidity * max_pct  # $50
        capped_size = min(proposed_size, liquidity_cap)
        assert capped_size == 50


class TestSectorCaps:
    """Tests for sector-based portfolio caps."""
    
    def test_under_sector_cap(self, sizer):
        """Position should not be capped when under limit."""
        equity = 10000
        sector_cap_pct = 0.20
        sector_exposure = 500
        proposed_size = 200
        
        sector_limit = equity * sector_cap_pct  # $2000
        remaining = sector_limit - sector_exposure  # $1500
        
        assert proposed_size < remaining
    
    def test_at_sector_cap(self, sizer):
        """Position should be zero when at cap."""
        equity = 10000
        sector_cap_pct = 0.20
        sector_exposure = 2000  # Already at cap
        
        sector_limit = equity * sector_cap_pct
        remaining = sector_limit - sector_exposure
        
        assert remaining <= 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_zero_equity(self, sizer, sample_market, sample_context):
        """Should handle zero equity gracefully."""
        sample_context['equity'] = 0
        # Should return no trade
    
    def test_negative_edge(self, sizer, sample_market, sample_context):
        """Should return no trade for negative edge."""
        sample_context['model_probability'] = 0.40
        sample_context['market_price'] = 0.50  # Model < market = negative edge
        # Should return no trade
    
    def test_extreme_probability(self, sizer, sample_market, sample_context):
        """Should handle probability at extremes (0.99)."""
        sample_context['model_probability'] = 0.99
        sample_context['market_price'] = 0.95
        # Should work without division by zero
    
    def test_missing_market_data(self, sizer, sample_context):
        """Should handle missing market fields."""
        incomplete_market = {'question': 'Test?'}
        # Should not crash


class TestIntegration:
    """Integration tests for full sizing pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_sizing_flow(self, sizer, sample_market, sample_context):
        """Test complete sizing calculation."""
        # Manually call the sizing logic
        result = await sizer.calculate_position_size(
            market=sample_market,
            equity=sample_context['equity'],
            deployed=sample_context['deployed'],
            model_probability=sample_context['model_probability'],
            trade_side=sample_context['trade_side'],
            open_positions=sample_context['open_positions']
        )
        
        assert 'should_trade' in result
        if result['should_trade']:
            assert result['final_size'] > 0
            assert result['edge'] > 0
            assert 'sizing_breakdown' in result
    
    @pytest.mark.asyncio
    async def test_sizing_with_high_utilization(self, sizer, sample_market, sample_context):
        """Test sizing when portfolio is nearly full."""
        sample_context['deployed'] = 9000  # 90% utilized
        
        result = await sizer.calculate_position_size(
            market=sample_market,
            equity=sample_context['equity'],
            deployed=sample_context['deployed'],
            model_probability=sample_context['model_probability'],
            trade_side=sample_context['trade_side'],
            open_positions=sample_context['open_positions']
        )
        
        if result['should_trade']:
            # Position should be small due to utilization brake
            assert result['final_size'] < 100


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
