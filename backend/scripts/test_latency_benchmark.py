#!/usr/bin/env python3
"""
LATENCY BENCHMARK TEST
======================

Measures actual latencies for Path A and Path B components.

Run with: python scripts/test_latency_benchmark.py
"""

import asyncio
import time
import logging
import os
import sys
import statistics
from datetime import datetime, timezone
from typing import Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("LATENCY_TEST")

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("data.polymarket_api").setLevel(logging.WARNING)


async def measure_latency(func, *args, **kwargs) -> Tuple[float, any]:
    """Measure execution time of an async function"""
    start = time.perf_counter()
    result = await func(*args, **kwargs)
    end = time.perf_counter()
    latency_ms = (end - start) * 1000
    return latency_ms, result


def measure_sync_latency(func, *args, **kwargs) -> Tuple[float, any]:
    """Measure execution time of a sync function"""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    end = time.perf_counter()
    latency_ms = (end - start) * 1000
    return latency_ms, result


async def test_rest_api_latency(iterations: int = 5) -> Dict:
    """Test REST API market fetch latency"""
    logger.info("=" * 60)
    logger.info("TEST 1: REST API Latency (Gamma API)")
    logger.info("=" * 60)
    
    from data.polymarket_api import PolymarketAPI
    
    latencies = []
    market_counts = []
    
    for i in range(iterations):
        async with PolymarketAPI() as api:
            latency, markets = await measure_latency(api.get_markets, limit=100)
            latencies.append(latency)
            market_counts.append(len(markets) if markets else 0)
            logger.info(f"  Run {i+1}: {latency:.2f}ms ({len(markets) if markets else 0} markets)")
    
    result = {
        'component': 'REST API (Gamma)',
        'iterations': iterations,
        'min_ms': min(latencies),
        'max_ms': max(latencies),
        'avg_ms': statistics.mean(latencies),
        'median_ms': statistics.median(latencies),
        'avg_markets': statistics.mean(market_counts)
    }
    
    logger.info(f"  RESULT: avg={result['avg_ms']:.2f}ms, median={result['median_ms']:.2f}ms")
    return result


async def test_websocket_cache_latency(iterations: int = 10) -> Dict:
    """Test WebSocket cache read latency (in-memory)"""
    logger.info("=" * 60)
    logger.info("TEST 2: WebSocket Cache Read Latency")
    logger.info("=" * 60)
    
    try:
        from services.realtime_market_service import get_realtime_market_service
        
        service = get_realtime_market_service()
        
        # Check if service is already running (from paper trader)
        # If not, we can't start it here without async context properly
        if not service._running:
            logger.info("  Starting WebSocket service...")
            await service.start()
            await asyncio.sleep(5)  # Wait for cache to populate
        
        latencies = []
        market_counts = []
        
        for i in range(iterations):
            start = time.perf_counter()
            markets = service.get_markets(limit=100)
            end = time.perf_counter()
            latency = (end - start) * 1000
            latencies.append(latency)
            market_counts.append(len(markets) if markets else 0)
            logger.info(f"  Run {i+1}: {latency:.4f}ms ({len(markets) if markets else 0} markets)")
        
        result = {
            'component': 'WebSocket Cache (Memory)',
            'iterations': iterations,
            'min_ms': min(latencies),
            'max_ms': max(latencies),
            'avg_ms': statistics.mean(latencies),
            'median_ms': statistics.median(latencies),
            'avg_markets': statistics.mean(market_counts)
        }
        
        logger.info(f"  RESULT: avg={result['avg_ms']:.4f}ms, median={result['median_ms']:.4f}ms")
        return result
        
    except Exception as e:
        logger.warning(f"  WebSocket service not available: {e}")
        import traceback
        traceback.print_exc()
        return {'component': 'WebSocket Cache', 'error': str(e)}


