"""
Unit Tests for Inventory Skew and Safety Leash Logic in MakerOrderExecutor.

Tests verify:
1. Inventory skew moves quotes in the correct direction
2. Safety leash clamps quotes when Alpha deviates too far from market
3. Edge cases and boundary conditions
"""

import pytest
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.maker_executor import MakerOrderExecutor, ExecutionMode, DEFAULT_CONFIG
from trading.clob_client import OrderBook
from datetime import datetime, timezone


class TestInventorySkew:
    """Test suite for inventory skew logic."""
    
    def setup_method(self):
        """Setup fresh executor for each test."""
        self.executor = MakerOrderExecutor(mode=ExecutionMode.PAPER)
    
    def test_inventory_skew_direction_long_position(self):
        """
        Test Case A: Long Position (We have +1000 USDC inventory)
        Expectation: Quotes shift DOWN to encourage selling (reduce inventory).
        """
        market_id = "test_market_long"
        spread = 0.04
        max_inventory = 1000.0
        
        # Configure executor
        self.executor.config['max_inventory_usd'] = max_inventory
        self.executor.config['skew_factor'] = 0.05
        
        # Set inventory: Full long position
        self.executor._inventory[market_id] = 1000.0  # Full long
        
        # Calculate skew
        skew_long = self.executor.calculate_inventory_skew(market_id, spread)
        
        # When long, skew should be POSITIVE (we subtract from quotes to lower them)
        assert skew_long > 0, f"Error: Long position skew should be positive, got {skew_long}"
        print(f"Long position skew: {skew_long:.6f} (positive = lower quotes)")
    
    def test_inventory_skew_direction_short_position(self):
        """
        Test Case B: Short Position (We have -1000 USDC inventory)
        Expectation: Quotes shift UP to encourage buying (increase inventory).
        """
        market_id = "test_market_short"
        spread = 0.04
        max_inventory = 1000.0
        
        # Configure executor
        self.executor.config['max_inventory_usd'] = max_inventory
        self.executor.config['skew_factor'] = 0.05
        
        # Set inventory: Full short position
        self.executor._inventory[market_id] = -1000.0  # Full short
        
        # Calculate skew
        skew_short = self.executor.calculate_inventory_skew(market_id, spread)
        
        # When short, skew should be NEGATIVE (we add to quotes to raise them)
        assert skew_short < 0, f"Error: Short position skew should be negative, got {skew_short}"
        print(f"Short position skew: {skew_short:.6f} (negative = raise quotes)")
    
    def test_inventory_skew_quote_movement(self):
        """
        Full integration test: Verify bid/ask quotes move correctly with inventory.
        
        - Long inventory → lower both bid and ask
        - Short inventory → raise both bid and ask
        """
        theoretical_price = 0.50
        spread = 0.04
        max_inventory = 1000.0
        
        # Configure executor
        self.executor.config['max_inventory_usd'] = max_inventory
        self.executor.config['skew_factor'] = 0.05
        self.executor.config['ofi_threshold'] = 0.9  # High threshold to disable OFI for this test
        
        # Create mock orderbook with balanced liquidity (no OFI effect)
        orderbook = OrderBook(
            token_id="test_token",
            bids=[{'price': '0.48', 'size': '100'}, {'price': '0.47', 'size': '100'}],
            asks=[{'price': '0.52', 'size': '100'}, {'price': '0.53', 'size': '100'}],
            timestamp=datetime.now(timezone.utc)
        )
        
        # Case A: Long Position (+1000)
        market_id_long = "test_market_long"
        self.executor._inventory[market_id_long] = 1000.0
        
        bid_long, ask_long, debug_long = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id_long,
            order_book=orderbook,
            market_mid=0.50
        )
        
        # Case B: Short Position (-1000)
        market_id_short = "test_market_short"
        self.executor._inventory[market_id_short] = -1000.0
        
        bid_short, ask_short, debug_short = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id_short,
            order_book=orderbook,
            market_mid=0.50
        )
        
        # Case C: Neutral Position (0)
        market_id_neutral = "test_market_neutral"
        self.executor._inventory[market_id_neutral] = 0.0
        
        bid_neutral, ask_neutral, debug_neutral = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id_neutral,
            order_book=orderbook,
            market_mid=0.50
        )
        
        # ASSERTIONS
        # 1. When Long, quotes should be LOWER than neutral (to encourage selling)
        assert bid_long < bid_neutral, f"Error: Long bid ({bid_long:.4f}) should be < Neutral bid ({bid_neutral:.4f})"
        assert ask_long < ask_neutral, f"Error: Long ask ({ask_long:.4f}) should be < Neutral ask ({ask_neutral:.4f})"
        
        # 2. When Short, quotes should be HIGHER than neutral (to encourage buying)
        assert bid_short > bid_neutral, f"Error: Short bid ({bid_short:.4f}) should be > Neutral bid ({bid_neutral:.4f})"
        assert ask_short > ask_neutral, f"Error: Short ask ({ask_short:.4f}) should be > Neutral ask ({ask_neutral:.4f})"
        
        # 3. Long < Neutral < Short for both bid and ask
        assert bid_long < bid_short, f"Error: Long bid ({bid_long:.4f}) should be < Short bid ({bid_short:.4f})"
        assert ask_long < ask_short, f"Error: Long ask ({ask_long:.4f}) should be < Short ask ({ask_short:.4f})"
        
        print(f"\n=== INVENTORY SKEW VERIFICATION ===")
        print(f"Long Position  (+1000): Bid={bid_long:.4f} Ask={ask_long:.4f}")
        print(f"Neutral Position (0):   Bid={bid_neutral:.4f} Ask={ask_neutral:.4f}")
        print(f"Short Position (-1000): Bid={bid_short:.4f} Ask={ask_short:.4f}")
        print(f"✅ Skew Logic Verified: Long < Neutral < Short")
    
    def test_inventory_skew_zero_inventory(self):
        """Test that zero inventory results in zero skew."""
        market_id = "test_market_zero"
        spread = 0.04
        
        self.executor._inventory[market_id] = 0.0
        
        skew = self.executor.calculate_inventory_skew(market_id, spread)
        
        assert skew == 0.0, f"Error: Zero inventory should have zero skew, got {skew}"
        print(f"Zero inventory skew: {skew} (correct)")


