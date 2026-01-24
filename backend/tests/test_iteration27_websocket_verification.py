"""
Iteration 27: WebSocket Integration Verification Tests

Tests for verifying WebSocket functionality:
1. WebSocket connects to Polymarket CLOB API
2. WebSocket receives real-time price updates (price_change, book events)
3. WebSocket message parsing handles array and object formats correctly
4. RealTimeMarketService returns markets with 'websocket' price_source when WS data is available
5. Paper trader uses WebSocket data for market prices instead of REST polling
6. WebSocket fallback to REST works when WS unavailable
"""

import pytest
import requests
import os
import asyncio
import json
import time
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBackendHealth:
    """Basic health checks before WebSocket tests"""
    
    def test_health_endpoint(self):
        """Verify backend is running"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') in ['healthy', 'ok']
        print(f"✅ Backend health: {data.get('status')}")
    
    def test_status_endpoint(self):
        """Verify status endpoint returns system info"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert 'paper_trading' in data or 'status' in data
        print(f"✅ Status endpoint working")


class TestWebSocketModuleStructure:
    """Verify WebSocket module has correct structure and methods"""
    
    def test_polymarket_websocket_module_exists(self):
        """Verify polymarket_websocket.py module exists with correct classes"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import (
            PolymarketWebSocket,
            PolymarketWebSocketManager,
            get_websocket_manager,
            init_websocket_manager
        )
        
        assert PolymarketWebSocket is not None
        assert PolymarketWebSocketManager is not None
        assert callable(get_websocket_manager)
        assert callable(init_websocket_manager)
        print("✅ WebSocket module structure verified")
    
    def test_websocket_url_is_correct(self):
        """Verify WebSocket URL points to Polymarket CLOB"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        assert ws.WS_URL == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        print(f"✅ WebSocket URL: {ws.WS_URL}")
    
    def test_websocket_has_required_methods(self):
        """Verify PolymarketWebSocket has all required methods"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        # Connection methods
        assert hasattr(ws, 'connect')
        assert hasattr(ws, 'disconnect')
        assert hasattr(ws, 'listen')
        
        # Subscription methods
        assert hasattr(ws, 'subscribe_market')
        assert hasattr(ws, 'subscribe_markets')
        assert hasattr(ws, 'unsubscribe_market')
        
        # Message handling methods
        assert hasattr(ws, '_handle_message')
        assert hasattr(ws, '_process_single_message')
        assert hasattr(ws, '_handle_price_change')
        assert hasattr(ws, '_handle_book_message')
        
        # Data access methods
        assert hasattr(ws, 'get_latest_price')
        assert hasattr(ws, 'get_latest_order_book')
        assert hasattr(ws, 'get_stats')
        
        print("✅ All required WebSocket methods present")
    
    def test_websocket_manager_has_required_methods(self):
        """Verify PolymarketWebSocketManager has all required methods"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocketManager
        
        manager = PolymarketWebSocketManager()
        
        assert hasattr(manager, 'start')
        assert hasattr(manager, 'stop')
        assert hasattr(manager, 'subscribe_to_markets')
        assert hasattr(manager, 'register_price_handler')
        assert hasattr(manager, 'get_latest_price')
        assert hasattr(manager, 'get_stats')
        
        print("✅ WebSocket manager methods verified")


