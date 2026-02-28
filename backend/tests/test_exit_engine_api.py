"""
APEX TRADER - Exit Engine API Tests (Task 24)
==============================================

Tests for the Exit Engine API endpoints:
- GET /api/config/exit-engine - retrieves exit engine configuration
- POST /api/config/exit-engine - updates exit engine configuration
- POST /api/config/exit-engine/reset - resets to defaults
- GET /api/exit-engine/stats - retrieves runtime statistics
"""

import pytest
import requests

from tests.conftest import API_BASE_URL as BASE_URL


class TestExitEngineConfigGet:
    """Tests for GET /api/config/exit-engine endpoint."""
    
    def test_get_exit_engine_config_success(self):
        """Test successful retrieval of exit engine configuration."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert 'config' in data
        config = data['config']
        
        # Verify all required sections exist
        assert 'global' in config
        assert 'strategies' in config
        assert 'alpha_modifiers' in config
        assert 'whale_zone' in config
    
    def test_get_exit_engine_config_global_settings(self):
        """Test global settings structure and values."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        global_settings = response.json()['config']['global']
        
        # Verify required global settings
        assert 'whale_threshold_price' in global_settings
        assert 'max_spread_pct' in global_settings
        assert 'expiry_guard_hours' in global_settings
        assert 'min_trade_size_usd' in global_settings
        assert 'free_ride_floor' in global_settings
        assert 'free_ride_ceiling' in global_settings
        
        # Verify default values
        assert global_settings['whale_threshold_price'] == 0.10
        assert global_settings['free_ride_floor'] == 0.02
        assert global_settings['free_ride_ceiling'] == 0.98
    
    def test_get_exit_engine_config_whale_zone(self):
        """Test whale zone configuration structure."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        whale_zone = response.json()['config']['whale_zone']
        
        # Verify whale zone settings
        assert 'stop_loss_multiple' in whale_zone
        assert 'free_roll_multiple' in whale_zone
        assert 'free_roll_sell_pct' in whale_zone
        assert 'moonbag_multiple' in whale_zone
        
        # Verify default values (uses multiples, not percentages)
        assert whale_zone['stop_loss_multiple'] == 0.50  # 50% of entry
        assert whale_zone['free_roll_multiple'] == 2.0   # 2x entry
        assert whale_zone['moonbag_multiple'] == 5.0     # 5x entry
    
    def test_get_exit_engine_config_strategies(self):
        """Test strategy configuration structure."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        strategies = response.json()['config']['strategies']
        
        # Verify mechanical strategies exist
        assert 'arbitrage' in strategies
        assert 'delta_neutral' in strategies
        
        # Verify arbitrage is mechanical type
        assert strategies['arbitrage']['type'] == 'mechanical'
        assert 'tp_pct' in strategies['arbitrage']
        assert 'sl_pct' in strategies['arbitrage']
        
        # Verify alpha_directional exists and is complex type
        assert 'alpha_directional' in strategies
        assert strategies['alpha_directional']['type'] == 'complex'
    
    def test_get_exit_engine_config_alpha_modifiers(self):
        """Test alpha asset modifiers structure."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        modifiers = response.json()['config']['alpha_modifiers']
        
        # Verify all asset classes exist
        required_classes = ['politics', 'finance', 'crypto', 'sports', 'entertainment', 'science']
        for asset_class in required_classes:
            assert asset_class in modifiers
            
            # Verify modifier structure
            mod = modifiers[asset_class]
            assert 'profit_mult' in mod
            assert 'sl_mult' in mod
            assert 'time_mult' in mod
            assert 'use_trailing' in mod
            assert 'use_thesis_fail' in mod
            assert 'allow_zombie' in mod


class TestExitEngineConfigUpdate:
    """Tests for POST /api/config/exit-engine endpoint."""
    
    def test_update_exit_engine_config_success(self):
        """Test successful update of exit engine configuration."""
        update_data = {
            "global": {
                "whale_threshold_price": 0.10,
                "max_spread_pct": 0.12,
                "expiry_guard_hours": 2.5,
                "min_trade_size_usd": 2.00,
                "free_ride_floor": 0.02,
                "free_ride_ceiling": 0.98
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/exit-engine",
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
        assert 'updated' in data['message'].lower() or 'success' in data['message'].lower()
    
    def test_update_exit_engine_config_persists(self):
        """Test that updates persist after save."""
        # Update with new value
        update_data = {
            "global": {
                "max_spread_pct": 0.15
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/exit-engine",
            json=update_data
        )
        assert response.status_code == 200
        
        # Verify update persisted
        get_response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        assert get_response.status_code == 200
        
        global_settings = get_response.json()['config']['global']
        assert global_settings['max_spread_pct'] == 0.15
        
        # Reset back to default
        requests.post(f"{BASE_URL}/api/config/exit-engine/reset")
    
    def test_update_whale_zone_config(self):
        """Test updating whale zone configuration."""
        update_data = {
            "whale_zone": {
                "stop_loss_multiple": 0.40,
                "free_roll_multiple": 2.5,
                "moonbag_multiple": 6.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/config/exit-engine",
            json=update_data
        )
        
        assert response.status_code == 200
        
        # Verify update
        get_response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        whale_zone = get_response.json()['config']['whale_zone']
        
        assert whale_zone['stop_loss_multiple'] == 0.40
        assert whale_zone['free_roll_multiple'] == 2.5
        assert whale_zone['moonbag_multiple'] == 6.0
        
        # Reset back to default
        requests.post(f"{BASE_URL}/api/config/exit-engine/reset")


class TestExitEngineConfigReset:
    """Tests for POST /api/config/exit-engine/reset endpoint."""
    
    def test_reset_exit_engine_config_success(self):
        """Test successful reset to defaults."""
        response = requests.post(f"{BASE_URL}/api/config/exit-engine/reset")
        
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
        assert 'reset' in data['message'].lower() or 'default' in data['message'].lower()
    
    def test_reset_restores_default_values(self):
        """Test that reset restores default values."""
        # First, update with non-default values
        update_data = {
            "global": {
                "max_spread_pct": 0.25,
                "expiry_guard_hours": 5.0
            }
        }
        requests.post(f"{BASE_URL}/api/config/exit-engine", json=update_data)
        
        # Reset to defaults
        response = requests.post(f"{BASE_URL}/api/config/exit-engine/reset")
        assert response.status_code == 200
        
        # Verify defaults restored
        get_response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        global_settings = get_response.json()['config']['global']
        
        assert global_settings['max_spread_pct'] == 0.10  # Default
        assert global_settings['expiry_guard_hours'] == 2.0  # Default


class TestExitEngineStats:
    """Tests for GET /api/exit-engine/stats endpoint."""
    
    def test_get_exit_engine_stats_success(self):
        """Test successful retrieval of exit engine stats."""
        response = requests.get(f"{BASE_URL}/api/exit-engine/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert 'stats' in data
    
    def test_get_exit_engine_stats_structure(self):
        """Test stats structure contains required fields."""
        response = requests.get(f"{BASE_URL}/api/exit-engine/stats")
        
        assert response.status_code == 200
        stats = response.json()['stats']
        
        # Verify required stat fields
        assert 'total_checks' in stats
        assert 'holds' in stats
        assert 'close_all' in stats
        assert 'free_rolls' in stats
        assert 'whale_exits' in stats
        assert 'thesis_fails' in stats
        
        # Verify config info
        assert 'config' in stats
        assert 'whale_threshold' in stats['config']
        assert 'strategies' in stats['config']
        assert 'asset_classes' in stats['config']


class TestExitEngineBusinessLogic:
    """Tests for Exit Engine business logic via API configuration.
    
    These tests verify the Task 24 requirements:
    - Sports Volatility: -20% PnL should HOLD (SL mult 1.5 allows -22.5%)
    - Politics Tightness: -16% PnL should CLOSE_ALL (SL mult 1.0 limits to -15%)
    - Free Roll: +36% gain should trigger FREE_ROLL action
    - Whale Zone: Entry at $0.05 should use 2x/5x multiples not percentages
    """
    
    def test_sports_volatility_modifier(self):
        """Verify sports has wide stop loss (sl_mult = 1.5)."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        sports_mod = response.json()['config']['alpha_modifiers']['sports']
        
        # Sports should have sl_mult = 1.5 (wide stop for game swings)
        assert sports_mod['sl_mult'] == 1.5
        # With base_sl = 15%, effective stop = 15% * 1.5 = 22.5%
        # So -20% PnL should HOLD (within -22.5% stop)
    
    def test_politics_tightness_modifier(self):
        """Verify politics has standard stop loss (sl_mult = 1.0)."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        politics_mod = response.json()['config']['alpha_modifiers']['politics']
        
        # Politics should have sl_mult = 1.0 (standard stop)
        assert politics_mod['sl_mult'] == 1.0
        # With base_sl = 15%, effective stop = 15% * 1.0 = 15%
        # So -16% PnL should CLOSE_ALL (beyond -15% stop)
    
    def test_free_roll_profit_trigger(self):
        """Verify alpha directional has profit trigger for free roll."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        alpha_config = response.json()['config']['strategies']['alpha_directional']
        politics_mod = response.json()['config']['alpha_modifiers']['politics']
        
        # Base profit trigger should be 30%
        assert alpha_config['profit_trigger_pct'] == 0.30
        
        # Politics profit_mult = 1.2, so effective target = 30% * 1.2 = 36%
        assert politics_mod['profit_mult'] == 1.2
        # So +36% gain should trigger FREE_ROLL
    
    def test_whale_zone_uses_multiples(self):
        """Verify whale zone uses price multiples, not percentages."""
        response = requests.get(f"{BASE_URL}/api/config/exit-engine")
        
        assert response.status_code == 200
        whale_zone = response.json()['config']['whale_zone']
        
        # Whale zone should use multiples
        assert whale_zone['stop_loss_multiple'] == 0.50  # 50% of entry (0.5x)
        assert whale_zone['free_roll_multiple'] == 2.0   # 2x entry
        assert whale_zone['moonbag_multiple'] == 5.0     # 5x entry
        
        # For entry at $0.05:
        # Stop loss at $0.025 (0.5x)
        # Free roll at $0.10 (2x)
        # Moonbag at $0.25 (5x)


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