class TestSafetyLeash:
    """Test suite for safety leash (anti-hallucination) logic."""
    
    def setup_method(self):
        """Setup fresh executor for each test."""
        self.executor = MakerOrderExecutor(mode=ExecutionMode.PAPER)
        self.executor.config['max_alpha_deviation'] = 0.15  # 15 cents
    
    def test_safety_leash_no_clamping_within_bounds(self):
        """Test that quotes within deviation limit are not clamped."""
        market_mid = 0.50
        my_bid = 0.55  # Within 0.15 of 0.50
        my_ask = 0.60  # Within 0.15 of 0.50
        
        safe_bid, safe_ask, was_clamped = self.executor.clamp_to_reality(
            my_bid=my_bid,
            my_ask=my_ask,
            market_mid=market_mid
        )
        
        assert not was_clamped, "Should not clamp when within bounds"
        assert safe_bid == my_bid, f"Bid should not change: {safe_bid} vs {my_bid}"
        assert safe_ask == my_ask, f"Ask should not change: {safe_ask} vs {my_ask}"
        print(f"Within bounds: No clamping needed (bid={safe_bid:.4f}, ask={safe_ask:.4f})")
    
    def test_safety_leash_clamps_extreme_bid(self):
        """Test that hallucinated bid far above market is clamped."""
        market_mid = 0.50
        my_bid = 0.80  # Way above 0.50 + 0.15 = 0.65
        my_ask = 0.85
        
        safe_bid, safe_ask, was_clamped = self.executor.clamp_to_reality(
            my_bid=my_bid,
            my_ask=my_ask,
            market_mid=market_mid
        )
        
        assert was_clamped, "Should clamp extreme quotes"
        assert safe_bid == 0.65, f"Bid should be clamped to upper bound: {safe_bid}"
        assert safe_ask == 0.65, f"Ask should be clamped to upper bound: {safe_ask}"
        print(f"Clamped high quotes: bid {my_bid:.2f}→{safe_bid:.2f}, ask {my_ask:.2f}→{safe_ask:.2f}")
    
    def test_safety_leash_clamps_extreme_low(self):
        """Test that hallucinated quotes far below market are clamped."""
        market_mid = 0.50
        my_bid = 0.20  # Way below 0.50 - 0.15 = 0.35
        my_ask = 0.25
        
        safe_bid, safe_ask, was_clamped = self.executor.clamp_to_reality(
            my_bid=my_bid,
            my_ask=my_ask,
            market_mid=market_mid
        )
        
        assert was_clamped, "Should clamp extreme low quotes"
        assert safe_bid == 0.35, f"Bid should be clamped to lower bound: {safe_bid}"
        assert safe_ask == 0.35, f"Ask should be clamped to lower bound: {safe_ask}"
        print(f"Clamped low quotes: bid {my_bid:.2f}→{safe_bid:.2f}, ask {my_ask:.2f}→{safe_ask:.2f}")
    
    def test_safety_leash_hallucination_scenario(self):
        """
        Critical test: Model hallucinates Alpha = 0.99 when market is 0.50
        
        This is the primary scenario the safety leash protects against.
        Without clamping, we'd place a bid at ~0.97 when the market says 0.50!
        """
        theoretical_price = 0.99  # Hallucinated Alpha
        market_mid = 0.50        # Reality
        spread = 0.04
        max_deviation = 0.15
        
        # Expected: Quotes should be clamped to 0.50 ± 0.15 = [0.35, 0.65]
        # Without clamping: bid ≈ 0.97, ask ≈ 1.01
        
        self.executor.config['max_alpha_deviation'] = max_deviation
        
        # Create mock orderbook
        orderbook = OrderBook(
            token_id="test_token",
            bids=[{'price': '0.48', 'size': '100'}],
            asks=[{'price': '0.52', 'size': '100'}],
            timestamp=datetime.now(timezone.utc)
        )
        
        market_id = "hallucination_test"
        self.executor._inventory[market_id] = 0.0  # Neutral inventory
        
        bid, ask, debug = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id,
            order_book=orderbook,
            market_mid=market_mid
        )
        
        # Verify safety leash was triggered
        assert debug['safety_leash_triggered'], "Safety leash should trigger for hallucinated Alpha"
        
        # Verify quotes are within bounds
        upper_bound = market_mid + max_deviation
        lower_bound = market_mid - max_deviation
        
        assert bid <= upper_bound, f"Bid {bid:.4f} should be <= {upper_bound}"
        assert ask <= upper_bound, f"Ask {ask:.4f} should be <= {upper_bound}"
        assert bid >= lower_bound, f"Bid {bid:.4f} should be >= {lower_bound}"
        assert ask >= lower_bound, f"Ask {ask:.4f} should be >= {lower_bound}"
        
        print(f"\n=== HALLUCINATION PROTECTION TEST ===")
        print(f"Alpha (hallucinated): {theoretical_price}")
        print(f"Market mid (reality): {market_mid}")
        print(f"Pre-clamp bid/ask:    {debug['pre_clamp_bid']:.4f} / {debug['pre_clamp_ask']:.4f}")
        print(f"Post-clamp bid/ask:   {bid:.4f} / {ask:.4f}")
        print(f"Bounds: [{lower_bound:.2f}, {upper_bound:.2f}]")
        print(f"✅ Hallucination protected!")
    
    def test_safety_leash_edge_boundaries(self):
        """Test boundary conditions at 0 and 1."""
        # Test near 0
        safe_bid, safe_ask, _ = self.executor.clamp_to_reality(
            my_bid=-0.10,  # Invalid
            my_ask=0.05,
            market_mid=0.05
        )
        assert safe_bid >= 0.001, f"Bid should not be negative: {safe_bid}"
        
        # Test near 1
        safe_bid, safe_ask, _ = self.executor.clamp_to_reality(
            my_bid=0.95,
            my_ask=1.10,  # Invalid
            market_mid=0.95
        )
        assert safe_ask <= 0.999, f"Ask should not exceed 0.999: {safe_ask}"
        
        print(f"Edge boundary tests passed")
    
    def test_safety_leash_custom_deviation(self):
        """Test with custom deviation limit."""
        custom_deviation = 0.05  # Tighter leash
        
        safe_bid, safe_ask, was_clamped = self.executor.clamp_to_reality(
            my_bid=0.60,  # > 0.50 + 0.05
            my_ask=0.65,
            market_mid=0.50,
            deviation_limit=custom_deviation
        )
        
        assert was_clamped, "Should clamp with tighter deviation"
        assert safe_bid == 0.55, f"Bid should be clamped to 0.55: {safe_bid}"
        print(f"Custom deviation ({custom_deviation}): Clamped to {safe_bid:.4f}")


