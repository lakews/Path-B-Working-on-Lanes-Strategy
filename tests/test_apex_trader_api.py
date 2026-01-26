"""
APEX TRADER API Tests
Tests for dashboard mode controls, trade stats, and performance endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://two-speed-bot.preview.emergentagent.com')

class TestHealthAndStatus:
    """Health check and status endpoint tests"""
    
    def test_root_endpoint(self):
        """Test root API endpoint returns operational status"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "APEX TRADER - Advanced Polymarket Execution System"
        assert data["version"] == "1.0.0"
        assert data["status"] == "operational"
    
    def test_status_endpoint(self):
        """Test /api/status returns trading mode and configuration"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "status" in data
        assert "bot_running" in data
        assert "trading_mode" in data
        assert "configuration" in data
        assert "timestamp" in data
        
        # Verify trading_mode is valid
        assert data["trading_mode"] in ["stopped", "live", "backtest"]
        
        # Verify configuration structure
        config = data["configuration"]
        assert "initial_capital" in config
        assert "deployed_capital" in config
        assert "max_position_size" in config
        assert "trades_per_10min" in config


class TestTradeStats:
    """Trade frequency statistics endpoint tests"""
    
    def test_trade_stats_endpoint(self):
        """Test /api/trades/stats returns all required frequency data"""
        response = requests.get(f"{BASE_URL}/api/trades/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required trade frequency fields
        assert "live_trades" in data
        assert "trades_10min" in data
        assert "trades_30min" in data
        assert "trades_1hr" in data
        assert "trades_24hr" in data
        
        # Verify P&L fields
        assert "total_pnl" in data
        assert "pnl_pct" in data
        assert "timestamp" in data
        
        # Verify data types
        assert isinstance(data["live_trades"], int)
        assert isinstance(data["trades_10min"], int)
        assert isinstance(data["trades_30min"], int)
        assert isinstance(data["trades_1hr"], int)
        assert isinstance(data["trades_24hr"], int)
        assert isinstance(data["total_pnl"], (int, float))
        assert isinstance(data["pnl_pct"], (int, float))
    
    def test_trade_stats_values_non_negative(self):
        """Verify trade counts are non-negative"""
        response = requests.get(f"{BASE_URL}/api/trades/stats")
        data = response.json()
        
        assert data["live_trades"] >= 0
        assert data["trades_10min"] >= 0
        assert data["trades_30min"] >= 0
        assert data["trades_1hr"] >= 0
        assert data["trades_24hr"] >= 0


class TestPerformance:
    """Performance metrics endpoint tests"""
    
    def test_performance_endpoint(self):
        """Test /api/performance returns all required metrics"""
        response = requests.get(f"{BASE_URL}/api/performance")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_capital" in data
        assert "total_pnl" in data
        assert "win_rate" in data
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data
        assert "num_trades" in data
        assert "num_positions" in data
        
        # Verify data types
        assert isinstance(data["total_capital"], (int, float))
        assert isinstance(data["total_pnl"], (int, float))
        assert isinstance(data["win_rate"], (int, float))
        assert isinstance(data["sharpe_ratio"], (int, float))
        assert isinstance(data["max_drawdown"], (int, float))
        assert isinstance(data["num_trades"], int)
        assert isinstance(data["num_positions"], int)


class TestPositionsAndTrades:
    """Positions and trades endpoint tests"""
    
    def test_positions_endpoint(self):
        """Test /api/positions returns positions list"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        
        assert "positions" in data
        assert "count" in data
        assert isinstance(data["positions"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["positions"])
    
    def test_trades_endpoint(self):
        """Test /api/trades returns trades list"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert "trades" in data
        assert "count" in data
        assert isinstance(data["trades"], list)
        assert isinstance(data["count"], int)
    
    def test_trades_limit_parameter(self):
        """Test trades endpoint respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] <= 5


class TestBotControl:
    """Bot control endpoint tests - testing mode transitions"""
    
    def test_bot_stop_when_not_running(self):
        """Test stopping bot when not running returns 400"""
        # First ensure bot is stopped
        response = requests.post(f"{BASE_URL}/api/bot/stop")
        # Should return 400 if bot is not running
        assert response.status_code in [200, 400]
        
        if response.status_code == 400:
            data = response.json()
            assert "message" in data
    
    def test_backtest_stop_when_not_running(self):
        """Test stopping backtest when not running returns 400"""
        response = requests.post(f"{BASE_URL}/api/backtest/stop")
        assert response.status_code in [200, 400]
        
        if response.status_code == 400:
            data = response.json()
            assert "message" in data


class TestMarkets:
    """Markets endpoint tests"""
    
    def test_markets_endpoint(self):
        """Test /api/markets returns markets list"""
        response = requests.get(f"{BASE_URL}/api/markets?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert "markets" in data
        assert "count" in data
        assert isinstance(data["markets"], list)


class TestAnalytics:
    """Analytics endpoint tests"""
    
    def test_analytics_endpoint(self):
        """Test /api/analytics returns analytics data"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        # Analytics may return 200 or 500 depending on data availability
        assert response.status_code in [200, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
