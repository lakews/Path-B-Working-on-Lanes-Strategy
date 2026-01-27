"""
Analytics Schemas - Strict Pydantic Models for API Contract
============================================================
Defines the exact shape of analytics responses for:
- Lane Performance (HFT/ALPHA/GAMMA)
- Strategy Performance
- Asset Class Performance
- Comprehensive Metrics

These schemas ensure:
1. Swagger/OpenAPI documentation is perfect
2. Type validation catches errors early
3. Frontend developers have a clear contract

Author: APEX TRADER
Date: January 2026
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime


# =============================================================================
# LANE METRICS (Three-Speed Architecture)
# =============================================================================

class LaneMetric(BaseModel):
    """
    Performance metrics for a single lane (HFT, ALPHA, or GAMMA).
    
    Example:
        {
            "total_pnl": 150.50,
            "total_trades": 25,
            "win_rate": 64.0,
            "wins": 16,
            "losses": 9,
            "total_volume": 5000.0,
            "avg_pnl_per_trade": 6.02
        }
    """
    total_pnl: float = Field(default=0.0, description="Total realized P&L for this lane")
    total_trades: int = Field(default=0, description="Number of trades in this lane")
    win_rate: float = Field(default=0.0, description="Win rate percentage (0-100)")
    wins: int = Field(default=0, description="Number of winning trades")
    losses: int = Field(default=0, description="Number of losing trades")
    total_volume: float = Field(default=0.0, description="Total volume traded in USD")
    avg_pnl_per_trade: float = Field(default=0.0, description="Average P&L per trade")


class LanePerformance(BaseModel):
    """
    Container for all three lane metrics.
    Keys are lane names: HFT, ALPHA, GAMMA
    """
    HFT: Optional[LaneMetric] = Field(default=None, description="HFT lane metrics (35% allocation)")
    ALPHA: Optional[LaneMetric] = Field(default=None, description="Alpha lane metrics (55% allocation)")
    GAMMA: Optional[LaneMetric] = Field(default=None, description="Gamma lane metrics (10% allocation)")


# =============================================================================
# STRATEGY METRICS
# =============================================================================

class StrategyMetric(BaseModel):
    """Performance metrics for a single strategy."""
    total_pnl: float = Field(default=0.0)
    total_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    wins: int = Field(default=0)
    total_volume: float = Field(default=0.0)
    classification: str = Field(default="neutral", description="Performance classification")


# =============================================================================
# ASSET CLASS METRICS
# =============================================================================

class AssetClassMetric(BaseModel):
    """Performance metrics for a single asset class."""
    total_pnl: float = Field(default=0.0)
    total_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    wins: int = Field(default=0)
    total_volume: float = Field(default=0.0)


# =============================================================================
# COMPREHENSIVE METRICS RESPONSE
# =============================================================================

class ComprehensiveMetricsResponse(BaseModel):
    """
    Complete performance analytics response.
    
    This is the main response model for GET /api/analytics
    """
    # Core Metrics
    total_trades: int = Field(default=0, description="Total number of trades")
    overall_win_rate: float = Field(default=0.0, description="Overall win rate percentage")
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    total_pnl: float = Field(default=0.0, description="Total realized P&L")
    realized_pnl: float = Field(default=0.0)
    unrealized_pnl: float = Field(default=0.0)
    
    # Strategy Breakdown
    strategy_performance: Dict[str, StrategyMetric] = Field(
        default_factory=dict,
        description="Performance by strategy name"
    )
    
    # Asset Class Breakdown
    asset_class_performance: Dict[str, AssetClassMetric] = Field(
        default_factory=dict,
        description="Performance by asset class"
    )
    
    # Three-Speed Lane Breakdown (NEW)
    lane_performance: Dict[str, LaneMetric] = Field(
        default_factory=dict,
        description="Performance by lane (HFT, ALPHA, GAMMA)"
    )
    
    # Advanced Metrics
    portfolio_volatility: float = Field(default=0.0)
    sortino_ratio: float = Field(default=0.0)
    profit_factor: float = Field(default=0.0)
    win_loss_ratio: float = Field(default=0.0)
    recovery_factor: float = Field(default=0.0)
    expectancy: float = Field(default=0.0)
    avg_win: float = Field(default=0.0)
    avg_loss: float = Field(default=0.0)
    max_consecutive_wins: int = Field(default=0)
    max_consecutive_losses: int = Field(default=0)
    
    # Metadata
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp of calculation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_trades": 100,
                "overall_win_rate": 55.0,
                "total_pnl": 250.50,
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
                }
            }
        }
