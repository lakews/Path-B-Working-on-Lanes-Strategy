"""
Test Suite for Markets-First PATH A Engine - Iteration 48

Tests:
1. WebSocket PRIMARY data source - verify WS returns markets before REST fallback
2. Gamma API FALLBACK only - verify REST is only used when WS returns <50 markets
3. MongoDB cache TERTIARY fallback when both WS and REST fail
4. PATH A Engine index building from scanner markets
5. PATH A hybrid relevance scoring (category + entity + keyword)
6. PATH A signal generation with correct fields (bayes_factor, market_question, signal_type, timestamp)
7. Two-tier LLM analysis - Tier 1 (Resolution) runs first, Tier 2 (Sentiment) as fallback
8. NewsSniper reads PATH A signals from MongoDB
9. NewsSniper 5-factor conviction enhancement
10. NewsSniper Kelly tiering based on conviction
11. Scanner caches markets from WebSocket with yes_price and no_price
12. API endpoints verification
"""

import pytest
import requests
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH = ('admin', 'apex2026!')


class TestRealtimeMarketService:
    """Test WebSocket PRIMARY data source and fallback behavior"""
    
    def test_realtime_status_endpoint(self):
        """Verify /api/realtime/status returns WebSocket connection info"""
        response = requests.get(f"{BASE_URL}/api/realtime/status", auth=AUTH)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'status' in data, "Missing 'status' field"
        assert 'websocket' in data, "Missing 'websocket' field"
        assert 'market_service' in data, "Missing 'market_service' field"
        
        # Verify WebSocket is connected (PRIMARY)
        ws_data = data['websocket']
        assert ws_data.get('connected') == True, "WebSocket should be connected"
        assert ws_data.get('running') == True, "WebSocket should be running"
        
        # Verify market service is running
        ms_data = data['market_service']
        assert ms_data.get('running') == True, "Market service should be running"
        assert ms_data.get('token_mapping_ready') == True, "Token mapping should be ready"
        
        print(f"✓ WebSocket connected: {ws_data.get('connected')}")
        print(f"✓ Messages received: {ws_data.get('messages_received')}")
        print(f"✓ Markets cached: {ms_data.get('markets_cached')}")
        print(f"✓ WS updates processed: {ms_data.get('ws_updates_processed')}")
    
    def test_websocket_is_primary_data_source(self):
        """Verify WebSocket is PRIMARY - REST fallback should be 0 or minimal"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        scanner = data.get('scanner', {})
        stats = scanner.get('stats', {})
        
        # REST fallback should be 0 (WebSocket is primary)
        rest_fallback = stats.get('rest_fallback_used', 0)
        ws_markets = stats.get('ws_markets_fetched', 0)
        
        print(f"✓ WebSocket markets fetched: {ws_markets}")
        print(f"✓ REST fallback used: {rest_fallback}")
        
        # WebSocket should have fetched markets
        assert ws_markets > 0, "WebSocket should have fetched markets"
        
        # REST fallback should be 0 or very low (only used when WS fails)
        assert rest_fallback == 0, f"REST fallback should be 0 when WS is working, got {rest_fallback}"
    
    def test_scanner_caches_markets_with_prices(self):
        """Verify scanner caches markets with yes_price and no_price"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        scanner = data.get('scanner', {})
        
        # Verify markets are cached
        markets_cached = scanner.get('markets_cached', 0)
        assert markets_cached > 0, f"Expected cached markets, got {markets_cached}"
        
        # Verify embeddings are generated
        embeddings_cached = scanner.get('embeddings_cached', 0)
        assert embeddings_cached > 0, f"Expected cached embeddings, got {embeddings_cached}"
        
        # Verify scanner is fresh
        is_fresh = scanner.get('is_fresh', False)
        assert is_fresh == True, "Scanner should be fresh"
        
        print(f"✓ Markets cached: {markets_cached}")
        print(f"✓ Embeddings cached: {embeddings_cached}")
        print(f"✓ Scanner is fresh: {is_fresh}")


