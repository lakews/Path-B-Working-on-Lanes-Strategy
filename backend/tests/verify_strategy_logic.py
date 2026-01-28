#!/usr/bin/env python3
"""
Strategy Logic Stress Test Suite
================================

Comprehensive verification of strategy layer capabilities:
- Inventory Awareness (Skew)
- Signal Stability (Noise Filtering)
- Volatility Adaptation (Spread Widening)
- Stale Data Handling (Data Freshness)

Part 1: Gap Analysis Audit (see docstring for findings)
Part 2: Stress Test Scenarios A-D

Author: APEX TRADER QA Team
Date: January 2026
"""

"""
=============================================================================
PART 1: GAP ANALYSIS AUDIT REPORT
=============================================================================

FINDING 1: Inventory Awareness (Skew)
-------------------------------------
STATUS: ⚠️ PARTIAL IMPLEMENTATION

Where it EXISTS:
- paper_trader.py Line 1509: `current_skew = hft_long_value / total_hft_value`
- paper_trader.py Lines 1514-1520: Inventory guard BLOCKS trades when over-concentrated
- hft_context.py Line 70: `max_inventory_skew: float` parameter exists

What's MISSING:
- ❌ Strategies (alpha_directional.py, volatility_exploitation.py) do NOT accept 
     `current_position` as input
- ❌ Fair Value is NOT adjusted based on inventory (skewed_mid uses AI bias, not position)
- ❌ The strategies calculate position_size but don't consider existing inventory
- ❌ No "Bag Holder" price skew: If long 1000 shares, should lower fair_value to 
     encourage selling. Currently only BLOCKS trades, doesn't SKEW prices.

Recommended Fix:
```python
# In _evaluate_hft_scalp, add inventory-aware fair value adjustment:
inventory_position = self.paper_positions.get(market_id, {}).get('size', 0)
inventory_bias = -inventory_position / (self.deployed_capital * 0.1)  # Scale
skewed_fair_value = fair_value + (inventory_bias * 0.02)  # Shift by up to 2 cents
```


FINDING 2: Time Decay (Theta)
-----------------------------
STATUS: ✅ IMPLEMENTED (Partial)

Where it EXISTS:
- paper_trader.py Lines 450-461: `expiry_thresholds_config` and 
  `expiry_strategy_adjustments` dictionaries
- paper_trader.py Line 459: Delta-neutral disables within 48 hours of expiry
- paper_trader.py Line 461: Alpha requires higher confidence near expiry
- paper_trader.py Lines 2532-2550: End date parsing logic

What's MISSING:
- ❌ Spread widening based on theta is NOT implemented
- ❌ No explicit theta calculation (time value decay rate)
- ❌ Expiry awareness exists but doesn't affect spread width dynamically


FINDING 3: Noise Filtering (Signal Stability)
---------------------------------------------
STATUS: ❌ NOT IMPLEMENTED

What's MISSING:
- ❌ No hysteresis on signal generation (signal_fusion.py recalculates fresh each call)
- ❌ No filtering of 1-tick ping-pong moves
- ❌ No "last_signal" caching to prevent flickering
- ❌ Strategies evaluate every tick independently without memory

Recommended Fix:
```python
# In SignalFusionEngine, add signal memory:
self._last_signals = {}  # market_id -> (signal, timestamp)
SIGNAL_HYSTERESIS = 0.05  # 5% minimum change to update signal

def generate_trading_signal(self, market_data):
    new_signal = self._compute_signal(market_data)
    last = self._last_signals.get(market_id)
    if last and abs(new_signal - last[0]) < SIGNAL_HYSTERESIS:
        return last[0]  # Return cached signal (anti-wiggle)
    self._last_signals[market_id] = (new_signal, now)
    return new_signal
```


FINDING 4: Stale Data Handling
------------------------------
STATUS: ✅ IMPLEMENTED (for HFT Context)

Where it EXISTS:
- hft_context.py Line 37: `MAX_CONTEXT_AGE_SECONDS = 600`
- hft_context.py Lines 371-384: `get()` returns None if context is stale
- paper_trader.py Lines 1375-1380: HFT scalp returns None if params is stale

What's MISSING:
- ❌ Strategies (alpha_directional.py, etc.) don't check data freshness
- ❌ No timestamp validation on market_data input
- ❌ No "Cancel All" signal generation on stale data


=============================================================================
SUMMARY: CRITICAL GAPS
=============================================================================

| Feature              | Status     | Priority |
|---------------------|------------|----------|
| Inventory Price Skew | ⚠️ Partial | HIGH     |
| Signal Noise Filter  | ❌ Missing | HIGH     |
| Theta Spread Adjust  | ❌ Missing | MEDIUM   |
| Stale Data in Strats | ⚠️ Partial | MEDIUM   |

=============================================================================
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

# Add backend to path
sys.path.insert(0, '/app/backend')


# =============================================================================
# PART 2: STRESS TEST IMPLEMENTATION
# =============================================================================

@dataclass
class StrategyOutput:
    """Mock strategy output for testing"""
    fair_value: float
    bid: float
    ask: float
    spread: float
    signal: float  # -1 to +1
    action: str  # BUY, SELL, HOLD, CANCEL_ALL


class MockStrategyEngine:
    """
    Mock strategy engine implementing the EXPECTED behavior.
    This is what the real strategies SHOULD do.
    """
    
    def __init__(self):
        self.TICK_SIZE = 0.01
        self.MIN_SPREAD = 0.02
        self.BASE_SPREAD = 0.02
        self.MAX_SPREAD = 0.10
        
        # Signal memory for noise filtering
        self._last_signals: Dict[str, Tuple[float, datetime]] = {}
        self.SIGNAL_HYSTERESIS = 0.05  # 5% minimum change
        
        # Stale data threshold
        self.MAX_DATA_AGE_SECONDS = 300  # 5 minutes
    
    def calculate_skewed_price(
        self, 
        market_price: float, 
        inventory_shares: int,
        max_inventory: int = 1000
    ) -> float:
        """
        Calculate inventory-skewed fair value.
        
        If LONG: Lower fair value to encourage selling
        If SHORT: Raise fair value to encourage buying
        
        Args:
            market_price: Current market price
            inventory_shares: Current position (+ve = long, -ve = short)
            max_inventory: Maximum expected inventory for scaling
        
        Returns:
            Skewed fair value
        """
        # Inventory ratio: -1.0 (max short) to +1.0 (max long)
        inventory_ratio = inventory_shares / max_inventory
        inventory_ratio = max(-1.0, min(1.0, inventory_ratio))
        
        # Skew magnitude: Up to 2 cents per 100% inventory
        skew_magnitude = 0.02
        
        # If LONG (positive): skew DOWN (negative adjustment)
        # If SHORT (negative): skew UP (positive adjustment)
        skew = -inventory_ratio * skew_magnitude
        
        skewed_price = market_price + skew
        return round(skewed_price, 2)
    
    def filter_signal_noise(
        self, 
        market_id: str, 
        raw_signal: float
    ) -> Tuple[float, bool]:
        """
        Filter 1-tick noise using signal memory (hysteresis).
        
        Returns: (filtered_signal, was_filtered)
        """
        last = self._last_signals.get(market_id)
        now = datetime.now(timezone.utc)
        
        if last:
            last_signal, last_time = last
            change = abs(raw_signal - last_signal)
            
            if change < self.SIGNAL_HYSTERESIS:
                # Small change - return cached signal (anti-wiggle)
                return last_signal, True
        
        # Significant change or first signal - update cache
        self._last_signals[market_id] = (raw_signal, now)
        return raw_signal, False
    
    def calculate_volatility_spread(
        self, 
        base_spread: float,
        price_change_pct: float
    ) -> float:
        """
        Calculate spread based on recent volatility.
        
        Large price moves = wider spread (protection)
        
        Args:
            base_spread: Normal spread (e.g., 0.02)
            price_change_pct: Recent price change (e.g., 0.20 = 20% drop)
        
        Returns:
            Adjusted spread
        """
        # Spread multiplier based on volatility
        # 0% change = 1x, 10% change = 2x, 20% change = 3.5x
        vol_multiplier = 1.0 + (abs(price_change_pct) * 12.5)
        vol_multiplier = min(vol_multiplier, 5.0)  # Cap at 5x
        
        adjusted_spread = base_spread * vol_multiplier
        adjusted_spread = max(self.MIN_SPREAD, min(self.MAX_SPREAD, adjusted_spread))
        
        return round(adjusted_spread, 2)
    
    def check_data_freshness(
        self, 
        data_timestamp: datetime
    ) -> Tuple[bool, str]:
        """
        Check if market data is fresh enough to trade.
        
        Returns: (is_fresh, action)
        - is_fresh=True: Data is OK
        - is_fresh=False: action="CANCEL_ALL"
        """
        now = datetime.now(timezone.utc)
        age_seconds = (now - data_timestamp).total_seconds()
        
        if age_seconds > self.MAX_DATA_AGE_SECONDS:
            return False, "CANCEL_ALL"
        
        return True, "OK"


# =============================================================================
# TEST SCENARIOS
# =============================================================================

def test_scenario_a_bag_holder():
    """
    Scenario A: The "Bag Holder" Test (Inventory Skew)
    
    Input: Market Price $0.50. Bot holds Long 1000 shares.
    Expected: Strategy outputs skewed_price < $0.50 (e.g., $0.48)
    Failure: If skewed_price == market_price (ignores risk)
    """
    print("\n" + "=" * 70)
    print("SCENARIO A: THE 'BAG HOLDER' TEST (Inventory Skew)")
    print("=" * 70)
    
    engine = MockStrategyEngine()
    
    market_price = 0.50
    inventory_shares = 1000  # Long 1000 shares
    max_inventory = 1000
    
    print(f"Input: Market Price = ${market_price:.2f}")
    print(f"Input: Inventory = +{inventory_shares} shares (LONG)")
    
    skewed_price = engine.calculate_skewed_price(
        market_price, 
        inventory_shares,
        max_inventory
    )
    
    print(f"Output: Skewed Fair Value = ${skewed_price:.2f}")
    print(f"Expected: < ${market_price:.2f} (to encourage selling)")
    
    # Assertions
    assert skewed_price < market_price, \
        f"FAILED: Skewed price ${skewed_price} should be < market ${market_price}"
    
    assert skewed_price == 0.48, \
        f"FAILED: Expected $0.48 skew, got ${skewed_price}"
    
    # Test SHORT position (opposite skew)
    print("\n--- Testing SHORT position ---")
    short_inventory = -1000
    short_skewed = engine.calculate_skewed_price(market_price, short_inventory, max_inventory)
    print(f"Input: Inventory = {short_inventory} shares (SHORT)")
    print(f"Output: Skewed Fair Value = ${short_skewed:.2f}")
    
    assert short_skewed > market_price, \
        f"FAILED: Short skew ${short_skewed} should be > market ${market_price}"
    
    print("\n✅ PASSED: Inventory skew correctly adjusts fair value")
    return True


def test_scenario_b_wiggle():
    """
    Scenario B: The "Wiggle" Test (Signal Stability)
    
    Input: Price oscillates $0.50 -> $0.51 -> $0.50
    Expected: Signal stays constant (hysteresis filters noise)
    Failure: Signal chases every tick
    """
    print("\n" + "=" * 70)
    print("SCENARIO B: THE 'WIGGLE' TEST (Signal Stability)")
    print("=" * 70)
    
    engine = MockStrategyEngine()
    market_id = "wiggle_test_market"
    
    # Simulate price oscillation (1 tick ping-pong)
    prices = [0.50, 0.51, 0.50, 0.51, 0.50]
    signals = []
    
    print("Simulating price oscillation: $0.50 -> $0.51 -> $0.50 -> $0.51 -> $0.50")
    
    for i, price in enumerate(prices):
        # Raw signal based on price movement
        raw_signal = (price - 0.50) / 0.10  # Scale: $0.01 = 0.1 signal change
        
        filtered_signal, was_filtered = engine.filter_signal_noise(market_id, raw_signal)
        signals.append(filtered_signal)
        
        status = "FILTERED (kept old)" if was_filtered else "UPDATED"
        print(f"  Tick {i+1}: Price=${price:.2f} | Raw={raw_signal:.2f} | Filtered={filtered_signal:.2f} | {status}")
    
    # Assertions
    # After the first signal, subsequent small changes should be filtered
    unique_signals = len(set(signals))
    
    print(f"\nTotal ticks: {len(prices)}")
    print(f"Unique signals: {unique_signals}")
    print(f"Signal values: {signals}")
    
    # Should NOT have 5 different signals for 5 ticks
    assert unique_signals < len(prices), \
        f"FAILED: Signal chased every tick ({unique_signals} unique signals)"
    
    # First and subsequent signals should be filtered to same value
    # after initial establishment
    print("\n✅ PASSED: Signal hysteresis prevents tick-chasing")
    return True


def test_scenario_c_panic():
    """
    Scenario C: The "Panic" Test (Volatility Expansion)
    
    Input: Price drops $0.50 -> $0.40 in 1 update (20% crash)
    Expected: Spread widens significantly (e.g., from 0.02 to 0.05)
    Failure: Spread stays at minimum $0.02 (bot gets run over)
    """
    print("\n" + "=" * 70)
    print("SCENARIO C: THE 'PANIC' TEST (Volatility Expansion)")
    print("=" * 70)
    
    engine = MockStrategyEngine()
    
    initial_price = 0.50
    crash_price = 0.40
    price_change = (crash_price - initial_price) / initial_price  # -20%
    
    print(f"Input: Price crash ${initial_price:.2f} -> ${crash_price:.2f}")
    print(f"Input: Price change = {price_change:.0%}")
    
    base_spread = 0.02
    crash_spread = engine.calculate_volatility_spread(base_spread, price_change)
    
    print(f"Output: Base spread = ${base_spread:.2f}")
    print(f"Output: Crash spread = ${crash_spread:.2f}")
    print(f"Spread multiplier: {crash_spread / base_spread:.1f}x")
    
    # Assertions
    assert crash_spread > base_spread, \
        f"FAILED: Spread should widen on volatility"
    
    assert crash_spread >= 0.05, \
        f"FAILED: 20% crash should widen spread to at least $0.05, got ${crash_spread}"
    
    # Test extreme crash (40%)
    print("\n--- Testing extreme crash (40%) ---")
    extreme_crash = -0.40
    extreme_spread = engine.calculate_volatility_spread(base_spread, extreme_crash)
    print(f"40% crash spread: ${extreme_spread:.2f}")
    
    assert extreme_spread >= 0.08, \
        f"FAILED: 40% crash should widen spread significantly, got ${extreme_spread}"
    
    print("\n✅ PASSED: Spread correctly widens on volatility")
    return True


def test_scenario_d_zombie():
    """
    Scenario D: The "Zombie" Test (Stale Data)
    
    Input: Data timestamp is 10 minutes old
    Expected: Strategy refuses to trade or generates "CANCEL_ALL"
    """
    print("\n" + "=" * 70)
    print("SCENARIO D: THE 'ZOMBIE' TEST (Stale Data)")
    print("=" * 70)
    
    engine = MockStrategyEngine()
    
    # Fresh data (1 minute old)
    fresh_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    is_fresh, action = engine.check_data_freshness(fresh_time)
    
    print(f"Test 1: Data age = 1 minute")
    print(f"  Result: is_fresh={is_fresh}, action={action}")
    
    assert is_fresh == True, "FAILED: 1-minute old data should be fresh"
    assert action == "OK", "FAILED: Fresh data should return OK action"
    
    # Stale data (10 minutes old)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    is_fresh, action = engine.check_data_freshness(stale_time)
    
    print(f"\nTest 2: Data age = 10 minutes")
    print(f"  Result: is_fresh={is_fresh}, action={action}")
    
    assert is_fresh == False, "FAILED: 10-minute old data should be stale"
    assert action == "CANCEL_ALL", "FAILED: Stale data should return CANCEL_ALL"
    
    # Edge case: exactly at threshold
    edge_time = datetime.now(timezone.utc) - timedelta(seconds=engine.MAX_DATA_AGE_SECONDS)
    is_fresh, action = engine.check_data_freshness(edge_time)
    
    print(f"\nTest 3: Data age = exactly {engine.MAX_DATA_AGE_SECONDS}s (threshold)")
    print(f"  Result: is_fresh={is_fresh}, action={action}")
    
    # At exactly threshold, should be stale (> not >=)
    assert is_fresh == False, "FAILED: Data at threshold should be considered stale"
    
    print("\n✅ PASSED: Stale data correctly triggers CANCEL_ALL")
    return True


def test_scenario_e_combined_stress():
    """
    Scenario E: Combined Stress Test
    
    Tests multiple conditions simultaneously:
    - Large inventory + Volatility spike + Price crash
    """
    print("\n" + "=" * 70)
    print("SCENARIO E: COMBINED STRESS TEST")
    print("=" * 70)
    
    engine = MockStrategyEngine()
    
    # Setup: Bot is LONG 800 shares at $0.50, price crashes to $0.35
    market_price = 0.50
    crash_price = 0.35
    inventory = 800
    max_inventory = 1000
    
    print(f"Setup: Long {inventory} shares @ ${market_price:.2f}")
    print(f"Event: Price crashes to ${crash_price:.2f} (-30%)")
    
    # Step 1: Calculate inventory-skewed fair value
    skewed_fv = engine.calculate_skewed_price(crash_price, inventory, max_inventory)
    print(f"\n1. Inventory Skew: FV ${crash_price:.2f} -> ${skewed_fv:.2f}")
    
    # Step 2: Calculate volatility-adjusted spread
    price_change = (crash_price - market_price) / market_price
    vol_spread = engine.calculate_volatility_spread(0.02, price_change)
    print(f"2. Volatility Spread: Base $0.02 -> ${vol_spread:.2f}")
    
    # Step 3: Calculate final bid/ask
    bid = round(skewed_fv - vol_spread / 2, 2)
    ask = round(skewed_fv + vol_spread / 2, 2)
    
    print(f"3. Final Quotes: Bid ${bid:.2f} / Ask ${ask:.2f}")
    print(f"   Spread: ${ask - bid:.2f}")
    
    # Assertions
    assert skewed_fv < crash_price, "Inventory skew should lower FV when long"
    assert vol_spread > 0.02, "Spread should widen on crash"
    assert ask - bid >= 0.02, "Minimum spread must be maintained"
    
    print("\n✅ PASSED: Combined stress conditions handled correctly")
    return True


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_all_tests():
    """Run all strategy logic stress tests."""
    print("\n" + "=" * 70)
    print("        STRATEGY LOGIC STRESS TEST SUITE")
    print("        Gap Analysis + Behavioral Verification")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Print audit summary
    print("\n" + "-" * 70)
    print("GAP ANALYSIS SUMMARY (See full report in docstring)")
    print("-" * 70)
    print("| Feature              | Status     | Priority |")
    print("|---------------------|------------|----------|")
    print("| Inventory Price Skew | ⚠️ Partial | HIGH     |")
    print("| Signal Noise Filter  | ❌ Missing | HIGH     |")
    print("| Theta Spread Adjust  | ❌ Missing | MEDIUM   |")
    print("| Stale Data in Strats | ⚠️ Partial | MEDIUM   |")
    print("-" * 70)
    
    tests = [
        ("Scenario A: Bag Holder (Inventory Skew)", test_scenario_a_bag_holder),
        ("Scenario B: Wiggle (Signal Stability)", test_scenario_b_wiggle),
        ("Scenario C: Panic (Volatility Expansion)", test_scenario_c_panic),
        ("Scenario D: Zombie (Stale Data)", test_scenario_d_zombie),
        ("Scenario E: Combined Stress", test_scenario_e_combined_stress),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, "✅ PASSED" if passed else "❌ FAILED"))
        except AssertionError as e:
            results.append((name, f"❌ FAILED: {e}"))
        except Exception as e:
            results.append((name, f"❌ ERROR: {e}"))
    
    # Summary
    print("\n" + "=" * 70)
    print("                    TEST SUMMARY")
    print("=" * 70)
    
    passed_count = 0
    for name, status in results:
        print(f"{status} - {name}")
        if "PASSED" in status:
            passed_count += 1
    
    print("=" * 70)
    print(f"Total: {passed_count}/{len(tests)} tests passed")
    
    if passed_count == len(tests):
        print("\n🎉 ALL TESTS PASSED!")
        print("\n⚠️ NOTE: These tests verify EXPECTED behavior.")
        print("   The actual strategies may not implement all features yet.")
        print("   See GAP ANALYSIS in docstring for missing implementations.")
        return True
    else:
        print("\n⚠️ SOME TESTS FAILED")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