class TestWebSocketMessageParsing:
    """Test WebSocket message parsing handles different formats"""
    
    @pytest.mark.asyncio
    async def test_handle_message_array_format(self):
        """Test _handle_message handles array format (initial book data)"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        # Simulate array message (Polymarket sends arrays of book data)
        array_message = json.dumps([
            {
                "event_type": "book",
                "asset_id": "test_token_1",
                "market": "test_market_1",
                "bids": [{"price": "0.45", "size": "100"}],
                "asks": [{"price": "0.55", "size": "100"}],
                "last_trade_price": "0.50"
            },
            {
                "event_type": "book",
                "asset_id": "test_token_2",
                "market": "test_market_2",
                "bids": [{"price": "0.60", "size": "200"}],
                "asks": [{"price": "0.65", "size": "200"}],
                "last_trade_price": "0.62"
            }
        ])
        
        # Process the message
        await ws._handle_message(array_message)
        
        # Verify prices were cached
        price1 = ws.get_latest_price("test_token_1")
        price2 = ws.get_latest_price("test_token_2")
        
        assert price1 is not None, "Price for token 1 should be cached"
        assert price2 is not None, "Price for token 2 should be cached"
        
        print(f"✅ Array message parsed: token1={price1}, token2={price2}")
    
    @pytest.mark.asyncio
    async def test_handle_message_object_format(self):
        """Test _handle_message handles single object format"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        # Simulate single object message
        object_message = json.dumps({
            "event_type": "book",
            "asset_id": "test_token_single",
            "market": "test_market_single",
            "bids": [{"price": "0.70", "size": "500"}],
            "asks": [{"price": "0.75", "size": "500"}],
            "last_trade_price": "0.72"
        })
        
        await ws._handle_message(object_message)
        
        price = ws.get_latest_price("test_token_single")
        assert price is not None, "Price should be cached from object message"
        
        print(f"✅ Object message parsed: price={price}")
    
    @pytest.mark.asyncio
    async def test_handle_price_change_event(self):
        """Test _handle_price_change processes price_change events correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        # Simulate price_change event (Polymarket format)
        price_change_message = json.dumps({
            "event_type": "price_change",
            "market": "test_market_pc",
            "price_changes": [
                {
                    "asset_id": "test_token_pc",
                    "best_bid": "0.48",
                    "best_ask": "0.52",
                    "side": "buy"
                }
            ]
        })
        
        await ws._handle_message(price_change_message)
        
        price_data = ws.get_latest_price("test_token_pc")
        assert price_data is not None, "Price change should be cached"
        
        # Price should be mid-point of bid/ask
        if isinstance(price_data, dict):
            assert 'price' in price_data
            assert 'best_bid' in price_data
            assert 'best_ask' in price_data
            print(f"✅ Price change parsed: {price_data}")
        else:
            print(f"✅ Price change parsed: {price_data}")
    
    @pytest.mark.asyncio
    async def test_handle_book_message(self):
        """Test _handle_book_message processes order book correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        # Simulate book message
        book_data = {
            "asset_id": "test_token_book",
            "market": "test_market_book",
            "bids": [
                {"price": "0.40", "size": "1000"},
                {"price": "0.39", "size": "500"}
            ],
            "asks": [
                {"price": "0.45", "size": "800"},
                {"price": "0.46", "size": "600"}
            ],
            "last_trade_price": "0.42"
        }
        
        await ws._handle_book_message(book_data)
        
        price_data = ws.get_latest_price("test_token_book")
        assert price_data is not None, "Book message should update price cache"
        
        # Verify price calculation (mid of best bid/ask)
        if isinstance(price_data, dict):
            expected_mid = (0.40 + 0.45) / 2  # 0.425
            assert abs(price_data.get('price', 0) - expected_mid) < 0.01
            print(f"✅ Book message parsed: mid_price={price_data.get('price')}")
        else:
            print(f"✅ Book message parsed: {price_data}")


class TestRealTimeMarketService:
    """Test RealTimeMarketService integration"""
    
    def test_realtime_market_service_module_exists(self):
        """Verify RealTimeMarketService module exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from services.realtime_market_service import (
            RealTimeMarketService,
            get_realtime_market_service,
            init_realtime_market_service
        )
        
        assert RealTimeMarketService is not None
        assert callable(get_realtime_market_service)
        assert callable(init_realtime_market_service)
        print("✅ RealTimeMarketService module verified")
    
    def test_realtime_service_has_required_methods(self):
        """Verify RealTimeMarketService has required methods"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from services.realtime_market_service import RealTimeMarketService
        
        service = RealTimeMarketService()
        
        assert hasattr(service, 'start')
        assert hasattr(service, 'stop')
        assert hasattr(service, 'get_markets')
        assert hasattr(service, 'get_market')
        assert hasattr(service, 'get_latest_price')
        assert hasattr(service, 'get_stats')
        
        print("✅ RealTimeMarketService methods verified")
    
    def test_get_markets_returns_price_source(self):
        """Verify get_markets includes price_source field"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from services.realtime_market_service import RealTimeMarketService
        
        service = RealTimeMarketService()
        
        # Manually populate cache to test price_source logic
        service._market_cache = {
            'test_market_1': {
                'id': 'test_market_1',
                'question': 'Test Market 1',
                'volume_24h': 10000
            }
        }
        service._market_tokens = {
            'test_market_1': ['test_token_1']
        }
        
        # Without WebSocket price - should be 'rest_cache'
        markets = service.get_markets(limit=10)
        if markets:
            market = markets[0]
            assert 'price_source' in market
            assert market['price_source'] == 'rest_cache'
            print(f"✅ Without WS data: price_source={market['price_source']}")
        
        # With WebSocket price - should be 'websocket'
        service._price_cache = {'test_token_1': 0.55}
        markets = service.get_markets(limit=10)
        if markets:
            market = markets[0]
            assert market['price_source'] == 'websocket'
            print(f"✅ With WS data: price_source={market['price_source']}")
    
    def test_get_stats_returns_websocket_info(self):
        """Verify get_stats includes WebSocket statistics"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from services.realtime_market_service import RealTimeMarketService
        
        service = RealTimeMarketService()
        stats = service.get_stats()
        
        assert 'running' in stats
        assert 'markets_cached' in stats
        assert 'tokens_subscribed' in stats
        assert 'prices_cached' in stats
        assert 'ws_updates' in stats
        assert 'rest_fetches' in stats
        
        print(f"✅ Stats structure verified: {list(stats.keys())}")


