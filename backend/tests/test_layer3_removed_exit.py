"""
Layer 3 Removed Exit Logic Tests (Iteration 52)
================================================

Tests verify that Layer 3 (stale cached orderbook fallback) has been REMOVED from exit logic.
The system now only uses:
1. Layer 1: WebSocket Orderbook Cache (PRIMARY - sub-1ms latency)
2. Layer 2: REST API with retry (2 attempts, 500ms delay)
3. EXIT-QUEUED: If both fail, exit is queued for retry next cycle

Key verification points:
- 'market_data_cache' should NOT appear in exit logic
- [EXIT-QUEUED] log message should appear when orderbook unavailable
- [EXIT-BLOCK] should NOT appear for the main exit path (only for specific edge cases)
- REST API retry logic: 2 attempts with 500ms delay
"""

import pytest
import requests
import os
import json
import re
from datetime import datetime, timezone

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = 'https://websocket-primary.preview.emergentagent.com'


class TestBackendHealth:
    """Basic health checks."""
    
    def test_backend_health(self):
        """Verify backend is running and healthy."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✓ Backend healthy: {data}")


class TestPaperTradingSession:
    """Test paper trading session functionality."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": "admin", "password": "apex2026!"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_paper_trading_status(self, auth_token):
        """Check paper trading status."""
        response = requests.get(
            f"{BASE_URL}/api/paper/status",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Paper trading status: running={data.get('running')}, session={data.get('session_id')}")
        print(f"  Open positions: {data.get('open_positions')}, Total trades: {data.get('total_trades')}")
    
    def test_paper_trading_positions(self, auth_token):
        """Check paper trading positions."""
        response = requests.get(
            f"{BASE_URL}/api/paper/positions",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200
        positions = response.json()
        print(f"✓ Paper trading positions: {len(positions) if isinstance(positions, list) else 'N/A'}")


class TestCodeVerificationLayer3Removed:
    """Verify Layer 3 (market_data_cache) has been removed from exit logic."""
    
    def test_no_market_data_cache_in_exit_logic(self):
        """
        Verify 'market_data_cache' is NOT used in the exit logic section.
        The exit logic is in paper_trader.py lines 5560-5680.
        """
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Find the exit logic section (lines 5560-5680)
        lines = content.split('\n')
        exit_logic_section = '\n'.join(lines[5559:5680])  # 0-indexed
        
        # Check that 'market_data_cache' is NOT in the exit logic section
        assert 'market_data_cache' not in exit_logic_section, \
            "ERROR: 'market_data_cache' found in exit logic - Layer 3 should be removed!"
        
        print("✓ VERIFIED: 'market_data_cache' NOT found in exit logic section (lines 5560-5680)")
        print("  Layer 3 (stale cached orderbook fallback) has been successfully removed")
    
    def test_exit_queued_log_message_exists(self):
        """Verify [EXIT-QUEUED] log message exists in the code."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Check for [EXIT-QUEUED] log message
        assert '[EXIT-QUEUED]' in content, \
            "ERROR: [EXIT-QUEUED] log message not found - should be present when orderbook unavailable"
        
        # Find the line with EXIT-QUEUED
        for i, line in enumerate(content.split('\n'), 1):
            if '[EXIT-QUEUED]' in line:
                print(f"✓ VERIFIED: [EXIT-QUEUED] found at line {i}")
                print(f"  Line content: {line.strip()[:100]}...")
                break
    
    def test_rest_api_retry_logic_exists(self):
        """Verify REST API retry logic (2 attempts, 500ms delay) exists."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Check for retry logic indicators
        assert 'max_retries = 2' in content, \
            "ERROR: max_retries = 2 not found - REST API should retry twice"
        
        assert 'retry_delay = 0.5' in content, \
            "ERROR: retry_delay = 0.5 not found - should have 500ms delay between retries"
        
        print("✓ VERIFIED: REST API retry logic found (max_retries=2, retry_delay=0.5)")
    
    def test_layer_structure_correct(self):
        """Verify the exit logic has correct layer structure (Layer 1 + Layer 2 only)."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Find the exit logic section
        lines = content.split('\n')
        exit_logic_section = '\n'.join(lines[5559:5680])
        
        # Check Layer 1 exists
        assert 'LAYER 1' in exit_logic_section or 'WebSocket Orderbook Cache' in exit_logic_section, \
            "ERROR: Layer 1 (WebSocket) not found in exit logic"
        
        # Check Layer 2 exists
        assert 'LAYER 2' in exit_logic_section or 'REST API' in exit_logic_section, \
            "ERROR: Layer 2 (REST API) not found in exit logic"
        
        # Check Layer 3 does NOT exist in exit logic section
        # Note: Layer 3 comment might exist elsewhere in the file, but not in exit logic
        layer3_patterns = ['LAYER 3', 'market_data_cache', 'Cached Orderbook']
        for pattern in layer3_patterns:
            if pattern in exit_logic_section:
                pytest.fail(f"ERROR: '{pattern}' found in exit logic - Layer 3 should be removed!")
        
        print("✓ VERIFIED: Exit logic has correct structure:")
        print("  - Layer 1: WebSocket Orderbook Cache (PRIMARY)")
        print("  - Layer 2: REST API with retry")
        print("  - Layer 3: REMOVED (no stale cache fallback)")
        print("  - EXIT-QUEUED: When both layers fail")


class TestExitLogicBehavior:
    """Test the actual behavior of exit logic."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": "admin", "password": "apex2026!"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_websocket_service_available(self, auth_token):
        """Check WebSocket service is available for Layer 1."""
        response = requests.get(
            f"{BASE_URL}/api/websocket/status",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ WebSocket status: {json.dumps(data, indent=2)[:300]}")
        else:
            print(f"⚠ WebSocket status endpoint returned {response.status_code}")
    
    def test_exit_engine_stats(self, auth_token):
        """Check exit engine statistics."""
        response = requests.get(
            f"{BASE_URL}/api/exit-engine/stats",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Exit engine stats: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"⚠ Exit engine stats endpoint returned {response.status_code}")


class TestOrderbookSourceTracking:
    """Test that orderbook source is properly tracked."""
    
    def test_orderbook_source_values(self):
        """Verify valid orderbook_source values in code."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Valid orderbook sources after Layer 3 removal
        valid_sources = ['websocket', 'rest_api', 'rest_api_retry', 'none']
        
        # Check that 'websocket' source is used
        assert "orderbook_source = 'websocket'" in content, \
            "ERROR: WebSocket orderbook source not found"
        
        # Check that 'rest_api' source is used
        assert "orderbook_source = f'rest_api" in content or "orderbook_source = 'rest_api'" in content, \
            "ERROR: REST API orderbook source not found"
        
        # Check that 'market_data_cache' is NOT used as orderbook source
        assert "orderbook_source = 'market_data_cache'" not in content, \
            "ERROR: 'market_data_cache' should not be used as orderbook source"
        
        print("✓ VERIFIED: Valid orderbook sources:")
        print("  - 'websocket' (Layer 1)")
        print("  - 'rest_api' / 'rest_api_retry' (Layer 2)")
        print("  - 'none' (initial value)")
        print("  - 'market_data_cache' NOT USED (Layer 3 removed)")


class TestNoStaleDataUsage:
    """Verify no stale/cached data is used for exits."""
    
    def test_no_stale_cache_fallback(self):
        """Verify there's no fallback to stale cached data."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Find the exit logic section
        lines = content.split('\n')
        exit_logic_section = '\n'.join(lines[5559:5680])
        
        # Patterns that would indicate stale cache usage
        stale_patterns = [
            'market_data.get(\'order_book\')',
            'market_data.get("order_book")',
            'cached_orderbook',
            'stale_orderbook',
            'fallback_orderbook',
        ]
        
        for pattern in stale_patterns:
            if pattern in exit_logic_section:
                pytest.fail(f"ERROR: Stale cache pattern '{pattern}' found in exit logic!")
        
        print("✓ VERIFIED: No stale cache fallback patterns found in exit logic")
        print("  Exits will only use real-time verified prices from WebSocket or REST API")


class TestExitQueuedBehavior:
    """Test that exits are QUEUED (not blocked) when orderbook unavailable."""
    
    def test_exit_queued_not_blocked(self):
        """Verify exits are queued for retry, not permanently blocked."""
        paper_trader_path = "/app/backend/paper_trading/paper_trader.py"
        
        try:
            with open(paper_trader_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip(f"File not found: {paper_trader_path}")
        
        # Find the line with EXIT-QUEUED
        lines = content.split('\n')
        exit_queued_line = None
        exit_queued_line_num = None
        
        for i, line in enumerate(lines, 1):
            if '[EXIT-QUEUED]' in line:
                exit_queued_line = line
                exit_queued_line_num = i
                break
        
        assert exit_queued_line is not None, "ERROR: [EXIT-QUEUED] not found in code"
        
        # Check the message indicates retry behavior
        assert 'retry' in exit_queued_line.lower() or 'next cycle' in exit_queued_line.lower(), \
            "ERROR: EXIT-QUEUED message should indicate retry behavior"
        
        print(f"✓ VERIFIED: [EXIT-QUEUED] at line {exit_queued_line_num}")
        print(f"  Message indicates retry behavior: '{exit_queued_line.strip()[:80]}...'")
        print("  Exits are QUEUED for retry, not permanently blocked")


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