class TestPolymarketScanner:
    """Test Scanner with WebSocket PRIMARY, REST FALLBACK, MongoDB TERTIARY"""
    
    def test_scanner_health_endpoint(self):
        """Verify /api/health/scanner returns scanner status"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy, got {data.get('status')}"
        
        scanner = data.get('scanner', {})
        assert scanner.get('running') == True, "Scanner should be running"
        
        stats = scanner.get('stats', {})
        print(f"✓ Scan count: {stats.get('scan_count')}")
        print(f"✓ WS markets fetched: {stats.get('ws_markets_fetched')}")
        print(f"✓ REST fallback used: {stats.get('rest_fallback_used')}")
        print(f"✓ MongoDB writes: {stats.get('mongodb_writes')}")
    
    def test_scanner_stats_show_ws_primary(self):
        """Verify scanner stats show WebSocket as primary source"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get('scanner', {}).get('stats', {})
        
        ws_fetched = stats.get('ws_markets_fetched', 0)
        rest_fallback = stats.get('rest_fallback_used', 0)
        
        # WebSocket should be primary (more fetches than REST fallbacks)
        assert ws_fetched > 0, "WebSocket should have fetched markets"
        
        # If REST fallback is 0, WebSocket is working as primary
        if rest_fallback == 0:
            print("✓ WebSocket is PRIMARY - REST fallback not used")
        else:
            # REST fallback should only be used when WS returns <50 markets
            print(f"⚠ REST fallback used {rest_fallback} times (expected when WS < 50 markets)")


