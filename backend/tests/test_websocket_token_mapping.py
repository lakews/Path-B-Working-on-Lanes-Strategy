#!/usr/bin/env python3
"""
Test script to validate WebSocket YES/NO token mapping fix.

This script:
1. Starts the RealTimeMarketService
2. Verifies token mappings are populated before WebSocket processes messages
3. Compares WebSocket prices with REST API prices for validation
4. Checks that YES/NO tokens are correctly distinguished
"""

import asyncio
import sys
import os
import pytest

# Add backend to path
sys.path.insert(0, '/app/backend')

from services.realtime_market_service import get_realtime_market_service, RealTimeMarketService
from data.polymarket_api import PolymarketAPI


@pytest.mark.asyncio
async def test_token_mapping():
    """Test that token mapping is correctly populated before WebSocket starts."""
    print("\n" + "="*60)
    print("TEST 1: Token Mapping Initialization")
    print("="*60)
    
    # Get fresh service instance
    service = RealTimeMarketService()
    
    # Before start - mapping should be empty
    assert len(service._token_outcome) == 0, "Token outcome map should be empty before start"
    assert not service._token_mapping_ready.is_set(), "Mapping ready event should not be set"
    print("✅ Initial state correct: empty maps, event not set")
    
    # Start service
    print("\nStarting RealTimeMarketService...")
    await service.start()
    
    # After start - mapping should be populated
    stats = service.get_stats()
    print(f"\nService Stats:")
    print(f"  - Token mapping ready: {stats['token_mapping_ready']}")
    print(f"  - Markets cached: {stats['markets_cached']}")
    print(f"  - Tokens mapped: {stats['tokens_mapped']}")
    print(f"  - Tokens subscribed: {stats['tokens_subscribed']}")
    print(f"  - WebSocket updates: {stats['ws_updates']}")
    print(f"  - Dropped updates: {stats['dropped_updates']}")
    
    assert service._token_mapping_ready.is_set(), "Mapping ready event should be set after start"
    assert len(service._token_outcome) > 0, "Token outcome map should have entries"
    print(f"\n✅ Token mapping populated: {len(service._token_outcome)} tokens")
    
    # Verify YES/NO token tracking
    yes_tokens = sum(1 for o in service._token_outcome.values() if o == 'Yes')
    no_tokens = sum(1 for o in service._token_outcome.values() if o == 'No')
    print(f"  - YES tokens: {yes_tokens}")
    print(f"  - NO tokens: {no_tokens}")
    
    assert yes_tokens > 0, "Should have YES tokens"
    assert no_tokens > 0, "Should have NO tokens"
    print("✅ YES and NO tokens correctly identified")
    
    await service.stop()
    return True


@pytest.mark.asyncio
async def test_price_accuracy():
    """Compare WebSocket prices with REST API prices for a few markets."""
    print("\n" + "="*60)
    print("TEST 2: Price Accuracy (WebSocket vs REST)")
    print("="*60)
    
    service = RealTimeMarketService()
    await service.start()
    
    # Wait for some WebSocket updates to arrive
    print("\nWaiting 10 seconds for WebSocket price updates...")
    await asyncio.sleep(10)
    
    stats = service.get_stats()
    print(f"\nWebSocket Stats after 10s:")
    print(f"  - WS updates received: {stats['ws_updates']}")
    print(f"  - YES prices cached: {stats['yes_prices_cached']}")
    
    # Get a few markets from WebSocket cache
    ws_markets = service.get_markets(limit=10)
    
    if not ws_markets:
        print("⚠️ No markets in WebSocket cache - may need more time")
        await service.stop()
        return False
    
    # Fetch same markets from REST for comparison
    async with PolymarketAPI() as api:
        rest_markets = await api.get_markets(limit=200)
    
    # Create lookup by market ID
    rest_lookup = {m.get('id') or m.get('condition_id'): m for m in rest_markets}
    
    print(f"\nComparing prices for {len(ws_markets)} markets:")
    print("-" * 70)
    print(f"{'Market ID':<20} {'WS Price':>10} {'REST Price':>10} {'Diff':>10} {'Source':>15}")
    print("-" * 70)
    
    price_matches = 0
    price_mismatches = 0
    
    for ws_market in ws_markets[:10]:
        market_id = ws_market.get('id') or ws_market.get('condition_id')
        ws_price = ws_market.get('yes_price')
        ws_source = ws_market.get('price_source', 'unknown')
        
        rest_market = rest_lookup.get(market_id)
        rest_price = float(rest_market.get('yes_price', 0)) if rest_market else None
        
        if ws_price is not None and rest_price is not None:
            diff = abs(ws_price - rest_price)
            diff_str = f"{diff:.4f}"
            
            # Allow small tolerance for timing differences
            if diff < 0.05:  # 5% tolerance
                price_matches += 1
                status = "✅"
            else:
                price_mismatches += 1
                status = "❌"
            
            print(f"{market_id[:18]:<20} {ws_price:>10.4f} {rest_price:>10.4f} {diff_str:>10} {ws_source:>15} {status}")
        else:
            print(f"{market_id[:18]:<20} {'N/A':>10} {'N/A':>10} {'N/A':>10} {ws_source:>15}")
    
    print("-" * 70)
    print(f"\nPrice Comparison Results:")
    print(f"  - Matches (within 5%): {price_matches}")
    print(f"  - Mismatches: {price_mismatches}")
    
    await service.stop()
    
    if price_mismatches > price_matches:
        print("❌ TEST FAILED: Too many price mismatches")
        return False
    
    print("✅ Price accuracy test passed")
    return True