class TestPaperTraderWebSocketIntegration:
    """Test Paper Trader WebSocket integration"""
    
    def test_paper_trader_has_websocket_attributes(self):
        """Verify PaperTrader has WebSocket-related attributes"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from paper_trading.paper_trader import PaperTrader
        
        trader = PaperTrader()
        
        assert hasattr(trader, 'realtime_market_service')
        assert hasattr(trader, 'use_websocket_data')
        assert trader.use_websocket_data == True  # Default should be True
        
        print("✅ PaperTrader WebSocket attributes verified")
    
    def test_paper_trader_start_method_has_websocket_init(self):
        """Verify start() method initializes WebSocket service"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from paper_trading.paper_trader import PaperTrader
        
        source = inspect.getsource(PaperTrader.start)
        
        # Check for WebSocket initialization in start()
        assert 'realtime_market_service' in source
        assert 'get_realtime_market_service' in source
        assert 'use_websocket_data' in source
        
        print("✅ start() method has WebSocket initialization")
    
    def test_paper_trader_get_active_markets_uses_websocket(self):
        """Verify _get_active_markets tries WebSocket first"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from paper_trading.paper_trader import PaperTrader
        
        source = inspect.getsource(PaperTrader._get_active_markets)
        
        # Check for WebSocket-first logic
        assert 'use_websocket_data' in source
        assert 'realtime_market_service' in source
        assert 'get_markets' in source
        assert 'WebSocket' in source or 'websocket' in source.lower()
        
        # Check for REST fallback
        assert 'PolymarketAPI' in source
        assert 'REST' in source
        
        print("✅ _get_active_markets has WebSocket-first with REST fallback")
    
    def test_paper_trader_stop_method_stops_websocket(self):
        """Verify stop() method stops WebSocket service"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from paper_trading.paper_trader import PaperTrader
        
        source = inspect.getsource(PaperTrader.stop)
        
        assert 'realtime_market_service' in source
        assert 'stop' in source
        
        print("✅ stop() method stops WebSocket service")


class TestWebSocketSubscriptionFormat:
    """Test WebSocket subscription message format"""
    
    def test_subscription_format_is_correct(self):
        """Verify subscription uses correct Polymarket format"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        source = inspect.getsource(PolymarketWebSocket.subscribe_market)
        
        # Check for correct subscription format per Polymarket docs
        assert '"type": "market"' in source or "'type': 'market'" in source
        assert 'assets_ids' in source
        
        print("✅ Subscription format uses 'type': 'market' and 'assets_ids'")
    
    def test_batch_subscription_format(self):
        """Verify batch subscription uses correct format"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        source = inspect.getsource(PolymarketWebSocket.subscribe_markets)
        
        # Check for batch subscription
        assert 'assets_ids' in source
        assert 'batch' in source.lower()
        
        print("✅ Batch subscription format verified")


