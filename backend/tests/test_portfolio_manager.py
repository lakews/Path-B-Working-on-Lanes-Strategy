"""
Unit Tests for Unified Portfolio Manager (Task 23)
===================================================

Tests cover:
1. Whale Zone - Price <$0.10 gets hard-capped at $15 regardless of signal
2. Core Zone - Kelly-based sizing with caps
3. Sector Caps - Trade returns 0 if sector allocation is full
4. Event Caps - Trade returns 0 if event allocation is full
5. Liquidity - Trade is reduced if order book is thin
6. Strategy Routing - TAKER uses Kelly, MAKER uses unit
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.portfolio_manager import (
    PortfolioManager,
    TradingRegime,
    SizingResult,
    get_portfolio_manager
)
from risk_config import RISK


class TestZoneClassification:
    """Test zone classification based on price."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
    
    def test_whale_zone_below_threshold(self):
        """Prices below $0.10 should be WHALE zone."""
        assert self.pm.get_zone_for_price(0.05) == 'WHALE'
        assert self.pm.get_zone_for_price(0.09) == 'WHALE'
        assert self.pm.get_zone_for_price(0.03) == 'WHALE'
    
    def test_core_zone_at_and_above_threshold(self):
        """Prices at or above $0.10 should be CORE zone."""
        assert self.pm.get_zone_for_price(0.10) == 'CORE'
        assert self.pm.get_zone_for_price(0.50) == 'CORE'
        assert self.pm.get_zone_for_price(0.95) == 'CORE'


class TestWhaleZoneSizing:
    """Test Whale Zone sizing - hard caps regardless of signal."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.wallet = 10000.0  # $10K wallet
    
    def test_whale_zone_hard_cap_15_usd(self):
        """Whale zone should cap at $15 even with max signal."""
        result = self.pm.calculate_target_size(
            price=0.05,  # Whale zone
            regime='TAKER',
            signal_strength=1.0,  # Max signal
            wallet_balance=self.wallet,
            liquidity_at_price=10000,  # High liquidity
            sector='crypto'
        )
        
        assert result.zone == 'WHALE'
        # Should be capped at $15 (WHALE_MAX_USD)
        assert result.target_size <= RISK.WHALE_MAX_USD
        assert result.target_size <= 15.0
    
    def test_whale_zone_ignores_kelly(self):
        """Whale zone should ignore signal strength (no Kelly)."""
        result_low = self.pm.calculate_target_size(
            price=0.05,
            regime='TAKER',
            signal_strength=0.51,  # Low signal
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='crypto'
        )
        
        result_high = self.pm.calculate_target_size(
            price=0.05,
            regime='TAKER',
            signal_strength=0.99,  # High signal
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='crypto'
        )
        
        # Both should have same size (no Kelly scaling in whale zone)
        assert result_low.target_size == result_high.target_size
        assert result_low.kelly_fraction is None
    
    def test_whale_zone_percentage_cap(self):
        """Whale zone should also respect 1% of deployed cap."""
        # With $1000 wallet, 80% deployed = $800
        # 1% of $800 = $8, which is less than $15
        result = self.pm.calculate_target_size(
            price=0.05,
            regime='TAKER',
            signal_strength=1.0,
            wallet_balance=1000.0,  # Small wallet
            liquidity_at_price=10000,
            sector='crypto'
        )
        
        # Should be min($15, $8) = $8
        deployed = 1000.0 * 0.80
        pct_cap = deployed * 0.01
        assert result.target_size <= pct_cap + 0.01  # Allow rounding


class TestCoreZoneSizing:
    """Test Core Zone sizing - Kelly-based with caps."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.wallet = 10000.0
    
    def test_core_zone_taker_uses_kelly(self):
        """TAKER regime should use Kelly-based sizing."""
        result = self.pm.calculate_target_size(
            price=0.50,  # Core zone
            regime='TAKER',
            signal_strength=0.70,  # Decent signal
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        assert result.zone == 'CORE'
        assert result.kelly_fraction is not None
        assert result.kelly_fraction > 0
    
    def test_core_zone_maker_uses_unit(self):
        """MAKER regime should use fixed unit sizing (2%)."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='MAKER',
            signal_strength=0.70,
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        assert result.zone == 'CORE'
        # HFT_UNIT_PCT = 0.02 (2%)
        # Deployed = $8000, 2% = $160
        # But capped at $100 (CORE_MAX_USD)
        assert result.target_size <= RISK.CORE_MAX_USD
    
    def test_core_zone_respects_100_usd_cap(self):
        """Core zone should cap at $100 even with high signal."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=1.0,  # Max signal
            wallet_balance=100000.0,  # Very large wallet
            liquidity_at_price=100000,
            sector='politics'
        )
        
        assert result.target_size <= RISK.CORE_MAX_USD
        assert result.target_size <= 100.0
    
    def test_kelly_scaling_applied(self):
        """Higher signal should produce larger (but still capped) size."""
        result_low = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.55,  # Just above threshold
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        result_high = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,  # High signal
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        # Higher signal should produce larger Kelly fraction
        assert result_high.kelly_fraction > result_low.kelly_fraction


