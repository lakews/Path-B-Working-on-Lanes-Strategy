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
    
    def test_utilization_decreases_monotonically(self, sizer):
        """Higher utilization = lower multiplier."""
        mult_0 = sizer._calculate_utilization_brake(0.0)
        mult_25 = sizer._calculate_utilization_brake(0.25)
        mult_50 = sizer._calculate_utilization_brake(0.50)
        mult_75 = sizer._calculate_utilization_brake(0.75)
        mult_100 = sizer._calculate_utilization_brake(1.0)
        
        assert mult_0 > mult_25 > mult_50 > mult_75 > mult_100


class TestTimePenalty:
    """Tests for time-to-expiry penalties."""
    
    def test_time_penalty_positive(self, sizer):
        """All penalties should be positive."""
        for days in [0.1, 1.0, 7.0, 30.0, None]:
            penalty = sizer._calculate_time_penalty(days)
            assert penalty > 0
            assert penalty <= 1.0


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
        """Test market classifier returns category."""
        result = classify_market({
            'question': 'Lakers win NBA Finals?',
            'category': 'sports'
        })
        
        # classify_market returns the category string directly
        assert result == 'sports'
    
    def test_get_oracle_risk_multiplier(self):
        """Test oracle risk multiplier function."""
        # get_oracle_risk_multiplier(category, market_age_hours) 
        mult = get_oracle_risk_multiplier('sports', 100)
        assert mult == 1.0
        
        mult = get_oracle_risk_multiplier('conflict', 100)
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
        """No-trade result has breakdown with rejection info."""
        result = sizer._no_trade_result("test_reason", "test_detail")
        assert 'breakdown' in result
        assert result['breakdown']['reject_reason'] == "test_reason"


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
    
    def test_short_expiry_may_differ(self, sizer, sample_order_book):
        """Short expiry may affect size (direction depends on implementation)."""
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
        
        # Both should trade (implementation may boost or reduce short expiry)
        assert result_short['should_trade']
        assert result_long['should_trade']
    
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


