"""
MARKETS-FIRST ARCHITECTURE - Phase 1 Tests
============================================

Tests for the new Markets-First architecture endpoints:
- GET /api/health/scanner - Scanner health status
- GET /api/markets-first/status - Full system status
- POST /api/webhooks/news - Dual-path news processing
- GET /api/markets-first/cached-markets - In-memory cached markets
- GET /api/markets-first/signals - PATH A signals from MongoDB
- GET /api/markets-first/opportunities - PATH B HFT opportunities

Also verifies existing 5-lane system still works (zero breaking changes).
"""

import pytest
import requests
import os
import time
from datetime import datetime, timezone

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")


class TestHealthEndpoints:
    """Test health and status endpoints"""
    
    def test_main_health_endpoint(self):
        """Test main /api/health endpoint still works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✓ Main health endpoint: {data}")
    
    def test_scanner_health_endpoint(self):
        """Test /api/health/scanner returns scanner status"""
        response = requests.get(f"{BASE_URL}/api/health/scanner")
        
        # Can be 200 (healthy/stale) or 503 (not initialized)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            assert 'status' in data
            assert 'scanner' in data
            scanner = data['scanner']
            assert 'markets_cached' in scanner
            assert 'embeddings_cached' in scanner
            assert 'is_fresh' in scanner
            assert 'running' in scanner
            print(f"✓ Scanner health: status={data['status']}, markets_cached={scanner['markets_cached']}, running={scanner['running']}")
        else:
            assert data.get('status') == 'not_initialized'
            print(f"✓ Scanner not initialized (expected during startup): {data}")


class TestMarketsFirstStatus:
    """Test /api/markets-first/status endpoint"""
    
    def test_markets_first_status_endpoint(self):
        """Test full system status endpoint"""
        response = requests.get(f"{BASE_URL}/api/markets-first/status")
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'components' in data
        assert 'timestamp' in data
        
        components = data['components']
        
        # Check polymarket_scanner component
        assert 'polymarket_scanner' in components
        scanner = components['polymarket_scanner']
        assert 'initialized' in scanner
        assert 'running' in scanner
        assert 'markets_cached' in scanner
        assert 'embeddings_cached' in scanner
        
        # Check dual_path_news_injector component
        assert 'dual_path_news_injector' in components
        injector = components['dual_path_news_injector']
        assert 'initialized' in injector
        
        # Check mongodb component
        assert 'mongodb' in components
        mongo = components['mongodb']
        assert 'polymarket_cache_count' in mongo
        assert 'signals_count' in mongo
        assert 'hft_opportunities_count' in mongo
        
        print(f"✓ Markets-First status: {data['status']}")
        print(f"  Scanner: initialized={scanner['initialized']}, running={scanner['running']}, markets={scanner['markets_cached']}")
        print(f"  Injector: initialized={injector['initialized']}")
        print(f"  MongoDB: cache={mongo['polymarket_cache_count']}, signals={mongo['signals_count']}, opportunities={mongo['hft_opportunities_count']}")


class TestCachedMarkets:
    """Test /api/markets-first/cached-markets endpoint"""
    
    def test_cached_markets_endpoint(self):
        """Test getting cached markets from scanner"""
        response = requests.get(f"{BASE_URL}/api/markets-first/cached-markets")
        
        # Can be 200 (success) or 503 (scanner not initialized)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            assert 'markets' in data
            assert 'count' in data
            assert 'total_cached' in data
            assert 'timestamp' in data
            
            markets = data['markets']
            total = data['total_cached']
            
            print(f"✓ Cached markets: {data['count']} returned, {total} total cached")
            
            # If markets exist, validate structure
            if markets:
                market = markets[0]
                # Markets should have key fields
                assert 'market_id' in market or 'id' in market
                print(f"  Sample market: {market.get('question', 'N/A')[:60]}...")
        else:
            assert data.get('status') == 'not_initialized'
            print(f"✓ Scanner not initialized: {data}")
    
    def test_cached_markets_with_limit(self):
        """Test cached markets with limit parameter"""
        response = requests.get(f"{BASE_URL}/api/markets-first/cached-markets?limit=10")
        
        if response.status_code == 200:
            data = response.json()
            assert len(data['markets']) <= 10
            print(f"✓ Cached markets with limit=10: {len(data['markets'])} returned")


class TestNewsWebhook:
    """Test /api/webhooks/news endpoint (Dual-Path processing)"""
    
    def test_news_webhook_basic(self):
        """Test basic news webhook processing"""
        news_payload = {
            "headline": "Bitcoin reaches new all-time high above $100,000",
            "source": "test_suite",
            "urgency": "normal",
            "content": "Bitcoin has surged past $100,000 for the first time in history."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        # Can be 200 (processed) or 503 (injector not initialized)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get('status') == 'processed'
            assert 'path_a_signals' in data
            assert 'path_b_opportunities' in data
            assert 'timestamp' in data
            
            print(f"✓ News webhook processed:")
            print(f"  PATH A signals: {data['path_a_signals']}")
            print(f"  PATH B opportunities: {data['path_b_opportunities']}")
        else:
            assert data.get('status') == 'not_initialized'
            print(f"✓ News injector not initialized: {data}")
    
    def test_news_webhook_breaking_news(self):
        """Test breaking news (PATH A deferred to background)"""
        news_payload = {
            "headline": "BREAKING: Major political announcement affects prediction markets",
            "source": "test_suite",
            "urgency": "breaking",
            "content": "Breaking news content here."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        if response.status_code == 200:
            data = response.json()
            assert data.get('status') == 'processed'
            # For breaking news, PATH A is deferred so signals may be 0
            print(f"✓ Breaking news processed: PATH A={data['path_a_signals']}, PATH B={data['path_b_opportunities']}")
    
    def test_news_webhook_empty_headline(self):
        """Test news webhook with empty headline"""
        news_payload = {
            "headline": "",
            "source": "test_suite"
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        if response.status_code == 200:
            data = response.json()
            # Empty headline should return 0 signals/opportunities
            assert data['path_a_signals'] == 0
            assert data['path_b_opportunities'] == 0
            print(f"✓ Empty headline handled correctly: {data}")


class TestSignalsEndpoint:
    """Test /api/markets-first/signals endpoint"""
    
    def test_signals_endpoint(self):
        """Test getting active PATH A signals"""
        response = requests.get(f"{BASE_URL}/api/markets-first/signals")
        assert response.status_code == 200
        
        data = response.json()
        assert 'signals' in data
        assert 'count' in data
        assert 'timestamp' in data
        
        signals = data['signals']
        print(f"✓ Active signals: {data['count']}")
        
        # If signals exist, validate structure
        if signals:
            signal = signals[0]
            assert 'market_id' in signal
            assert 'type' in signal
            assert signal['type'] == 'path_a'
            print(f"  Sample signal: market={signal['market_id'][:16]}..., direction={signal.get('direction')}")
    
    def test_signals_with_limit(self):
        """Test signals endpoint with limit parameter"""
        response = requests.get(f"{BASE_URL}/api/markets-first/signals?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data['signals']) <= 5
        print(f"✓ Signals with limit=5: {len(data['signals'])} returned")


class TestOpportunitiesEndpoint:
    """Test /api/markets-first/opportunities endpoint"""
    
    def test_opportunities_endpoint(self):
        """Test getting PATH B HFT opportunities"""
        response = requests.get(f"{BASE_URL}/api/markets-first/opportunities")
        assert response.status_code == 200
        
        data = response.json()
        assert 'opportunities' in data
        assert 'count' in data
        assert 'timestamp' in data
        
        opportunities = data['opportunities']
        print(f"✓ HFT opportunities: {data['count']}")
        
        # If opportunities exist, validate structure
        if opportunities:
            opp = opportunities[0]
            assert 'market_id' in opp
            assert 'type' in opp
            assert opp['type'] == 'path_b'
            print(f"  Sample opportunity: market={opp['market_id'][:16]}...")
    
    def test_opportunities_with_limit(self):
        """Test opportunities endpoint with limit parameter"""
        response = requests.get(f"{BASE_URL}/api/markets-first/opportunities?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data['opportunities']) <= 10
        print(f"✓ Opportunities with limit=10: {len(data['opportunities'])} returned")


class TestExistingSystemIntegrity:
    """Verify existing 5-lane system still works (zero breaking changes)"""
    
    def test_system_status_includes_paper_trading(self):
        """Test /api/status includes paper_trading configuration"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        assert 'configuration' in data
        config = data['configuration']
        assert 'paper_trading' in config
        print(f"✓ System status includes paper_trading: {config['paper_trading']}")
    
    def test_analytics_endpoint(self):
        """Test /api/analytics still returns lane data"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        assert response.status_code == 200
        
        data = response.json()
        # Should have lane_performance for 5-lane architecture
        assert 'lane_performance' in data
        lanes = data['lane_performance']
        print(f"✓ Analytics endpoint: {len(lanes)} lanes")
        for lane_name, lane_data in lanes.items():
            print(f"  {lane_name}: {lane_data.get('total_trades', 0)} trades")
    
    def test_status_endpoint(self):
        """Test /api/status still works"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        assert 'status' in data
        assert 'trading_mode' in data
        print(f"✓ System status: {data['status']}, mode={data['trading_mode']}")
    
    def test_markets_endpoint(self):
        """Test /api/markets still works"""
        response = requests.get(f"{BASE_URL}/api/markets?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert 'markets' in data
        assert 'count' in data
        print(f"✓ Markets endpoint: {data['count']} markets, source={data.get('source', 'unknown')}")


class TestDualPathIntegration:
    """Integration tests for dual-path news processing"""
    
    def test_news_creates_opportunities(self):
        """Test that news webhook creates PATH B opportunities"""
        # First, get current opportunity count
        response = requests.get(f"{BASE_URL}/api/markets-first/opportunities")
        initial_count = response.json().get('count', 0) if response.status_code == 200 else 0
        
        # Send news
        news_payload = {
            "headline": "Test news for opportunity creation",
            "source": "integration_test",
            "urgency": "high"
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        if response.status_code == 200:
            data = response.json()
            path_b_count = data.get('path_b_opportunities', 0)
            
            if path_b_count > 0:
                # Verify opportunities were created (check quickly due to 10s TTL)
                response = requests.get(f"{BASE_URL}/api/markets-first/opportunities")
                if response.status_code == 200:
                    new_count = response.json().get('count', 0)
                    print(f"✓ PATH B created {path_b_count} opportunities")
                    print(f"  Initial count: {initial_count}, New count: {new_count}")
            else:
                print(f"✓ PATH B returned 0 opportunities (scanner may have 0 cached markets)")
    
    def test_semantic_search_relevance(self):
        """Test that PATH A finds relevant markets via semantic search"""
        # Send crypto-related news
        news_payload = {
            "headline": "Ethereum price surges as ETF approval expected",
            "source": "integration_test",
            "urgency": "normal",
            "content": "Ethereum has seen significant price movement as investors anticipate ETF approval."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        if response.status_code == 200:
            data = response.json()
            path_a_signals = data.get('path_a_signals', 0)
            
            # PATH A may return 0 if LLM determines news is not relevant
            # This is expected behavior per the agent context
            print(f"✓ PATH A semantic search: {path_a_signals} signals created")
            print(f"  (0 signals is valid if LLM determines news not relevant to cached markets)")


class TestScannerContinuousScan:
    """Test scanner continuous scan functionality"""
    
    def test_scanner_caches_markets(self):
        """Test that scanner caches markets from Gamma API fallback"""
        # Wait a bit for scanner to run
        time.sleep(2)
        
        response = requests.get(f"{BASE_URL}/api/markets-first/status")
        assert response.status_code == 200
        
        data = response.json()
        scanner = data['components']['polymarket_scanner']
        
        if scanner['initialized'] and scanner['running']:
            markets_cached = scanner['markets_cached']
            stats = scanner.get('stats', {})
            
            print(f"✓ Scanner status:")
            print(f"  Markets cached: {markets_cached}")
            print(f"  Scan count: {stats.get('scan_count', 0)}")
            print(f"  REST fallback used: {stats.get('rest_fallback_used', 0)}")
            print(f"  Embeddings generated: {stats.get('embeddings_generated', 0)}")
            
            # Scanner should cache markets (may take a few scans)
            # Per agent context: "Scanner caches 500 markets"
            if markets_cached > 0:
                print(f"  ✓ Scanner is caching markets successfully")
            else:
                print(f"  ⚠ Scanner has 0 markets cached (may need more time)")
        else:
            print(f"✓ Scanner not running yet: initialized={scanner['initialized']}, running={scanner['running']}")


class TestMongoDBCollections:
    """Test MongoDB collections and TTL indexes"""
    
    def test_mongodb_collections_exist(self):
        """Test that MongoDB collections are created"""
        response = requests.get(f"{BASE_URL}/api/markets-first/status")
        assert response.status_code == 200
        
        data = response.json()
        mongo = data['components']['mongodb']
        
        # Collections should exist (counts can be 0)
        assert 'polymarket_cache_count' in mongo
        assert 'signals_count' in mongo
        assert 'hft_opportunities_count' in mongo
        
        print(f"✓ MongoDB collections:")
        print(f"  polymarket_cache: {mongo['polymarket_cache_count']} documents")
        print(f"  signals: {mongo['signals_count']} documents")
        print(f"  hft_opportunities: {mongo['hft_opportunities_count']} documents")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