class TestSectorCaps:
    """Test sector exposure limits."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.wallet = 10000.0
        self.deployed = self.wallet * 0.80  # $8000
    
    def test_sector_cap_crypto_20_percent(self):
        """Crypto sector should be capped at 20%."""
        # Max crypto = $8000 * 0.20 = $1600
        # If we already have $1500 exposure, only $100 remaining
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.80,
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            current_exposure_sector=1500.0,  # Already have $1500 in crypto
            sector='crypto'
        )
        
        # Remaining sector capacity = $1600 - $1500 = $100
        assert result.sector_cap == 100.0
        assert result.target_size <= 100.0
    
    def test_sector_full_returns_zero(self):
        """Full sector allocation should return 0 size."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            current_exposure_sector=2000.0,  # Already at/above 20% cap
            sector='crypto'
        )
        
        # Sector is full, should reject
        assert result.target_size == 0.0
        assert 'sector' in result.reject_reason.lower()
    
    def test_sector_cap_politics_25_percent(self):
        """Politics sector should be capped at 25%."""
        limit = self.pm.get_sector_limit('politics')
        assert limit == 0.25
    
    def test_sector_cap_conflict_10_percent(self):
        """Conflict sector should be capped at 10% (most restrictive)."""
        limit = self.pm.get_sector_limit('conflict')
        assert limit == 0.10


class TestEventCaps:
    """Test event exposure limits."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.wallet = 10000.0
        self.deployed = self.wallet * 0.80  # $8000
    
    def test_event_cap_15_percent(self):
        """Event exposure should be capped at 15%."""
        # Max event = $8000 * 0.15 = $1200
        # If we already have $1100 exposure, only $100 remaining
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.80,
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            current_exposure_event=1100.0,  # Already have $1100 in event
            sector='politics'
        )
        
        # Remaining event capacity = $1200 - $1100 = $100
        assert result.event_cap == 100.0
        assert result.target_size <= 100.0
    
    def test_event_full_returns_zero(self):
        """Full event allocation should return 0 size."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,
            wallet_balance=self.wallet,
            liquidity_at_price=10000,
            current_exposure_event=1500.0,  # Already at/above 15% cap
            sector='politics'
        )
        
        # Event is full, should reject
        assert result.target_size == 0.0
        assert 'event' in result.reject_reason.lower()