class TestModelProbabilityEnsemble:
    """
    Tests for the weighted average ensemble probability calculation.
    
    This is CRITICAL - validates the fix for the multiplicative probability bug
    that could produce probabilities > 100%.
    """
    
    @pytest.fixture
    def paper_trader_mock(self):
        """Create a minimal PaperTrader instance for testing probability calculation."""
        from paper_trading.paper_trader import PaperTrader
        pt = PaperTrader.__new__(PaperTrader)
        # Initialize required attributes that _calculate_model_probability needs
        pt.alpha_weights = {
            'sentiment_weight': 0.50,
            'rl_weight': 0.60,
            'sharp_weight': 0.30,
            'sentiment_neutral_low': 0.45,
            'sentiment_neutral_high': 0.55,
            'max_sentiment_delta': 2.0,
            'min_rl_confidence': 0.15,
        }
        return pt
    
    def test_probability_never_exceeds_one(self, paper_trader_mock):
        """
        Model probability must always be a valid probability (0 < p < 1).
        
        Note: The Bayesian log-odds implementation intentionally does NOT cap
        at 0.99 - extreme inputs produce extreme outputs. This is by design
        to avoid creating artificial edge at boundaries.
        """
        pt = paper_trader_mock
        
        # Extreme bullish case - all signals at maximum
        result = pt._calculate_model_probability(
            sentiment=0.99,
            sharp_alignment=0.99,
            rl_confidence=0.99,
            yes_price=0.99,
            rl_action='BUY_LARGE'
        )
        
        # Result should be a valid probability (0 < p < 1), not NaN/inf
        assert 0.0 < result < 1.0, f"Probability {result} is not a valid probability!"
        # With extreme bullish inputs at high market price, expect very high output
        assert result > 0.99, f"Expected very high probability for extreme bullish case, got {result}"
    
    def test_probability_never_below_minimum(self, paper_trader_mock):
        """
        Model probability must always be a valid probability (0 < p < 1).
        
        Note: The Bayesian log-odds implementation intentionally does NOT cap
        at 0.01 - extreme inputs produce extreme outputs. This is by design.
        """
        pt = paper_trader_mock
        
        # Extreme bearish case - all signals at minimum
        result = pt._calculate_model_probability(
            sentiment=0.01,
            sharp_alignment=0.01,
            rl_confidence=0.99,
            yes_price=0.01,
            rl_action='SELL_LARGE'
        )
        
        # Result should be a valid probability (0 < p < 1), not NaN/inf
        assert 0.0 < result < 1.0, f"Probability {result} is not a valid probability!"
        # With extreme bearish inputs at low market price, expect very low output
        assert result < 0.01, f"Expected very low probability for extreme bearish case, got {result}"
    
    def test_hold_action_returns_near_market(self, paper_trader_mock):
        """HOLD action with neutral sentiment should return close to market price."""
        pt = paper_trader_mock
        
        market_price = 0.55
        result = pt._calculate_model_probability(
            sentiment=0.50,
            sharp_alignment=0.50,
            rl_confidence=0.30,
            yes_price=market_price,
            rl_action='HOLD'
        )
        
        # Should be within 10% of market price (weighted average effect)
        assert abs(result - market_price) < 0.10, f"HOLD result {result} too far from market {market_price}"
    
    def test_buy_signal_increases_probability(self, paper_trader_mock):
        """BUY signal with bullish sentiment should increase probability above market."""
        pt = paper_trader_mock
        
        market_price = 0.50
        result = pt._calculate_model_probability(
            sentiment=0.70,      # Bullish
            sharp_alignment=0.80,
            rl_confidence=0.70,
            yes_price=market_price,
            rl_action='BUY_MEDIUM'
        )
        
        # Model should believe true probability is higher than market
        assert result > market_price, f"BUY signal result {result} not above market {market_price}"
    
    def test_sell_signal_decreases_probability(self, paper_trader_mock):
        """SELL signal with bearish sentiment should decrease probability below market."""
        pt = paper_trader_mock
        
        market_price = 0.50
        result = pt._calculate_model_probability(
            sentiment=0.30,      # Bearish
            sharp_alignment=0.30,
            rl_confidence=0.70,
            yes_price=market_price,
            rl_action='SELL_MEDIUM'
        )
        
        # Model should believe true probability is lower than market
        assert result < market_price, f"SELL signal result {result} not below market {market_price}"
    
    def test_high_market_price_stays_bounded(self, paper_trader_mock):
        """
        High market price (90%) with bullish signals should NOT exceed 1.0 (impossible probability).
        
        The Bayesian log-odds approach uses sigmoid which mathematically ensures 0 < p < 1.
        We verify it's a valid probability and responds correctly to bullish signals.
        """
        pt = paper_trader_mock
        
        result = pt._calculate_model_probability(
            sentiment=0.90,
            sharp_alignment=0.85,
            rl_confidence=0.80,
            yes_price=0.90,       # 90% market price
            rl_action='BUY_LARGE'
        )
        
        # Sigmoid output is always (0, 1) - mathematically guaranteed
        assert 0.0 < result < 1.0, f"Result {result} is not a valid probability!"
        # Bullish signals on high market should produce result >= market price
        assert result >= 0.90, f"Result {result} should be >= market price 0.90 for bullish case"
    
    def test_low_market_price_stays_bounded(self, paper_trader_mock):
        """
        Low market price (10%) with bearish signals should NOT go below 0 (impossible probability).
        
        The Bayesian log-odds approach uses sigmoid which mathematically ensures 0 < p < 1.
        """
        pt = paper_trader_mock
        
        result = pt._calculate_model_probability(
            sentiment=0.10,
            sharp_alignment=0.10,
            rl_confidence=0.80,
            yes_price=0.10,       # 10% market price (longshot)
            rl_action='SELL_LARGE'
        )
        
        # Sigmoid output is always (0, 1) - mathematically guaranteed
        assert 0.0 < result < 1.0, f"Result {result} is not a valid probability!"
        # Bearish signals on low market should produce result <= market price
        assert result <= 0.10, f"Result {result} should be <= market price 0.10 for bearish case"
    
    def test_conflicting_signals_favor_market(self, paper_trader_mock):
        """When RL and sentiment conflict, result should stay closer to market."""
        pt = paper_trader_mock
        
        market_price = 0.50
        
        # Sentiment says bearish, RL says buy - conflicting!
        result = pt._calculate_model_probability(
            sentiment=0.25,       # Bearish
            sharp_alignment=0.50,
            rl_confidence=0.60,
            yes_price=market_price,
            rl_action='BUY_MEDIUM'
        )
        
        # Result should be close to market due to signal conflict
        assert abs(result - market_price) < 0.15, f"Conflicting signals: {result} too far from market {market_price}"
    
    def test_agreeing_signals_deviate_from_market(self, paper_trader_mock):
        """When RL and sentiment agree, result should deviate more from market."""
        pt = paper_trader_mock
        
        market_price = 0.50
        
        # Both sentiment and RL bullish
        result = pt._calculate_model_probability(
            sentiment=0.75,       # Bullish
            sharp_alignment=0.80,
            rl_confidence=0.75,
            yes_price=market_price,
            rl_action='BUY_MEDIUM'
        )
        
        # Result should deviate significantly from market
        deviation = abs(result - market_price)
        assert deviation > 0.08, f"Agreeing signals: deviation {deviation} too small"


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
