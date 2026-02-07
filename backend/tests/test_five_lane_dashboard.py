"""
Test Suite: Five-Lane Performance Dashboard (P0 Task)
=====================================================
Tests the 5-lane trading architecture display:
- HFT (High Frequency Trading)
- ALPHA (Directional)
- GAMMA (Moonshots)
- SPORTS (Sports Arbitrage)
- NEWS (Event Driven)

Verifies:
1. /api/analytics endpoint returns lane_performance
2. Backend strategy-to-lane mapping
3. LanePerformance component data structure
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAnalyticsEndpoint:
    """Test /api/analytics endpoint for lane_performance data"""
    
    def test_analytics_endpoint_returns_200(self):
        """Verify analytics endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ /api/analytics returns 200")
    
    def test_analytics_contains_lane_performance(self):
        """Verify lane_performance key exists in response"""
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=10)
        data = response.json()
        
        assert 'lane_performance' in data, "lane_performance key missing from analytics response"
        print(f"✅ lane_performance found in response")
        print(f"   Lanes present: {list(data['lane_performance'].keys())}")
    
    def test_lane_performance_has_hft_data(self):
        """Verify HFT lane data is present"""
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=10)
        data = response.json()
        lane_perf = data.get('lane_performance', {})
        
        # HFT should be present if there are HFT trades
        if 'HFT' in lane_perf:
            hft = lane_perf['HFT']
            assert 'total_pnl' in hft, "HFT missing total_pnl"
            assert 'total_trades' in hft, "HFT missing total_trades"
            assert 'win_rate' in hft, "HFT missing win_rate"
            print(f"✅ HFT lane data: {hft['total_trades']} trades, ${hft['total_pnl']:.2f} P&L, {hft['win_rate']:.1f}% win rate")
        else:
            print("⚠️ HFT lane not present (no HFT trades yet)")
    
    def test_lane_performance_has_alpha_data(self):
        """Verify ALPHA lane data is present"""
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=10)
        data = response.json()
        lane_perf = data.get('lane_performance', {})
        
        # ALPHA should be present if there are ALPHA trades
        if 'ALPHA' in lane_perf:
            alpha = lane_perf['ALPHA']
            assert 'total_pnl' in alpha, "ALPHA missing total_pnl"
            assert 'total_trades' in alpha, "ALPHA missing total_trades"
            assert 'win_rate' in alpha, "ALPHA missing win_rate"
            print(f"✅ ALPHA lane data: {alpha['total_trades']} trades, ${alpha['total_pnl']:.2f} P&L, {alpha['win_rate']:.1f}% win rate")
        else:
            print("⚠️ ALPHA lane not present (no ALPHA trades yet)")
    
    def test_lane_metrics_structure(self):
        """Verify lane metrics have correct structure"""
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=10)
        data = response.json()
        lane_perf = data.get('lane_performance', {})
        
        expected_fields = ['total_pnl', 'total_trades', 'win_rate', 'wins', 'losses', 'total_volume', 'avg_pnl_per_trade']
        
        for lane_name, lane_data in lane_perf.items():
            for field in expected_fields:
                assert field in lane_data, f"{lane_name} missing field: {field}"
            print(f"✅ {lane_name} has all required fields")


