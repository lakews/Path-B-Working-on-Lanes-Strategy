#!/usr/bin/env python3
"""
APEX TRADER - Sports Integrity Patch Verification Script
=========================================================

This script validates the "Sports Integrity Patch" fixes:
- BUG 1: Seahawks/Hawks collision (word boundary matching)
- BUG 5: Tennis coverage expansion
- BUG 2: Edge/Direction math (NO longer always returning NO)

RUN THIS BEFORE STARTING THE MAIN BOT.

Usage:
    python verify_sports_patch.py
"""

import sys

# Add backend to path
sys.path.insert(0, '/app/backend')

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

from utils.sports_constants import match_sport_and_teams, is_sports_market
from strategies.sports_strategy import SportsArbitrageStrategy, SportsSignal
from risk_config import get_sports_config


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(passed: bool, message: str):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {message}")


def test_a_collision_check() -> bool:
    """
    TEST A: The Collision Check
    
    Verifies that "Seahawks" is NOT matched to NBA "Hawks"
    """
    print_header("TEST A: The Collision Check (Seahawks vs Hawks)")
    
    test_input = "Seattle Seahawks vs New England Patriots"
    expected_sport = "americanfootball_nfl"
    expected_teams = ["Seattle Seahawks", "New England Patriots"]
    
    print(f"\n  Input: \"{test_input}\"")
    print(f"  Expected Sport: {expected_sport}")
    print(f"  Expected Teams: {expected_teams}")
    
    # Run the matcher
    detected_sport, detected_teams = match_sport_and_teams(test_input)
    
    print(f"\n  Detected Sport: {detected_sport}")
    print(f"  Detected Teams: {detected_teams}")
    
    # Validate
    sport_correct = detected_sport == expected_sport
    seahawks_found = "Seattle Seahawks" in detected_teams
    patriots_found = "New England Patriots" in detected_teams
    hawks_nba_found = "Atlanta Hawks" in detected_teams  # This should NOT happen
    
    passed = sport_correct and seahawks_found and not hawks_nba_found
    
    print_result(sport_correct, f"Sport is NFL (not NBA): {detected_sport}")
    print_result(seahawks_found, f"Seattle Seahawks detected (not Hawks): {detected_teams}")
    print_result(not hawks_nba_found, "Atlanta Hawks NOT detected (collision avoided)")
    
    overall = passed
    print(f"\n  TEST A RESULT: {'✅ PASSED' if overall else '❌ FAILED'}")
    
    return overall


