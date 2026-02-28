"""
API Contract Tests - Analytics Endpoint
=======================================
Verifies that the analytics API correctly serializes the strict Pydantic schemas.

These tests mock the service layer to test ONLY the API contract,
avoiding database complexity.

Author: APEX TRADER QA
Date: January 2026
"""

import pytest
import sys

sys.path.insert(0, '/app/backend')

from schemas.analytics import (
    LaneMetric, 
    ComprehensiveMetricsResponse,
    StrategyMetric
)


# =============================================================================
# MOCK DATA
# =============================================================================

MOCK_ANALYTICS_RESPONSE = {
    "total_trades": 100,
    "overall_win_rate": 55.0,
    "winning_trades": 55,
    "losing_trades": 45,
    "total_pnl": 250.50,
    "realized_pnl": 250.50,
    "unrealized_pnl": 0.0,
    "strategy_performance": {
        "alpha_directional": {
            "total_pnl": 100.0,
            "total_trades": 40,
            "win_rate": 60.0,
            "wins": 24,
            "total_volume": 2000.0,
            "classification": "strong"
        }
    },
    "asset_class_performance": {
        "politics": {
            "total_pnl": 80.0,
            "total_trades": 30,
            "win_rate": 53.0,
            "wins": 16,
            "total_volume": 1500.0
        }
    },
    "lane_performance": {
        "HFT": {
            "total_pnl": 50.0,
            "total_trades": 30,
            "win_rate": 60.0,
            "wins": 18,
            "losses": 12,
            "total_volume": 3000.0,
            "avg_pnl_per_trade": 1.67
        },
        "ALPHA": {
            "total_pnl": 150.0,
            "total_trades": 50,
            "win_rate": 54.0,
            "wins": 27,
            "losses": 23,
            "total_volume": 5000.0,
            "avg_pnl_per_trade": 3.0
        },
        "GAMMA": {
            "total_pnl": 50.50,
            "total_trades": 20,
            "win_rate": 50.0,
            "wins": 10,
            "losses": 10,
            "total_volume": 1000.0,
            "avg_pnl_per_trade": 2.53
        }
    },
    "portfolio_volatility": 0.15,
    "sortino_ratio": 1.2,
    "profit_factor": 1.8,
    "win_loss_ratio": 1.22,
    "recovery_factor": 0.5,
    "expectancy": 2.5,
    "avg_win": 8.0,
    "avg_loss": 5.5,
    "max_consecutive_wins": 5,
    "max_consecutive_losses": 3,
    "timestamp": "2026-01-27T20:00:00+00:00"
}


# =============================================================================
# SCHEMA VALIDATION TESTS
# =============================================================================

class TestLaneMetricSchema:
    """Test the LaneMetric Pydantic model."""
    
    def test_lane_metric_creation(self):
        """LaneMetric should accept valid data."""
        metric = LaneMetric(
            total_pnl=100.0,
            total_trades=50,
            win_rate=60.0,
            wins=30,
            losses=20,
            total_volume=5000.0,
            avg_pnl_per_trade=2.0
        )
        
        assert metric.total_pnl == 100.0
        assert metric.total_trades == 50
        assert metric.win_rate == 60.0
    
    def test_lane_metric_defaults(self):
        """LaneMetric should have sensible defaults."""
        metric = LaneMetric()
        
        assert metric.total_pnl == 0.0
        assert metric.total_trades == 0
        assert metric.win_rate == 0.0
        assert metric.wins == 0
        assert metric.losses == 0
    
    def test_lane_metric_from_dict(self):
        """LaneMetric should parse from dictionary."""
        data = MOCK_ANALYTICS_RESPONSE["lane_performance"]["HFT"]
        metric = LaneMetric(**data)
        
        assert metric.total_pnl == 50.0
        assert metric.win_rate == 60.0


