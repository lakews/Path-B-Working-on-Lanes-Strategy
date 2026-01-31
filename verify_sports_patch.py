#!/usr/bin/env python3
"""
APEX TRADER - Sports Integrity Patch Verification Script
=========================================================

Clean Slate Validation Protocol - Phase 2: Logic Stress Test

This script runs 3 mandatory tests to verify the Sports Integrity Patch:
1. Test A (Collision Check): Seahawks must NOT match Hawks (NBA)
2. Test B (Tennis Expansion): Wimbledon matches must detect tennis
3. Test C (Edge/Direction Math): Correct YES/NO signal generation

USAGE:
    python verify_sports_patch.py

EXIT CODES:
    0 = All tests passed, ready to start main bot
    1 = One or more tests failed, DO NOT start main bot
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from colorama import Fore, Style, init

# Initialize colorama for cross-platform colors
init(autoreset=True)


def banner(text):
    """Print a banner."""
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def success(text):
    """Print success message."""
    print(f"{Fore.GREEN}[PASS]{Style.RESET_ALL} {text}")


def failure(text):
    """Print failure message."""
    print(f"{Fore.RED}[FAIL]{Style.RESET_ALL} {text}")


def info(text):
    """Print info message."""
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {text}")


def run_test_a_collision_check():
    """
    TEST A: The Collision Check (BUG 1 FIX)
    
    Input: "Seattle Seahawks vs New England Patriots"
    Expected: Sport = 'americanfootball_nfl' (NOT NBA)
    
    The old code had "Hawks" match before "Seahawks", causing the 
    Seahawks to be incorrectly classified as the Atlanta Hawks (NBA).
    
    The fix uses:
    1. Word boundary regex matching (\\bSeahawks\\b)
    2. Longest match first strategy (Seahawks > Hawks)
    """
    banner("TEST A: Collision Check (Seahawks vs Hawks)")
    
    from utils.sports_constants import match_sport_and_teams, detect_sport
    
    test_cases = [
        ("Seattle Seahawks vs New England Patriots", 'americanfootball_nfl', ['Seattle Seahawks']),
        ("Will the Seahawks beat the Patriots?", 'americanfootball_nfl', ['Seattle Seahawks', 'New England Patriots']),
        ("Hawks vs Celtics", 'basketball_nba', ['Atlanta Hawks', 'Boston Celtics']),
        ("Atlanta Hawks game tonight", 'basketball_nba', ['Atlanta Hawks']),
    ]
    
    all_passed = True
    
    for question, expected_sport, expected_teams_partial in test_cases:
        sport_key, teams = match_sport_and_teams(question)
        
        info(f"Question: '{question}'")
        info(f"  -> Sport: {sport_key}, Teams: {teams}")
        
        # Check sport detection
        if sport_key != expected_sport:
            failure(f"  Sport mismatch! Expected '{expected_sport}', got '{sport_key}'")
            all_passed = False
        else:
            success(f"  Sport correctly detected as '{sport_key}'")
        
        # Check at least one expected team is found
        found_expected = any(t in teams for t in expected_teams_partial)
        if not found_expected:
            failure(f"  Expected one of {expected_teams_partial} in {teams}")
            all_passed = False
        else:
            success(f"  Team(s) correctly matched")
    
    # Critical test: Seahawks must NOT be detected as NBA
    critical_question = "Seattle Seahawks vs Arizona Cardinals"
    sport_key, teams = match_sport_and_teams(critical_question)
    
    info(f"\nCRITICAL TEST: '{critical_question}'")
    
    if 'nba' in (sport_key or '').lower() or 'basketball' in (sport_key or '').lower():
        failure(f"  CRITICAL: Detected as NBA ({sport_key})! This is the Seahawks/Hawks bug!")
        all_passed = False
    elif 'Atlanta Hawks' in teams:
        # Only fail if the exact team "Atlanta Hawks" is in the list
        failure(f"  CRITICAL: Matched Atlanta Hawks! Teams: {teams}")
        all_passed = False
    else:
        success(f"  Sport: {sport_key}, Teams: {teams} - Correctly avoided NBA/Hawks collision")
    
    return all_passed


def run_test_b_tennis_expansion():
    """
    TEST B: Tennis Expansion (BUG 5 FIX)
    
    Input: "Wimbledon: Carlos Alcaraz vs Novak Djokovic"
    Expected: Sport detected, NOT None/Unknown
    
    Tennis keywords and players were missing from the original constants.
    """
    banner("TEST B: Tennis Expansion")
    
    from utils.sports_constants import match_sport_and_teams, detect_sport, is_sports_market
    
    test_cases = [
        ("Wimbledon: Carlos Alcaraz vs Novak Djokovic", True),
        ("Will Djokovic win the Australian Open?", True),
        ("Sinner vs Medvedev ATP Finals", True),
        ("US Open Tennis: Gauff vs Swiatek", True),
        ("Will Rafael Nadal play at Roland Garros?", True),
    ]
    
    all_passed = True
    
    for question, should_be_sports in test_cases:
        is_sports = is_sports_market(question)
        sport_key = detect_sport(question)
        
        info(f"Question: '{question}'")
        info(f"  -> is_sports: {is_sports}, sport_key: {sport_key}")
        
        if should_be_sports and not is_sports:
            failure(f"  Should be detected as sports market!")
            all_passed = False
        elif should_be_sports and sport_key is None:
            failure(f"  Sport key is None! Tennis not properly expanded.")
            all_passed = False
        elif should_be_sports and 'tennis' not in (sport_key or '').lower():
            failure(f"  Sport key '{sport_key}' doesn't contain 'tennis'")
            all_passed = False
        else:
            success(f"  Correctly detected as tennis")
    
    # Check that tennis players are in the database
    from utils.sports_constants import TEAM_DATABASE
    
    tennis_players = ['djokovic', 'alcaraz', 'sinner', 'nadal', 'federer', 'swiatek', 'gauff']
    missing = [p for p in tennis_players if p not in TEAM_DATABASE]
    
    if missing:
        failure(f"  Missing tennis players in database: {missing}")
        all_passed = False
    else:
        success(f"  All major tennis players present in TEAM_DATABASE")
    
    return all_passed


def run_test_c_edge_direction_math():
    """
    TEST C: Edge/Direction Math (BUG 2 FIX)
    
    Input: Fair_Win_Prob = 0.65, Market_Yes_Price = 0.40 (Implied 40%)
    Expected: Signal = YES (Buy YES because fair value > market price)
    
    The old logic had a bug where it would always generate NO signals
    regardless of the actual edge direction.
    
    CORRECT MATH:
    - YES edge = fair_value - yes_price = 0.65 - 0.40 = +0.25 (YES is underpriced!)
    - NO edge = (1 - fair_value) - no_price = 0.35 - 0.60 = -0.25 (NO is overpriced)
    - Signal: BUY YES (because YES has positive edge)
    """
    banner("TEST C: Edge/Direction Math")
    
    from strategies.sports_strategy import SportsArbitrageStrategy, SportsSignal
    from risk_config import SportsConfig
    
    # Create a test config
    config = SportsConfig(
        enabled=True,
        min_edge=0.02,
        taker_fee=0.02,
        min_volume=0,  # Disable volume check for test
        allocation_pct=10,
        total_capital=10000,
        max_position_size=100,
        kelly_fraction=0.25,
        min_kelly=0.05,
        max_kelly=0.20,
        min_trade_size=5.0,
    )
    
    strategy = SportsArbitrageStrategy(config)
    
    test_cases = [
        # (fair_value, yes_price, expected_side, description)
        (0.65, 0.40, 'YES', "Fair=0.65 > Price=0.40: YES is underpriced, BUY YES"),
        (0.35, 0.60, 'NO', "Fair=0.35 < Price=0.60: NO is underpriced, BUY NO"),
        (0.50, 0.50, None, "Fair=Price: No edge, should HOLD"),
        (0.70, 0.65, 'YES', "Fair=0.70 > Price=0.65: Small YES edge after fees"),
        (0.30, 0.35, 'NO', "Fair=0.30 < Price=0.35: Small NO edge after fees"),
        (0.55, 0.52, None, "Edge too small after fees: Should HOLD"),
    ]
    
    all_passed = True
    
    for fair_value, yes_price, expected_side, description in test_cases:
        # Create mock market data
        market_data = {
            'id': 'test_market',
            'yes_price': yes_price,
            'volume_24h': 10000,  # Pass volume filter
        }
        
        # Generate signal
        signal = strategy.generate_signal(market_data, fair_value)
        
        info(f"\n{description}")
        info(f"  FV={fair_value:.2f}, YES_Price={yes_price:.2f}, NO_Price={1-yes_price:.2f}")
        info(f"  YES_Edge={fair_value - yes_price:.4f}, NO_Edge={(1-fair_value) - (1-yes_price):.4f}")
        info(f"  -> Signal: {signal.signal.value}, Side: {signal.side}, Edge: {signal.edge:.4f}")
        
        # Verify result
        if expected_side is None:
            # Should be HOLD or NO_EDGE
            if signal.signal in [SportsSignal.HOLD, SportsSignal.NO_EDGE]:
                success(f"  Correctly held (no tradeable edge)")
            else:
                failure(f"  Should have held but got {signal.signal.value} {signal.side}")
                all_passed = False
        else:
            # Should have generated the expected signal
            if signal.side == expected_side:
                success(f"  Correctly generated {expected_side} signal")
            else:
                failure(f"  Expected {expected_side} but got {signal.side} ({signal.signal.value})")
                all_passed = False
    
    # Critical test: Fair=0.65, Price=0.40 MUST generate YES, not NO
    info("\nCRITICAL TEST: Fair=0.65, Price=0.40 must generate YES signal")
    
    market_data = {'id': 'critical_test', 'yes_price': 0.40, 'volume_24h': 10000}
    signal = strategy.generate_signal(market_data, 0.65)
    
    if signal.side == 'NO':
        failure(f"  CRITICAL: Generated NO signal! This is the directional bias bug!")
        failure(f"  The bot will bet AGAINST favorites even when they're underpriced.")
        all_passed = False
    elif signal.side == 'YES':
        success(f"  CRITICAL: Correctly generated YES signal (edge={signal.edge:.4f})")
    else:
        failure(f"  Unexpected: Got {signal.signal.value} with side={signal.side}")
        all_passed = False
    
    return all_passed


def purge_corrupted_database():
    """
    Phase 1: The Purge (Database Reset)
    
    Delete the corrupted paper_trades.json file if it exists.
    This removes:
    - Invalid "Seahawks matched as NBA" trades
    - "All NO" trades from the directional bias bug
    - Duplicate trade locks that block valid trades
    """
    banner("PHASE 1: Database Purge")
    
    import glob
    
    # Possible locations for trade data
    trade_files = [
        '/app/backend/data/paper_trades.json',
        '/app/backend/paper_trades.json',
        '/app/paper_trades.json',
        '/app/backend/data/trades.db',
    ]
    
    # Also find any paper_trades files using glob
    trade_files.extend(glob.glob('/app/**/paper_trades*.json', recursive=True))
    trade_files.extend(glob.glob('/app/**/trades*.db', recursive=True))
    
    # Remove duplicates
    trade_files = list(set(trade_files))
    
    files_found = []
    files_deleted = []
    
    for filepath in trade_files:
        if os.path.exists(filepath):
            files_found.append(filepath)
            try:
                os.remove(filepath)
                files_deleted.append(filepath)
                success(f"Deleted: {filepath}")
            except Exception as e:
                failure(f"Could not delete {filepath}: {e}")
    
    if not files_found:
        info("No trade database files found (already clean)")
    else:
        info(f"Found {len(files_found)} file(s), deleted {len(files_deleted)}")
    
    return len(files_found) == len(files_deleted)


def main():
    """Run all verification tests."""
    print(f"""
{Fore.CYAN}
 ____  ____   ___  ____  _____  ____   ___  ______ ______ _    _ 
