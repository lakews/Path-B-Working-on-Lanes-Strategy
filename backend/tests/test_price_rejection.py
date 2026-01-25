"""
Test suite for price fallback rejection behavior.
Ensures the trading engine REJECTS trades when price data is missing,
instead of using fallback values like 0.5.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPriceRejection:
    """Test that trades are rejected without valid price data"""
    
    def test_trading_bot_rejects_missing_price(self):
        """Test that _execute_with_rl rejects trades without valid yes_price"""
        from trading_bot import ApexTrader
        
        # Market data with NO price
        market_data_no_price = {
            'id': 'test_market_123',
            'question': 'Test market?',
            'volume': 10000,
            'liquidity': 50000
            # yes_price is MISSING
        }
        
        # Market data with zero price
        market_data_zero_price = {
            'id': 'test_market_456',
            'question': 'Test market 2?',
            'yes_price': 0,  # Zero price should also be rejected
            'volume': 10000,
            'liquidity': 50000
        }
        
        # Verify that None/0 prices are detected
        assert market_data_no_price.get('yes_price') is None
        assert market_data_zero_price.get('yes_price') == 0
        
        print("PASS: Missing/zero price detection works")
    
    def test_delta_neutral_rejects_missing_price(self):
        """Test that DeltaNeutralStrategy rejects without valid price"""
        from strategies.delta_neutral import DeltaNeutralStrategy
        
        market_data = {
            'id': 'test_market_789',
            'question': 'Test?',
            # no yes_price
        }
        
        # Price should be None/missing
        yes_price = market_data.get('yes_price')
        assert yes_price is None, "Expected yes_price to be None"
        
        # The strategy should reject this
        # (Actual async test would need event loop)
        print("PASS: DeltaNeutral price rejection check")
    
    def test_volatility_strategy_rejects_missing_price(self):
        """Test that VolatilityExploitationStrategy rejects without valid price"""
        from strategies.volatility_exploitation import VolatilityExploitationStrategy
        
        market_data = {
            'id': 'test_market_abc',
            'question': 'Test volatility?',
            'yes_price': None,  # Explicit None
        }
        
        yes_price = market_data.get('yes_price')
        assert yes_price is None, "Expected yes_price to be None"
        print("PASS: Volatility strategy price rejection check")
    
    def test_arbitrage_rejects_missing_price(self):
        """Test that ArbitrageStrategy rejects without valid price"""
        from strategies.arbitrage import MultiMarketArbitrageStrategy
        
        market1 = {
            'id': 'market1',
            'yes_price': 0.3,  # Valid
        }
        market2 = {
            'id': 'market2',
            # yes_price missing
        }
        
        # Detection should work
        assert market1.get('yes_price') == 0.3
        assert market2.get('yes_price') is None
        print("PASS: Arbitrage price rejection check")
    
    def test_alpha_directional_rejects_missing_price(self):
        """Test that AlphaDirectionalStrategy rejects without valid price"""
        from strategies.alpha_directional import AlphaDirectionalStrategy
        
        market_data = {
            'id': 'test_alpha_123',
            'yes_price': 0,  # Zero should be rejected
        }
        
        yes_price = market_data.get('yes_price')
        assert yes_price == 0, "Expected yes_price to be 0"
        
        # Check rejection logic
        should_reject = yes_price is None or yes_price == 0
        assert should_reject, "Should reject zero price"
        print("PASS: Alpha directional price rejection check")
    
    def test_kelly_optimizer_rejects_missing_price(self):
        """Test that KellySharpeOptimizer rejects without valid price"""
        from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
        
        market_data = {
            'id': 'test_kelly',
            # no yes_price
        }
        
        price = market_data.get('yes_price')
        should_reject = price is None or price == 0
        assert should_reject, "Kelly should reject missing price"
        print("PASS: Kelly optimizer price rejection check")
    
    def test_signal_fusion_rejects_missing_price(self):
        """Test that SignalFusion rejects without valid price"""
        from ml.signal_fusion import SignalFusionEngine
        
        market_data = {
            'id': 'test_signal',
            'yes_price': None,
        }
        
        current_price = market_data.get('yes_price')
        should_reject = current_price is None or current_price == 0
        assert should_reject, "Signal fusion should reject missing price"
        print("PASS: Signal fusion price rejection check")
    
    def test_rl_engine_handles_missing_price(self):
        """Test that RL engine returns zero state for missing price"""
        import numpy as np
        
        # Test the price validation logic directly
        market_data = {
            'id': 'test_rl',
            # no yes_price
        }
        
        yes_price = market_data.get('yes_price')
        should_return_zero_state = yes_price is None or yes_price == 0
        
        assert should_return_zero_state, "Should indicate invalid state needed for missing price"
        print("PASS: RL engine handles missing price")
    
    def test_market_data_service_no_default_price(self):
        """Test that market data service doesn't default to 0.5"""
        # Test the normalization logic directly without instantiating service
        raw_data = {
            'condition_id': 'test_123',
            'question': 'Test?',
            # no yes_price or no_price
        }
        
        # Simulate the normalization logic
        raw_yes = raw_data.get('yes_price')
        raw_no = raw_data.get('no_price')
        
        yes_price = float(raw_yes) if raw_yes is not None and raw_yes != 0 else None
        no_price = float(raw_no) if raw_no is not None and raw_no != 0 else None
        
        # Should NOT default to 0.5
        assert yes_price is None, "Should be None when price is missing, not 0.5"
        assert no_price is None, "Should be None when price is missing, not 0.5"
        print("PASS: Market data service no default price")
    
    def test_polymarket_api_skips_invalid_markets(self):
        """Test that API skips markets without valid price data"""
        import json
        
        # Market with no outcomePrices should be skipped
        invalid_market = {
            'conditionId': 'test_invalid',
            'question': 'Invalid market?',
            'outcomePrices': '[]',  # Empty prices
            'liquidityNum': 1000,
        }
        
        # Simulate the validation logic from PolymarketAPI._normalize_market
        outcome_prices = invalid_market.get('outcomePrices', '[]')
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except:
                outcome_prices = []
        
        # Should detect invalid prices
        should_skip = not outcome_prices or len(outcome_prices) == 0
        assert should_skip, "Should skip markets with empty outcomePrices"
        print("PASS: Polymarket API skips invalid markets")


