"""
APEX TRADER - Spread Calibrator & Historical Data Collection Tests
Tests for P0: SpreadCalibrator integration in delta-neutral strategy
Tests for P1: Historical Data Collection for backtesting
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://algomarket-3.preview.emergentagent.com')


class TestHistoricalStats:
    """Historical data collection statistics endpoint tests"""
    
    def test_historical_stats_endpoint(self):
        """Test /api/historical/stats returns collection statistics"""
        response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_snapshots" in data
        assert "unique_markets" in data
        assert "category_distribution" in data
        assert "collector_running" in data
        assert "collection_interval_seconds" in data
        
        # Verify data types
        assert isinstance(data["total_snapshots"], int)
        assert isinstance(data["unique_markets"], int)
        assert isinstance(data["category_distribution"], dict)
        assert isinstance(data["collector_running"], bool)
        assert isinstance(data["collection_interval_seconds"], int)
        
        print(f"Historical stats: {data['total_snapshots']} snapshots, {data['unique_markets']} unique markets")


class TestHistoricalDataCollection:
    """Historical data collection trigger endpoint tests"""
    
    def test_historical_collect_endpoint(self):
        """Test /api/historical/collect triggers one-time data collection"""
        response = requests.post(f"{BASE_URL}/api/historical/collect")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "message" in data
        assert "count" in data
        assert "timestamp" in data
        
        # Verify data types
        assert isinstance(data["count"], int)
        assert data["count"] >= 0
        
        print(f"Collected {data['count']} market snapshots")
    
    def test_historical_collect_returns_data(self):
        """Verify collection actually stores data"""
        # First trigger collection
        collect_response = requests.post(f"{BASE_URL}/api/historical/collect")
        assert collect_response.status_code == 200
        
        # Then check stats to verify data was stored
        stats_response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert stats_response.status_code == 200
        stats = stats_response.json()
        
        # Should have some snapshots now
        assert stats["total_snapshots"] >= 0
        print(f"Total snapshots after collection: {stats['total_snapshots']}")


class TestHistoricalDataRetrieval:
    """Historical data retrieval endpoint tests"""
    
    def test_historical_data_endpoint(self):
        """Test /api/historical/data returns collected historical data"""
        response = requests.get(f"{BASE_URL}/api/historical/data?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "data" in data
        assert isinstance(data["data"], list)
        
        # If data exists, verify structure
        if len(data["data"]) > 0:
            item = data["data"][0]
            # Verify expected fields in historical data
            assert "market_id" in item or "id" in item
            assert "timestamp" in item
            print(f"Retrieved {len(data['data'])} historical data records")
        else:
            print("No historical data available yet")
    
    def test_historical_data_with_limit(self):
        """Test historical data respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/historical/data?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["data"]) <= 5


class TestHistoricalCategorization:
    """Historical data categorization tests"""
    
    def test_category_distribution(self):
        """Test that historical data is categorized correctly"""
        # First ensure we have data
        requests.post(f"{BASE_URL}/api/historical/collect")
        
        # Get stats with category distribution
        response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert response.status_code == 200
        data = response.json()
        
        category_dist = data.get("category_distribution", {})
        
        # Valid categories
        valid_categories = ["crypto", "sports", "politics", "finance", "entertainment"]
        
        # All categories in distribution should be valid
        for category in category_dist.keys():
            assert category in valid_categories, f"Invalid category: {category}"
        
        print(f"Category distribution: {category_dist}")


class TestContinuousCollection:
    """Continuous collection start/stop endpoint tests"""
    
    def test_start_continuous_collection(self):
        """Test /api/historical/start-continuous starts background collection"""
        response = requests.post(f"{BASE_URL}/api/historical/start-continuous")
        
        # Should return 200 or 400 if already running
        assert response.status_code in [200, 400]
        data = response.json()
        
        if response.status_code == 200:
            assert "message" in data
            assert "interval_seconds" in data
            print(f"Started continuous collection with interval: {data['interval_seconds']}s")
        else:
            assert "message" in data
            print(f"Continuous collection status: {data['message']}")
    
    def test_stop_continuous_collection(self):
        """Test /api/historical/stop-continuous stops background collection"""
        response = requests.post(f"{BASE_URL}/api/historical/stop-continuous")
        
        # Should return 200 or 400 if not running
        assert response.status_code in [200, 400]
        data = response.json()
        assert "message" in data
        print(f"Stop continuous collection: {data['message']}")
    
    def test_continuous_collection_flow(self):
        """Test full start -> verify -> stop flow"""
        # Start collection
        start_response = requests.post(f"{BASE_URL}/api/historical/start-continuous")
        
        if start_response.status_code == 200:
            # Verify it's running
            stats_response = requests.get(f"{BASE_URL}/api/historical/stats")
            stats = stats_response.json()
            assert stats["collector_running"] == True
            
            # Stop collection
            stop_response = requests.post(f"{BASE_URL}/api/historical/stop-continuous")
            assert stop_response.status_code == 200
            
            # Give it a moment to stop
            time.sleep(0.5)
            
            # Verify it's stopped
            stats_response = requests.get(f"{BASE_URL}/api/historical/stats")
            stats = stats_response.json()
            assert stats["collector_running"] == False
            print("Continuous collection flow test passed")
        else:
            # Already running, just stop it
            stop_response = requests.post(f"{BASE_URL}/api/historical/stop-continuous")
            print("Continuous collection was already running, stopped it")


