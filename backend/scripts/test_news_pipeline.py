#!/usr/bin/env python3
"""
CORTEX INTEGRATION TEST: "Wake Up" Test
========================================

Purpose: Verify the end-to-end news analysis pipeline works:
    Apify Tweet → NewsInjector → LLM → EventBayes → Signal Cache

This test manually pushes a mock tweet through the pipeline
and verifies each stage produces output.

Run with: python scripts/test_news_pipeline.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("CORTEX_TEST")

# Reduce noise from other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# =============================================================================
# MOCK DATA
# =============================================================================

# Simulated @Tier10k style tweet (crypto alpha)
MOCK_APIFY_TWEET = {
    "headline": "🚨 BREAKING: Bitcoin ETF sees $500M inflows today, largest since approval. Institutional demand accelerating.",
    "content": "Bitcoin ETF sees $500M inflows today, largest since approval. Institutional demand accelerating. BlackRock and Fidelity leading the charge. This is extremely bullish for BTC price action.",
    "source": "twitter.com/Tier10k",
    "source_type": "apify_twitter",
    "url": "https://twitter.com/Tier10k/status/1234567890",
    "priority": "high",
    "metadata": {
        "author": "Tier10k",
        "likes": 5000,
        "retweets": 1200,
        "account_type": "crypto_alpha"
    }
}

# Mock market that the tweet should be relevant to
MOCK_MARKET = {
    "id": "test_btc_100k_market",
    "question": "Will Bitcoin reach $100,000 by end of 2025?",
    "description": "This market resolves YES if Bitcoin (BTC) reaches or exceeds $100,000 USD at any point before December 31, 2025.",
    "category": "crypto",
    "yes_price": 0.45,
    "no_price": 0.55,
    "volume_24h": 250000,
    "end_date": "2025-12-31"
}


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

async def test_llm_service_directly():
    """
    TEST 1: Verify LLM Service can analyze news
    """
    logger.info("=" * 60)
    logger.info("TEST 1: Direct LLM Service Test")
    logger.info("=" * 60)
    
    try:
        from services.llm_service import get_llm_service, EmergentLLMService
        
        llm_service = get_llm_service()
        logger.info(f"LLM Service initialized: model={llm_service.model}")
        
        # Check if API key is available
        if not llm_service._api_key:
            logger.error("❌ EMERGENT_LLM_KEY not found in environment!")
            return None
        
        logger.info("✅ EMERGENT_LLM_KEY found")
        
        # Analyze the mock tweet against the mock market
        logger.info(f"Analyzing tweet: '{MOCK_APIFY_TWEET['headline'][:50]}...'")
        logger.info(f"Against market: '{MOCK_MARKET['question']}'")
        
        result = await llm_service.analyze_news_for_market(
            news_headline=MOCK_APIFY_TWEET['headline'],
            news_content=MOCK_APIFY_TWEET['content'],
            market_question=MOCK_MARKET['question'],
            market_description=MOCK_MARKET['description']
        )
        
        logger.info("-" * 40)
        logger.info("LLM ANALYSIS RESULT:")
        logger.info(f"  is_relevant: {result.is_relevant}")
        logger.info(f"  is_bullish_for_yes: {result.is_bullish_for_yes}")
        logger.info(f"  confidence: {result.confidence}")
        logger.info(f"  direction: {result.direction}")
        logger.info(f"  impact: {result.impact}")
        logger.info(f"  rationale: {result.rationale}")
        
        if result.error:
            logger.error(f"  error: {result.error}")
        
        if result.is_relevant and result.confidence > 0.5:
            logger.info("✅ TEST 1 PASSED: LLM correctly analyzed the tweet!")
        else:
            logger.warning("⚠️ TEST 1 PARTIAL: LLM returned low relevance/confidence")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_event_bayes():
    """
    TEST 2: Verify EventBayes can calculate Bayes Factor
    """
    logger.info("=" * 60)
    logger.info("TEST 2: Event Bayesian Updater Test")
    logger.info("=" * 60)
    
    try:
        from bayesian_math.event_bayes import get_event_bayes, EventBayesianUpdater
        
        event_bayes = get_event_bayes()
        logger.info("EventBayes initialized")
        
        # Mock LLM analysis result
        llm_analysis = {
            "direction": "YES",
            "impact": "strong",
            "confidence": 0.80,
            "reasoning": "ETF inflows are strongly bullish for BTC price"
        }
        
        # Calculate posterior
        posterior = event_bayes.update(
            market_id=MOCK_MARKET['id'],
            market_question=MOCK_MARKET['question'],
            current_price=MOCK_MARKET['yes_price'],
            news_headline=MOCK_APIFY_TWEET['headline'],
            news_content=MOCK_APIFY_TWEET['content'],
            news_source=MOCK_APIFY_TWEET['source'],
            llm_analysis=llm_analysis
        )
        
        logger.info("-" * 40)
        logger.info("BAYES UPDATE RESULT:")
        logger.info(f"  prior: {posterior.prior:.4f}")
        logger.info(f"  posterior: {posterior.posterior:.4f}")
        logger.info(f"  bayes_factor: {posterior.bayes_factor:.4f}")
        logger.info(f"  news_impact: {posterior.news_impact.value}")
        logger.info(f"  direction: {posterior.direction}")
        logger.info(f"  confidence: {posterior.confidence:.4f}")
        logger.info(f"  is_actionable (BF >= 3.0): {posterior.is_actionable()}")
        logger.info(f"  ttl_seconds: {posterior.ttl_seconds}")
        
        if posterior.bayes_factor > 1.0:
            logger.info("✅ TEST 2 PASSED: Bayes Factor calculated correctly!")
        else:
            logger.warning("⚠️ TEST 2 WARNING: Bayes Factor <= 1.0 (weak signal)")
        
        return posterior
        
    except Exception as e:
        logger.error(f"❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_full_pipeline():
    """
    TEST 3: Full Pipeline Test (NewsInjector → LLM → Bayes → Cache)
    """
    logger.info("=" * 60)
    logger.info("TEST 3: Full Pipeline Integration Test")
    logger.info("=" * 60)
    
    try:
        from services.news_injector import NewsInjector, NewsItem, get_news_injector
        
        # Create a mock market fetcher that returns our test market
        async def mock_market_fetcher() -> List[Dict]:
            return [MOCK_MARKET]
        
        # Create a mock signal cache to capture injections
        class MockSignalCache:
            def __init__(self):
                self.injected_signals = []
            
            async def set(self, key: str, value: Dict, ttl: int = 300):
                self.injected_signals.append({
                    "key": key,
                    "value": value,
                    "ttl": ttl,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"📥 SIGNAL INJECTED TO CACHE:")
                logger.info(f"  key: {key}")
                logger.info(f"  direction: {value.get('direction')}")
                logger.info(f"  bayes_factor: {value.get('bayes_factor')}")
                logger.info(f"  confidence: {value.get('confidence')}")
        
        mock_cache = MockSignalCache()
        
        # Create NewsInjector with our mocks
        injector = NewsInjector(
            config={
                'min_bayes_factor': 2.0,  # Lower threshold for testing
                'llm_model': 'gpt-4o-mini'
            },
            signal_cache=mock_cache,
            market_fetcher=mock_market_fetcher
        )
        
        # Create NewsItem from our mock tweet
        news_item = NewsItem(
            headline=MOCK_APIFY_TWEET['headline'],
            content=MOCK_APIFY_TWEET['content'],
            source=MOCK_APIFY_TWEET['source'],
            url=MOCK_APIFY_TWEET['url'],
            published_at=datetime.now(timezone.utc)
        )
        
        logger.info(f"Processing news: '{news_item.headline[:50]}...'")
        logger.info(f"Source: {news_item.source}")
        
        # Process the news through the full pipeline
        await injector.process_news(news_item)
        
        logger.info("-" * 40)
        logger.info("PIPELINE RESULT:")
        
        if mock_cache.injected_signals:
            logger.info(f"✅ TEST 3 PASSED: {len(mock_cache.injected_signals)} signal(s) injected!")
            for sig in mock_cache.injected_signals:
                logger.info(f"  Signal: {sig}")
        else:
            logger.warning("⚠️ TEST 3 WARNING: No signals injected (may be below threshold)")
        
        return mock_cache.injected_signals
        
    except Exception as e:
        logger.error(f"❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_batch_analyze():
    """
    TEST 4: Batch Analysis (Multiple Markets)
    """
    logger.info("=" * 60)
    logger.info("TEST 4: Batch Analysis Test")
    logger.info("=" * 60)
    
    try:
        from services.llm_service import get_llm_service
        
        llm_service = get_llm_service()
        
        # Multiple markets to test against
        test_markets = [
            MOCK_MARKET,
            {
                "id": "test_eth_5k_market",
                "question": "Will Ethereum reach $5,000 by end of 2025?",
                "description": "Market resolves YES if ETH >= $5000 before Dec 31, 2025",
                "category": "crypto"
            },
            {
                "id": "test_trump_market",
                "question": "Will Trump win the 2024 presidential election?",
                "description": "Market resolves YES if Trump wins",
                "category": "politics"
            }
        ]
        
        logger.info(f"Batch analyzing against {len(test_markets)} markets...")
        
        results = await llm_service.batch_analyze(
            news_headline=MOCK_APIFY_TWEET['headline'],
            news_content=MOCK_APIFY_TWEET['content'],
            markets=test_markets
        )
        
        logger.info("-" * 40)
        logger.info("BATCH ANALYSIS RESULTS:")
        
        if results:
            for market_id, result in results.items():
                logger.info(f"  Market: {market_id}")
                logger.info(f"    relevant: {result.is_relevant}, bullish: {result.is_bullish_for_yes}")
                logger.info(f"    confidence: {result.confidence}, direction: {result.direction}")
            logger.info(f"✅ TEST 4 PASSED: Batch analysis returned {len(results)} results!")
        else:
            logger.warning("⚠️ TEST 4 WARNING: Batch analysis returned no results")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all integration tests"""
    logger.info("🧠 CORTEX INTEGRATION TEST SUITE")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Test Tweet: {MOCK_APIFY_TWEET['headline'][:60]}...")
    logger.info(f"Test Market: {MOCK_MARKET['question']}")
    logger.info("=" * 60)
    
    results = {}
    
    # Run tests sequentially
    results['test_1_llm'] = await test_llm_service_directly()
    results['test_2_bayes'] = await test_event_bayes()
    results['test_3_pipeline'] = await test_full_pipeline()
    results['test_4_batch'] = await test_batch_analyze()
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results.items():
        if result is not None:
            logger.info(f"  ✅ {test_name}: PASSED")
            passed += 1
        else:
            logger.info(f"  ❌ {test_name}: FAILED")
            failed += 1
    
    logger.info("-" * 40)
    logger.info(f"Total: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 ALL TESTS PASSED! The Cortex is AWAKE!")
    else:
        logger.warning(f"⚠️ {failed} test(s) failed. Check logs above.")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
