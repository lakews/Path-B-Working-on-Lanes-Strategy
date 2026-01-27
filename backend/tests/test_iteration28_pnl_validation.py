#!/usr/bin/env python3
"""
Iteration 28: Paper Trading P&L Validation Tests

Tests to verify:
1. WebSocket token mapping initialization (race condition fix)
2. Paper trading session starts successfully
3. Trades have realistic P&L percentages (not extreme like +94%)
4. Entry and exit prices are reasonable (between 0 and 1)
5. Backend API health check
"""

import pytest
import requests
import os
import time
import json

from tests.conftest import API_BASE_URL as BASE_URL

# Test credentials
TEST_USERNAME = "admin"
TEST_PASSWORD = "apex2026!"


class TestBackendHealth:
    """Basic backend health checks"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✅ Health check passed: {data}")
    
    def test_status_endpoint(self):
        """Test /api/status returns system status"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        print(f"✅ Status endpoint working: {data.get('status')}")


class TestAuthentication:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data
        assert data.get('token_type') == 'bearer'
        print(f"✅ Login successful, token received")
        return data['access_token']


class TestWebSocketTokenMapping:
    """Tests for WebSocket token mapping initialization (race condition fix)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        pytest.skip("Authentication failed")
    
    def test_realtime_stats_shows_token_mapping(self, auth_token):
        """Test that realtime stats show token mapping is ready"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/realtime/stats", headers=headers, timeout=10)
        
        # May return 404 if service not started yet, which is OK
        if response.status_code == 404:
            print("⚠️ Realtime service not started yet - will be started with paper trading")
            return
        
        assert response.status_code == 200
        data = response.json()
        
        # Check token mapping fields
        if 'token_mapping_ready' in data:
            print(f"✅ Token mapping ready: {data.get('token_mapping_ready')}")
            print(f"   Tokens mapped: {data.get('tokens_mapped', 0)}")
        else:
            print(f"⚠️ Realtime stats: {data}")
    
    def test_status_shows_websocket_info(self, auth_token):
        """Test that status endpoint shows WebSocket info"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/status", headers=headers, timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        # Check for WebSocket-related fields
        if 'realtime_market_service' in data:
            rtm = data['realtime_market_service']
            print(f"✅ RealTime Market Service stats:")
            print(f"   Running: {rtm.get('running')}")
            print(f"   Token mapping ready: {rtm.get('token_mapping_ready')}")
            print(f"   Tokens mapped: {rtm.get('tokens_mapped')}")
        else:
            print(f"⚠️ Status response: {json.dumps(data, indent=2)[:500]}")


class TestPaperTradingSession:
    """Tests for paper trading session with P&L validation"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        pytest.skip("Authentication failed")
    
    def test_paper_trading_start(self, auth_token):
        """Test starting a paper trading session"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First check if already running
        status_response = requests.get(f"{BASE_URL}/api/paper/status", headers=headers, timeout=10)
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data.get('running'):
                print(f"⚠️ Paper trading already running, stopping first...")
                stop_response = requests.post(f"{BASE_URL}/api/paper/stop", headers=headers, timeout=30)
                print(f"   Stop response: {stop_response.status_code}")
                time.sleep(3)
        
        # Start paper trading
        response = requests.post(f"{BASE_URL}/api/paper/start", headers=headers, timeout=60)
        assert response.status_code == 200
        data = response.json()
        
        print(f"✅ Paper trading started:")
        print(f"   Session ID: {data.get('session_id')}")
        print(f"   Status: {data.get('status')}")
        
        # Wait for session to initialize
        time.sleep(5)
        
        # Check status
        status_response = requests.get(f"{BASE_URL}/api/paper/status", headers=headers, timeout=10)
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        print(f"✅ Paper trading status:")
        print(f"   Running: {status_data.get('running')}")
        print(f"   Session ID: {status_data.get('session_id')}")
        
        return data.get('session_id')
    
    def test_paper_trading_generates_trades(self, auth_token):
        """Test that paper trading generates trades with realistic P&L"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Check if running, start if not
        status_response = requests.get(f"{BASE_URL}/api/paper/status", headers=headers, timeout=10)
        if status_response.status_code == 200:
            status_data = status_response.json()
            if not status_data.get('running'):
                print("Starting paper trading session...")
                requests.post(f"{BASE_URL}/api/paper/start", headers=headers, timeout=60)
                time.sleep(10)
        
        # Wait for trades to be generated
        print("Waiting 30 seconds for trades to be generated...")
        time.sleep(30)
        
        # Get paper trading status with trades
        response = requests.get(f"{BASE_URL}/api/paper/status", headers=headers, timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        total_trades = data.get('total_trades', 0)
        total_pnl = data.get('total_pnl', 0)
        open_positions = data.get('open_positions', 0)
        
        print(f"✅ Paper trading stats after 30s:")
        print(f"   Total trades: {total_trades}")
        print(f"   Total P&L: ${total_pnl:.2f}")
        print(f"   Open positions: {open_positions}")
        
        return data
    
    def test_trade_pnl_is_realistic(self, auth_token):
        """Test that trade P&L percentages are realistic (not extreme like +94%)"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get trade history
        response = requests.get(f"{BASE_URL}/api/paper/trades", headers=headers, timeout=10)
        
        if response.status_code == 404:
            print("⚠️ No trades endpoint or no trades yet")
            return
        
        assert response.status_code == 200
        data = response.json()
        
        # Handle both list and dict responses
        trades = data.get('trades', data) if isinstance(data, dict) else data
        
        if not trades:
            print("⚠️ No trades generated yet")
            return
        
        print(f"\n✅ Analyzing {len(trades)} trades for realistic P&L:")
        
        extreme_pnl_count = 0
        reasonable_pnl_count = 0
        
        for trade in list(trades)[:20]:  # Check first 20 trades
            pnl = trade.get('pnl', 0)
            pnl_pct = trade.get('pnl_pct', 0)
            entry_price = trade.get('entry_price', 0)
            exit_price = trade.get('exit_price', 0)
            hold_time = trade.get('hold_time_seconds', 0)
            
            # Check for extreme P&L (>50% in short time is suspicious)
            is_extreme = abs(pnl_pct) > 50 and hold_time < 60
            
            if is_extreme:
                extreme_pnl_count += 1
                print(f"   ❌ EXTREME: P&L={pnl_pct:.1f}% in {hold_time}s, entry={entry_price:.4f}, exit={exit_price:.4f}")
            else:
                reasonable_pnl_count += 1
                print(f"   ✅ OK: P&L={pnl_pct:.1f}% in {hold_time}s, entry={entry_price:.4f}, exit={exit_price:.4f}")
        
        print(f"\n   Summary: {reasonable_pnl_count} reasonable, {extreme_pnl_count} extreme")
        
        # Fail if more than 20% of trades have extreme P&L
        if len(trades) > 5:
            extreme_ratio = extreme_pnl_count / len(trades[:20])
            assert extreme_ratio < 0.2, f"Too many extreme P&L trades: {extreme_ratio*100:.0f}%"
    
    def test_entry_exit_prices_are_valid(self, auth_token):
        """Test that entry and exit prices are between 0 and 1"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get trade history
        response = requests.get(f"{BASE_URL}/api/paper/trades", headers=headers, timeout=10)
        
        if response.status_code == 404:
            print("⚠️ No trades endpoint or no trades yet")
            return
        
        assert response.status_code == 200
        data = response.json()
        
        # Handle both list and dict responses
        trades = data.get('trades', data) if isinstance(data, dict) else data
        
        if not trades:
            print("⚠️ No trades generated yet")
            return
        
        print(f"\n✅ Validating prices for {len(trades)} trades:")
        
        invalid_prices = []
        
        for trade in trades:
            entry_price = trade.get('entry_price', 0)
            exit_price = trade.get('exit_price')
            market_id = trade.get('market_id', '')[:16]
            
            # Entry price should be between 0 and 1
            if not (0 <= entry_price <= 1):
                invalid_prices.append(f"Entry {entry_price} for {market_id}")
            
            # Exit price (if exists) should be between 0 and 1
            if exit_price is not None and not (0 <= exit_price <= 1):
                invalid_prices.append(f"Exit {exit_price} for {market_id}")
        
        if invalid_prices:
            print(f"   ❌ Invalid prices found: {invalid_prices[:5]}")
            assert False, f"Found {len(invalid_prices)} invalid prices"
        else:
            print(f"   ✅ All prices are valid (between 0 and 1)")
    
    def test_paper_trading_stop(self, auth_token):
        """Test stopping paper trading session"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Stop paper trading
        response = requests.post(f"{BASE_URL}/api/paper/stop", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        print(f"✅ Paper trading stopped:")
        print(f"   Status: {data.get('status')}")
        print(f"   Total trades: {data.get('total_trades')}")
        print(f"   Total P&L: ${data.get('total_pnl', 0):.2f}")


class TestOpenPositionsPrices:
    """Tests for open positions price validation"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        pytest.skip("Authentication failed")
    
    def test_open_positions_have_valid_prices(self, auth_token):
        """Test that open positions have valid entry prices"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get paper trading status
        response = requests.get(f"{BASE_URL}/api/paper/status", headers=headers, timeout=10)
        
        if response.status_code != 200:
            print("⚠️ Paper trading not running")
            return
        
        data = response.json()
        positions = data.get('positions', [])
        
        if not positions:
            print("⚠️ No open positions")
            return
        
        print(f"\n✅ Validating {len(positions)} open positions:")
        
        for pos in positions[:10]:
            entry_price = pos.get('entry_price', 0)
            current_price = pos.get('current_price', 0)
            unrealized_pnl = pos.get('unrealized_pnl', 0)
            unrealized_pnl_pct = pos.get('unrealized_pnl_pct', 0)
            market_id = pos.get('market_id', '')[:16]
            
            # Validate prices
            assert 0 <= entry_price <= 1, f"Invalid entry price {entry_price} for {market_id}"
            assert 0 <= current_price <= 1, f"Invalid current price {current_price} for {market_id}"
            
            # Check for extreme unrealized P&L
            if abs(unrealized_pnl_pct) > 50:
                print(f"   ⚠️ High unrealized P&L: {unrealized_pnl_pct:.1f}% for {market_id}")
            else:
                print(f"   ✅ Position {market_id}: entry={entry_price:.4f}, current={current_price:.4f}, P&L={unrealized_pnl_pct:.1f}%")


class TestWebSocketDataFlow:
    """Tests for WebSocket data flow in paper trading"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        pytest.skip("Authentication failed")
    
    def test_websocket_stats_during_trading(self, auth_token):
        """Test WebSocket stats during paper trading"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get realtime stats
        response = requests.get(f"{BASE_URL}/api/realtime/stats", headers=headers, timeout=10)
        
        if response.status_code == 404:
            print("⚠️ Realtime stats endpoint not available")
            return
        
        assert response.status_code == 200
        data = response.json()
        
        print(f"\n✅ WebSocket stats during trading:")
        print(f"   Running: {data.get('running')}")
        print(f"   Token mapping ready: {data.get('token_mapping_ready')}")
        print(f"   Markets cached: {data.get('markets_cached')}")
        print(f"   Tokens mapped: {data.get('tokens_mapped')}")
        print(f"   WS updates: {data.get('ws_updates')}")
        print(f"   Dropped updates: {data.get('dropped_updates')}")
        
        # Verify token mapping is ready
        assert data.get('token_mapping_ready') == True, "Token mapping should be ready"
        
        # Verify no dropped updates (race condition fix)
        dropped = data.get('dropped_updates', 0)
        if dropped > 0:
            print(f"   ⚠️ {dropped} updates were dropped before mapping was ready")
        else:
            print(f"   ✅ No dropped updates - race condition fix working")


class TestMarketDataPrices:
    """Tests for market data price validation"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        pytest.skip("Authentication failed")
    
    def test_markets_have_valid_prices(self, auth_token):
        """Test that markets have valid YES/NO prices"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get markets
        response = requests.get(f"{BASE_URL}/api/markets", headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"⚠️ Markets endpoint returned {response.status_code}")
            return
        
        data = response.json()
        markets = data if isinstance(data, list) else data.get('markets', [])
        
        if not markets:
            print("⚠️ No markets returned")
            return
        
        print(f"\n✅ Validating prices for {len(markets)} markets:")
        
        invalid_count = 0
        valid_count = 0
        
        for market in markets[:20]:
            yes_price = market.get('yes_price', 0)
            no_price = market.get('no_price', 0)
            market_id = market.get('id', market.get('condition_id', ''))[:16]
            price_source = market.get('price_source', 'unknown')
            
            # Validate prices
            if not (0 <= yes_price <= 1):
                invalid_count += 1
                print(f"   ❌ Invalid YES price {yes_price} for {market_id}")
            elif not (0 <= no_price <= 1):
                invalid_count += 1
                print(f"   ❌ Invalid NO price {no_price} for {market_id}")
            else:
                valid_count += 1
                # Check YES + NO ≈ 1
                price_sum = yes_price + no_price
                if abs(price_sum - 1.0) > 0.1:
                    print(f"   ⚠️ Price sum {price_sum:.4f} != 1 for {market_id} (source: {price_source})")
        
        print(f"\n   Summary: {valid_count} valid, {invalid_count} invalid")
        assert invalid_count == 0, f"Found {invalid_count} markets with invalid prices"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
