"""
Test Suite: Gamma API Live Data Pipeline and Paper Trading gross_loss Fix
Iteration 14 - Testing the fix for deprecated CLOB API and KeyError: 'gross_loss' bug

Features tested:
1. /api/markets returns live data with source='gamma_api_live'
2. Markets have real prices (not all 0.5), high liquidity ($100K+), recent end dates
3. Paper Trading Start/Status/Stop flow works without errors
4. gross_loss KeyError is fixed in paper trading P&L calculation
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGammaAPILiveData:
    """Test the Gamma API live data pipeline fix"""
    
    def test_markets_endpoint_returns_live_data(self):
        """Verify /api/markets returns data with source='gamma_api_live'"""
        response = requests.get(f"{BASE_URL}/api/markets", params={"limit": 20})
        assert response.status_code == 200, f"Markets endpoint failed: {response.text}"
        
        data = response.json()
        assert "markets" in data, "Response missing 'markets' key"
        assert "source" in data, "Response missing 'source' key"
        
        # Verify source is gamma_api_live (not historical_data fallback)
        source = data.get("source")
        print(f"Markets source: {source}")
        assert source == "gamma_api_live", f"Expected source='gamma_api_live', got '{source}'"
        
        markets = data.get("markets", [])
        assert len(markets) > 0, "No markets returned"
        print(f"Returned {len(markets)} live markets from Gamma API")
    
    def test_markets_have_real_prices(self):
        """Verify markets have real prices (not all 0.5 default)"""
        response = requests.get(f"{BASE_URL}/api/markets", params={"limit": 20})
        assert response.status_code == 200
        
        data = response.json()
        markets = data.get("markets", [])
        assert len(markets) > 0, "No markets to test"
        
        # Check that not all prices are 0.5 (default/stale)
        prices = [m.get("yes_price", 0.5) for m in markets]
        unique_prices = set(prices)
        
        print(f"Sample prices: {prices[:5]}")
        print(f"Unique prices count: {len(unique_prices)}")
        
        # At least some prices should be different from 0.5
        non_default_prices = [p for p in prices if p != 0.5]
        assert len(non_default_prices) > 0, "All prices are 0.5 (stale/default data)"
        
        # Prices should be in valid range (0 to 1)
        for price in prices:
            assert 0 <= price <= 1, f"Invalid price: {price}"
        
        print(f"Found {len(non_default_prices)} markets with non-default prices")
    
    def test_markets_have_high_liquidity(self):
        """Verify markets have high liquidity ($100K+)"""
        response = requests.get(f"{BASE_URL}/api/markets", params={"limit": 20})
        assert response.status_code == 200
        
        data = response.json()
        markets = data.get("markets", [])
        assert len(markets) > 0, "No markets to test"
        
        # Check liquidity values
        high_liquidity_markets = []
        for m in markets:
            liquidity = m.get("liquidity", 0)
            if liquidity >= 100000:  # $100K+
                high_liquidity_markets.append({
                    "question": m.get("question", "")[:50],
                    "liquidity": liquidity
                })
        
        print(f"Markets with $100K+ liquidity: {len(high_liquidity_markets)}")
        for m in high_liquidity_markets[:3]:
            print(f"  - {m['question']}... (${m['liquidity']:,.0f})")
        
        # At least some markets should have high liquidity
        assert len(high_liquidity_markets) > 0, "No markets with $100K+ liquidity found"
    
    def test_markets_have_recent_end_dates(self):
        """Verify markets have recent end dates (2025-2026)"""
        response = requests.get(f"{BASE_URL}/api/markets", params={"limit": 20})
        assert response.status_code == 200
        
        data = response.json()
        markets = data.get("markets", [])
        assert len(markets) > 0, "No markets to test"
        
        # Check end dates
        recent_markets = []
        for m in markets:
            end_date = m.get("end_date", "")
            if end_date and ("2025" in str(end_date) or "2026" in str(end_date)):
                recent_markets.append({
                    "question": m.get("question", "")[:50],
                    "end_date": end_date
                })
        
        print(f"Markets with 2025-2026 end dates: {len(recent_markets)}")
        for m in recent_markets[:3]:
            print(f"  - {m['question']}... (ends: {m['end_date']})")
        
        # At least some markets should have recent end dates
        assert len(recent_markets) > 0, "No markets with 2025-2026 end dates found"
    
    def test_markets_structure_complete(self):
        """Verify market data structure is complete"""
        response = requests.get(f"{BASE_URL}/api/markets", params={"limit": 5})
        assert response.status_code == 200
        
        data = response.json()
        markets = data.get("markets", [])
        assert len(markets) > 0, "No markets to test"
        
        # Check required fields in first market
        market = markets[0]
        required_fields = ["id", "question", "category", "yes_price", "no_price", "volume", "liquidity"]
        
        for field in required_fields:
            assert field in market, f"Market missing required field: {field}"
        
        print(f"Market structure verified: {list(market.keys())}")


class TestPaperTradingGrossLossFix:
    """Test the gross_loss KeyError fix in paper trading"""
    
    @pytest.fixture
    def auth_token(self):
        """Get JWT authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/json",
            json={"username": "admin", "password": "apex2026!"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with Bearer token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_paper_trading_start(self, auth_headers):
        """Verify /api/paper/start works and creates a trading session"""
        # First stop any existing session
        requests.post(f"{BASE_URL}/api/paper/stop", headers=auth_headers)
        time.sleep(1)
        
        # Start paper trading
        response = requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        assert response.status_code == 200, f"Paper start failed: {response.text}"
        
        data = response.json()
        assert "session_id" in data or "message" in data, "Response missing expected fields"
        print(f"Paper trading started: {data}")
    
    def test_paper_trading_status_running(self, auth_headers):
        """Verify /api/paper/status shows running=true with session details"""
        # Ensure paper trading is started
        requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        time.sleep(2)  # Wait for session to initialize
        
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200, f"Paper status failed: {response.text}"
        
        data = response.json()
        print(f"Paper status: running={data.get('running')}, session_id={data.get('session_id')}")
        
        # Verify running status
        assert data.get("running") == True, f"Expected running=True, got {data.get('running')}"
        assert "session_id" in data, "Status missing session_id"
        
        # Verify key fields exist (these are needed for P&L calculation)
        assert "total_pnl" in data, "Status missing total_pnl"
        assert "current_capital" in data, "Status missing current_capital"
        assert "initial_capital" in data, "Status missing initial_capital"
    
    def test_paper_trading_status_has_strategy_results(self, auth_headers):
        """Verify status includes strategy_results with gross_profit/gross_loss fields"""
        # Ensure paper trading is started
        requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        time.sleep(2)
        
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify strategy_results structure exists
        assert "strategy_results" in data, "Status missing strategy_results"
        strategy_results = data.get("strategy_results", {})
        
        print(f"Strategy results: {list(strategy_results.keys())}")
        
        # Check that each strategy has the required fields (including gross_profit/gross_loss)
        for strategy, stats in strategy_results.items():
            assert "trades" in stats, f"Strategy {strategy} missing 'trades'"
            assert "pnl" in stats, f"Strategy {strategy} missing 'pnl'"
            assert "gross_profit" in stats, f"Strategy {strategy} missing 'gross_profit' (KeyError fix)"
            assert "gross_loss" in stats, f"Strategy {strategy} missing 'gross_loss' (KeyError fix)"
            print(f"  {strategy}: trades={stats['trades']}, pnl={stats['pnl']}, gross_profit={stats['gross_profit']}, gross_loss={stats['gross_loss']}")
    
    def test_paper_trading_status_has_asset_class_results(self, auth_headers):
        """Verify status includes asset_class_results with gross_profit/gross_loss fields"""
        # Ensure paper trading is started
        requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        time.sleep(2)
        
        response = requests.get(f"{BASE_URL}/api/paper/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify asset_class_results structure exists
        assert "asset_class_results" in data, "Status missing asset_class_results"
        asset_class_results = data.get("asset_class_results", {})
        
        print(f"Asset class results: {list(asset_class_results.keys())}")
        
        # Check that each asset class has the required fields (including gross_profit/gross_loss)
        for asset_class, stats in asset_class_results.items():
            assert "trades" in stats, f"Asset class {asset_class} missing 'trades'"
            assert "pnl" in stats, f"Asset class {asset_class} missing 'pnl'"
            assert "gross_profit" in stats, f"Asset class {asset_class} missing 'gross_profit' (KeyError fix)"
            assert "gross_loss" in stats, f"Asset class {asset_class} missing 'gross_loss' (KeyError fix)"
            print(f"  {asset_class}: trades={stats['trades']}, pnl={stats['pnl']}, gross_profit={stats['gross_profit']}, gross_loss={stats['gross_loss']}")
    
    def test_paper_trading_stop(self, auth_headers):
        """Verify /api/paper/stop works and closes all positions"""
        # Ensure paper trading is started first
        requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        time.sleep(2)
        
        # Stop paper trading
        response = requests.post(f"{BASE_URL}/api/paper/stop", headers=auth_headers)
        assert response.status_code == 200, f"Paper stop failed: {response.text}"
        
        data = response.json()
        print(f"Paper trading stopped: {data}")
        
        # Verify session stopped
        time.sleep(1)
        status_response = requests.get(f"{BASE_URL}/api/paper/status")
        status = status_response.json()
        
        # After stop, running should be False
        assert status.get("running") == False, f"Expected running=False after stop, got {status.get('running')}"
    
    def test_paper_trading_full_cycle_no_errors(self, auth_headers):
        """Test full paper trading cycle: start -> wait -> stop without KeyError"""
        # Stop any existing session
        requests.post(f"{BASE_URL}/api/paper/stop", headers=auth_headers)
        time.sleep(1)
        
        # Start paper trading
        start_response = requests.post(f"{BASE_URL}/api/paper/start", headers=auth_headers)
        assert start_response.status_code == 200, f"Start failed: {start_response.text}"
        print("Started paper trading session")
        
        # Wait for some trading activity
        time.sleep(5)
        
        # Check status multiple times (this is where KeyError would occur)
        for i in range(3):
            status_response = requests.get(f"{BASE_URL}/api/paper/status")
            assert status_response.status_code == 200, f"Status check {i+1} failed: {status_response.text}"
            status = status_response.json()
            
            # Verify no errors in response
            assert "error" not in status, f"Error in status: {status.get('error')}"
            
            # Verify strategy_results and asset_class_results are present
            assert "strategy_results" in status, f"Missing strategy_results in check {i+1}"
            assert "asset_class_results" in status, f"Missing asset_class_results in check {i+1}"
            
            print(f"Status check {i+1}: running={status.get('running')}, trades={status.get('total_trades')}")
            time.sleep(2)
        
        # Stop paper trading
        stop_response = requests.post(f"{BASE_URL}/api/paper/stop", headers=auth_headers)
        assert stop_response.status_code == 200, f"Stop failed: {stop_response.text}"
        print("Stopped paper trading session - No KeyError occurred!")


class TestHealthAndBasicEndpoints:
    """Basic health and endpoint tests"""
    
    def test_health_endpoint(self):
        """Verify health endpoint works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
    
    def test_status_endpoint(self):
        """Verify status endpoint works"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trading_mode" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