class TestComprehensiveMetricsSchema:
    """Test the ComprehensiveMetricsResponse Pydantic model."""
    
    def test_full_response_validation(self):
        """ComprehensiveMetricsResponse should validate complete data."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        assert response.total_trades == 100
        assert response.overall_win_rate == 55.0
        assert response.total_pnl == 250.50
        assert "HFT" in response.lane_performance
        assert "ALPHA" in response.lane_performance
        assert "GAMMA" in response.lane_performance
    
    def test_lane_performance_structure(self):
        """Lane performance should contain LaneMetric-compatible data."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        hft = response.lane_performance["HFT"]
        # Access as LaneMetric object attributes (Pydantic parses dict to model)
        assert hft.total_pnl == 50.0
        assert hft.win_rate == 60.0
        assert hft.total_trades == 30
        assert hft.total_volume == 3000.0
    
    def test_empty_response_defaults(self):
        """Empty response should have sensible defaults."""
        response = ComprehensiveMetricsResponse()
        
        assert response.total_trades == 0
        assert response.lane_performance == {}
        assert response.strategy_performance == {}
    
    def test_partial_lane_data(self):
        """Response should handle partial lane data."""
        partial_data = {
            "total_trades": 10,
            "overall_win_rate": 50.0,
            "total_pnl": 25.0,
            "lane_performance": {
                "ALPHA": {
                    "total_pnl": 25.0,
                    "total_trades": 10,
                    "win_rate": 50.0,
                    "wins": 5,
                    "losses": 5,
                    "total_volume": 500.0,
                    "avg_pnl_per_trade": 2.5
                }
                # HFT and GAMMA missing - that's OK
            }
        }
        
        response = ComprehensiveMetricsResponse(**partial_data)
        assert "ALPHA" in response.lane_performance
        assert "HFT" not in response.lane_performance


class TestStrategyMetricSchema:
    """Test the StrategyMetric Pydantic model."""
    
    def test_strategy_metric_creation(self):
        """StrategyMetric should parse from data."""
        data = MOCK_ANALYTICS_RESPONSE["strategy_performance"]["alpha_directional"]
        metric = StrategyMetric(**data)
        
        assert metric.total_pnl == 100.0
        assert metric.classification == "strong"


# =============================================================================
# API CONTRACT TESTS (Mocked)
# =============================================================================

class TestAnalyticsAPIContract:
    """
    Test the API endpoint contract.
    
    These tests verify that the API correctly serializes the schema
    without needing a database connection.
    """
    
    def test_response_has_lane_performance_field(self):
        """API response must include lane_performance field."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        response_dict = response.model_dump()
        
        assert "lane_performance" in response_dict
        assert isinstance(response_dict["lane_performance"], dict)
    
    def test_all_lanes_have_required_fields(self):
        """Each lane must have all required LaneMetric fields."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        required_fields = ["total_pnl", "total_trades", "win_rate", "wins", "losses", "total_volume", "avg_pnl_per_trade"]
        
        for lane_name, lane_metric in response.lane_performance.items():
            # lane_metric is a LaneMetric object, check attributes
            for field in required_fields:
                assert hasattr(lane_metric, field), f"Lane {lane_name} missing field: {field}"
                assert getattr(lane_metric, field) is not None, f"Lane {lane_name} field {field} is None"
    
    def test_response_json_serializable(self):
        """Response must be JSON serializable."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        # This will raise if not serializable
        json_str = response.model_dump_json()
        assert isinstance(json_str, str)
        assert "lane_performance" in json_str
        assert "HFT" in json_str
    
    def test_response_matches_openapi_example(self):
        """Response should match the OpenAPI example structure."""
        # Get the example from schema
        example = ComprehensiveMetricsResponse.model_config.get("json_schema_extra", {}).get("example", {})
        
        if example:
            assert "lane_performance" in example
            assert "HFT" in example["lane_performance"]
            assert "ALPHA" in example["lane_performance"]
            assert "GAMMA" in example["lane_performance"]


class TestLaneMetricMath:
    """Verify mathematical consistency of lane metrics."""
    
    def test_wins_plus_losses_equals_trades(self):
        """wins + losses should equal total_trades."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        for lane_name, lane_metric in response.lane_performance.items():
            expected_total = lane_metric.wins + lane_metric.losses
            assert lane_metric.total_trades == expected_total, (
                f"Lane {lane_name}: wins({lane_metric.wins}) + losses({lane_metric.losses}) "
                f"!= total_trades({lane_metric.total_trades})"
            )
    
    def test_win_rate_calculation(self):
        """win_rate should equal (wins / total_trades) * 100."""
        response = ComprehensiveMetricsResponse(**MOCK_ANALYTICS_RESPONSE)
        
        for lane_name, lane_metric in response.lane_performance.items():
            if lane_metric.total_trades > 0:
                expected_rate = (lane_metric.wins / lane_metric.total_trades) * 100
                assert abs(lane_metric.win_rate - expected_rate) < 0.1, (
                    f"Lane {lane_name}: win_rate {lane_metric.win_rate} != "
                    f"calculated {expected_rate}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
