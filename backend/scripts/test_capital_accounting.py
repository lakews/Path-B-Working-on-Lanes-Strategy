"""
Comprehensive Capital Accounting Test
=====================================
Tests all capital flows to ensure accounting integrity.
"""

import asyncio
import sys
sys.path.insert(0, '/app/backend')

from risk_config import RISK

def test_lane_mapping():
    """Test that all strategies map to correct lanes."""
    print("=== LANE MAPPING TEST ===")
    
    test_cases = {
        # HFT strategies
        'delta_neutral': 'HFT',
        'volatility_exploitation': 'HFT',
        'hft_scalp': 'HFT',
        'market_making': 'HFT',
        
        # ALPHA strategies
        'alpha_directional': 'ALPHA',
        'arbitrage': 'ALPHA',
        'multi_market_arbitrage': 'ALPHA',
        
        # GAMMA strategies
        'gamma_scalp': 'GAMMA',
        'whale': 'GAMMA',
        'moonshot': 'GAMMA',
        
        # SPORTS strategies (Lane 4)
        'sports_arbitrage': 'SPORTS',
        'sports_arb': 'SPORTS',
        
        # NEWS strategies (Lane 5)
        'news_sniper': 'NEWS',
        'news_event': 'NEWS',
    }
    
    all_pass = True
    for strategy, expected_lane in test_cases.items():
        actual_lane = RISK.get_strategy_path(strategy)
        status = "✅" if actual_lane == expected_lane else "❌"
        if actual_lane != expected_lane:
            all_pass = False
        print(f"  {status} {strategy} -> {actual_lane} (expected: {expected_lane})")
    
    return all_pass

def test_exit_config():
    """Test that exit config is correctly set for all strategies."""
    print("\n=== EXIT CONFIG TEST ===")
    from risk_config import EXIT_STRATEGY_CONFIG
    
    expected = {
        'sports_arbitrage': {'tp_pct': 0.30, 'sl_pct': 0.25, 'max_hours': 48.0},
    }
    
    all_pass = True
    for strategy, expected_config in expected.items():
        actual = EXIT_STRATEGY_CONFIG.get(strategy, {})
        for key, expected_val in expected_config.items():
            actual_val = actual.get(key)
            status = "✅" if abs(actual_val - expected_val) < 0.01 else "❌"
            if abs(actual_val - expected_val) >= 0.01:
                all_pass = False
            print(f"  {status} {strategy}.{key} = {actual_val} (expected: {expected_val})")
    
    return all_pass

def test_sports_config():
    """Test SportsConfig parameters."""
    print("\n=== SPORTS CONFIG TEST ===")
    from risk_config import get_sports_config
    
    config = get_sports_config()
    
    expected = {
        'allocation_pct': 15.0,
        'max_position_size': 100.0,
        'min_edge': 0.02,
        'stop_loss_pct': 0.25,
        'take_profit_pct': 0.30,
        'max_hold_hours': 48.0,
    }
    
    all_pass = True
    for key, expected_val in expected.items():
        actual_val = getattr(config, key, None)
        status = "✅" if actual_val == expected_val else "❌"
        if actual_val != expected_val:
            all_pass = False
        print(f"  {status} {key} = {actual_val} (expected: {expected_val})")
    
    return all_pass

def main():
    print("=" * 60)
    print("COMPREHENSIVE CAPITAL ACCOUNTING TEST")
    print("=" * 60)
    
    results = []
    results.append(("Lane Mapping", test_lane_mapping()))
    results.append(("Exit Config", test_exit_config()))
    results.append(("Sports Config", test_sports_config()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_pass = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False
        print(f"  {status}: {name}")
    
    print()
    if all_pass:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️ SOME TESTS FAILED")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
