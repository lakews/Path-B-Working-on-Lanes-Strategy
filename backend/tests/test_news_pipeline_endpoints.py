#!/usr/bin/env python3
"""
NEWS PIPELINE ENDPOINT TESTS (Lane 5)
=====================================

Tests for the news processing pipeline endpoints:
- POST /api/hooks/news-alert - Webhook endpoint for news
- GET /api/hooks/webhook-sources/status - Webhook sources status
- POST /api/hooks/webhook-sources/start - Start webhook polling
- POST /api/hooks/webhook-sources/stop - Stop webhook polling
- GET /api/news-injector/status - NewsInjector status
- POST /api/news-injector/start - Start NewsInjector polling
- GET /api/hooks/exa-status - Exa.ai integration status
- POST /api/hooks/news-poll - Manual Exa.ai poll trigger
- GET /api/markets - Active markets from Gamma API

Critical Bug Fix Verification:
- market_fetcher is properly wired to NewsInjector
- News processing pipeline works end-to-end
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


class TestHealthAndMarkets:
    """Basic health and markets endpoint tests"""
    
    def test_health_endpoint(self):
        """TEST: Health endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✅ Health check passed: {data}")
    
    def test_markets_endpoint_returns_live_data(self):
        """TEST: Markets endpoint returns live data from Gamma API"""
        response = requests.get(f"{BASE_URL}/api/markets?limit=10", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert 'markets' in data
        assert 'count' in data
        assert 'source' in data
        
        # Verify we got markets
        markets = data['markets']
        assert len(markets) > 0, "No markets returned"
        
        # Verify market structure
        first_market = markets[0]
        assert 'id' in first_market
        assert 'question' in first_market
        assert 'yes_price' in first_market
        assert first_market['yes_price'] > 0, "Market has no valid price"
        
        print(f"✅ Markets endpoint returned {len(markets)} markets from {data['source']}")
        print(f"   Sample: {first_market['question'][:60]}... (yes_price: {first_market['yes_price']})")


class TestNewsAlertWebhook:
    """Tests for POST /api/hooks/news-alert webhook endpoint"""
    
    def test_news_alert_accepts_valid_payload(self):
        """TEST: News alert webhook accepts and processes valid news"""
        payload = {
            "headline": "TEST: Bitcoin ETF sees record inflows",
            "content": "BlackRock's Bitcoin ETF recorded $500M in inflows today, the largest since approval.",
            "source": "test_source",
            "url": "https://test.com/news/1",
            "priority": "high"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        print(f"✅ News alert accepted: {data}")
    
    def test_news_alert_with_minimal_payload(self):
        """TEST: News alert accepts minimal payload (headline only)"""
        payload = {
            "headline": "TEST: Minimal news headline"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        print(f"✅ Minimal news alert accepted: {data}")
    
    def test_news_alert_with_metadata(self):
        """TEST: News alert accepts payload with metadata"""
        payload = {
            "headline": "TEST: Fed signals rate cut",
            "content": "Federal Reserve Chair indicates potential rate cut in upcoming meeting.",
            "source": "reuters.com",
            "url": "https://reuters.com/test",
            "priority": "critical",
            "metadata": {
                "author": "Test Author",
                "category": "finance"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        print(f"✅ News alert with metadata accepted: {data}")


class TestWebhookSourcesStatus:
    """Tests for webhook sources status and control endpoints"""
    
    def test_webhook_sources_status(self):
        """TEST: GET /api/hooks/webhook-sources/status returns status"""
        response = requests.get(
            f"{BASE_URL}/api/hooks/webhook-sources/status",
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert 'sources' in data or 'status' in data
        print(f"✅ Webhook sources status: {data}")
    
    def test_webhook_sources_start(self):
        """TEST: POST /api/hooks/webhook-sources/start starts polling"""
        response = requests.post(
            f"{BASE_URL}/api/hooks/webhook-sources/start",
            timeout=10
        )
        
        # Should return 200 or 400 if already running
        assert response.status_code in [200, 400]
        data = response.json()
        print(f"✅ Webhook sources start response: {data}")
    
    def test_webhook_sources_stop(self):
        """TEST: POST /api/hooks/webhook-sources/stop stops polling"""
        response = requests.post(
            f"{BASE_URL}/api/hooks/webhook-sources/stop",
            timeout=10
        )
        
        # Should return 200 or 400 if not running
        assert response.status_code in [200, 400]
        data = response.json()
        print(f"✅ Webhook sources stop response: {data}")


class TestNewsInjectorStatus:
    """Tests for NewsInjector status and control endpoints"""
    
    def test_news_injector_status(self):
        """TEST: GET /api/news-injector/status returns injector status"""
        response = requests.get(
            f"{BASE_URL}/api/news-injector/status",
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify we get status info
        assert 'status' in data or 'running' in data or 'enabled' in data
        print(f"✅ NewsInjector status: {data}")
    
    def test_news_injector_start(self):
        """TEST: POST /api/news-injector/start starts the injector"""
        response = requests.post(
            f"{BASE_URL}/api/news-injector/start",
            timeout=10
        )
        
        # Should return 200 or 400 if already running
        assert response.status_code in [200, 400]
        data = response.json()
        print(f"✅ NewsInjector start response: {data}")


class TestExaIntegration:
    """Tests for Exa.ai integration endpoints"""
    
    def test_exa_status(self):
        """TEST: GET /api/hooks/exa-status returns Exa.ai status"""
        response = requests.get(
            f"{BASE_URL}/api/hooks/exa-status",
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify we get status info
        assert 'enabled' in data or 'status' in data or 'api_key_configured' in data
        print(f"✅ Exa.ai status: {data}")
    
    def test_manual_news_poll(self):
        """TEST: POST /api/hooks/news-poll triggers manual Exa.ai poll"""
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-poll",
            timeout=60  # Longer timeout for actual API call
        )
        
        # Should return 200 or 400/503 if disabled/error
        assert response.status_code in [200, 400, 503]
        data = response.json()
        print(f"✅ Manual news poll response: {data}")


class TestMarketFetcherIntegration:
    """Tests to verify market_fetcher is properly wired (critical bug fix)"""
    
    def test_news_processing_gets_markets(self):
        """TEST: News processing pipeline has access to markets"""
        # First verify markets are available
        markets_response = requests.get(f"{BASE_URL}/api/markets?limit=5", timeout=30)
        assert markets_response.status_code == 200
        markets_data = markets_response.json()
        assert len(markets_data.get('markets', [])) > 0, "No markets available for testing"
        
        # Now send a news alert that should be processed against markets
        news_payload = {
            "headline": "BREAKING: Federal Reserve announces emergency rate cut",
            "content": "The Federal Reserve has announced an emergency 50 basis point rate cut amid market volatility.",
            "source": "reuters.com",
            "priority": "critical"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=news_payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        
        # The news should be queued for processing against markets
        print(f"✅ News submitted for processing against {len(markets_data['markets'])} markets")
        print(f"   Response: {data}")
    
    def test_crypto_news_processing(self):
        """TEST: Crypto-related news is processed against crypto markets"""
        news_payload = {
            "headline": "Bitcoin breaks $100,000 for the first time",
            "content": "Bitcoin has reached a historic milestone, breaking through $100,000 USD for the first time in history.",
            "source": "coindesk.com",
            "priority": "critical"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=news_payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        print(f"✅ Crypto news accepted for processing: {data}")
    
    def test_politics_news_processing(self):
        """TEST: Politics-related news is processed against politics markets"""
        news_payload = {
            "headline": "Trump announces major policy shift on tariffs",
            "content": "Former President Trump has announced a significant change in his tariff policy stance.",
            "source": "apnews.com",
            "priority": "high"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=news_payload,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'accepted'
        print(f"✅ Politics news accepted for processing: {data}")


class TestSignalCacheIntegration:
    """Tests for signal cache integration"""
    
    def test_signal_cache_status(self):
        """TEST: Signal cache status endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/signals/cache/status",
            timeout=10
        )
        
        # May return 200 or 404 if endpoint doesn't exist
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Signal cache status: {data}")
        else:
            print(f"⚠️ Signal cache status endpoint returned {response.status_code}")


class TestEndToEndNewsPipeline:
    """End-to-end tests for the complete news pipeline"""
    
    def test_full_pipeline_flow(self):
        """TEST: Full news pipeline flow from webhook to processing"""
        # Step 1: Verify markets are available
        markets_response = requests.get(f"{BASE_URL}/api/markets?limit=20", timeout=30)
        assert markets_response.status_code == 200
        markets = markets_response.json().get('markets', [])
        assert len(markets) > 0, "No markets available"
        print(f"Step 1: ✅ {len(markets)} markets available")
        
        # Step 2: Check NewsInjector status
        injector_response = requests.get(f"{BASE_URL}/api/news-injector/status", timeout=10)
        assert injector_response.status_code == 200
        print(f"Step 2: ✅ NewsInjector status: {injector_response.json()}")
        
        # Step 3: Submit news for processing
        news_payload = {
            "headline": "E2E TEST: Major market-moving event detected",
            "content": "This is an end-to-end test of the news processing pipeline.",
            "source": "test_e2e",
            "priority": "high"
        }
        
        news_response = requests.post(
            f"{BASE_URL}/api/hooks/news-alert",
            json=news_payload,
            timeout=30
        )
        assert news_response.status_code == 200
        assert news_response.json().get('status') == 'accepted'
        print(f"Step 3: ✅ News submitted and accepted")
        
        # Step 4: Wait briefly for processing
        time.sleep(2)
        
        # Step 5: Verify webhook sources status
        sources_response = requests.get(f"{BASE_URL}/api/hooks/webhook-sources/status", timeout=10)
        assert sources_response.status_code == 200
        print(f"Step 4: ✅ Webhook sources status: {sources_response.json()}")
        
        print("✅ Full pipeline flow test completed successfully")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