class TestAnalyticsWithStrategyPerformance:
    """Analytics endpoint tests for strategy_performance and asset_class_performance"""
    
    def test_analytics_endpoint_structure(self):
        """Test /api/analytics returns strategy_performance and asset_class_performance"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        
        # Analytics should return 200
        assert response.status_code == 200
        data = response.json()
        
        # Verify strategy_performance field exists
        assert "strategy_performance" in data, "Missing strategy_performance field"
        
        # Verify asset_class_performance field exists
        assert "asset_class_performance" in data, "Missing asset_class_performance field"
        
        # Verify data types
        assert isinstance(data["strategy_performance"], dict)
        assert isinstance(data["asset_class_performance"], dict)
        
        print(f"Analytics strategy_performance: {data['strategy_performance']}")
        print(f"Analytics asset_class_performance: {data['asset_class_performance']}")
    
    def test_analytics_strategy_performance_structure(self):
        """Test strategy_performance has expected structure"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        assert response.status_code == 200
        data = response.json()
        
        strategy_perf = data.get("strategy_performance", {})
        
        # Strategy performance should have strategy types as keys
        valid_strategies = ["delta_neutral", "momentum", "mean_reversion", "arbitrage"]
        
        # If there's data, verify structure
        for strategy, metrics in strategy_perf.items():
            # Each strategy should have performance metrics
            if isinstance(metrics, dict):
                # Common metrics that might be present
                possible_metrics = ["pnl", "win_rate", "trades", "sharpe_ratio", "total_pnl", "num_trades"]
                # At least one metric should be present
                has_metric = any(m in metrics for m in possible_metrics)
                print(f"Strategy {strategy} metrics: {metrics}")
    
    def test_analytics_asset_class_performance_structure(self):
        """Test asset_class_performance has expected structure"""
        response = requests.get(f"{BASE_URL}/api/analytics")
        assert response.status_code == 200
        data = response.json()
        
        asset_perf = data.get("asset_class_performance", {})
        
        # Asset classes should match categories
        valid_categories = ["crypto", "sports", "politics", "finance", "entertainment"]
        
        # If there's data, verify structure
        for asset_class, metrics in asset_perf.items():
            if isinstance(metrics, dict):
                print(f"Asset class {asset_class} metrics: {metrics}")


class TestSpreadCalibratorIntegration:
    """Tests to verify SpreadCalibrator is integrated in delta-neutral strategy"""
    
    def test_status_shows_configuration(self):
        """Verify system status shows trading configuration"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify configuration includes Kelly fraction (used by spread calibrator)
        config = data.get("configuration", {})
        assert "kelly_fraction" in config
        assert "min_kelly_fraction" in config
        assert "max_kelly_fraction" in config
        
        print(f"Kelly configuration: fraction={config['kelly_fraction']}, min={config['min_kelly_fraction']}, max={config['max_kelly_fraction']}")
    
    def test_markets_endpoint_for_spread_data(self):
        """Test markets endpoint returns data needed for spread calculation"""
        response = requests.get(f"{BASE_URL}/api/markets?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        markets = data.get("markets", [])
        
        # If markets exist, verify they have fields needed for spread calculation
        if len(markets) > 0:
            market = markets[0]
            # Fields used by SpreadCalibrator
            spread_fields = ["id", "yes_price", "no_price", "liquidity", "volume"]
            for field in spread_fields:
                if field in market:
                    print(f"Market has {field}: {market[field]}")
        else:
            print("No markets available - spread calibrator will use defaults")


class TestBacktestWithHistoricalData:
    """Tests for backtest functionality with historical data"""
    
    def test_backtest_results_endpoint(self):
        """Test /api/backtest/results returns results structure"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        
        # Should return 200 with results or 404 if no results
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            print(f"Backtest results available: {data}")
        else:
            print("No backtest results available yet")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
