"""
P0 DIAGNOSTIC: Orderbook Data Integrity Check
==============================================
Purpose: Verify we are correctly parsing Polymarket orderbooks
Hypothesis: We may be confusing YES/NO tokens, causing 99% spreads

This script will:
1. Fetch top markets from Gamma API
2. For each market, fetch orderbooks for BOTH tokens
3. Compare spreads to identify the "real" YES orderbook
"""

import asyncio
import aiohttp
import json
from datetime import datetime

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


async def fetch_top_markets(session, limit=10):
    """Fetch top markets by volume"""
    url = f"{GAMMA_URL}/markets"
    params = {
        "limit": limit,
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false"
    }
    async with session.get(url, params=params) as response:
        if response.status == 200:
            return await response.json()
        return []


async def fetch_orderbook(session, token_id: str):
    """Fetch raw orderbook from CLOB"""
    url = f"{CLOB_URL}/book"
    params = {"token_id": token_id}
    async with session.get(url, params=params) as response:
        if response.status == 200:
            return await response.json()
        return {"bids": [], "asks": [], "error": f"Status {response.status}"}


def analyze_orderbook(book: dict, label: str):
    """Analyze an orderbook and return stats"""
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    
    if not bids or not asks:
        return {
            "label": label,
            "has_liquidity": False,
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "spread_pct": None,
            "bid_depth": len(bids),
            "ask_depth": len(asks),
        }
    
    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    spread = best_ask - best_bid
    mid = (best_bid + best_ask) / 2
    spread_pct = spread / mid if mid > 0 else 0
    
    return {
        "label": label,
        "has_liquidity": True,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "spread_pct": spread_pct,
        "bid_depth": len(bids),
        "ask_depth": len(asks),
        "top_bid_size": float(bids[0].get("size", 0)),
        "top_ask_size": float(asks[0].get("size", 0)),
    }


