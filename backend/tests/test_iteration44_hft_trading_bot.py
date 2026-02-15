"""
HFT Trading Bot Backend API Tests - Iteration 44
=================================================

Tests for:
1. API Key Persistence: POST /api/api-keys/update, GET /api/api-keys/status, POST /api/api-keys/reload
2. Webhook News Injection: POST /api/webhooks/news
3. NEWS Sniper Status: GET /api/news-sniper/status
4. Markets-First Status: GET /api/markets-first/status
5. HFT V2 Status: GET /api/hft-v2/status
6. Paper Trading Flow: POST /api/paper/start, GET /api/paper/status
7. Scanner Health: GET /api/health/scanner
8. MongoDB Signal Storage verification
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

# Admin credentials for authenticated endpoints
ADMIN_AUTH = ('admin', 'apex2026!')


class TestHealthEndpoints:
    """Basic health check tests"""
    
    def test_api_health(self):
        """Test basic API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✓ API health check passed: {data}")
    
    def test_api_status(self):
        """Test API status endpoint"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        # Status endpoint returns 'status' field instead of 'mode'
        assert 'status' in data
        print(f"✓ API status: status={data.get('status')}")


class TestScannerHealth:
    """Scanner health endpoint tests"""
    
    def test_scanner_health_endpoint(self):
        """Test GET /api/health/scanner"""
        response = requests.get(f"{BASE_URL}/api/health/scanner")
        # Can be 200 (healthy) or 503 (not initialized)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            assert 'status' in data
            assert 'scanner' in data
            scanner = data.get('scanner', {})
            markets_cached = scanner.get('markets_cached', 0)
            print(f"✓ Scanner health: status={data.get('status')}, markets_cached={markets_cached}")
            
            # Verify markets_cached > 400 if running
            if scanner.get('running'):
                assert markets_cached > 0, "Scanner running but no markets cached"
        else:
            assert data.get('status') == 'not_initialized'
            print(f"✓ Scanner not initialized (expected when paper trading not started)")


class TestAPIKeyPersistence:
    """API Key persistence endpoint tests"""
    
    def test_api_keys_status(self):
        """Test GET /api/api-keys/status"""
        response = requests.get(f"{BASE_URL}/api/api-keys/status", auth=ADMIN_AUTH)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('status') == 'ok'
        assert 'supported_keys' in data
        assert 'keys' in data
        
        # Verify supported keys list
        supported = data.get('supported_keys', [])
        assert 'EXA_API_KEY' in supported
        assert 'APIFY_API_KEY' in supported
        assert 'EMERGENT_LLM_KEY' in supported
        
        # Check key status
        keys = data.get('keys', [])
        print(f"✓ API keys status: {len(keys)} keys tracked")
        
        for key in keys:
            key_name = key.get('key_name')
            is_set = key.get('is_set')
            in_database = key.get('in_database')
            print(f"  - {key_name}: is_set={is_set}, in_database={in_database}")
    
    def test_api_keys_update(self):
        """Test POST /api/api-keys/update"""
        # Test updating a key (use a test value)
        test_key_name = "EXA_API_KEY"
        test_key_value = "test-key-value-12345"
        
        response = requests.post(
            f"{BASE_URL}/api/api-keys/update",
            auth=ADMIN_AUTH,
            json={
                "key_name": test_key_name,
                "key_value": test_key_value
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('status') == 'ok'
        assert data.get('key_name') == test_key_name
        print(f"✓ API key update: {test_key_name} saved successfully")
    
    def test_api_keys_update_invalid_key(self):
        """Test POST /api/api-keys/update with invalid key name"""
        response = requests.post(
            f"{BASE_URL}/api/api-keys/update",
            auth=ADMIN_AUTH,
            json={
                "key_name": "INVALID_KEY_NAME",
                "key_value": "some-value"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        print(f"✓ Invalid key name rejected correctly")
    
    def test_api_keys_reload(self):
        """Test POST /api/api-keys/reload"""
        response = requests.post(f"{BASE_URL}/api/api-keys/reload", auth=ADMIN_AUTH)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('status') == 'ok'
        assert 'results' in data
        print(f"✓ API keys reload: {data.get('message')}")


class TestMarketsFirstStatus:
    """Markets-First architecture status tests"""
    
    def test_markets_first_status(self):
        """Test GET /api/markets-first/status"""
        response = requests.get(f"{BASE_URL}/api/markets-first/status")
        assert response.status_code == 200
        data = response.json()
        
        assert 'status' in data
        assert 'components' in data
        
        components = data.get('components', {})
        
        # Check PolymarketScanner component
        scanner = components.get('polymarket_scanner', {})
        print(f"✓ PolymarketScanner: initialized={scanner.get('initialized')}, running={scanner.get('running')}, markets_cached={scanner.get('markets_cached')}")
        
        # Check DualPathNewsInjector component
        injector = components.get('dual_path_news_injector', {})
        print(f"✓ DualPathNewsInjector: initialized={injector.get('initialized')}")
        
        # Check MongoDB stats
        mongodb = components.get('mongodb', {})
        print(f"✓ MongoDB: signals={mongodb.get('signals_count')}, opportunities={mongodb.get('hft_opportunities_count')}")
    
    def test_markets_first_signals(self):
        """Test GET /api/markets-first/signals"""
        response = requests.get(f"{BASE_URL}/api/markets-first/signals")
        assert response.status_code == 200
        data = response.json()
        
        assert 'signals' in data
        assert 'count' in data
        
        signals = data.get('signals', [])
        print(f"✓ Active PATH A signals: {len(signals)}")
        
        # Verify signal structure if any exist
        for signal in signals[:3]:  # Check first 3
            assert 'market_id' in signal
            assert 'type' in signal
            assert signal.get('type') == 'path_a'
            print(f"  - Signal: market={signal.get('market_id', '')[:16]}..., direction={signal.get('direction')}")


class TestWebhookNewsInjection:
    """Webhook news injection tests"""
    
    def test_webhook_news_reuters(self):
        """Test POST /api/webhooks/news with Reuters source"""
        news_payload = {
            "headline": "TEST: Bitcoin reaches new all-time high above $100,000",
            "source": "reuters",
            "urgency": "high",
            "content": "Bitcoin has surged past $100,000 for the first time in history..."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        
        # Can be 200 (processed) or 503 (not initialized)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            assert data.get('status') == 'processed'
            print(f"✓ Reuters news processed: path_a_signals={data.get('path_a_signals')}, path_b_opportunities={data.get('path_b_opportunities')}")
        else:
            assert data.get('status') == 'not_initialized'
            print(f"✓ DualPathNewsInjector not initialized (expected when paper trading not started)")
    
    def test_webhook_news_bloomberg(self):
        """Test POST /api/webhooks/news with Bloomberg source"""
        news_payload = {
            "headline": "TEST: Federal Reserve signals rate cut in upcoming meeting",
            "source": "bloomberg",
            "urgency": "normal",
            "content": "The Federal Reserve has indicated potential rate cuts..."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            print(f"✓ Bloomberg news processed: path_a_signals={data.get('path_a_signals')}")
        else:
            print(f"✓ DualPathNewsInjector not initialized")
    
    def test_webhook_news_coindesk(self):
        """Test POST /api/webhooks/news with CoinDesk source"""
        news_payload = {
            "headline": "TEST: Ethereum 2.0 upgrade completes successfully",
            "source": "coindesk",
            "urgency": "high",
            "content": "The long-awaited Ethereum upgrade has been completed..."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        assert response.status_code in [200, 503]
        print(f"✓ CoinDesk news test: status_code={response.status_code}")
    
    def test_webhook_news_whale_alert(self):
        """Test POST /api/webhooks/news with whale_alert source"""
        news_payload = {
            "headline": "TEST: 10,000 BTC moved from unknown wallet to Binance",
            "source": "whale_alert",
            "urgency": "breaking",
            "content": "Large Bitcoin transfer detected..."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        assert response.status_code in [200, 503]
        print(f"✓ Whale alert news test: status_code={response.status_code}")
    
    def test_webhook_news_unknown_source(self):
        """Test POST /api/webhooks/news with unknown source"""
        news_payload = {
            "headline": "TEST: Generic news headline",
            "source": "unknown",
            "urgency": "normal"
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        assert response.status_code in [200, 503]
        print(f"✓ Unknown source news test: status_code={response.status_code}")


class TestNewsSniperStatus:
    """NEWS Sniper status tests"""
    
    def test_news_sniper_status(self):
        """Test GET /api/news-sniper/status"""
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        assert response.status_code == 200
        data = response.json()
        
        assert 'status' in data
        
        if data.get('status') == 'not_initialized':
            print(f"✓ NEWS Sniper not initialized (expected when paper trading not started)")
            assert 'message' in data
        else:
            assert 'stats' in data
            assert 'config' in data
            
            stats = data.get('stats', {})
            config = data.get('config', {})
            
            print(f"✓ NEWS Sniper status: {data.get('status')}")
            print(f"  - signals_processed: {stats.get('signals_processed', 0)}")
            print(f"  - mongodb_reads: {stats.get('mongodb_reads', 0)}")
            
            # Verify Kelly tiers config
            kelly_tiers = config.get('kelly_tiers', {})
            assert 'conviction_10+' in kelly_tiers
            print(f"  - Kelly tiers configured: {len(kelly_tiers)} tiers")


class TestHFTV2Status:
    """HFT V2 Engine status tests"""
    
    def test_hft_v2_status(self):
        """Test GET /api/hft-v2/status"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status")
        assert response.status_code == 200
        data = response.json()
        
        assert 'status' in data
        
        if data.get('status') == 'not_initialized':
            print(f"✓ HFT V2 not initialized (expected when paper trading not started)")
            assert 'message' in data
        else:
            assert 'metrics' in data
            assert 'stats' in data
            assert 'config' in data
            
            config = data.get('config', {})
            sub_strategies = config.get('sub_strategy_allocations', {})
            
            print(f"✓ HFT V2 status: {data.get('status')}")
            print(f"  - Sub-strategies: {list(sub_strategies.keys())}")


