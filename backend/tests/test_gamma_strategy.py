"""
Unit Tests for Gamma Strategy (Whale Execution Logic) - Task 22
================================================================

Tests cover:
1. Side Selection - Correctly identifies the cheap "whale" side
2. Gap Logic - Places limit bid inside wide spreads
3. Wall Logic - Snipes weak walls, joins strong walls
4. Exit Logic - Free Roll, Moonbag, Stop Loss
5. Non-Interference - Ensures existing tests still pass

ISOLATION VERIFICATION: This test file imports ONLY from gamma_strategy.py
and risk_config.py. It does NOT import from hft_strategy or alpha_model.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.gamma_strategy import (
    GammaTrader,
    GammaOrder,
    GammaOrderType,
    GammaOrderReason,
    get_gamma_trader
)
from risk_config import RISK


class TestSideSelection:
    """Test the side selection logic - identifies which side is "whale" side."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def test_yes_is_whale_when_cheap(self):
        """YES side at $0.05 should be identified as whale."""
        side, price = self.trader._identify_whale_side(yes_price=0.05, no_price=0.95)
        assert side == 'YES'
        assert price == 0.05
    
    def test_no_is_whale_when_cheap(self):
        """NO side at $0.05 should be identified as whale (YES at $0.95)."""
        side, price = self.trader._identify_whale_side(yes_price=0.95, no_price=0.05)
        assert side == 'NO'
        assert price == 0.05
    
    def test_neither_whale_when_both_expensive(self):
        """Neither side whale when both > $0.10."""
        side, price = self.trader._identify_whale_side(yes_price=0.50, no_price=0.50)
        assert side is None
        assert price == 0.0
    
    def test_cheaper_side_when_both_whale(self):
        """When both sides are whale zone, prefer cheaper one."""
        side, price = self.trader._identify_whale_side(yes_price=0.08, no_price=0.09)
        assert side == 'YES'
        assert price == 0.08
        
        # Flip it
        side, price = self.trader._identify_whale_side(yes_price=0.09, no_price=0.08)
        assert side == 'NO'
        assert price == 0.08
    
    def test_kill_switch_rejects_too_low(self):
        """Prices below kill switch ($0.03) should not be whale."""
        side, price = self.trader._identify_whale_side(yes_price=0.01, no_price=0.99)
        assert side is None  # $0.01 is below kill switch
    
    def test_boundary_at_ceiling(self):
        """Price at exactly $0.10 should NOT be whale (>= ceiling)."""
        side, price = self.trader._identify_whale_side(yes_price=0.10, no_price=0.90)
        assert side is None  # $0.10 is at ceiling, not below