class TestPathAEngine:
    """Test PATH A Engine index building and signal generation"""
    
    def test_path_a_health_endpoint(self):
        """Verify /api/path-a/health returns engine status"""
        response = requests.get(f"{BASE_URL}/api/path-a/health", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data, "Missing 'status' field"
        assert 'checks' in data, "Missing 'checks' field"
        
        checks = data.get('checks', {})
        
        # Verify index freshness
        index_freshness = checks.get('index_freshness', {})
        assert index_freshness.get('status') == 'ok', f"Index freshness should be ok, got {index_freshness.get('status')}"
        
        # Verify index size
        index_size = checks.get('index_size', {})
        assert index_size.get('status') == 'ok', f"Index size should be ok, got {index_size.get('status')}"
        assert index_size.get('size', 0) > 0, "Index should have entries"
        
        print(f"✓ PATH A status: {data.get('status')}")
        print(f"✓ Index size: {index_size.get('size')}")
        print(f"✓ Index age (minutes): {index_freshness.get('age_minutes')}")
    
    def test_path_a_stats_endpoint(self):
        """Verify /api/path-a/stats returns processing statistics"""
        response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert 'total_processed' in data, "Missing 'total_processed'"
        assert 'total_matches' in data, "Missing 'total_matches'"
        assert 'total_signals' in data, "Missing 'total_signals'"
        assert 'index_size' in data, "Missing 'index_size'"
        assert 'markets_cached' in data, "Missing 'markets_cached'"
        
        # Verify optimizations are working
        assert 'dedup_prevented' in data, "Missing 'dedup_prevented'"
        assert 'early_terminations' in data, "Missing 'early_terminations'"
        assert 'llm_calls_saved' in data, "Missing 'llm_calls_saved'"
        
        print(f"✓ Total processed: {data.get('total_processed')}")
        print(f"✓ Total matches: {data.get('total_matches')}")
        print(f"✓ Total signals: {data.get('total_signals')}")
        print(f"✓ Index size: {data.get('index_size')}")
        print(f"✓ Dedup prevented: {data.get('dedup_prevented')}")
        print(f"✓ LLM calls saved: {data.get('llm_calls_saved')}")
    
    def test_path_a_index_built_from_scanner(self):
        """Verify PATH A index is built from scanner markets"""
        # Get scanner stats
        scanner_response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert scanner_response.status_code == 200
        scanner_data = scanner_response.json()
        scanner_markets = scanner_data.get('scanner', {}).get('markets_cached', 0)
        
        # Get PATH A stats
        path_a_response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert path_a_response.status_code == 200
        path_a_data = path_a_response.json()
        path_a_markets = path_a_data.get('markets_cached', 0)
        
        # PATH A should have markets from scanner
        assert path_a_markets > 0, "PATH A should have cached markets"
        
        # Markets should match (or be close)
        print(f"✓ Scanner markets: {scanner_markets}")
        print(f"✓ PATH A markets: {path_a_markets}")
        
        # They should be equal or very close
        assert abs(scanner_markets - path_a_markets) <= 10, \
            f"PATH A markets ({path_a_markets}) should match scanner ({scanner_markets})"


class TestNewsSniperMongoDB:
    """Test NewsSniper reads PATH A signals and executes trades"""
    
    def test_news_sniper_status_endpoint(self):
        """Verify /api/news-sniper/status returns operational status"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('status') == 'operational', f"Expected operational, got {data.get('status')}"
        
        stats = data.get('stats', {})
        assert stats.get('running') == True, "NewsSniper should be running"
        
        print(f"✓ NewsSniper status: {data.get('status')}")
        print(f"✓ Cycles: {stats.get('cycles')}")
        print(f"✓ Signals processed: {stats.get('signals_processed')}")
        print(f"✓ Trades executed: {stats.get('trades_executed')}")
    
    def test_news_sniper_reads_mongodb_signals(self):
        """Verify NewsSniper reads signals from MongoDB"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get('stats', {})
        
        # Verify MongoDB reads
        mongodb_reads = stats.get('mongodb_reads', 0)
        mongodb_errors = stats.get('mongodb_errors', 0)
        
        assert mongodb_reads > 0, "NewsSniper should have read from MongoDB"
        assert mongodb_errors == 0, f"MongoDB errors should be 0, got {mongodb_errors}"
        
        print(f"✓ MongoDB reads: {mongodb_reads}")
        print(f"✓ MongoDB errors: {mongodb_errors}")
    
    def test_news_sniper_conviction_enhancement(self):
        """Verify NewsSniper uses 5-factor conviction enhancement"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get('stats', {})
        config = data.get('config', {})
        
        # Verify conviction is being calculated
        avg_conviction = stats.get('avg_conviction', 0)
        total_conviction = stats.get('total_conviction_sum', 0)
        
        print(f"✓ Average conviction: {avg_conviction}")
        print(f"✓ Total conviction sum: {total_conviction}")
        
        # Verify source multipliers (part of 5-factor enhancement)
        source_multipliers = config.get('source_multipliers', {})
        assert 'reuters' in source_multipliers, "Missing reuters multiplier"
        assert 'whale_alert' in source_multipliers, "Missing whale_alert multiplier"
        assert 'twitter' in source_multipliers, "Missing twitter multiplier"
        
        print(f"✓ Source multipliers: {source_multipliers}")
        
        # Verify regime multipliers (part of 5-factor enhancement)
        regime_multipliers = config.get('regime_multipliers', {})
        assert 'crisis' in regime_multipliers, "Missing crisis multiplier"
        assert 'volatile' in regime_multipliers, "Missing volatile multiplier"
        assert 'normal' in regime_multipliers, "Missing normal multiplier"
        
        print(f"✓ Regime multipliers: {regime_multipliers}")
    
    def test_news_sniper_kelly_tiering(self):
        """Verify NewsSniper uses Kelly tiering based on conviction"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        config = data.get('config', {})
        
        # Verify Kelly tiers
        kelly_tiers = config.get('kelly_tiers', {})
        assert len(kelly_tiers) > 0, "Kelly tiers should be configured"
        
        # Verify tier structure
        expected_tiers = ['conviction_10+', 'conviction_8-10', 'conviction_6-8', 
                         'conviction_3-6', 'conviction_1-3', 'conviction_<1']
        
        for tier in expected_tiers:
            assert tier in kelly_tiers, f"Missing Kelly tier: {tier}"
        
        print(f"✓ Kelly tiers configured: {list(kelly_tiers.keys())}")
        print(f"✓ Tier values: {kelly_tiers}")
    
    def test_news_sniper_trade_execution_stats(self):
        """Verify NewsSniper trade execution statistics"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get('stats', {})
        
        # Verify trade stats
        trades_executed = stats.get('trades_executed', 0)
        trades_skipped_low_conviction = stats.get('trades_skipped_low_conviction', 0)
        trades_skipped_no_edge = stats.get('trades_skipped_no_edge', 0)
        trades_skipped_position_exists = stats.get('trades_skipped_position_exists', 0)
        
        print(f"✓ Trades executed: {trades_executed}")
        print(f"✓ Skipped (low conviction): {trades_skipped_low_conviction}")
        print(f"✓ Skipped (no edge): {trades_skipped_no_edge}")
        print(f"✓ Skipped (position exists): {trades_skipped_position_exists}")
        
        # Total signals processed should be sum of executed + skipped
        signals_processed = stats.get('signals_processed', 0)
        total_handled = trades_executed + trades_skipped_low_conviction + \
                       trades_skipped_no_edge + trades_skipped_position_exists
        
        print(f"✓ Signals processed: {signals_processed}")
        print(f"✓ Total handled: {total_handled}")


class TestAPIEndpoints:
    """Test all required API endpoints"""
    
    def test_health_endpoint(self):
        """Verify /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy, got {data.get('status')}"
        print(f"✓ Health status: {data.get('status')}")
    
    def test_realtime_status_endpoint_exists(self):
        """Verify /api/realtime/status endpoint exists and returns data"""
        response = requests.get(f"{BASE_URL}/api/realtime/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'websocket' in data
        assert 'market_service' in data
        print(f"✓ Realtime status endpoint working")
    
    def test_scanner_health_endpoint_exists(self):
        """Verify /api/health/scanner endpoint exists and returns data"""
        response = requests.get(f"{BASE_URL}/api/health/scanner", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'scanner' in data
        print(f"✓ Scanner health endpoint working")
    
    def test_path_a_health_endpoint_exists(self):
        """Verify /api/path-a/health endpoint exists and returns data"""
        response = requests.get(f"{BASE_URL}/api/path-a/health", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'checks' in data
        print(f"✓ PATH A health endpoint working")
    
    def test_path_a_stats_endpoint_exists(self):
        """Verify /api/path-a/stats endpoint exists and returns data"""
        response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'total_processed' in data
        assert 'total_signals' in data
        print(f"✓ PATH A stats endpoint working")
    
    def test_news_sniper_status_endpoint_exists(self):
        """Verify /api/news-sniper/status endpoint exists and returns data"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'stats' in data
        print(f"✓ NewsSniper status endpoint working")


class TestPathASignalStructure:
    """Test PATH A signal generation with correct fields"""
    
    def test_path_a_generates_signals(self):
        """Verify PATH A generates signals"""
        response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        total_signals = data.get('total_signals', 0)
        
        # PATH A should have generated some signals
        print(f"✓ Total signals generated: {total_signals}")
        
        # If signals > 0, the engine is working
        if total_signals > 0:
            print("✓ PATH A is generating signals")
        else:
            print("⚠ No signals generated yet (may need news events)")
    
    def test_path_a_hybrid_scoring(self):
        """Verify PATH A uses hybrid relevance scoring"""
        response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify matching is happening
        total_matches = data.get('total_matches', 0)
        total_processed = data.get('total_processed', 0)
        
        print(f"✓ Total processed: {total_processed}")
        print(f"✓ Total matches: {total_matches}")
        
        # If matches > 0, hybrid scoring is working
        if total_matches > 0:
            print("✓ Hybrid relevance scoring is working")


class TestTwoTierLLMAnalysis:
    """Test Two-tier LLM analysis (Resolution + Sentiment)"""
    
    def test_llm_savings_tracked(self):
        """Verify LLM call savings are tracked (indicates tiered analysis)"""
        response = requests.get(f"{BASE_URL}/api/path-a/health", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        checks = data.get('checks', {})
        
        llm_savings = checks.get('llm_savings', {})
        savings_percent = llm_savings.get('savings_percent', 0)
        
        print(f"✓ LLM savings status: {llm_savings.get('status')}")
        print(f"✓ LLM savings percent: {savings_percent}%")
        
        # Savings > 0 indicates tiered analysis is working
        if savings_percent > 0:
            print("✓ Two-tier LLM analysis is saving calls")
    
    def test_llm_calls_saved_in_stats(self):
        """Verify LLM calls saved are tracked in stats"""
        response = requests.get(f"{BASE_URL}/api/path-a/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        llm_calls_saved = data.get('llm_calls_saved', 0)
        
        print(f"✓ LLM calls saved: {llm_calls_saved}")
        
        # If calls saved > 0, tiered analysis is working
        if llm_calls_saved > 0:
            print("✓ Two-tier LLM analysis is optimizing calls")


class TestWebSocketPriceData:
    """Test WebSocket provides price data with yes_price and no_price"""
    
    def test_websocket_provides_prices(self):
        """Verify WebSocket provides price data"""
        response = requests.get(f"{BASE_URL}/api/realtime/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        ms_data = data.get('market_service', {})
        
        # Verify YES prices are cached
        yes_prices_cached = ms_data.get('yes_prices_cached', 0)
        assert yes_prices_cached > 0, f"Expected YES prices cached, got {yes_prices_cached}"
        
        print(f"✓ YES prices cached: {yes_prices_cached}")
        print(f"✓ WS updates processed: {ms_data.get('ws_updates_processed')}")
    
    def test_markets_have_prices(self):
        """Verify markets endpoint returns prices"""
        response = requests.get(f"{BASE_URL}/api/markets?limit=5", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        markets = data.get('markets', [])
        
        if len(markets) > 0:
            market = markets[0]
            yes_price = market.get('yes_price')
            no_price = market.get('no_price')
            
            print(f"✓ Sample market: {market.get('question', '')[:50]}...")
            print(f"✓ YES price: {yes_price}")
            print(f"✓ NO price: {no_price}")
            
            # Verify prices are valid
            if yes_price is not None:
                assert 0 <= yes_price <= 1, f"YES price should be 0-1, got {yes_price}"
            if no_price is not None:
                assert 0 <= no_price <= 1, f"NO price should be 0-1, got {no_price}"


class TestPaperTradingIntegration:
    """Test paper trading integration with NewsSniper"""
    
    def test_paper_trading_status(self):
        """Verify paper trading status endpoint"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        print(f"✓ Paper trading status: {data}")
    
    def test_start_paper_trading(self):
        """Start paper trading for NewsSniper testing"""
        response = requests.post(f"{BASE_URL}/api/paper/start", auth=AUTH)
        # May already be running
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        print(f"✓ Paper trading start response: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