class TestStrategyLaneMapping:
    """Test backend strategy-to-lane mapping (risk_config.py)"""
    
    def test_sports_arbitrage_maps_to_sports(self):
        """Verify sports_arbitrage strategy maps to SPORTS lane"""
        from risk_config import RISK
        
        lane = RISK.get_strategy_path('sports_arbitrage')
        assert lane == 'SPORTS', f"Expected SPORTS, got {lane}"
        print("✅ sports_arbitrage -> SPORTS")
    
    def test_news_sniper_maps_to_news(self):
        """Verify news_sniper strategy maps to NEWS lane"""
        from risk_config import RISK
        
        lane = RISK.get_strategy_path('news_sniper')
        assert lane == 'NEWS', f"Expected NEWS, got {lane}"
        print("✅ news_sniper -> NEWS")
    
    def test_hft_strategies_map_to_hft(self):
        """Verify HFT strategies map to HFT lane"""
        from risk_config import RISK
        
        hft_strategies = ['hft_scalp', 'delta_neutral', 'hft_maker']
        for strategy in hft_strategies:
            lane = RISK.get_strategy_path(strategy)
            assert lane == 'HFT', f"Expected HFT for {strategy}, got {lane}"
            print(f"✅ {strategy} -> HFT")
    
    def test_alpha_strategies_map_to_alpha(self):
        """Verify ALPHA strategies map to ALPHA lane"""
        from risk_config import RISK
        
        alpha_strategies = ['alpha_directional', 'arbitrage']
        for strategy in alpha_strategies:
            lane = RISK.get_strategy_path(strategy)
            assert lane == 'ALPHA', f"Expected ALPHA for {strategy}, got {lane}"
            print(f"✅ {strategy} -> ALPHA")
    
    def test_gamma_strategies_map_to_gamma(self):
        """Verify GAMMA strategies map to GAMMA lane"""
        from risk_config import RISK
        
        gamma_strategies = ['gamma_scalp', 'volatility_exploitation']
        for strategy in gamma_strategies:
            lane = RISK.get_strategy_path(strategy)
            assert lane == 'GAMMA', f"Expected GAMMA for {strategy}, got {lane}"
            print(f"✅ {strategy} -> GAMMA")
    
    def test_all_five_lanes_supported(self):
        """Verify all 5 lanes are supported in mapping"""
        from risk_config import RISK
        
        test_cases = {
            'hft_scalp': 'HFT',
            'alpha_directional': 'ALPHA',
            'gamma_scalp': 'GAMMA',
            'sports_arbitrage': 'SPORTS',
            'news_sniper': 'NEWS'
        }
        
        for strategy, expected_lane in test_cases.items():
            actual_lane = RISK.get_strategy_path(strategy)
            assert actual_lane == expected_lane, f"{strategy}: expected {expected_lane}, got {actual_lane}"
        
        print("✅ All 5 lanes (HFT, ALPHA, GAMMA, SPORTS, NEWS) are supported")


class TestLanePerformanceCalculation:
    """Test lane metrics calculation in performance_analytics.py"""
    
    def test_lane_metrics_calculation_method_exists(self):
        """Verify _calculate_lane_metrics method exists"""
        from services.performance_analytics import PerformanceAnalytics
        
        analytics = PerformanceAnalytics()
        assert hasattr(analytics, '_calculate_lane_metrics'), "_calculate_lane_metrics method missing"
        print("✅ _calculate_lane_metrics method exists")
    
    def test_lane_metrics_returns_dict(self):
        """Verify _calculate_lane_metrics returns a dictionary"""
        from services.performance_analytics import PerformanceAnalytics
        
        analytics = PerformanceAnalytics()
        
        # Test with empty trades
        result = analytics._calculate_lane_metrics([])
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        print("✅ _calculate_lane_metrics returns dict")
    
    def test_lane_metrics_with_mock_trades(self):
        """Verify lane metrics calculation with mock trade data"""
        from services.performance_analytics import PerformanceAnalytics
        
        analytics = PerformanceAnalytics()
        
        # Mock trades with different lanes
        mock_trades = [
            {'strategy_lane': 'HFT', 'pnl': 10.0, 'size': 100, 'price': 0.5},
            {'strategy_lane': 'HFT', 'pnl': -5.0, 'size': 50, 'price': 0.6},
            {'strategy_lane': 'ALPHA', 'pnl': 20.0, 'size': 200, 'price': 0.4},
            {'strategy_lane': 'SPORTS', 'pnl': 15.0, 'size': 75, 'price': 0.7},
        ]
        
        result = analytics._calculate_lane_metrics(mock_trades)
        
        # Verify HFT lane
        assert 'HFT' in result, "HFT lane missing"
        assert result['HFT']['total_trades'] == 2, f"HFT trades: expected 2, got {result['HFT']['total_trades']}"
        assert result['HFT']['total_pnl'] == 5.0, f"HFT P&L: expected 5.0, got {result['HFT']['total_pnl']}"
        
        # Verify ALPHA lane
        assert 'ALPHA' in result, "ALPHA lane missing"
        assert result['ALPHA']['total_trades'] == 1, f"ALPHA trades: expected 1, got {result['ALPHA']['total_trades']}"
        
        # Verify SPORTS lane
        assert 'SPORTS' in result, "SPORTS lane missing"
        assert result['SPORTS']['total_trades'] == 1, f"SPORTS trades: expected 1, got {result['SPORTS']['total_trades']}"
        
        print("✅ Lane metrics calculation works correctly with mock data")


class TestHealthEndpoint:
    """Basic health check"""
    
    def test_health_endpoint(self):
        """Verify health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy, got {data.get('status')}"
        print("✅ Health endpoint returns healthy")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