class TestGapLogic:
    """Test the "Gap" scenario - wide spread, place bid inside."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def test_gap_creates_limit_bid_inside(self):
        """Wide gap (Bid $0.01 / Ask $0.04) → Limit bid at ~$0.02."""
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.01,
            best_ask=0.04,
            bid_volume=100.0,
            ask_volume=50.0,
            spread_cents=0.03,  # 3 cents > 2 cent threshold
            position_size=10.0
        )
        
        assert order is not None
        assert order.order_type == GammaOrderType.LIMIT_BID
        assert order.reason == GammaOrderReason.GAP_OPPORTUNITY
        # Bid should be inside the gap, above best_bid, below best_ask
        assert 0.01 < order.price < 0.04
        # Specifically, should be around midpoint
        assert 0.015 <= order.price <= 0.03
    
    def test_gap_bid_not_higher_than_ask(self):
        """Bid price should be at least 1 cent below ask."""
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.03,
            best_ask=0.06,
            bid_volume=100.0,
            ask_volume=50.0,
            spread_cents=0.03,
            position_size=10.0
        )
        
        assert order is not None
        assert order.price <= 0.05  # At least 1 cent below ask
    
    def test_gap_with_large_spread(self):
        """Very wide gap should still place reasonable bid."""
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="NO",
            best_bid=0.01,
            best_ask=0.08,
            bid_volume=100.0,
            ask_volume=50.0,
            spread_cents=0.07,  # 7 cents gap
            position_size=15.0
        )
        
        assert order is not None
        assert order.order_type == GammaOrderType.LIMIT_BID
        # Should be around midpoint (~$0.04-0.05)
        assert 0.03 <= order.price <= 0.06


class TestWallLogic:
    """Test the "Wall" scenario - tight spread, snipe or join."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def test_wall_strong_creates_limit_bid(self):
        """Strong wall (high ask volume) → Join the bid."""
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.01,
            best_ask=0.02,
            bid_volume=100.0,
            ask_volume=50.0,  # 50% of bid volume - wall is strong
            spread_cents=0.01,  # 1 cent < 2 cent threshold
            position_size=10.0
        )
        
        assert order is not None
        assert order.order_type == GammaOrderType.LIMIT_BID
        assert order.reason == GammaOrderReason.WALL_STRONG
        assert order.price == 0.01  # Join at best bid
    
    def test_wall_crumbling_creates_market_buy(self):
        """Weak wall (low ask volume) → Snipe with market buy."""
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.01,
            best_ask=0.02,
            bid_volume=100.0,
            ask_volume=10.0,  # 10% of bid volume - wall is crumbling!
            spread_cents=0.01,  # 1 cent < 2 cent threshold
            position_size=10.0
        )
        
        assert order is not None
        assert order.order_type == GammaOrderType.MARKET_BUY
        assert order.reason == GammaOrderReason.WALL_CRUMBLING
        assert order.price == 0.02  # Expected fill at ask
    
    def test_wall_crumble_threshold(self):
        """Test the exact 20% crumble threshold."""
        # Exactly 20% - should still be "strong" (boundary case)
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.01,
            best_ask=0.02,
            bid_volume=100.0,
            ask_volume=20.0,  # Exactly 20% - not < 20%
            spread_cents=0.01,
            position_size=10.0
        )
        
        assert order.reason == GammaOrderReason.WALL_STRONG
        
        # Just below 20% - should be "crumbling"
        order = self.trader._evaluate_spread(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            best_bid=0.01,
            best_ask=0.02,
            bid_volume=100.0,
            ask_volume=19.0,  # 19% < 20%
            spread_cents=0.01,
            position_size=10.0
        )
        
        assert order.reason == GammaOrderReason.WALL_CRUMBLING