class TestIntegration:
    """Integration tests combining inventory skew and safety leash."""
    
    def setup_method(self):
        """Setup fresh executor for each test."""
        self.executor = MakerOrderExecutor(mode=ExecutionMode.PAPER)
        self.executor.config['max_inventory_usd'] = 1000.0
        self.executor.config['skew_factor'] = 0.05
        self.executor.config['max_alpha_deviation'] = 0.15
        self.executor.config['ofi_threshold'] = 0.9  # Disable OFI
    
    def test_skew_with_safety_leash(self):
        """
        Test that inventory skew works correctly even when safety leash is active.
        
        Scenario: Large inventory + reasonable Alpha should still show skew direction,
        even if the overall quote gets clamped.
        """
        theoretical_price = 0.55
        market_mid = 0.50
        spread = 0.04
        
        orderbook = OrderBook(
            token_id="test_token",
            bids=[{'price': '0.48', 'size': '100'}],
            asks=[{'price': '0.52', 'size': '100'}],
            timestamp=datetime.now(timezone.utc)
        )
        
        # Case A: Long inventory
        market_id_long = "integration_long"
        self.executor._inventory[market_id_long] = 500.0
        
        bid_long, ask_long, debug_long = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id_long,
            order_book=orderbook,
            market_mid=market_mid
        )
        
        # Case B: Short inventory
        market_id_short = "integration_short"
        self.executor._inventory[market_id_short] = -500.0
        
        bid_short, ask_short, debug_short = self.executor.calculate_adjusted_quotes(
            theoretical_price=theoretical_price,
            spread=spread,
            market_id=market_id_short,
            order_book=orderbook,
            market_mid=market_mid
        )
        
        # Even with safety leash, skew direction should be preserved
        # Long should have lower quotes than short
        assert bid_long <= bid_short, f"Skew should preserve: Long bid <= Short bid"
        assert ask_long <= ask_short, f"Skew should preserve: Long ask <= Short ask"
        
        print(f"\n=== SKEW + SAFETY LEASH INTEGRATION ===")
        print(f"Alpha: {theoretical_price} | Market: {market_mid}")
        print(f"Long (+500):  Bid={bid_long:.4f} Ask={ask_long:.4f}")
        print(f"Short (-500): Bid={bid_short:.4f} Ask={ask_short:.4f}")
        print(f"✅ Skew direction preserved with safety leash")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