class TestLiquidityClamp:
    """Test liquidity consumption limits."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.wallet = 10000.0
    
    def test_liquidity_10_percent_consumption(self):
        """Should not consume more than 10% of order book depth."""
        # Liquidity = $500, max consumption = $50
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,
            wallet_balance=self.wallet,
            liquidity_at_price=500.0,  # Thin order book
            sector='politics'
        )
        
        # Max consumption = $500 * 0.10 = $50
        assert result.liquidity_cap == 50.0
        assert result.target_size <= 50.0
    
    def test_thin_liquidity_reduces_size(self):
        """Very thin liquidity should significantly reduce size."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,
            wallet_balance=self.wallet,
            liquidity_at_price=100.0,  # Very thin
            sector='politics'
        )
        
        # Max consumption = $100 * 0.10 = $10
        assert result.target_size <= 10.0
    
    def test_insufficient_liquidity_rejected(self):
        """Extremely thin liquidity should reject trade."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.90,
            wallet_balance=self.wallet,
            liquidity_at_price=10.0,  # Only $10 liquidity
            sector='politics'
        )
        
        # Max consumption = $10 * 0.10 = $1 (below $2 minimum)
        assert result.target_size == 0.0


class TestDustFilter:
    """Test minimum trade amount filter."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
    
    def test_below_minimum_rejected(self):
        """Trades below minimum should be rejected."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.51,  # Very weak signal
            wallet_balance=100.0,  # Very small wallet
            liquidity_at_price=10000,
            sector='politics'
        )
        
        # If calculated size < $2, should reject
        if result.raw_target < RISK.MIN_TRADE_AMOUNT:
            assert result.target_size == 0.0
            assert 'minimum' in result.reject_reason.lower()


class TestKellyCalculation:
    """Test Kelly criterion calculation."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
    
    def test_kelly_floor_for_weak_signal(self):
        """Signals at or below 50% should use minimum Kelly."""
        kelly = self.pm._calculate_kelly(0.50)
        assert kelly == RISK.MIN_KELLY_FRACTION
        
        kelly = self.pm._calculate_kelly(0.40)
        assert kelly == RISK.MIN_KELLY_FRACTION
    
    def test_kelly_scales_with_signal(self):
        """Kelly should scale with signal strength."""
        kelly_60 = self.pm._calculate_kelly(0.60)
        kelly_80 = self.pm._calculate_kelly(0.80)
        kelly_95 = self.pm._calculate_kelly(0.95)
        
        assert kelly_60 < kelly_80 < kelly_95
    
    def test_kelly_respects_ceiling(self):
        """Kelly should not exceed maximum fraction."""
        kelly = self.pm._calculate_kelly(1.0)  # Perfect signal
        assert kelly <= RISK.MAX_KELLY_FRACTION


class TestSizingResult:
    """Test SizingResult dataclass."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
    
    def test_result_to_dict(self):
        """Result should serialize to dictionary."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.70,
            wallet_balance=10000,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        result_dict = result.to_dict()
        
        assert 'target_size' in result_dict
        assert 'zone' in result_dict
        assert 'regime' in result_dict
        assert 'deployed_capital' in result_dict
        assert 'kelly_fraction' in result_dict


class TestStatistics:
    """Test statistics tracking."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
        self.pm.reset_stats()
    
    def test_stats_track_zones(self):
        """Stats should track whale vs core zone trades."""
        # Whale zone trade
        self.pm.calculate_target_size(
            price=0.05,
            regime='WHALE',
            signal_strength=0.70,
            wallet_balance=10000,
            liquidity_at_price=10000,
            sector='crypto'
        )
        
        # Core zone trade
        self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.70,
            wallet_balance=10000,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        stats = self.pm.get_stats()
        assert stats['whale_zone_trades'] >= 1
        assert stats['core_zone_trades'] >= 1
    
    def test_stats_reset(self):
        """Stats should reset to zero."""
        self.pm.stats['total_sizing_requests'] = 100
        self.pm.reset_stats()
        
        stats = self.pm.get_stats()
        assert stats['total_sizing_requests'] == 0


class TestSingleton:
    """Test singleton accessor."""
    
    def test_get_portfolio_manager_returns_same_instance(self):
        """get_portfolio_manager should return same instance."""
        pm1 = get_portfolio_manager()
        pm2 = get_portfolio_manager()
        
        assert pm1 is pm2


class TestCapitalAllocation:
    """Test capital allocation calculation."""
    
    def setup_method(self):
        self.pm = PortfolioManager()
    
    def test_80_percent_deployed(self):
        """80% of wallet should be deployed."""
        result = self.pm.calculate_target_size(
            price=0.50,
            regime='TAKER',
            signal_strength=0.70,
            wallet_balance=10000,
            liquidity_at_price=10000,
            sector='politics'
        )
        
        assert result.deployed_capital == 8000.0  # 80% of $10K


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