class TestExitLogic:
    """Test the exit logic - Free Roll, Moonbag, Stop Loss."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def _create_test_position(self, entry_price: float, size: float = 10.0) -> dict:
        """Helper to create a test position."""
        return {
            'market_id': 'test_market',
            'token_id': 'test_token',
            'side': 'YES',
            'entry_price': entry_price,
            'size': size,
            'strategy': 'gamma_scalp',
        }
    
    def test_free_roll_at_2x(self):
        """2x entry price → Sell 50% (Free Roll)."""
        positions = {
            'pos1': self._create_test_position(entry_price=0.02, size=10.0)
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.04,  # 2x entry price
                'best_ask': 0.05,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 1
        order = exit_orders[0]
        assert order.reason == GammaOrderReason.FREE_ROLL
        assert order.size == 5.0  # 50% of 10.0
        assert order.order_type == GammaOrderType.MARKET_SELL
    
    def test_moonbag_at_5x(self):
        """5x entry price → Sell 100% (Moonbag)."""
        positions = {
            'pos1': self._create_test_position(entry_price=0.02, size=10.0)
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.10,  # 5x entry price
                'best_ask': 0.11,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 1
        order = exit_orders[0]
        assert order.reason == GammaOrderReason.MOONBAG
        assert order.size == 10.0  # 100%
    
    def test_stop_loss_at_half(self):
        """0.5x entry price → Sell 100% (Stop Loss)."""
        positions = {
            'pos1': self._create_test_position(entry_price=0.04, size=10.0)
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.02,  # 0.5x entry price
                'best_ask': 0.03,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 1
        order = exit_orders[0]
        assert order.reason == GammaOrderReason.STOP_LOSS
        assert order.size == 10.0  # 100%
    
    def test_no_exit_in_neutral_zone(self):
        """Price at 1.5x should not trigger any exit."""
        positions = {
            'pos1': self._create_test_position(entry_price=0.02, size=10.0)
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.03,  # 1.5x entry price - neutral zone
                'best_ask': 0.04,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 0
    
    def test_moonbag_takes_precedence_over_free_roll(self):
        """At 5x, moonbag should trigger, not free roll."""
        positions = {
            'pos1': self._create_test_position(entry_price=0.02, size=10.0)
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.12,  # 6x entry price
                'best_ask': 0.13,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 1
        assert exit_orders[0].reason == GammaOrderReason.MOONBAG
    
    def test_free_roll_not_retriggered(self):
        """Free roll should only happen once (position tagged)."""
        positions = {
            'pos1': {
                **self._create_test_position(entry_price=0.02, size=5.0),
                'free_roll_done': True,  # Already done free roll
            }
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.05,  # 2.5x - would normally trigger free roll
                'best_ask': 0.06,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 0  # No exit because free roll already done
    
    def test_ignores_non_gamma_positions(self):
        """Should only process gamma/whale positions."""
        positions = {
            'pos1': {
                'market_id': 'test_market',
                'side': 'YES',
                'entry_price': 0.02,
                'size': 10.0,
                'strategy': 'alpha_directional',  # Not a gamma position
            }
        }
        
        market_prices = {
            'test_market': {
                'best_bid': 0.10,  # 5x - would trigger moonbag for gamma
                'best_ask': 0.11,
            }
        }
        
        exit_orders = self.trader.check_exit_signals(positions, market_prices)
        
        assert len(exit_orders) == 0  # Ignored because not gamma strategy


class TestCalculateOrders:
    """Test the full calculate_orders flow."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def _create_market_data(
        self,
        yes_price: float,
        best_bid: float,
        best_ask: float,
        bid_volume: float = 100.0,
        ask_volume: float = 50.0
    ) -> dict:
        """Helper to create test market data."""
        return {
            'id': 'test_market_123',
            'yes_price': yes_price,
            'no_price': 1 - yes_price,
            'clobTokenIds': ['yes_token', 'no_token'],
            'order_book': {
                'bids': [{'price': str(best_bid), 'size': str(bid_volume)}],
                'asks': [{'price': str(best_ask), 'size': str(ask_volume)}],
            }
        }
    
    def test_generates_order_for_whale_opportunity(self):
        """Should generate order when whale opportunity exists."""
        market_data = self._create_market_data(
            yes_price=0.05,  # Valid whale zone price (above $0.03 kill switch)
            best_bid=0.04,
            best_ask=0.06,
        )
        
        orders = self.trader.calculate_orders(
            market_data=market_data,
            active_positions={},
            available_capital=1000.0
        )
        
        assert len(orders) == 1
        assert orders[0].side == 'YES'
        assert orders[0].order_type == GammaOrderType.LIMIT_BID
    
    def test_no_order_when_both_sides_expensive(self):
        """Should not generate order when both sides > $0.10."""
        market_data = self._create_market_data(
            yes_price=0.50,
            best_bid=0.49,
            best_ask=0.51,
        )
        
        orders = self.trader.calculate_orders(
            market_data=market_data,
            active_positions={},
            available_capital=1000.0
        )
        
        assert len(orders) == 0
    
    def test_respects_max_position_limit(self):
        """Should not generate order when max position reached."""
        market_data = self._create_market_data(
            yes_price=0.02,
            best_bid=0.01,
            best_ask=0.03,
        )
        
        # Existing position at max
        existing_positions = {
            'pos1': {
                'market_id': 'test_market_123',
                'side': 'YES',
                'size': RISK.WHALE_MAX_POSITION,  # Already at max
                'strategy': 'gamma_scalp',
            }
        }
        
        orders = self.trader.calculate_orders(
            market_data=market_data,
            active_positions=existing_positions,
            available_capital=1000.0
        )
        
        assert len(orders) == 0
    
    def test_no_order_without_orderbook(self):
        """Should not generate order without orderbook data."""
        market_data = {
            'id': 'test_market',
            'yes_price': 0.02,
            'no_price': 0.98,
            'order_book': {},  # Empty orderbook
        }
        
        orders = self.trader.calculate_orders(
            market_data=market_data,
            active_positions={},
            available_capital=1000.0
        )
        
        assert len(orders) == 0