/ ___||  _ \\ / _ \\|  _ \\|_   _|/ ___| |  _ \\|  _  |_   _| |  | |
\\___ \\| |_) | | | | |_) | | |  \\___ \\ | |_) | |_| | | | | |__| |
 ___) |  __/| |_| |    /  | |   ___) ||  __/|  _  | | | |  __  |
|____/|_|    \\___/|_|\\_\\  |_|  |____/ |_|   |_| |_| |_| |_|  |_|
                                                                 
  INTEGRITY PATCH VERIFICATION SCRIPT
{Style.RESET_ALL}
    """)
    
    results = {}
    
    # Phase 1: Purge corrupted data
    results['purge'] = purge_corrupted_database()
    
    # Phase 2: Run logic stress tests
    results['test_a'] = run_test_a_collision_check()
    results['test_b'] = run_test_b_tennis_expansion()
    results['test_c'] = run_test_c_edge_direction_math()
    
    # Summary
    banner("VERIFICATION SUMMARY")
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if passed else f"{Fore.RED}FAIL{Style.RESET_ALL}"
        print(f"  {test_name.upper()}: [{status}]")
    
    print()
    
    if all_passed:
        print(f"{Fore.GREEN}{'='*60}")
        print(" PATCH VERIFIED. DATABASE CLEARED. READY FOR MAIN ENGINE.")
        print(f"{'='*60}{Style.RESET_ALL}")
        print()
        print(f"  To start the bot, run: {Fore.YELLOW}cd /app/backend && python main.py{Style.RESET_ALL}")
        print()
        return 0
    else:
        print(f"{Fore.RED}{'='*60}")
        print(" VERIFICATION FAILED. DO NOT START MAIN ENGINE.")
        print(f"{'='*60}{Style.RESET_ALL}")
        print()
        print("  Review the failed tests above and fix the issues.")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
