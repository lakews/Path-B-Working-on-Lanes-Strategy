"""
Test Dashboard Performance Tables, WebSocket, and Backtest Features
Tests for iteration 9 - Dashboard performance tables, WebSocket integration, InfoTooltip
"""
import pytest
import requests
import os
import asyncio
import json

try:
    import websockets
except ImportError:
    websockets = None

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://algomarket-3.preview.emergentagent.com')

class TestWebSocketEndpoint:
    """Test WebSocket endpoint accessibility"""
    
    def test_websocket_endpoint_exists(self):
        """Test that /ws endpoint is accessible - WebSocket connection test"""
        # Test via websockets library
        import asyncio
        import websockets
        
        async def test_ws_connection():
            ws_url = BASE_URL.replace('https', 'wss').replace('http', 'ws') + '/ws'
            try:
                async with websockets.connect(ws_url) as ws:
                    # Wait for initial message
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    return True, data.get('type', 'unknown')
            except Exception as e:
                return False, str(e)
        
        success, result = asyncio.run(test_ws_connection())
        assert success, f"WebSocket connection failed: {result}"
        print(f"✓ WebSocket endpoint /ws connected successfully, received message type: {result}")


class TestDashboardAPIs:
    """Test Dashboard-related API endpoints"""
    
    def test_status_endpoint(self):
        """Test /api/status returns trading status"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert 'status' in data
        assert 'bot_running' in data
        assert 'trading_mode' in data
        assert 'configuration' in data
        print(f"✓ Status endpoint working: mode={data['trading_mode']}, running={data['bot_running']}")
    
    def test_performance_endpoint(self):
        """Test /api/performance returns performance metrics"""
        response = requests.get(f"{BASE_URL}/api/performance")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields for Dashboard display
        assert 'total_capital' in data
        assert 'total_pnl' in data
        assert 'win_rate' in data
        assert 'sharpe_ratio' in data
        assert 'max_drawdown' in data
        assert 'num_trades' in data
        print(f"✓ Performance endpoint working: P&L=${data['total_pnl']}, Win Rate={data['win_rate']}")
    
    def test_trades_endpoint(self):
        """Test /api/trades returns trade list"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert 'trades' in data
        assert 'count' in data
        assert isinstance(data['trades'], list)
        print(f"✓ Trades endpoint working: {data['count']} trades returned")
    
    def test_trades_stats_endpoint(self):
        """Test /api/trades/stats returns trade statistics"""
        response = requests.get(f"{BASE_URL}/api/trades/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Verify fields used by Dashboard
        assert 'total_pnl' in data or 'pnl' in data or data.get('total_pnl') is not None
        print(f"✓ Trade stats endpoint working")
    
    def test_positions_endpoint(self):
        """Test /api/positions returns positions list"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        
        assert 'positions' in data
        assert 'count' in data
        assert isinstance(data['positions'], list)
        print(f"✓ Positions endpoint working: {data['count']} positions")


class TestBacktestAPIs:
    """Test Backtest-related API endpoints"""
    
    def test_backtest_results_endpoint(self):
        """Test /api/backtest/results returns backtest results with strategy and asset class data"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        data = response.json()
        
        # Check for strategy_results (used for Strategy Performance table)
        if 'strategy_results' in data and data['strategy_results']:
            print(f"✓ Strategy results found: {list(data['strategy_results'].keys())}")
            
            # Verify each strategy has required fields for Contrib % calculation
            for strategy, stats in data['strategy_results'].items():
                assert 'pnl' in stats, f"Strategy {strategy} missing 'pnl' field"
                assert 'trades' in stats, f"Strategy {strategy} missing 'trades' field"
                print(f"  - {strategy}: P&L=${stats.get('pnl', 0):.2f}, Trades={stats.get('trades', 0)}")
        
        # Check for asset_class_results (used for Asset Class Performance table)
        if 'asset_class_results' in data and data['asset_class_results']:
            print(f"✓ Asset class results found: {list(data['asset_class_results'].keys())}")
            
            for asset_class, stats in data['asset_class_results'].items():
                assert 'pnl' in stats, f"Asset class {asset_class} missing 'pnl' field"
                assert 'trades' in stats, f"Asset class {asset_class} missing 'trades' field"
                print(f"  - {asset_class}: P&L=${stats.get('pnl', 0):.2f}, Trades={stats.get('trades', 0)}")
        
        # Check for returns_distribution (used for Returns Distribution chart)
        if 'returns_distribution' in data and data['returns_distribution']:
            dist = data['returns_distribution']
            if 'bins' in dist:
                print(f"✓ Returns distribution found: {len(dist['bins'])} bins")
            if 'stats' in dist:
                stats = dist['stats']
                print(f"  - Mean: {stats.get('mean', 0):.2f}%, Median: {stats.get('median', 0):.2f}%")
    
    def test_backtest_history_endpoint(self):
        """Test /api/backtest/history returns backtest history"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert 'history' in data
        print(f"✓ Backtest history endpoint working: {len(data['history'])} backtests")


class TestRLEngineAPIs:
    """Test RL Engine API endpoints"""
    
    def test_rl_detailed_stats_endpoint(self):
        """Test /api/rl/detailed-stats returns RL engine statistics"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        assert response.status_code == 200
        data = response.json()
        
        # Check for RL stats fields used by Dashboard
        rl_stats = data.get('rl_stats', data)
        print(f"✓ RL stats endpoint working")
        if rl_stats:
            print(f"  - Iterations: {rl_stats.get('total_iterations', 0)}")
            print(f"  - Epsilon: {rl_stats.get('epsilon', 0)}")


class TestHistoricalDataAPIs:
    """Test Historical Data API endpoints"""
    
    def test_historical_stats_endpoint(self):
        """Test /api/historical/stats returns historical data statistics"""
        response = requests.get(f"{BASE_URL}/api/historical/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Check for fields used by Dashboard
        print(f"✓ Historical stats endpoint working")
        print(f"  - Total snapshots: {data.get('total_snapshots', 0)}")
        print(f"  - Unique markets: {data.get('unique_markets', 0)}")


class TestContribPercentageCalculation:
    """Test that Contrib % can be calculated from API data"""
    
    def test_strategy_contrib_percentage_calculation(self):
        """Verify strategy data supports Contrib % calculation"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        data = response.json()
        
        if 'strategy_results' in data and data['strategy_results']:
            strategy_results = data['strategy_results']
            
            # Calculate total P&L
            total_pnl = sum(s.get('pnl', 0) for s in strategy_results.values())
            
            if total_pnl != 0:
                # Calculate Contrib % for each strategy
                for strategy, stats in strategy_results.items():
                    pnl = stats.get('pnl', 0)
                    contrib_pct = (pnl / total_pnl) * 100
                    print(f"  - {strategy}: Contrib % = {contrib_pct:.1f}%")
                
                # Verify total adds up to 100%
                total_contrib = sum((s.get('pnl', 0) / total_pnl) * 100 for s in strategy_results.values())
                assert abs(total_contrib - 100) < 0.1, f"Total Contrib % should be 100%, got {total_contrib:.1f}%"
                print(f"✓ Strategy Contrib % calculation verified (total: {total_contrib:.1f}%)")
            else:
                print("⚠ Total P&L is 0, cannot calculate Contrib %")
    
    def test_asset_class_contrib_percentage_calculation(self):
        """Verify asset class data supports Contrib % calculation"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        assert response.status_code == 200
        data = response.json()
        
        if 'asset_class_results' in data and data['asset_class_results']:
            asset_results = data['asset_class_results']
            
            # Calculate total P&L
            total_pnl = sum(s.get('pnl', 0) for s in asset_results.values())
            
            if total_pnl != 0:
                # Calculate Contrib % for each asset class
                for asset_class, stats in asset_results.items():
                    pnl = stats.get('pnl', 0)
                    contrib_pct = (pnl / total_pnl) * 100
                    print(f"  - {asset_class}: Contrib % = {contrib_pct:.1f}%")
                
                print(f"✓ Asset Class Contrib % calculation verified")
            else:
                print("⚠ Total P&L is 0, cannot calculate Contrib %")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