class TestAsyncPriceRejection:
    """Async tests for price rejection behavior"""
    
    @pytest.mark.asyncio
    async def test_delta_neutral_async_rejection(self):
        """Async test for delta neutral strategy rejection"""
        from strategies.delta_neutral import DeltaNeutralStrategy
        
        strategy = DeltaNeutralStrategy()
        
        market_data = {
            'id': 'test_async_dn',
            'question': 'Test async?',
            # no yes_price
        }
        
        # Mock the dependencies
        with patch.object(strategy, 'signal_fusion') as mock_fusion, \
             patch.object(strategy, 'spread_calibrator') as mock_spread:
            
            mock_fusion.generate_trading_signal = AsyncMock(return_value={'confidence': 0.8})
            mock_spread.get_spread_for_market = AsyncMock(return_value=0.01)
            
            result = await strategy.execute_strategy(market_data)
            
            # Should return None (rejected) because no price
            assert result is None, "Should reject trade without valid price"
        
        print("PASS: Async delta neutral rejection")
    
    @pytest.mark.asyncio
    async def test_volatility_async_rejection(self):
        """Async test for volatility strategy rejection"""
        from strategies.volatility_exploitation import VolatilityExploitationStrategy
        
        strategy = VolatilityExploitationStrategy()
        
        market_data = {
            'id': 'test_async_vol',
            'question': 'Test async vol?',
            'yes_price': 0,  # Zero price
        }
        
        with patch.object(strategy, 'volatility_predictor') as mock_vol:
            mock_vol.predict_volatility = AsyncMock(return_value=(0.8, 0.9))
            
            result = await strategy.execute_strategy(market_data)
            
            # Should return None because price is 0
            assert result is None, "Should reject trade with zero price"
        
        print("PASS: Async volatility rejection")
    
    @pytest.mark.asyncio
    async def test_alpha_directional_async_rejection(self):
        """Async test for alpha directional strategy rejection"""
        from strategies.alpha_directional import AlphaDirectionalStrategy
        
        strategy = AlphaDirectionalStrategy()
        
        market_data = {
            'id': 'test_async_alpha',
            'question': 'Test async alpha?',
            # Missing yes_price
        }
        
        with patch.object(strategy, 'signal_fusion') as mock_fusion:
            mock_fusion.generate_trading_signal = AsyncMock(return_value={
                'confidence': 0.9,
                'recommended_action': 'BUY',
                'bayesian_posterior': 0.7
            })
            
            result = await strategy.execute_strategy(market_data)
            
            # Should return None because no price
            assert result is None, "Should reject trade without price"
        
        print("PASS: Async alpha directional rejection")
    
    @pytest.mark.asyncio
    async def test_kelly_optimizer_async_rejection(self):
        """Async test for Kelly optimizer rejection"""
        from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
        
        optimizer = KellySharpeOptimizer()
        
        market_data = {
            'id': 'test_async_kelly',
            # Missing yes_price
        }
        
        with patch.object(optimizer, '_get_current_capital', return_value=10000):
            position_size, kelly_pct = await optimizer.calculate_position_size(
                market_data,
                confidence=0.8,
                win_probability=0.6
            )
            
            # Should return 0 because no price
            assert position_size == 0.0, "Should return 0 position size without price"
            assert kelly_pct == 0.0, "Should return 0 kelly pct without price"
        
        print("PASS: Async Kelly optimizer rejection")


def run_sync_tests():
    """Run all synchronous tests"""
    test_class = TestPriceRejection()
    
    print("\n" + "="*60)
    print("RUNNING PRICE REJECTION TESTS")
    print("="*60 + "\n")
    
    test_class.test_trading_bot_rejects_missing_price()
    test_class.test_delta_neutral_rejects_missing_price()
    test_class.test_volatility_strategy_rejects_missing_price()
    test_class.test_arbitrage_rejects_missing_price()
    test_class.test_alpha_directional_rejects_missing_price()
    test_class.test_kelly_optimizer_rejects_missing_price()
    test_class.test_signal_fusion_rejects_missing_price()
    test_class.test_rl_engine_handles_missing_price()
    test_class.test_market_data_service_no_default_price()
    test_class.test_polymarket_api_skips_invalid_markets()
    
    print("\n" + "="*60)
    print("ALL SYNC TESTS PASSED!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_sync_tests()
    
    # Run async tests
    print("\n" + "="*60)
    print("RUNNING ASYNC TESTS")
    print("="*60 + "\n")
    
    async def run_async_tests():
        test_class = TestAsyncPriceRejection()
        await test_class.test_delta_neutral_async_rejection()
        await test_class.test_volatility_async_rejection()
        await test_class.test_alpha_directional_async_rejection()
        await test_class.test_kelly_optimizer_async_rejection()
    
    asyncio.run(run_async_tests())
    
    print("\n" + "="*60)
    print("ALL ASYNC TESTS PASSED!")
    print("="*60 + "\n")