async def test_signal_cache_latency(iterations: int = 20) -> Dict:
    """Test signal cache read/write latency"""
    logger.info("=" * 60)
    logger.info("TEST 3: Signal Cache Read/Write Latency")
    logger.info("=" * 60)
    
    from services.signal_cache import get_signal_cache
    
    cache = get_signal_cache()
    
    # Test writes
    write_latencies = []
    for i in range(iterations):
        test_signal = {
            'direction': 'YES',
            'posterior': 0.75,
            'bayes_factor': 4.5,
            'confidence': 0.80,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        latency, _ = await measure_latency(
            cache.set, 
            f"latency_test:{i}", 
            test_signal, 
            ttl=60
        )
        write_latencies.append(latency)
    
    # Test reads
    read_latencies = []
    for i in range(iterations):
        latency, _ = await measure_latency(cache.get, f"latency_test:{i}")
        read_latencies.append(latency)
    
    result = {
        'component': 'Signal Cache',
        'iterations': iterations,
        'write_avg_ms': statistics.mean(write_latencies),
        'write_median_ms': statistics.median(write_latencies),
        'read_avg_ms': statistics.mean(read_latencies),
        'read_median_ms': statistics.median(read_latencies),
    }
    
    logger.info(f"  WRITE: avg={result['write_avg_ms']:.4f}ms, median={result['write_median_ms']:.4f}ms")
    logger.info(f"  READ:  avg={result['read_avg_ms']:.4f}ms, median={result['read_median_ms']:.4f}ms")
    return result


async def test_llm_latency(iterations: int = 3) -> Dict:
    """Test LLM call latency (Path A)"""
    logger.info("=" * 60)
    logger.info("TEST 4: LLM Service Latency (GPT-4o-mini)")
    logger.info("=" * 60)
    
    try:
        from services.llm_service import get_llm_service
        
        llm_service = get_llm_service()
        
        test_headline = "Bitcoin ETF sees record $500M inflows"
        test_content = "BlackRock and Fidelity leading institutional demand"
        test_question = "Will Bitcoin reach $100,000 by end of 2025?"
        
        latencies = []
        
        for i in range(iterations):
            latency, result = await measure_latency(
                llm_service.analyze_news_for_market,
                news_headline=test_headline,
                news_content=test_content,
                market_question=test_question,
                market_description=""
            )
            latencies.append(latency)
            logger.info(f"  Run {i+1}: {latency:.0f}ms (relevant={result.is_relevant}, conf={result.confidence:.2f})")
        
        result = {
            'component': 'LLM Service (GPT-4o-mini)',
            'iterations': iterations,
            'min_ms': min(latencies),
            'max_ms': max(latencies),
            'avg_ms': statistics.mean(latencies),
            'median_ms': statistics.median(latencies),
        }
        
        logger.info(f"  RESULT: avg={result['avg_ms']:.0f}ms, median={result['median_ms']:.0f}ms")
        return result
        
    except Exception as e:
        logger.error(f"  LLM test failed: {e}")
        return {'component': 'LLM Service', 'error': str(e)}


async def test_sentiment_analyzer_latency(iterations: int = 3) -> Dict:
    """Test sentiment analyzer latency (Path B with cache)"""
    logger.info("=" * 60)
    logger.info("TEST 5: Sentiment Analyzer Latency (Path B)")
    logger.info("=" * 60)
    
    try:
        from ml.sentiment_analyzer import get_sentiment_analyzer
        
        analyzer = get_sentiment_analyzer()
        
        test_market = {
            'id': 'latency_test_market',
            'question': 'Will Bitcoin reach $100k?',
            'category': 'crypto',
            'yes_price': 0.45,
            'volume_24h': 100000,
            'liquidity': 50000
        }
        
        # First call (cold cache)
        logger.info("  Cold cache test:")
        cold_latency, cold_result = await measure_latency(
            analyzer.get_sentiment,
            market_data=test_market
        )
        logger.info(f"    Cold: {cold_latency:.0f}ms (sentiment={cold_result[0]:.2f})")
        
        # Subsequent calls (hot cache)
        hot_latencies = []
        logger.info("  Hot cache tests:")
        for i in range(iterations):
            latency, result = await measure_latency(
                analyzer.get_sentiment,
                market_data=test_market
            )
            hot_latencies.append(latency)
            logger.info(f"    Run {i+1}: {latency:.4f}ms")
        
        result = {
            'component': 'Sentiment Analyzer',
            'cold_cache_ms': cold_latency,
            'hot_cache_avg_ms': statistics.mean(hot_latencies),
            'hot_cache_median_ms': statistics.median(hot_latencies),
            'hot_cache_min_ms': min(hot_latencies),
            'hot_cache_max_ms': max(hot_latencies),
        }
        
        logger.info(f"  RESULT: cold={result['cold_cache_ms']:.0f}ms, hot_avg={result['hot_cache_avg_ms']:.4f}ms")
        return result
        
    except Exception as e:
        logger.error(f"  Sentiment test failed: {e}")
        import traceback
        traceback.print_exc()
        return {'component': 'Sentiment Analyzer', 'error': str(e)}


async def test_signal_fusion_latency(iterations: int = 5) -> Dict:
    """Test signal fusion engine latency"""
    logger.info("=" * 60)
    logger.info("TEST 6: Signal Fusion Engine Latency")
    logger.info("=" * 60)
    
    try:
        from ml.signal_fusion import SignalFusionEngine
        
        engine = SignalFusionEngine()
        
        test_market = {
            'id': 'fusion_test_market',
            'question': 'Will Bitcoin reach $100k?',
            'category': 'crypto',
            'yes_price': 0.45,
            'no_price': 0.55,
            'volume_24h': 100000,
            'liquidity': 50000
        }
        
        latencies = []
        
        for i in range(iterations):
            latency, result = await measure_latency(
                engine.generate_trading_signal,
                market_data=test_market
            )
            latencies.append(latency)
            signal = result.get('signal', 'N/A') if result else 'N/A'
            logger.info(f"  Run {i+1}: {latency:.2f}ms (signal={signal})")
        
        result = {
            'component': 'Signal Fusion Engine',
            'iterations': iterations,
            'min_ms': min(latencies),
            'max_ms': max(latencies),
            'avg_ms': statistics.mean(latencies),
            'median_ms': statistics.median(latencies),
        }
        
        logger.info(f"  RESULT: avg={result['avg_ms']:.2f}ms, median={result['median_ms']:.2f}ms")
        return result
        
    except Exception as e:
        logger.error(f"  Signal fusion test failed: {e}")
        import traceback
        traceback.print_exc()
        return {'component': 'Signal Fusion Engine', 'error': str(e)}


async def test_bayes_updater_latency(iterations: int = 10) -> Dict:
    """Test Bayesian updater latency"""
    logger.info("=" * 60)
    logger.info("TEST 7: Event Bayesian Updater Latency")
    logger.info("=" * 60)
    
    try:
        from bayesian_math.event_bayes import get_event_bayes
        
        bayes = get_event_bayes()
        
        llm_analysis = {
            "direction": "YES",
            "impact": "strong",
            "confidence": 0.80,
            "reasoning": "Test analysis"
        }
        
        latencies = []
        
        for i in range(iterations):
            start = time.perf_counter()
            result = bayes.update(
                market_id=f"bayes_test_{i}",
                market_question="Will Bitcoin reach $100k?",
                current_price=0.45,
                news_headline="Test headline",
                news_content="Test content",
                news_source="test",
                llm_analysis=llm_analysis
            )
            end = time.perf_counter()
            latency = (end - start) * 1000
            latencies.append(latency)
            logger.info(f"  Run {i+1}: {latency:.4f}ms (BF={result.bayes_factor:.2f})")
        
        result = {
            'component': 'Event Bayesian Updater',
            'iterations': iterations,
            'min_ms': min(latencies),
            'max_ms': max(latencies),
            'avg_ms': statistics.mean(latencies),
            'median_ms': statistics.median(latencies),
        }
        
        logger.info(f"  RESULT: avg={result['avg_ms']:.4f}ms, median={result['median_ms']:.4f}ms")
        return result
        
    except Exception as e:
        logger.error(f"  Bayes test failed: {e}")
        return {'component': 'Event Bayesian Updater', 'error': str(e)}


async def test_whale_direct_injection_latency(iterations: int = 5) -> Dict:
    """Test whale direct injection latency (bypasses LLM)"""
    logger.info("=" * 60)
    logger.info("TEST 8: Whale Direct Injection Latency")
    logger.info("=" * 60)
    
    try:
        from services.webhook_sources import WebhookSourcesManager
        from services.signal_cache import get_signal_cache
        
        cache = get_signal_cache()
        manager = WebhookSourcesManager(signal_cache=cache)
        
        latencies = []
        
        for i in range(iterations):
            trade_data = {
                'market': f'whale_latency_test_{i}',
                'side': 'BUY',
                'price': 0.45,
                'size': 50000 / 0.45  # $50k trade
            }
            
            start = time.perf_counter()
            news = await manager.whale.process_trade(trade_data)
            end = time.perf_counter()
            
            latency = (end - start) * 1000
            latencies.append(latency)
            logger.info(f"  Run {i+1}: {latency:.2f}ms")
        
        result = {
            'component': 'Whale Direct Injection',
            'iterations': iterations,
            'min_ms': min(latencies),
            'max_ms': max(latencies),
            'avg_ms': statistics.mean(latencies),
            'median_ms': statistics.median(latencies),
        }
        
        logger.info(f"  RESULT: avg={result['avg_ms']:.2f}ms, median={result['median_ms']:.2f}ms")
        return result
        
    except Exception as e:
        logger.error(f"  Whale injection test failed: {e}")
        import traceback
        traceback.print_exc()
        return {'component': 'Whale Direct Injection', 'error': str(e)}


async def main():
    """Run all latency benchmarks"""
    logger.info("🏎️  LATENCY BENCHMARK SUITE")
    logger.info("=" * 60)
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)
    
    results = {}
    
    # Run all tests
    results['rest_api'] = await test_rest_api_latency(iterations=5)
    results['websocket_cache'] = await test_websocket_cache_latency(iterations=10)
    results['signal_cache'] = await test_signal_cache_latency(iterations=20)
    results['llm_service'] = await test_llm_latency(iterations=3)
    results['sentiment'] = await test_sentiment_analyzer_latency(iterations=5)
    results['signal_fusion'] = await test_signal_fusion_latency(iterations=5)
    results['bayes_updater'] = await test_bayes_updater_latency(iterations=10)
    results['whale_direct'] = await test_whale_direct_injection_latency(iterations=5)
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 LATENCY SUMMARY")
    logger.info("=" * 60)
    
    print("\n" + "=" * 80)
    print(f"{'COMPONENT':<35} {'AVG (ms)':<15} {'MEDIAN (ms)':<15} {'NOTES':<20}")
    print("=" * 80)
    
    for key, data in results.items():
        if 'error' in data:
            print(f"{data['component']:<35} {'ERROR':<15} {'-':<15} {data['error'][:20]}")
        elif 'avg_ms' in data:
            avg = f"{data['avg_ms']:.2f}" if data['avg_ms'] >= 1 else f"{data['avg_ms']:.4f}"
            median = f"{data.get('median_ms', 0):.2f}" if data.get('median_ms', 0) >= 1 else f"{data.get('median_ms', 0):.4f}"
            print(f"{data['component']:<35} {avg:<15} {median:<15}")
        elif 'cold_cache_ms' in data:
            print(f"{data['component']:<35} {data['hot_cache_avg_ms']:.4f} (hot)    {data['cold_cache_ms']:.0f}ms (cold)")
        elif 'write_avg_ms' in data:
            print(f"{data['component']:<35} R:{data['read_avg_ms']:.4f}      W:{data['write_avg_ms']:.4f}")
    
    print("=" * 80)
    
    # Path comparison
    print("\n" + "=" * 80)
    print("PATH COMPARISON")
    print("=" * 80)
    
    # Path A total (News → LLM → Bayes → Cache)
    llm_latency = results.get('llm_service', {}).get('avg_ms', 0)
    bayes_latency = results.get('bayes_updater', {}).get('avg_ms', 0)
    cache_write = results.get('signal_cache', {}).get('write_avg_ms', 0)
    path_a_total = llm_latency + bayes_latency + cache_write
    
    print("\nPATH A (News → LLM → Bayes → Cache):")
    print(f"  LLM Analysis:     {llm_latency:.0f}ms")
    print(f"  Bayes Update:     {bayes_latency:.2f}ms")
    print(f"  Cache Write:      {cache_write:.4f}ms")
    print("  ─────────────────────────")
    print(f"  TOTAL:            {path_a_total:.0f}ms")
    
    # Path A (Whale Direct)
    whale_latency = results.get('whale_direct', {}).get('avg_ms', 0)
    print("\nPATH A (Whale Direct - skip LLM):")
    print(f"  Direct Injection: {whale_latency:.2f}ms")
    print(f"  SAVINGS:          {llm_latency - whale_latency:.0f}ms faster!")
    
    # Path B total (Market → Fusion → Trade)
    rest_latency = results.get('rest_api', {}).get('avg_ms', 0)
    ws_latency = results.get('websocket_cache', {}).get('avg_ms', 0)
    fusion_latency = results.get('signal_fusion', {}).get('avg_ms', 0)
    cache_read = results.get('signal_cache', {}).get('read_avg_ms', 0)
    
    path_b_ws = ws_latency + fusion_latency + cache_read
    path_b_rest = rest_latency + fusion_latency + cache_read
    
    print("\nPATH B (Market → Fusion → Trade):")
    print(f"  With WebSocket:   {ws_latency:.4f}ms (market data)")
    print(f"  Signal Fusion:    {fusion_latency:.2f}ms")
    print(f"  Cache Read:       {cache_read:.4f}ms")
    print("  ─────────────────────────")
    print(f"  TOTAL (WS):       {path_b_ws:.2f}ms")
    print(f"  TOTAL (REST):     {path_b_rest:.0f}ms")
    
    print("\n" + "=" * 80)
    print("WINNER: ", end="")
    if path_b_ws < whale_latency:
        print(f"PATH B (WebSocket) at {path_b_ws:.2f}ms")
    else:
        print(f"PATH A (Whale Direct) at {whale_latency:.2f}ms")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