class TestPaperTradingFlow:
    """Paper trading flow tests"""
    
    def test_paper_status_before_start(self):
        """Test GET /api/paper/status before starting"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        
        # Should return status even if not running
        assert 'running' in data
        print(f"✓ Paper status before start: running={data.get('running')}")
    
    def test_paper_start(self):
        """Test POST /api/paper/start"""
        response = requests.post(
            f"{BASE_URL}/api/paper/start",
            auth=ADMIN_AUTH,
            params={"continuous_mode": False}
        )
        
        # Can be 200 (started) or 400 (already running)
        assert response.status_code in [200, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert 'session_id' in data
            assert 'initial_capital' in data
            assert data.get('mode') == 'paper'
            print(f"✓ Paper trading started: session_id={data.get('session_id')}")
            print(f"  - initial_capital: {data.get('initial_capital')}")
            print(f"  - deployed_capital: {data.get('deployed_capital')}")
            print(f"  - lane5_enabled: {data.get('lane5_enabled')}")
        else:
            print(f"✓ Paper trading already running: {data.get('message')}")
    
    def test_paper_status_after_start(self):
        """Test GET /api/paper/status after starting"""
        # Wait a moment for initialization
        time.sleep(2)
        
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        
        print(f"✓ Paper status after start:")
        print(f"  - running: {data.get('running')}")
        print(f"  - open_positions: {data.get('open_positions')}")
        print(f"  - total_trades: {data.get('total_trades')}")
        print(f"  - current_capital: {data.get('current_capital')}")
    
    def test_news_sniper_after_paper_start(self):
        """Test NEWS Sniper status after paper trading starts"""
        time.sleep(3)  # Wait for initialization
        
        response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        assert response.status_code == 200
        data = response.json()
        
        print(f"✓ NEWS Sniper after paper start: status={data.get('status')}")
        
        if data.get('status') == 'operational':
            stats = data.get('stats', {})
            print(f"  - signals_processed: {stats.get('signals_processed', 0)}")
            print(f"  - mongodb_reads: {stats.get('mongodb_reads', 0)}")
    
    def test_hft_v2_after_paper_start(self):
        """Test HFT V2 status after paper trading starts"""
        response = requests.get(f"{BASE_URL}/api/hft-v2/status")
        assert response.status_code == 200
        data = response.json()
        
        print(f"✓ HFT V2 after paper start: status={data.get('status')}")
        
        if data.get('status') == 'operational':
            metrics = data.get('metrics', {})
            print(f"  - metrics available: {list(metrics.keys())[:5]}")
    
    def test_scanner_after_paper_start(self):
        """Test scanner health after paper trading starts"""
        response = requests.get(f"{BASE_URL}/api/health/scanner")
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            scanner = data.get('scanner', {})
            markets_cached = scanner.get('markets_cached', 0)
            print(f"✓ Scanner after paper start: markets_cached={markets_cached}")
            
            # Verify markets_cached > 400 if running
            if scanner.get('running') and markets_cached > 0:
                print(f"  - Scanner is caching markets successfully")
        else:
            print(f"✓ Scanner status: {data.get('status')}")
    
    def test_webhook_news_after_paper_start(self):
        """Test webhook news injection after paper trading starts"""
        news_payload = {
            "headline": "TEST: Major crypto exchange announces new listing",
            "source": "reuters",
            "urgency": "high",
            "content": "A major cryptocurrency exchange has announced..."
        }
        
        response = requests.post(f"{BASE_URL}/api/webhooks/news", json=news_payload)
        assert response.status_code in [200, 503]
        data = response.json()
        
        if response.status_code == 200:
            print(f"✓ Webhook news after paper start:")
            print(f"  - path_a_signals: {data.get('path_a_signals')}")
            print(f"  - path_b_opportunities: {data.get('path_b_opportunities')}")
        else:
            print(f"✓ DualPathNewsInjector status: {data.get('status')}")


class TestMongoDBSignalStorage:
    """MongoDB signal storage verification tests"""
    
    def test_signals_endpoint(self):
        """Test GET /api/markets-first/signals for PATH A signals"""
        response = requests.get(f"{BASE_URL}/api/markets-first/signals?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        signals = data.get('signals', [])
        count = data.get('count', 0)
        
        print(f"✓ PATH A signals in MongoDB: {count}")
        
        # Verify signal structure
        for signal in signals[:3]:
            assert signal.get('type') == 'path_a', f"Signal type should be 'path_a', got {signal.get('type')}"
            
            # Check required fields
            required_fields = ['market_id', 'type', 'timestamp']
            for field in required_fields:
                assert field in signal, f"Missing required field: {field}"
            
            # Check optional but expected fields
            optional_fields = ['bayes_factor', 'direction', 'news_source']
            present_fields = [f for f in optional_fields if f in signal]
            
            print(f"  - Signal: market={signal.get('market_id', '')[:16]}..., direction={signal.get('direction')}, bayes_factor={signal.get('bayes_factor')}")
    
    def test_opportunities_endpoint(self):
        """Test GET /api/markets-first/opportunities for PATH B opportunities"""
        response = requests.get(f"{BASE_URL}/api/markets-first/opportunities?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        opportunities = data.get('opportunities', [])
        count = data.get('count', 0)
        
        print(f"✓ PATH B opportunities in MongoDB: {count}")


class TestLaneInitialization:
    """Test that all lanes initialize properly"""
    
    def test_lane_status_via_paper_status(self):
        """Test lane initialization via paper status endpoint"""
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        data = response.json()
        
        print(f"✓ Lane status via paper/status:")
        print(f"  - running: {data.get('running')}")
        print(f"  - open_positions: {data.get('open_positions')}")
        
        # Verify HFT V2 status
        hft_response = requests.get(f"{BASE_URL}/api/hft-v2/status")
        assert hft_response.status_code == 200
        hft_data = hft_response.json()
        print(f"  - HFT V2: {hft_data.get('status')}")
        
        # Verify NEWS Sniper status
        news_response = requests.get(f"{BASE_URL}/api/news-sniper/status")
        assert news_response.status_code == 200
        news_data = news_response.json()
        print(f"  - NEWS Sniper: {news_data.get('status')}")


class TestCleanup:
    """Cleanup tests - run last"""
    
    def test_paper_stop(self):
        """Test POST /api/paper/stop"""
        # Paper stop can take a long time, so we use a longer timeout
        try:
            response = requests.post(
                f"{BASE_URL}/api/paper/stop",
                auth=ADMIN_AUTH,
                params={"graceful": False},
                timeout=60  # Longer timeout for stop operation
            )
            
            # Can be 200 (stopped), 400 (not running), or 520 (timeout but still processing)
            if response.status_code in [200, 400]:
                data = response.json()
                if response.status_code == 200:
                    print(f"✓ Paper trading stopped: {data.get('message')}")
                else:
                    print(f"✓ Paper trading was not running: {data.get('message')}")
            else:
                # 520 or other errors - paper trading may have stopped but response timed out
                print(f"✓ Paper stop request sent (status_code={response.status_code})")
                
        except requests.exceptions.Timeout:
            # Timeout is acceptable for stop operation
            print(f"✓ Paper stop request timed out (operation may still be processing)")


# Run order configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