class TestStatistics:
    """Test statistics tracking."""
    
    def setup_method(self):
        """Create fresh GammaTrader for each test."""
        self.trader = GammaTrader()
    
    def test_stats_initialized(self):
        """Stats should be initialized to zero."""
        stats = self.trader.get_stats()
        assert stats['orders_generated'] == 0
        assert stats['gap_opportunities'] == 0
        assert stats['wall_snipes'] == 0
    
    def test_stats_increment_on_gap(self):
        """Stats should increment on gap opportunity."""
        self.trader._evaluate_spread(
            market_id="test",
            token_id="test",
            side="YES",
            best_bid=0.01,
            best_ask=0.04,
            bid_volume=100.0,
            ask_volume=50.0,
            spread_cents=0.03,
            position_size=10.0
        )
        
        stats = self.trader.get_stats()
        assert stats['gap_opportunities'] == 1
    
    def test_stats_reset(self):
        """Stats should reset to zero."""
        self.trader.stats['orders_generated'] = 10
        self.trader.reset_stats()
        
        stats = self.trader.get_stats()
        assert stats['orders_generated'] == 0


class TestIsolation:
    """Test that Gamma strategy is properly isolated."""
    
    def test_no_dependency_on_hft(self):
        """GammaTrader should not import from HFT modules."""
        import trading.gamma_strategy as gamma_module
        
        # Check that the module doesn't import HFT-related modules
        imported_modules = dir(gamma_module)
        assert 'hft_strategy' not in str(imported_modules).lower()
    
    def test_no_dependency_on_alpha(self):
        """GammaTrader should not import from Alpha modules."""
        import trading.gamma_strategy as gamma_module
        
        imported_modules = dir(gamma_module)
        assert 'alpha_model' not in str(imported_modules).lower()
    
    def test_uses_risk_config(self):
        """GammaTrader should use centralized RiskConfig."""
        trader = GammaTrader()
        stats = trader.get_stats()
        
        assert 'config' in stats
        assert stats['config']['whale_price_ceiling'] == RISK.WHALE_PRICE_CEILING
        assert stats['config']['whale_max_position'] == RISK.WHALE_MAX_POSITION


class TestGammaOrderDataclass:
    """Test GammaOrder dataclass."""
    
    def test_order_to_dict(self):
        """Order should serialize to dictionary."""
        order = GammaOrder(
            market_id="test_market",
            token_id="test_token",
            side="YES",
            order_type=GammaOrderType.LIMIT_BID,
            price=0.02,
            size=10.0,
            reason=GammaOrderReason.GAP_OPPORTUNITY,
            best_bid=0.01,
            best_ask=0.03,
        )
        
        order_dict = order.to_dict()
        
        assert order_dict['market_id'] == "test_market"
        assert order_dict['order_type'] == "limit_bid"
        assert order_dict['reason'] == "gap_opportunity"
        assert 'timestamp' in order_dict


class TestSingleton:
    """Test singleton accessor."""
    
    def test_get_gamma_trader_returns_same_instance(self):
        """get_gamma_trader should return same instance."""
        trader1 = get_gamma_trader()
        trader2 = get_gamma_trader()
        
        assert trader1 is trader2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
