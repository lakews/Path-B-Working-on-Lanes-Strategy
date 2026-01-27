"""
Test Suite: Lane Analytics Verification
========================================
Verifies that the Three-Speed Architecture metrics are correctly calculated.

Tests:
1. Lane aggregation logic (HFT/ALPHA/GAMMA grouping)
2. Math accuracy (PnL, win rate, volume)
3. Legacy fallback (missing lane defaults to ALPHA)
4. Integration into comprehensive report

Author: APEX TRADER QA
Date: January 2026
"""

import pytest
import sys
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, '/app/backend')

from services.performance_analytics import PerformanceAnalytics


# =============================================================================
# MOCK TRADE DATA
# =============================================================================

MOCK_TRADES = [
    # HFT: 1 Win ($10), 1 Loss ($-2) = Net +$8, 50% win rate
    {"strategy_lane": "HFT", "pnl": 10.0, "size": 100, "price": 0.50},
    {"strategy_lane": "HFT", "pnl": -2.0, "size": 50, "price": 0.40},
    
    # GAMMA: 1 Big Win ($500) = Net +$500, 100% win rate
    {"strategy_lane": "GAMMA", "pnl": 500.0, "size": 1000, "price": 0.05},
    
    # ALPHA: 2 trades - 1 win ($20), 1 loss ($-5) = Net +$15, 50% win rate
    {"strategy_lane": "ALPHA", "pnl": 20.0, "size": 200, "price": 0.30},
    {"strategy_lane": "ALPHA", "pnl": -5.0, "size": 100, "price": 0.25},
    
    # LEGACY: No strategy_lane - should default to ALPHA
    {"pnl": -10.0, "size": 50, "price": 0.20}
]


# =============================================================================
# UNIT TESTS: Lane Aggregation Logic
# =============================================================================

class TestLaneAggregation:
    """Test the _calculate_lane_metrics method directly."""
    
    def setup_method(self):
        """Create service instance with mocked DB."""
        self.service = PerformanceAnalytics.__new__(PerformanceAnalytics)
        self.service.db = MagicMock()
    
    def test_hft_lane_metrics(self):
        """Verify HFT lane calculates correctly."""
        metrics = self.service._calculate_lane_metrics(MOCK_TRADES)
        
        assert "HFT" in metrics
        assert metrics["HFT"]["total_pnl"] == 8.0  # 10 - 2
        assert metrics["HFT"]["total_trades"] == 2
        assert metrics["HFT"]["win_rate"] == 50.0  # 1/2
        assert metrics["HFT"]["wins"] == 1
        assert metrics["HFT"]["losses"] == 1
    
    def test_gamma_lane_metrics(self):
        """Verify GAMMA lane calculates correctly."""
        metrics = self.service._calculate_lane_metrics(MOCK_TRADES)
        
        assert "GAMMA" in metrics
        assert metrics["GAMMA"]["total_pnl"] == 500.0
        assert metrics["GAMMA"]["total_trades"] == 1
        assert metrics["GAMMA"]["win_rate"] == 100.0  # 1/1
        assert metrics["GAMMA"]["wins"] == 1
        assert metrics["GAMMA"]["losses"] == 0
    
    def test_alpha_lane_with_legacy_fallback(self):
        """Verify ALPHA lane includes legacy trades without strategy_lane."""
        metrics = self.service._calculate_lane_metrics(MOCK_TRADES)
        
        assert "ALPHA" in metrics
        # Should include: 2 explicit ALPHA trades + 1 legacy trade
        assert metrics["ALPHA"]["total_trades"] == 3
        # PnL: 20 + (-5) + (-10) = 5
        assert metrics["ALPHA"]["total_pnl"] == 5.0
        # Wins: 1 (the $20 trade)
        assert metrics["ALPHA"]["wins"] == 1
        assert metrics["ALPHA"]["losses"] == 2
        # Win rate: 1/3 = 33.33%
        assert metrics["ALPHA"]["win_rate"] == pytest.approx(33.33, rel=0.01)
    
    def test_avg_pnl_per_trade(self):
        """Verify average PnL per trade is calculated correctly."""
        metrics = self.service._calculate_lane_metrics(MOCK_TRADES)
        
        # HFT: $8 / 2 trades = $4
        assert metrics["HFT"]["avg_pnl_per_trade"] == 4.0
        
        # GAMMA: $500 / 1 trade = $500
        assert metrics["GAMMA"]["avg_pnl_per_trade"] == 500.0
        
        # ALPHA: $5 / 3 trades = $1.67
        assert metrics["ALPHA"]["avg_pnl_per_trade"] == pytest.approx(1.67, rel=0.01)
    
    def test_empty_trades_list(self):
        """Verify empty trades list returns empty metrics."""
        metrics = self.service._calculate_lane_metrics([])
        assert metrics == {}
    
    def test_all_lanes_present(self):
        """Verify all three lanes are represented in output."""
        metrics = self.service._calculate_lane_metrics(MOCK_TRADES)
        
        assert "HFT" in metrics
        assert "ALPHA" in metrics
        assert "GAMMA" in metrics
        assert len(metrics) == 3