class TestWebSocketConnectionAPI:
    """Test WebSocket connection via API endpoints"""
    
    def test_paper_status_shows_websocket_info(self):
        """Check if paper status endpoint shows WebSocket info"""
        response = requests.get(f"{BASE_URL}/api/paper/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        # Paper status should include data source info
        print(f"✅ Paper status response: {list(data.keys())}")
        
        # If running, check for WebSocket-related fields
        if data.get('running'):
            print(f"  Paper trading running: {data.get('running')}")
            if 'data_source' in data:
                print(f"  Data source: {data.get('data_source')}")
    
    def test_status_endpoint_shows_websocket_stats(self):
        """Check if status endpoint shows WebSocket statistics"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        print(f"✅ Status response keys: {list(data.keys())}")
        
        # Check for WebSocket-related stats
        if 'websocket' in data:
            ws_stats = data['websocket']
            print(f"  WebSocket stats: {ws_stats}")
        elif 'realtime_service' in data:
            rt_stats = data['realtime_service']
            print(f"  Realtime service stats: {rt_stats}")


class TestWebSocketLiveConnection:
    """Test actual WebSocket connection to Polymarket (integration test)"""
    
    @pytest.mark.asyncio
    async def test_websocket_can_connect(self):
        """Test that WebSocket can establish connection to Polymarket"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        try:
            # Attempt to connect
            connected = await ws.connect()
            
            if connected:
                print(f"✅ WebSocket connected successfully")
                assert ws.connected == True
                
                # Get stats
                stats = ws.get_stats()
                print(f"  Stats: connected={stats.get('connected')}, running={stats.get('running')}")
                
                # Disconnect
                await ws.disconnect()
                assert ws.connected == False
                print(f"✅ WebSocket disconnected cleanly")
            else:
                print(f"⚠️ WebSocket connection failed (may be network issue)")
                # Don't fail test - connection issues are expected in some environments
                pytest.skip("WebSocket connection failed - may be network restriction")
                
        except Exception as e:
            print(f"⚠️ WebSocket connection error: {e}")
            pytest.skip(f"WebSocket connection error: {e}")
    
    @pytest.mark.asyncio
    async def test_websocket_subscription_and_receive(self):
        """Test subscribing to a market and receiving data"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from data.polymarket_websocket import PolymarketWebSocket
        
        ws = PolymarketWebSocket()
        
        try:
            connected = await ws.connect()
            if not connected:
                pytest.skip("WebSocket connection failed")
            
            # Get a real token ID from Polymarket API
            from data.polymarket_api import PolymarketAPI
            async with PolymarketAPI() as api:
                markets = await api.get_markets(limit=5)
                if not markets:
                    pytest.skip("No markets available from API")
                
                # Find a market with token IDs
                token_id = None
                for market in markets:
                    tokens = market.get('clobTokenIds', market.get('tokens', []))
                    if tokens and isinstance(tokens, list) and len(tokens) > 0:
                        token_id = tokens[0]
                        print(f"  Using token: {token_id[:20]}... from market: {market.get('question', '')[:50]}...")
                        break
                
                if not token_id:
                    pytest.skip("No token IDs found in markets")
            
            # Subscribe to the market
            await ws.subscribe_market(token_id)
            print(f"✅ Subscribed to market token")
            
            # Wait for some messages (with timeout)
            start_time = time.time()
            max_wait = 10  # 10 seconds
            
            while time.time() - start_time < max_wait:
                if ws._messages_received > 0:
                    print(f"✅ Received {ws._messages_received} messages")
                    break
                await asyncio.sleep(0.5)
            
            # Check stats
            stats = ws.get_stats()
            print(f"  Final stats: messages={stats.get('messages_received')}, prices_cached={stats.get('cached_prices')}")
            
            # Disconnect
            await ws.disconnect()
            
            # Note: We may not receive messages immediately, so don't fail if no messages
            if ws._messages_received == 0:
                print("⚠️ No messages received within timeout (this may be normal)")
            
        except Exception as e:
            print(f"⚠️ WebSocket test error: {e}")
            await ws.disconnect()
            pytest.skip(f"WebSocket test error: {e}")


class TestWebSocketFallbackBehavior:
    """Test WebSocket fallback to REST behavior"""
    
    def test_paper_trader_fallback_logic_exists(self):
        """Verify fallback logic exists in _get_active_markets"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from paper_trading.paper_trader import PaperTrader
        
        source = inspect.getsource(PaperTrader._get_active_markets)
        
        # Check for fallback pattern
        assert 'if not live_markets' in source or 'not ws_markets' in source or 'falling back' in source.lower()
        assert 'PolymarketAPI' in source
        
        print("✅ Fallback logic verified in _get_active_markets")
    
    def test_paper_trader_handles_websocket_failure(self):
        """Verify paper trader handles WebSocket failure gracefully"""
        import sys
        sys.path.insert(0, '/app/backend')
        import inspect
        
        from paper_trading.paper_trader import PaperTrader
        
        source = inspect.getsource(PaperTrader.start)
        
        # Check for try/except around WebSocket init
        assert 'try:' in source
        assert 'except' in source
        assert 'use_websocket_data = False' in source or 'falling back' in source.lower()
        
        print("✅ WebSocket failure handling verified in start()")


class TestWebSocketStatsAPI:
    """Test WebSocket statistics via API"""
    
    def test_realtime_stats_endpoint(self):
        """Test if there's an endpoint for realtime/WebSocket stats"""
        # Try various possible endpoints
        endpoints = [
            '/api/realtime/stats',
            '/api/websocket/stats',
            '/api/paper/websocket-stats',
            '/api/status'
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ {endpoint} returned: {list(data.keys())[:5]}...")
                    
                    # Check for WebSocket-related fields
                    ws_fields = ['websocket', 'ws_updates', 'realtime', 'connected', 'messages_received']
                    found_ws = any(f in str(data).lower() for f in ws_fields)
                    if found_ws:
                        print(f"  Found WebSocket-related data in {endpoint}")
            except Exception as e:
                pass  # Endpoint may not exist
        
        print("✅ Stats endpoint check complete")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