async def run_diagnostic():
    """Main diagnostic function"""
    print("=" * 80)
    print("P0 ORDERBOOK DIAGNOSTIC - Matrix Glitch Investigation")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Fetch top markets
        print("Step 1: Fetching Top 10 Markets by Volume...")
        markets = await fetch_top_markets(session, limit=10)
        
        if not markets:
            print("ERROR: Could not fetch markets!")
            return
        
        print(f"Found {len(markets)} markets")
        print()
        
        # Step 2: Analyze each market
        for i, market in enumerate(markets[:5], 1):
            print("-" * 80)
            question = market.get("question", "Unknown")[:60]
            condition_id = market.get("conditionId", "Unknown")
            volume_24h = float(market.get("volume24hr", 0))
            
            # Parse token IDs
            token_ids_raw = market.get("clobTokenIds", "[]")
            if isinstance(token_ids_raw, str):
                try:
                    token_ids = json.loads(token_ids_raw)
                except:
                    token_ids = []
            else:
                token_ids = token_ids_raw or []
            
            # Parse outcomes
            outcomes_raw = market.get("outcomes", "[]")
            if isinstance(outcomes_raw, str):
                try:
                    outcomes = json.loads(outcomes_raw)
                except:
                    outcomes = ["Unknown", "Unknown"]
            else:
                outcomes = outcomes_raw or ["Unknown", "Unknown"]
            
            # Parse outcome prices from Gamma
            outcome_prices_raw = market.get("outcomePrices", "[]")
            if isinstance(outcome_prices_raw, str):
                try:
                    outcome_prices = json.loads(outcome_prices_raw)
                except:
                    outcome_prices = []
            else:
                outcome_prices = outcome_prices_raw or []
            
            print(f"Market {i}: {question}...")
            print(f"  Condition ID: {condition_id[:20]}...")
            print(f"  Volume 24h: ${volume_24h:,.2f}")
            print(f"  Outcomes: {outcomes}")
            print(f"  Outcome Prices (Gamma): {outcome_prices}")
            print(f"  Token IDs: {len(token_ids)} tokens")
            print()
            
            if len(token_ids) >= 2:
                # Fetch orderbook for BOTH tokens
                print("  Fetching orderbooks for BOTH tokens...")
                
                # Token 0
                book0 = await fetch_orderbook(session, token_ids[0])
                analysis0 = analyze_orderbook(book0, f"Token[0] ({outcomes[0] if len(outcomes) > 0 else 'Unknown'})")
                
                # Token 1  
                book1 = await fetch_orderbook(session, token_ids[1])
                analysis1 = analyze_orderbook(book1, f"Token[1] ({outcomes[1] if len(outcomes) > 1 else 'Unknown'})")
                
                print()
                print(f"  === Token[0] Orderbook ({outcomes[0] if len(outcomes) > 0 else '?'}) ===")
                if analysis0["has_liquidity"]:
                    print(f"      Best Bid: {analysis0['best_bid']:.4f} (size: {analysis0.get('top_bid_size', 0):,.2f})")
                    print(f"      Best Ask: {analysis0['best_ask']:.4f} (size: {analysis0.get('top_ask_size', 0):,.2f})")
                    print(f"      Spread: {analysis0['spread']:.4f} ({analysis0['spread_pct']:.2%})")
                    print(f"      Depth: {analysis0['bid_depth']} bids / {analysis0['ask_depth']} asks")
                else:
                    print(f"      NO LIQUIDITY - Bids: {analysis0['bid_depth']}, Asks: {analysis0['ask_depth']}")
                
                print()
                print(f"  === Token[1] Orderbook ({outcomes[1] if len(outcomes) > 1 else '?'}) ===")
                if analysis1["has_liquidity"]:
                    print(f"      Best Bid: {analysis1['best_bid']:.4f} (size: {analysis1.get('top_bid_size', 0):,.2f})")
                    print(f"      Best Ask: {analysis1['best_ask']:.4f} (size: {analysis1.get('top_ask_size', 0):,.2f})")
                    print(f"      Spread: {analysis1['spread']:.4f} ({analysis1['spread_pct']:.2%})")
                    print(f"      Depth: {analysis1['bid_depth']} bids / {analysis1['ask_depth']} asks")
                else:
                    print(f"      NO LIQUIDITY - Bids: {analysis1['bid_depth']}, Asks: {analysis1['ask_depth']}")
                
                # CRITICAL ANALYSIS
                print()
                print("  >>> DIAGNOSIS <<<")
                
                # Check if Token[0] is the YES token (price should match outcomePrices[0])
                if outcome_prices and len(outcome_prices) > 0 and analysis0["has_liquidity"]:
                    gamma_yes_price = float(outcome_prices[0])
                    clob_mid0 = (analysis0['best_bid'] + analysis0['best_ask']) / 2
                    
                    price_match = abs(gamma_yes_price - clob_mid0) < 0.05
                    print(f"      Gamma YES price: {gamma_yes_price:.4f}")
                    print(f"      Token[0] mid:    {clob_mid0:.4f}")
                    print(f"      Match: {'✅ YES' if price_match else '❌ NO - MISMATCH!'}")
                
                # Determine which token is the "real" liquid one
                if analysis0["has_liquidity"] and analysis1["has_liquidity"]:
                    if analysis0["spread_pct"] < analysis1["spread_pct"]:
                        print(f"      Token[0] has tighter spread - likely the active YES token")
                    else:
                        print(f"      Token[1] has tighter spread - likely the active YES token")
                elif analysis0["has_liquidity"]:
                    print(f"      Only Token[0] has liquidity")
                elif analysis1["has_liquidity"]:
                    print(f"      Only Token[1] has liquidity - WE MAY BE FETCHING WRONG TOKEN!")
                else:
                    print(f"      ⚠️ NEITHER TOKEN HAS LIQUIDITY - Market is dead")
                
            elif len(token_ids) == 1:
                print(f"  Only 1 token ID available - fetching...")
                book = await fetch_orderbook(session, token_ids[0])
                analysis = analyze_orderbook(book, "Single Token")
                if analysis["has_liquidity"]:
                    print(f"      Spread: {analysis['spread']:.4f} ({analysis['spread_pct']:.2%})")
                else:
                    print(f"      NO LIQUIDITY")
            else:
                print(f"  ⚠️ NO TOKEN IDs FOUND!")
            
            print()
        
        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print("If you see 'MISMATCH' or 'Token[1] has tighter spread', we are fetching the wrong token!")
        print("The fix: Use Token[1] instead of Token[0], or verify outcomes array ordering.")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