class TestLaneVolume:
    """Test volume calculations in lane metrics."""
    
    def setup_method(self):
        self.service = PerformanceAnalytics.__new__(PerformanceAnalytics)
        self.service.db = MagicMock()
    
    def test_volume_calculation(self):
        """Verify volume is calculated as size * price."""
        trades = [
            {"strategy_lane": "HFT", "pnl": 10.0, "size": 100, "price": 0.50},  # Volume = 50
            {"strategy_lane": "HFT", "pnl": 5.0, "size": 200, "price": 0.25},   # Volume = 50
        ]
        
        metrics = self.service._calculate_lane_metrics(trades)
        
        # Total HFT volume: 50 + 50 = 100
        assert metrics["HFT"]["total_volume"] == 100.0
    
    def test_volume_with_amount_field(self):
        """Verify volume calculation works with 'amount' field too."""
        trades = [
            {"strategy_lane": "GAMMA", "pnl": 100.0, "amount": 500, "price": 0.10},
        ]
        
        metrics = self.service._calculate_lane_metrics(trades)
        
        # Volume = 500 * 0.10 = 50
        assert metrics["GAMMA"]["total_volume"] == 50.0


class TestLegacyCompatibility:
    """Test backward compatibility with trades missing strategy_lane."""
    
    def setup_method(self):
        self.service = PerformanceAnalytics.__new__(PerformanceAnalytics)
        self.service.db = MagicMock()
    
    def test_missing_lane_defaults_to_alpha(self):
        """Trades without strategy_lane should default to ALPHA."""
        trades = [
            {"pnl": 100.0, "size": 100, "price": 0.50},  # No lane
            {"strategy_lane": None, "pnl": 50.0, "size": 50, "price": 0.40},  # Explicit None
            {"strategy_lane": "", "pnl": 25.0, "size": 25, "price": 0.30},  # Empty string
        ]
        
        metrics = self.service._calculate_lane_metrics(trades)
        
        # All should end up in ALPHA
        assert len(metrics) == 1
        assert "ALPHA" in metrics
        assert metrics["ALPHA"]["total_trades"] == 3
        assert metrics["ALPHA"]["total_pnl"] == 175.0


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def setup_method(self):
        self.service = PerformanceAnalytics.__new__(PerformanceAnalytics)
        self.service.db = MagicMock()
    
    def test_zero_pnl_trade(self):
        """Trades with zero PnL should be counted but not as wins."""
        trades = [
            {"strategy_lane": "HFT", "pnl": 0.0, "size": 100, "price": 0.50},
        ]
        
        metrics = self.service._calculate_lane_metrics(trades)
        
        assert metrics["HFT"]["total_trades"] == 1
        assert metrics["HFT"]["wins"] == 0  # Zero is not a win
        assert metrics["HFT"]["losses"] == 1
        assert metrics["HFT"]["win_rate"] == 0.0
    
    def test_missing_pnl_field(self):
        """Trades missing PnL should default to 0."""
        trades = [
            {"strategy_lane": "ALPHA", "size": 100, "price": 0.50},  # No pnl field
        ]
        
        metrics = self.service._calculate_lane_metrics(trades)
        
        assert metrics["ALPHA"]["total_pnl"] == 0.0
        assert metrics["ALPHA"]["total_trades"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
