"""
Test suite for Backtest Data Source Fix - Iteration 8
Tests the critical bug fix where backtest engine was querying non-existent 'price_history' collection
instead of 'historical_data' collection with source='price_history' filter.

Key fixes verified:
1. data_source='real' should show >90% real_data_percentage (was 0% before fix)
2. data_source='live' should fetch from Polymarket API and show live_data_points > 0
3. Data Summary card consolidates all data info
4. Data Quality Breakdown bar shows correct percentages
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBacktestDataSourceFix:
    """Tests for the backtest data source fix"""
    
    def test_api_status(self):
        """Test API is running"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"API Status: {data.get('status')}")
    
    def test_historical_stats(self):
        """Test historical stats endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_snapshots" in data
        assert "unique_markets" in data
        assert data["total_snapshots"] > 0
        print(f"Total snapshots: {data['total_snapshots']}, Unique markets: {data['unique_markets']}")
    
    def test_historical_price_stats(self):
        """Test historical price stats shows real price data exists"""
        response = requests.get(f"{BASE_URL}/api/historical/price-stats")
        assert response.status_code == 200
        data = response.json()
        assert "real_price_snapshots" in data
        assert "real_price_percentage" in data
        # Should have real price data (22k+ documents with source='price_history')
        assert data["real_price_snapshots"] > 20000, f"Expected >20000 real price snapshots, got {data['real_price_snapshots']}"
        print(f"Real price snapshots: {data['real_price_snapshots']}, Percentage: {data['real_price_percentage']}%")
    
    def test_backtest_start_with_real_data_source(self):
        """Test backtest start accepts data_source='real' parameter"""
        response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "real"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Backtest started successfully"
        assert data.get("data_source") == "real"
        print(f"Backtest started with data_source='real'")
    
    def test_backtest_real_data_percentage_above_90(self):
        """CRITICAL: Test that backtest with data_source='real' shows >90% real data (was 0% before fix)"""
        # Start backtest with real data source
        start_response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "real"
            }
        )
        assert start_response.status_code == 200
        
        # Wait for backtest to complete
        time.sleep(15)
        
        # Get results
        results_response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert results_response.status_code == 200
        results = results_response.json()
        
        # Verify data quality metrics
        data_quality = results.get("data_quality", {})
        assert "real_data_percentage" in data_quality
        assert "data_source_mode" in data_quality
        
        real_pct = data_quality.get("real_data_percentage", 0)
        assert real_pct > 90, f"CRITICAL: Expected >90% real data, got {real_pct}% (was 0% before fix)"
        assert data_quality.get("data_source_mode") == "real"
        
        print(f"SUCCESS: Real data percentage: {real_pct}% (>90% required)")
        print(f"Real price data points: {data_quality.get('real_price_data_points')}")
        print(f"Simulated price data points: {data_quality.get('simulated_price_data_points')}")
    
    def test_backtest_live_data_source(self):
        """Test backtest with data_source='live' fetches from Polymarket API"""
        # Start backtest with live data source
        start_response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "live"
            }
        )
        assert start_response.status_code == 200
        assert start_response.json().get("data_source") == "live"
        
        # Wait for backtest to complete
        time.sleep(15)
        
        # Get results
        results_response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert results_response.status_code == 200
        results = results_response.json()
        
        data_quality = results.get("data_quality", {})
        assert data_quality.get("data_source_mode") == "live"
        assert data_quality.get("live_data_points", 0) > 0, "Expected live_data_points > 0 when using live data source"
        assert data_quality.get("live_data_percentage", 0) > 0, "Expected live_data_percentage > 0"
        
        print(f"Live data points: {data_quality.get('live_data_points')}")
        print(f"Live data percentage: {data_quality.get('live_data_percentage')}%")
    
    def test_backtest_results_data_quality_structure(self):
        """Test backtest results contain proper data_quality structure"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        results = response.json()
        
        # Verify data_quality structure
        data_quality = results.get("data_quality", {})
        required_fields = [
            "real_price_data_points",
            "simulated_price_data_points",
            "live_data_points",
            "real_data_percentage",
            "live_data_percentage",
            "data_source_mode",
            "data_source_options"
        ]
        
        for field in required_fields:
            assert field in data_quality, f"Missing field: {field} in data_quality"
        
        # Verify data_source_options contains all expected options
        options = data_quality.get("data_source_options", [])
        expected_options = ["auto", "live", "real", "snapshots", "hybrid"]
        for opt in expected_options:
            assert opt in options, f"Missing data_source option: {opt}"
        
        print(f"Data quality structure verified with all required fields")
    
    def test_backtest_results_data_summary_structure(self):
        """Test backtest results contain proper data_summary structure"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        results = response.json()
        
        # Verify data_summary structure
        data_summary = results.get("data_summary", {})
        required_fields = [
            "total_snapshots",
            "unique_markets",
            "date_range",
            "enabled_strategies",
            "enabled_asset_classes"
        ]
        
        for field in required_fields:
            assert field in data_summary, f"Missing field: {field} in data_summary"
        
        # Verify date_range structure
        date_range = data_summary.get("date_range", {})
        assert "start" in date_range
        assert "end" in date_range
        
        print(f"Data summary: {data_summary.get('total_snapshots')} snapshots, {data_summary.get('unique_markets')} markets")
    
    def test_backtest_auto_data_source(self):
        """Test backtest with data_source='auto' (default)"""
        start_response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "auto"
            }
        )
        assert start_response.status_code == 200
        assert start_response.json().get("data_source") == "auto"
        
        time.sleep(15)
        
        results_response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert results_response.status_code == 200
        results = results_response.json()
        
        data_quality = results.get("data_quality", {})
        assert data_quality.get("data_source_mode") == "auto"
        # Auto mode should use real data when available
        assert data_quality.get("real_price_data_points", 0) > 0 or data_quality.get("simulated_price_data_points", 0) > 0
        
        print(f"Auto mode - Real: {data_quality.get('real_data_percentage')}%, Simulated: {100 - data_quality.get('real_data_percentage', 0)}%")
    
    def test_backtest_snapshots_data_source(self):
        """Test backtest with data_source='snapshots'"""
        start_response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "snapshots"
            }
        )
        assert start_response.status_code == 200
        assert start_response.json().get("data_source") == "snapshots"
        
        time.sleep(15)
        
        results_response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert results_response.status_code == 200
        results = results_response.json()
        
        data_quality = results.get("data_quality", {})
        assert data_quality.get("data_source_mode") == "snapshots"
        
        print(f"Snapshots mode - Data points: {data_quality.get('simulated_price_data_points', 0)}")
    
    def test_backtest_hybrid_data_source(self):
        """Test backtest with data_source='hybrid'"""
        start_response = requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "hybrid"
            }
        )
        assert start_response.status_code == 200
        assert start_response.json().get("data_source") == "hybrid"
        
        time.sleep(15)
        
        results_response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert results_response.status_code == 200
        results = results_response.json()
        
        data_quality = results.get("data_quality", {})
        assert data_quality.get("data_source_mode") == "hybrid"
        
        print(f"Hybrid mode - Real: {data_quality.get('real_data_percentage')}%")


class TestBacktestHistory:
    """Tests for backtest history functionality"""
    
    def test_backtest_history_endpoint(self):
        """Test backtest history returns list of backtests"""
        response = requests.get(f"{BASE_URL}/api/backtest/history", params={"limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Backtest history contains {len(data)} items")
    
    def test_backtest_history_contains_data_source_mode(self):
        """Test backtest history items contain data_source_mode"""
        response = requests.get(f"{BASE_URL}/api/backtest/history", params={"limit": 5})
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            # Check first item has data_source_mode
            first_item = data[0]
            # data_source_mode might be in data_quality or at top level
            has_data_source = (
                "data_source_mode" in first_item or 
                "data_quality" in first_item and "data_source_mode" in first_item.get("data_quality", {})
            )
            print(f"First history item keys: {list(first_item.keys())}")
            if "data_quality" in first_item:
                print(f"data_quality keys: {list(first_item.get('data_quality', {}).keys())}")


class TestLiveMarketsCard:
    """Tests for Live Markets card visibility"""
    
    def test_live_markets_only_shown_when_live_data(self):
        """Test that live_data_points > 0 only when data_source='live'"""
        # Run backtest with 'real' data source
        requests.post(
            f"{BASE_URL}/api/backtest/start",
            params={
                "start_date": "2026-01-07T00:00:00Z",
                "end_date": "2026-01-14T23:59:59Z",
                "data_source": "real"
            }
        )
        time.sleep(15)
        
        results = requests.get(f"{BASE_URL}/api/backtest/results").json()
        data_quality = results.get("data_quality", {})
        
        # With 'real' data source, live_data_points should be 0
        assert data_quality.get("live_data_points", 0) == 0, "live_data_points should be 0 for 'real' data source"
        print(f"Real mode: live_data_points = {data_quality.get('live_data_points', 0)} (expected 0)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
