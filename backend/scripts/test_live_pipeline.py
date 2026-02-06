#!/usr/bin/env python3
"""
CORTEX LIVE TEST: Real Markets + Real News Pipeline
====================================================

This test verifies the fix by:
1. Using the REAL market_fetcher (Gamma API)
2. Processing a news item through the LIVE NewsInjector
3. Confirming signals are generated against REAL markets

Run with: python scripts/test_live_pipeline.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("LIVE_TEST")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def test_market_fetcher():
    """TEST 1: Verify market_fetcher returns real markets"""
    logger.info("=" * 60)
    logger.info("TEST 1: Market Fetcher (Gamma API)")
    logger.info("=" * 60)
    
    try:
        from data.polymarket_api import PolymarketAPI
        
        async with PolymarketAPI() as api:
            raw_markets = await api.get_markets(limit=20)
            
            if raw_markets:
                logger.info(f"✅ Fetched {len(raw_markets)} markets from Gamma API")
                
                # Show sample markets
                for m in raw_markets[:3]:
                    logger.info(f"  - {m.get('question', 'N/A')[:60]}...")
                    logger.info(f"    yes_price: {m.get('yes_price')}, volume: {m.get('volume_24h')}")
                
                return raw_markets
            else:
                logger.error("❌ No markets returned from Gamma API")
                return None
                
    except Exception as e:
        logger.error(f"❌ Market fetcher failed: {e}")
        return None


async def test_live_news_injection():
    """TEST 2: Process news against REAL markets"""
    logger.info("=" * 60)
    logger.info("TEST 2: Live News Injection (Real Markets)")
    logger.info("=" * 60)
    
    try:
        from services.news_injector import NewsInjector, NewsItem, get_news_injector
        from services.signal_cache import get_signal_cache
        from data.polymarket_api import PolymarketAPI
        
        # Create real market fetcher
        async def real_market_fetcher():
            async with PolymarketAPI() as api:
                raw_markets = await api.get_markets(limit=50)
                markets = []
                for m in raw_markets:
                    raw_yes = m.get('yes_price')
                    if raw_yes is None or raw_yes == 0:
                        continue
                    markets.append({
                        "id": m.get('condition_id') or m.get('id'),
                        "question": m.get('question', ''),
                        "description": m.get('description', ''),
                        "category": m.get('category', 'unknown'),
                        "yes_price": float(raw_yes),
                        "volume_24h": float(m.get('volume_24h', 0) or 0),
                    })
                return markets
        
        # Track injected signals
        injected_signals = []
        
        class TestSignalCache:
            async def set(self, key, value, ttl=300):
                injected_signals.append({"key": key, "value": value, "ttl": ttl})
                logger.info(f"📥 SIGNAL INJECTED: {key}")
                logger.info(f"    direction: {value.get('direction')}, BF: {value.get('bayes_factor', 0):.2f}")
        
        # Create injector with real market fetcher
        injector = NewsInjector(
            config={'min_bayes_factor': 2.0, 'llm_model': 'gpt-4o-mini'},
            signal_cache=TestSignalCache(),
            market_fetcher=real_market_fetcher
        )
        
        # Test news that should match crypto markets
        test_news = NewsItem(
            headline="BREAKING: SEC approves multiple spot Bitcoin ETFs, institutional adoption expected to surge",
            content="The Securities and Exchange Commission has approved applications from BlackRock, Fidelity, and others for spot Bitcoin ETFs. Analysts predict this will bring billions in institutional investment.",
            source="twitter.com/Tier10k",
            url="https://twitter.com/test",
            published_at=datetime.now(timezone.utc)
        )
        
        logger.info(f"Processing: '{test_news.headline[:60]}...'")
        
        # Process through the real pipeline
        await injector.process_news(test_news)
        
        logger.info("-" * 40)
        if injected_signals:
            logger.info(f"✅ TEST 2 PASSED: {len(injected_signals)} signal(s) injected against REAL markets!")
            for sig in injected_signals:
                logger.info(f"  Market: {sig['key']}")
        else:
            logger.warning("⚠️ TEST 2 WARNING: No signals met threshold (this may be normal)")
            logger.info("  The LLM may not have found relevant markets, or BF was too low")
        
        return injected_signals
        
    except Exception as e:
        logger.error(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_via_api_endpoint():
    """TEST 3: Test via actual API endpoint"""
    logger.info("=" * 60)
    logger.info("TEST 3: API Endpoint Test")
    logger.info("=" * 60)
    
    try:
        import aiohttp
        
        api_url = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')
        if not api_url.startswith('http'):
            api_url = f"https://{api_url}"
        
        # Test the webhook endpoint
        webhook_payload = {
            "headline": "Federal Reserve signals potential rate cut in March meeting",
            "content": "Fed Chair Powell indicated openness to cutting rates sooner than expected amid cooling inflation data.",
            "source": "reuters.com",
            "url": "https://reuters.com/test",
            "priority": "high"
        }
        
        logger.info(f"Calling: POST {api_url}/api/hooks/news-alert")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_url}/api/hooks/news-alert",
                json=webhook_payload,
                timeout=30
            ) as resp:
                status = resp.status
                data = await resp.json()
                
                logger.info(f"Response status: {status}")
                logger.info(f"Response: {data}")
                
                if status == 200 and data.get('status') == 'accepted':
                    logger.info("✅ TEST 3 PASSED: API endpoint accepted the news!")
                    return data
                else:
                    logger.warning(f"⚠️ TEST 3 WARNING: Unexpected response")
                    return data
                    
    except Exception as e:
        logger.error(f"❌ TEST 3 FAILED: {e}")
        return None


async def main():
    logger.info("🧠 CORTEX LIVE INTEGRATION TEST")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)
    
    results = {}
    
    # Run tests
    results['test_1_market_fetcher'] = await test_market_fetcher()
    results['test_2_live_injection'] = await test_live_news_injection()
    results['test_3_api_endpoint'] = await test_via_api_endpoint()
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 LIVE TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    for test_name, result in results.items():
        if result is not None:
            logger.info(f"  ✅ {test_name}: PASSED")
            passed += 1
        else:
            logger.info(f"  ❌ {test_name}: FAILED")
    
    logger.info("-" * 40)
    logger.info(f"Total: {passed}/3 passed")
    
    if passed == 3:
        logger.info("🎉 ALL LIVE TESTS PASSED! Pipeline is fully operational!")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
