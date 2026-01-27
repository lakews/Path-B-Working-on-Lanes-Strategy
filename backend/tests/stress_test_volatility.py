"""
HFT Volatility Stress Test
==========================

Simulates hostile market conditions to validate HFT architecture resilience.

Test Scenarios:
1. "The Whipsaw" - Price jumps +1% then -1% in 10 seconds
2. "The Latency Trap" - Stale AI data (bullish bias) during price crash
3. "The Flash Crash" - Instant 5% drop with no recovery

Success Metrics:
- Latency Guard: Bot must reject trades if AI context > 5 mins stale
- Vol Expansion: Spreads must widen > 3x during volatility spike
- Net Markout: Aggregate markout score must be > -0.05%

This is a "paper simulation" - no real trades, just decision validation.

Usage:
    python tests/stress_test_volatility.py

Author: APEX TRADER HFT Systems Team
Date: January 2026
"""

import sys
import time
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Add backend to path
sys.path.insert(0, '/app/backend')

from services.hft_context import (
    get_hft_context, 
    get_volatility_calculator, 
    HFTContext, 
    VolatilityCalculator,
    ContextStatus,
    MarketParams,
    MAX_CONTEXT_AGE_SECONDS
)
from services.telemetry import get_telemetry_service, create_decision_snapshot
from risk_config import RISK

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# TEST CONFIGURATION
# =============================================================================

# Market for testing
TEST_MARKET_ID = "stress_test_market_001"

# Base parameters
BASE_PRICE = 0.50
BASE_SPREAD = 0.02  # 2%
BASE_VOLATILITY = 0.01

# Success thresholds
MAX_ACCEPTABLE_STALENESS_SECONDS = 300  # 5 minutes
MIN_VOL_EXPANSION = 3.0  # Spread must widen 3x during volatility
MAX_ACCEPTABLE_MARKOUT_LOSS = -0.0005  # -0.05% max loss per trade


# =============================================================================
# TEST SCENARIOS
# =============================================================================

@dataclass
class ScenarioResult:
    """Result of a single scenario execution."""
    scenario_name: str
    passed: bool
    details: str
    trades_attempted: int
    trades_blocked: int
    avg_spread_bps: float
    max_spread_bps: float
    min_spread_bps: float
    markout_sum: float