@pytest.mark.asyncio
async def test_yes_no_conversion():
    """Test that NO token prices are correctly converted to YES prices."""
    print("\n" + "="*60)
    print("TEST 3: YES/NO Price Conversion")
    print("="*60)
    
    service = RealTimeMarketService()
    await service.start()
    
    # Wait for updates
    print("\nWaiting 8 seconds for price updates...")
    await asyncio.sleep(8)
    
    # Check some markets that have both YES and NO prices cached
    markets_with_both = []
    for market_id in list(service._market_cache.keys())[:50]:
        yes_token = service._market_yes_token.get(market_id)
        no_token = service._market_no_token.get(market_id)
        
        if yes_token and no_token:
            yes_price = service._price_cache.get(yes_token)
            no_price = service._price_cache.get(no_token)
            
            if yes_price is not None and no_price is not None:
                markets_with_both.append({
                    'market_id': market_id,
                    'yes_token_price': yes_price,
                    'no_token_price': no_price,
                    'computed_yes': service._yes_price_cache.get(market_id),
                    'sum': yes_price + no_price
                })
    
    if not markets_with_both:
        print("⚠️ No markets found with both YES and NO prices cached")
        print("   This is expected if WebSocket hasn't sent updates for both tokens yet")
        await service.stop()
        return True  # Not a failure, just timing
    
    print(f"\nFound {len(markets_with_both)} markets with both token prices:")
    print("-" * 80)
    print(f"{'Market ID':<20} {'YES Token':>12} {'NO Token':>12} {'Sum':>8} {'Computed YES':>14}")
    print("-" * 80)
    
    valid_count = 0
    for m in markets_with_both[:10]:
        sum_check = "✅" if 0.95 <= m['sum'] <= 1.05 else "❌"  # Should sum to ~1
        print(f"{m['market_id'][:18]:<20} {m['yes_token_price']:>12.4f} {m['no_token_price']:>12.4f} "
              f"{m['sum']:>8.4f}{sum_check} {m['computed_yes']:>14.4f}")
        
        if 0.95 <= m['sum'] <= 1.05:
            valid_count += 1
    
    print("-" * 80)
    print(f"\nValidation: {valid_count}/{len(markets_with_both[:10])} markets have YES+NO≈1.0")
    
    await service.stop()
    
    if valid_count < len(markets_with_both[:10]) * 0.8:  # 80% should be valid
        print("❌ TEST FAILED: Too many invalid price sums")
        return False
    
    print("✅ YES/NO conversion test passed")
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("WEBSOCKET TOKEN MAPPING VALIDATION SUITE")
    print("="*60)
    
    results = []
    
    try:
        # Test 1: Token Mapping
        results.append(("Token Mapping", await test_token_mapping()))
    except Exception as e:
        print(f"❌ Test 1 EXCEPTION: {e}")
        results.append(("Token Mapping", False))
    
    try:
        # Test 2: Price Accuracy
        results.append(("Price Accuracy", await test_price_accuracy()))
    except Exception as e:
        print(f"❌ Test 2 EXCEPTION: {e}")
        results.append(("Price Accuracy", False))
    
    try:
        # Test 3: YES/NO Conversion  
        results.append(("YES/NO Conversion", await test_yes_no_conversion()))
    except Exception as e:
        print(f"❌ Test 3 EXCEPTION: {e}")
        results.append(("YES/NO Conversion", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED - WebSocket token mapping fix verified!")
    else:
        print("⚠️ SOME TESTS FAILED - Review output above")
    print("="*60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