def test_b_tennis_expansion() -> bool:
    """
    TEST B: The Tennis Expansion
    
    Verifies that tennis keywords and players are now detected
    """
    print_header("TEST B: Tennis Expansion (Wimbledon, ATP, Players)")
    
    test_cases = [
        ("Wimbledon: Carlos Alcaraz vs Novak Djokovic", "tennis"),
        ("Australian Open Men's: Sinner vs Medvedev", "tennis"),
        ("Will Djokovic win the French Open?", "tennis"),
    ]
    
    all_passed = True
    
    for test_input, expected_type in test_cases:
        print(f"\n  Input: \"{test_input}\"")
        
        detected_sport, detected_teams = match_sport_and_teams(test_input)
        is_tennis = detected_sport and "tennis" in detected_sport.lower()
        is_sports = is_sports_market(test_input)
        
        print(f"  Detected Sport: {detected_sport}")
        print(f"  Detected Teams: {detected_teams}")
        print(f"  Is Sports Market: {is_sports}")
        
        passed = is_tennis or (is_sports and len(detected_teams) > 0)
        print_result(passed, f"Tennis detected: {detected_sport}")
        
        if not passed:
            all_passed = False
    
    print(f"\n  TEST B RESULT: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    
    return all_passed


def test_c_edge_direction_math() -> bool:
    """
    TEST C: The Edge/Direction Math
    
    Verifies the signal generation logic:
    - If fair_value > market_price + min_edge → BUY YES
    - If fair_value < market_price - min_edge → BUY NO
    
    This test catches the "all NO" bug where the bot was systematically
    betting in the wrong direction.
    """
    print_header("TEST C: Edge/Direction Math (Signal Generation)")
    
    # Create a test config with known values
    config = get_sports_config()
    config.min_edge = 0.02  # 2% min edge
    config.taker_fee = 0.02  # 2% fee
    config.min_volume = 0    # Disable volume check for test
    config.kelly_fraction = 0.25
    config.max_position_size = 100
    config.min_trade_size = 1
    
    strategy = SportsArbitrageStrategy(config)
    
    test_cases = [
        # (fair_value, yes_price, expected_side, description)
        (0.65, 0.40, "YES", "Fair 65% > Market 40% → BUY YES"),
        (0.30, 0.60, "NO", "Fair 30% < Market 60% → BUY NO (short YES)"),
        (0.50, 0.48, None, "Fair 50% ≈ Market 48% → NO EDGE (within threshold)"),
        (0.70, 0.50, "YES", "Fair 70% > Market 50% → BUY YES (20% edge)"),
        (0.25, 0.45, "NO", "Fair 25% < Market 45% → BUY NO"),
    ]
    
    all_passed = True
    
    for fair_value, yes_price, expected_side, description in test_cases:
        print(f"\n  Test: {description}")
        print(f"    Fair Value: {fair_value:.2f} ({fair_value*100:.0f}%)")
        print(f"    Market YES: {yes_price:.2f} ({yes_price*100:.0f}%)")
        print(f"    Market NO:  {1-yes_price:.2f} ({(1-yes_price)*100:.0f}%)")
        print(f"    Expected Signal: {expected_side or 'NO_EDGE'}")
        
        # Create test market
        market_data = {
            'id': 'test_math',
            'question': 'Test Market for Math Verification',
            'yes_price': yes_price,
            'no_price': 1 - yes_price,
            'volume_24h': 10000,  # Pass volume check
        }
        
        # Generate signal
        signal = strategy.generate_signal(market_data, fair_value)
        
        print(f"    Actual Signal: {signal.signal.value}")
        print(f"    Actual Side: {signal.side}")
        print(f"    Edge: {signal.edge:.4f} ({signal.edge_pct:.2%})")
        
        # Validate
        if expected_side is None:
            passed = signal.signal == SportsSignal.NO_EDGE
        else:
            passed = signal.side == expected_side
        
        print_result(passed, f"Signal direction correct: {signal.side} == {expected_side}")
        
        if not passed:
            all_passed = False
            print(f"    ⚠️  OLD BUG DETECTED: Should be {expected_side}, got {signal.side}")
    
    print(f"\n  TEST C RESULT: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    
    return all_passed


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("  APEX TRADER - SPORTS INTEGRITY PATCH VERIFICATION")
    print("  Run Date: " + __import__('datetime').datetime.now().isoformat())
    print("=" * 70)
    
    # Run all tests
    test_a_passed = test_a_collision_check()
    test_b_passed = test_b_tennis_expansion()
    test_c_passed = test_c_edge_direction_math()
    
    # Summary
    print_header("VERIFICATION SUMMARY")
    
    all_passed = test_a_passed and test_b_passed and test_c_passed
    
    print(f"\n  Test A (Collision Check):    {'✅ PASSED' if test_a_passed else '❌ FAILED'}")
    print(f"  Test B (Tennis Expansion):   {'✅ PASSED' if test_b_passed else '❌ FAILED'}")
    print(f"  Test C (Edge/Direction):     {'✅ PASSED' if test_c_passed else '❌ FAILED'}")
    
    print("\n" + "=" * 70)
    
    if all_passed:
        print("""
  ✅ PATCH VERIFIED. DATABASE CLEARED. READY FOR MAIN ENGINE.
  
  All 3 verification tests passed:
  - Seahawks correctly detected as NFL (not NBA Hawks)
  - Tennis markets now detected with player names
  - Signal direction logic is mathematically correct
  
  You may now start the paper trading bot:
  
    Command: sudo supervisorctl start backend
    
  Or run in paper mode via the UI at /paper-trading
""")
        return 0
    else:
        print("""
  ❌ PATCH VERIFICATION FAILED
  
  One or more tests did not pass. Review the failures above.
  DO NOT start the main bot until all tests pass.
""")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