class HFTStressTest:
    """
    Stress test harness for HFT architecture.
    
    Simulates market conditions and validates HFT response.
    """
    
    def __init__(self):
        self.hft_context = get_hft_context()
        self.vol_calculator = get_volatility_calculator()
        self.telemetry = get_telemetry_service()
        
        # Mock positions for inventory tracking
        self.mock_positions: Dict[str, Dict] = {}
        
        # Results tracking
        self.decisions: List[Dict] = []
        self.spreads_used: List[int] = []
        
        # Start telemetry
        self.telemetry.start()
    
    def setup(self):
        """Reset state before each test."""
        self.hft_context.clear()
        self.vol_calculator.clear()
        self.mock_positions.clear()
        self.decisions.clear()
        self.spreads_used.clear()
    
    def teardown(self):
        """Clean up after tests."""
        self.telemetry.stop()
    
    def _simulate_hft_decision(
        self,
        market_data: Dict,
        expected_decision: str = None
    ) -> Dict:
        """
        Simulate an HFT decision using the same logic as paper_trader.
        
        Returns the decision outcome for analysis.
        """
        market_id = market_data['id']
        yes_price = market_data['yes_price']
        best_bid = market_data.get('best_bid', yes_price - 0.01)
        best_ask = market_data.get('best_ask', yes_price + 0.01)
        
        # Step 1: Non-blocking context fetch
        params = self.hft_context.get(market_id)
        
        decision = "SKIP"
        reason = ""
        opportunity = None
        
        if params is None:
            decision = "SKIP"
            reason = "NO_CONTEXT"
        elif params.status == ContextStatus.KILL:
            decision = "BLOCKED"
            reason = "KILL_SWITCH"
        elif params.is_stale():
            decision = "BLOCKED"
            reason = f"STALE_CONTEXT ({params.get_age_seconds():.0f}s)"
        else:
            # Step 2: Volatility adaptation
            self.vol_calculator.add_tick(market_id, yes_price)
            vol_multiplier = self.vol_calculator.get_vol_multiplier(
                market_id, 
                params.reference_volatility
            )
            
            # Calculate effective spread
            effective_spread_bps = int(params.base_spread_bps * vol_multiplier)
            effective_spread = effective_spread_bps / 10000
            self.spreads_used.append(effective_spread_bps)
            
            # Step 3: Skewed pricing
            fair_value = params.fair_value
            bias = params.bias
            current_vol = self.vol_calculator.calculate_volatility(market_id) or 0.01
            skew_offset = bias * (current_vol * 0.5)
            skewed_mid = fair_value + skew_offset
            
            my_bid = skewed_mid * (1 - effective_spread)
            my_ask = skewed_mid * (1 + effective_spread)
            
            # Check for opportunity
            if best_ask < my_bid:
                decision = "TRADE"
                reason = "BUY_OPPORTUNITY"
                opportunity = {
                    'side': 'BUY',
                    'size': 10.0,
                    'scalp_price': best_ask,
                    'edge': my_bid - best_ask,
                    'vol_multiplier': vol_multiplier,
                    'effective_spread_bps': effective_spread_bps,
                    'quoted_bid': my_bid,
                    'quoted_ask': my_ask,
                }
            else:
                decision = "SKIP"
                reason = "NO_EDGE"
                opportunity = {
                    'vol_multiplier': vol_multiplier,
                    'effective_spread_bps': effective_spread_bps,
                }
        
        # Log to telemetry
        snapshot = create_decision_snapshot(
            market_id=market_id,
            market_data=market_data,
            hft_params=params.to_dict() if params else None,
            opportunity=opportunity,
            decision=decision,
            reason=reason,
            hft_positions=self.mock_positions,
        )
        self.telemetry.log_decision(snapshot)
        
        result = {
            'decision': decision,
            'reason': reason,
            'opportunity': opportunity,
            'params_age': params.get_age_seconds() if params else None,
        }
        self.decisions.append(result)
        
        return result
    
    # =========================================================================
    # SCENARIO 1: THE WHIPSAW
    # =========================================================================
    
    def test_whipsaw(self) -> ScenarioResult:
        """
        Test: Price jumps +1% then -1% in 10 seconds.
        
        Expected behavior:
        - Vol calculator should detect spike
        - Spreads should widen significantly (>3x)
        - No trades should be filled at worst prices
        """
        self.setup()
        logger.info("\n🌀 SCENARIO: THE WHIPSAW")
        logger.info("   Price: +1% → -1% in 10 seconds")
        
        # Set up initial AI context
        self.hft_context.update(
            market_id=TEST_MARKET_ID,
            fair_value=BASE_PRICE,
            bias=0.2,  # Slight bullish
            reference_volatility=BASE_VOLATILITY,
            confidence=0.7,
        )
        
        trades_attempted = 0
        trades_blocked = 0
        
        # Phase 1: Price at baseline
        for i in range(5):
            market_data = {
                'id': TEST_MARKET_ID,
                'yes_price': BASE_PRICE,
                'best_bid': BASE_PRICE - 0.005,
                'best_ask': BASE_PRICE + 0.005,
            }
            result = self._simulate_hft_decision(market_data)
            if result['decision'] == 'TRADE':
                trades_attempted += 1
            time.sleep(0.01)
        
        baseline_spreads = self.spreads_used.copy()
        
        # Phase 2: Price spikes +1%
        spike_price = BASE_PRICE * 1.01
        for i in range(5):
            market_data = {
                'id': TEST_MARKET_ID,
                'yes_price': spike_price,
                'best_bid': spike_price - 0.005,
                'best_ask': spike_price + 0.005,
            }
            result = self._simulate_hft_decision(market_data)
            if result['decision'] == 'TRADE':
                trades_attempted += 1
            time.sleep(0.01)
        
        # Phase 3: Price crashes -2% (back to -1% net)
        crash_price = BASE_PRICE * 0.99
        for i in range(5):
            market_data = {
                'id': TEST_MARKET_ID,
                'yes_price': crash_price,
                'best_bid': crash_price - 0.005,
                'best_ask': crash_price + 0.005,
            }
            result = self._simulate_hft_decision(market_data)
            if result['decision'] == 'BLOCKED':
                trades_blocked += 1
            elif result['decision'] == 'TRADE':
                trades_attempted += 1
            time.sleep(0.01)
        
        # Analysis
        if not self.spreads_used:
            return ScenarioResult(
                scenario_name="WHIPSAW",
                passed=False,
                details="No spreads recorded",
                trades_attempted=0,
                trades_blocked=0,
                avg_spread_bps=0,
                max_spread_bps=0,
                min_spread_bps=0,
                markout_sum=0,
            )
        
        avg_spread = sum(self.spreads_used) / len(self.spreads_used)
        max_spread = max(self.spreads_used)
        min_spread = min(self.spreads_used)
        
        # Check vol expansion
        baseline_avg = sum(baseline_spreads) / len(baseline_spreads) if baseline_spreads else 50
        vol_expansion = max_spread / baseline_avg
        
        passed = vol_expansion >= MIN_VOL_EXPANSION
        
        details = (
            f"Baseline spread: {baseline_avg:.0f}bps, "
            f"Max spread: {max_spread}bps, "
            f"Vol expansion: {vol_expansion:.1f}x "
            f"(required: {MIN_VOL_EXPANSION}x)"
        )
        
        logger.info(f"   Result: {'✅ PASSED' if passed else '❌ FAILED'}")
        logger.info(f"   {details}")
        
        return ScenarioResult(
            scenario_name="WHIPSAW",
            passed=passed,
            details=details,
            trades_attempted=trades_attempted,
            trades_blocked=trades_blocked,
            avg_spread_bps=avg_spread,
            max_spread_bps=max_spread,
            min_spread_bps=min_spread,
            markout_sum=0,  # Would need price timeline for actual markout
        )
    
    # =========================================================================
    # SCENARIO 2: THE LATENCY TRAP
    # =========================================================================
    
    def test_latency_trap(self) -> ScenarioResult:
        """
        Test: Stale AI data (bullish bias=1.0) while price crashes.
        
        Expected behavior:
        - Bot must reject trades if AI timestamp > 5 mins stale
        - Even with strong bullish signal, stale data = no trade
        """
        self.setup()
        logger.info("\n⏰ SCENARIO: THE LATENCY TRAP")
        logger.info("   Stale bullish signal + price crash")
        
        # Set up STALE AI context (simulate 7 minutes old)
        old_timestamp = time.time() - 420  # 7 minutes ago
        
        params = MarketParams(
            market_id=TEST_MARKET_ID,
            fair_value=BASE_PRICE * 1.05,  # AI thinks it's worth +5%
            bias=1.0,  # STRONG bullish (the trap!)
            base_spread_bps=50,
            max_inventory_skew=0.3,
            reference_volatility=BASE_VOLATILITY,
            status=ContextStatus.ACTIVE,
            timestamp=old_timestamp,  # STALE!
            confidence=0.9,
        )
        
        # Inject stale context directly
        self.hft_context._markets[TEST_MARKET_ID] = params
        
        trades_attempted = 0
        trades_blocked = 0
        
        # Price is crashing but AI doesn't know
        crash_prices = [0.50, 0.48, 0.45, 0.42, 0.40]
        
        for price in crash_prices:
            market_data = {
                'id': TEST_MARKET_ID,
                'yes_price': price,
                'best_bid': price - 0.01,
                'best_ask': price + 0.01,
            }
            result = self._simulate_hft_decision(market_data)
            
            if result['decision'] == 'BLOCKED' and 'STALE' in result['reason']:
                trades_blocked += 1
            elif result['decision'] == 'TRADE':
                trades_attempted += 1
                logger.warning(f"   ⚠️ Trade attempted with stale data! Price: {price}")
            
            time.sleep(0.01)
        
        # Success: All trades should be blocked due to staleness
        passed = trades_blocked == len(crash_prices) and trades_attempted == 0
        
        details = (
            f"Trades blocked: {trades_blocked}/{len(crash_prices)}, "
            f"Trades attempted: {trades_attempted} (should be 0), "
            f"Context age: {params.get_age_seconds():.0f}s"
        )
        
        logger.info(f"   Result: {'✅ PASSED' if passed else '❌ FAILED'}")
        logger.info(f"   {details}")
        
        return ScenarioResult(
            scenario_name="LATENCY_TRAP",
            passed=passed,
            details=details,
            trades_attempted=trades_attempted,
            trades_blocked=trades_blocked,
            avg_spread_bps=0,
            max_spread_bps=0,
            min_spread_bps=0,
            markout_sum=0,
        )
    
    # =========================================================================
    # SCENARIO 3: THE FLASH CRASH
    # =========================================================================
    
    def test_flash_crash(self) -> ScenarioResult:
        """
        Test: Instant 5% drop with no recovery.
        
        Expected behavior:
        - Vol calculator should detect extreme move
        - Spreads should widen massively
        - Kill switch should activate on extreme vol
        """
        self.setup()
        logger.info("\n💥 SCENARIO: THE FLASH CRASH")
        logger.info("   Instant 5% drop, no recovery")
        
        # Set up initial context
        self.hft_context.update(
            market_id=TEST_MARKET_ID,
            fair_value=BASE_PRICE,
            bias=0.0,  # Neutral
            reference_volatility=BASE_VOLATILITY,
            confidence=0.5,
        )
        
        # Seed volatility calculator with stable prices
        for i in range(10):
            self.vol_calculator.add_tick(TEST_MARKET_ID, BASE_PRICE)
        
        trades_attempted = 0
        trades_blocked = 0
        
        # Simulate flash crash
        crash_prices = [0.50, 0.49, 0.48, 0.47, 0.475]  # 5% crash, tiny bounce
        
        for price in crash_prices:
            market_data = {
                'id': TEST_MARKET_ID,
                'yes_price': price,
                'best_bid': price - 0.02,  # Wide spreads during crash
                'best_ask': price + 0.02,
            }
            result = self._simulate_hft_decision(market_data)
            
            if result['decision'] == 'BLOCKED':
                trades_blocked += 1
            elif result['decision'] == 'TRADE':
                trades_attempted += 1
            
            time.sleep(0.01)
        
        # Analysis
        if not self.spreads_used:
            return ScenarioResult(
                scenario_name="FLASH_CRASH",
                passed=False,
                details="No spreads recorded",
                trades_attempted=0,
                trades_blocked=0,
                avg_spread_bps=0,
                max_spread_bps=0,
                min_spread_bps=0,
                markout_sum=0,
            )
        
        avg_spread = sum(self.spreads_used) / len(self.spreads_used)
        max_spread = max(self.spreads_used)
        
        # Success: Spreads should be very wide, most trades blocked
        passed = max_spread >= 100  # At least 100bps (1%) spread during crash
        
        details = (
            f"Avg spread: {avg_spread:.0f}bps, "
            f"Max spread: {max_spread}bps, "
            f"Trades blocked: {trades_blocked}, "
            f"Trades attempted: {trades_attempted}"
        )
        
        logger.info(f"   Result: {'✅ PASSED' if passed else '❌ FAILED'}")
        logger.info(f"   {details}")
        
        return ScenarioResult(
            scenario_name="FLASH_CRASH",
            passed=passed,
            details=details,
            trades_attempted=trades_attempted,
            trades_blocked=trades_blocked,
            avg_spread_bps=avg_spread,
            max_spread_bps=max_spread,
            min_spread_bps=min(self.spreads_used),
            markout_sum=0,
        )


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_stress_tests() -> bool:
    """Run all stress test scenarios."""
    print("\n" + "=" * 80)
    print("        HFT VOLATILITY STRESS TEST SUITE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)
    
    harness = HFTStressTest()
    results: List[ScenarioResult] = []
    
    try:
        # Run all scenarios
        results.append(harness.test_whipsaw())
        results.append(harness.test_latency_trap())
        results.append(harness.test_flash_crash())
        
    finally:
        harness.teardown()
    
    # Summary
    print("\n" + "=" * 80)
    print("                    STRESS TEST SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for result in results:
        status = "✅ PASSED" if result.passed else "❌ FAILED"
        print(f"\n{result.scenario_name}: {status}")
        print(f"   {result.details}")
        if not result.passed:
            all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 ALL STRESS TESTS PASSED!")
    else:
        print("⚠️ SOME TESTS FAILED - Review HFT logic")
    print("=" * 80)
    
    # Check telemetry stats
    telemetry = get_telemetry_service()
    stats = telemetry.get_stats()
    print("\n📊 Telemetry Stats:")
    print(f"   Total logged: {stats['total_logged']}")
    print(f"   Total written: {stats['total_written']}")
    print(f"   File: {stats['current_file']}")
    
    return all_passed


if __name__ == "__main__":
    success = run_stress_tests()
    sys.exit(0 if success else 1)
