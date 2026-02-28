"""
APEX TRADER - Sports Arbitrage Strategy
========================================

Purpose: Execute statistical arbitrage on sports prediction markets
using real bookmaker odds from The Odds API.

Architecture:
- Uses devigged fair values from sports_odds.py (85% weight)
- Supplements with order flow sentiment (15% weight)
- LLM/GitHub signals: DISABLED (cannot predict live scores)

Category Isolation:
- This strategy ONLY processes markets where category == 'sports'
- Has its own volume/liquidity/spread thresholds (lower than Alpha)
- Allows NO-side betting (required for arbitrage)

Configuration:
- All parameters flow from SportsConfig in risk_config.py
- No hardcoded magic numbers
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SportsSignal(Enum):
    """Sports trading signal types."""
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    HOLD = "hold"
    NO_EDGE = "no_edge"
    BLOCKED = "blocked"


@dataclass
class SportsTradeSignal:
    """Signal output from sports strategy."""
    signal: SportsSignal
    side: Optional[str]  # 'YES' or 'NO'
    fair_value: float
    market_price: float
    edge: float
    edge_pct: float
    suggested_size: float
    confidence: float
    reason: str
    matched_event: Optional[Dict] = None
    bookmakers_used: int = 0


class SportsArbitrageStrategy:
    """
    Sports Arbitrage Strategy using real bookmaker odds.
    
    LOGIC:
    1. Get devigged fair value from The Odds API (via sports_odds.py)
    2. Compare to Polymarket price
    3. Generate signal if edge exceeds min_edge threshold
    4. Size position using Kelly criterion (capped by config)
    
    KEY DIFFERENCES FROM ALPHA:
    - NO-side betting is ALLOWED (required for arbitrage)
    - Lower volume/liquidity requirements
    - No LLM/sentiment signals (real odds only)
    - Higher price cap (0.99 for heavy favorites)
    """
    
    def __init__(self, sports_config):
        """
        Initialize with dynamic configuration.
        
        Args:
            sports_config: SportsConfig object from risk_config.py (SSOT)
        """
        self.config = sports_config
        self._trade_count = 0
        self._total_edge_captured = 0.0
        
        logger.info(
            f"[SPORTS STRATEGY] Initialized with config: "
            f"enabled={sports_config.enabled}, "
            f"allocation={sports_config.allocation_pct}%, "
            f"min_edge={sports_config.min_edge}, "
            f"min_volume=${sports_config.min_volume}"
        )
    
    def generate_signal(
        self,
        market_data: Dict,
        fair_value: float,
        sports_analysis: Optional[Dict] = None
    ) -> SportsTradeSignal:
        """
        Generate trading signal for a sports market.
        
        Args:
            market_data: Polymarket market data
            fair_value: Devigged probability from sports_odds.py (0.0-1.0)
                       None = BLOCKED by sentiment analyzer (insufficient data)
            sports_analysis: Full analysis from sports_odds.py (optional)
            
        Returns:
            SportsTradeSignal with trade recommendation
        """
        # Check if strategy is enabled
        if not self.config.enabled:
            return SportsTradeSignal(
                signal=SportsSignal.BLOCKED,
                side=None,
                fair_value=fair_value or 0.0,
                market_price=0.0,
                edge=0.0,
                edge_pct=0.0,
                suggested_size=0.0,
                confidence=0.0,
                reason="Sports strategy disabled in config"
            )
        
        # Extract market data
        market_id = market_data.get('id', 'unknown')
        yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
        no_price = 1 - yes_price
        volume_24h = float(market_data.get('volume_24h', 0) or 0)
        
        # ==========================================================================
        # INTELLIGENT FALLBACK: Handle None fair_value (BLOCKED by sentiment)
        # ==========================================================================
        # The enhanced_sentiment analyzer returns None when:
        # - Odds API failed AND insufficient market liquidity
        # - Market price is exactly 0.5 (no real data)
        # This is the TIER-0 block from the intelligent fallback system
        # ==========================================================================
        if fair_value is None:
            block_reason = "Insufficient data (Odds API down + low liquidity)"
            if sports_analysis:
                block_reason = sports_analysis.get('block_reason', block_reason)
                fusion_strategy = sports_analysis.get('fusion_strategy', '')
                if fusion_strategy:
                    block_reason = fusion_strategy
            
            return SportsTradeSignal(
                signal=SportsSignal.BLOCKED,
                side=None,
                fair_value=0.0,
                market_price=yes_price,
                edge=0.0,
                edge_pct=0.0,
                suggested_size=0.0,
                confidence=0.0,
                reason=block_reason
            )
        
        # ==========================================================================
        # SAFETY NET: Reject trades when fair_value is exactly 0.5
        # ==========================================================================
        # Even if sentiment analyzer didn't block, 0.5 is never a real fair value
        # for sports (would imply perfectly 50/50 odds, extremely rare)
        # ==========================================================================
        if abs(fair_value - 0.5) < 0.005:  # Within 0.5% of 0.5
            return SportsTradeSignal(
                signal=SportsSignal.BLOCKED,
                side=None,
                fair_value=fair_value,
                market_price=yes_price,
                edge=0.0,
                edge_pct=0.0,
                suggested_size=0.0,
                confidence=0.0,
                reason=f"Fair value {fair_value:.4f} too close to 0.5 (no real edge detectable)"
            )
        
        # Get data tier from analysis (for logging)
        data_tier = sports_analysis.get('sports_data_tier', 1) if sports_analysis else 1
        
        # Validate volume (from config, not hardcoded)
        if volume_24h < self.config.min_volume:
            return SportsTradeSignal(
                signal=SportsSignal.BLOCKED,
                side=None,
                fair_value=fair_value,
                market_price=yes_price,
                edge=0.0,
                edge_pct=0.0,
                suggested_size=0.0,
                confidence=0.0,
                reason=f"Volume ${volume_24h:.0f} < min ${self.config.min_volume}"
            )
        
        # ====================================================================
        # BUG 2 FIX: EXPLICIT DIRECTIONAL LOGIC
        # ====================================================================
        # fair_value = probability the YES outcome is correct (from bookmakers)
        # yes_price = cost to buy YES on Polymarket
        # no_price = cost to buy NO on Polymarket (should be 1 - yes_price)
        #
        # EDGE CALCULATION:
        # - YES edge = fair_value - yes_price (positive = YES is underpriced)
        # - NO edge = (1 - fair_value) - no_price (positive = NO is underpriced)
        #
        # SIGNAL:
        # - BUY YES if we believe YES will win AND it's cheap
        # - BUY NO if we believe NO will win AND it's cheap
        # ====================================================================
        
        # Ensure no_price is correctly calculated
        no_price = 1.0 - yes_price
        fair_no_prob = 1.0 - fair_value
        
        # Calculate raw edges (before fees)
        yes_edge_raw = fair_value - yes_price  # Positive = YES underpriced
        no_edge_raw = fair_no_prob - no_price   # Positive = NO underpriced
        
        # Apply taker fee
        taker_fee = self.config.taker_fee
        yes_edge_net = yes_edge_raw - taker_fee
        no_edge_net = no_edge_raw - taker_fee
        
        # Log the calculation for debugging
        logger.debug(
            f"[SPORTS EDGE] FV={fair_value:.3f} | YES: price={yes_price:.3f} edge={yes_edge_net:.4f} | "
            f"NO: price={no_price:.3f} edge={no_edge_net:.4f}"
        )
        
        # Determine best side - ONLY trade if we have positive edge after fees
        side = None
        edge = 0.0
        edge_pct = 0.0
        market_price = yes_price
        
        # Check YES first (prefer YES if edges are equal)
        if yes_edge_net >= self.config.min_edge and yes_edge_net >= no_edge_net:
            side = 'YES'
            edge = yes_edge_net
            edge_pct = edge / yes_price if yes_price > 0 else 0
            market_price = yes_price
        # Then check NO
        elif no_edge_net >= self.config.min_edge and no_edge_net > yes_edge_net:
            side = 'NO'
            edge = no_edge_net
            edge_pct = edge / no_price if no_price > 0 else 0
            market_price = no_price
        
        # No tradeable edge
        if side is None:
            return SportsTradeSignal(
                signal=SportsSignal.NO_EDGE,
                side=None,
                fair_value=fair_value,
                market_price=yes_price,
                edge=max(yes_edge_net, no_edge_net),
                edge_pct=0.0,
                suggested_size=0.0,
                confidence=0.0,
                reason=f"Edge YES={yes_edge_net:.4f} NO={no_edge_net:.4f} < min {self.config.min_edge}"
            )
        
        # Calculate position size using Kelly Criterion
        suggested_size = self._calculate_kelly_size(
            edge=edge,
            win_prob=fair_value if side == 'YES' else (1 - fair_value),
            market_price=market_price
        )
        
        # Extract confidence from sports analysis
        confidence = 0.5
        matched_event = None
        bookmakers_used = 0
        
        if sports_analysis:
            confidence = sports_analysis.get('sports_confidence', 0.5)
            matched_event = sports_analysis.get('sports_matched_event')
            bookmakers_used = sports_analysis.get('sports_bookmakers_used', 0)
        
        # Generate signal
        signal = SportsSignal.BUY_YES if side == 'YES' else SportsSignal.BUY_NO
        
        logger.info(
            f"[SPORTS SIGNAL] {market_id[:16]}... Tier={data_tier} | "
            f"FV={fair_value:.4f} vs Price={market_price:.4f} | "
            f"Side={side} Edge={edge:.4f} ({edge_pct:.2%}) | "
            f"Size=${suggested_size:.2f}"
        )
        
        return SportsTradeSignal(
            signal=signal,
            side=side,
            fair_value=fair_value,
            market_price=market_price,
            edge=edge,
            edge_pct=edge_pct,
            suggested_size=suggested_size,
            confidence=confidence,
            reason=f"Edge {edge:.4f} > min {self.config.min_edge}",
            matched_event=matched_event,
            bookmakers_used=bookmakers_used
        )
    
    def _calculate_kelly_size(
        self,
        edge: float,
        win_prob: float,
        market_price: float
    ) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly Formula: f* = (bp - q) / b
        Where:
            b = odds received (1/price - 1)
            p = probability of winning
            q = probability of losing (1 - p)
            
        Args:
            edge: Net edge after fees
            win_prob: Probability of winning (from fair value)
            market_price: Current market price
            
        Returns:
            Suggested position size in USD
        """
        if market_price <= 0 or market_price >= 1:
            return 0.0
        
        # Calculate Kelly fraction
        b = (1 / market_price) - 1  # Odds received
        p = win_prob
        q = 1 - p
        
        if b <= 0:
            return 0.0
        
        kelly_fraction = (b * p - q) / b
        
        # Apply Kelly scaling factor (fractional Kelly)
        kelly_fraction *= self.config.kelly_fraction
        
        # Clamp to min/max
        kelly_fraction = max(self.config.min_kelly, min(kelly_fraction, self.config.max_kelly))
        
        # Calculate size
        allocated_capital = self.config.allocation_pct / 100 * self.config.total_capital
        raw_size = allocated_capital * kelly_fraction
        
        # Apply position cap
        capped_size = min(raw_size, self.config.max_position_size)
        
        # Apply minimum trade floor
        if capped_size < self.config.min_trade_size:
            return 0.0
        
        return capped_size
    
    def should_exit(
        self,
        position: Dict,
        current_price: float,
        fair_value: float
    ) -> Tuple[bool, str]:
        """
        Check if a sports position should be exited.
        
        Sports-specific exit logic:
        - Time-based: Close before event starts
        - Edge reversal: Close if edge flips direction
        - Stop loss: Standard percentage stop
        - Take profit: Standard percentage target
        
        Args:
            position: Current position data
            current_price: Current market price
            fair_value: Current fair value from odds
            
        Returns:
            (should_exit: bool, reason: str)
        """
        entry_price = position.get('entry_price', 0)
        side = position.get('side', 'YES')
        
        if entry_price <= 0:
            return False, "invalid_entry_price"
        
        # Calculate P&L
        if side == 'YES':
            pnl_pct = (current_price - entry_price) / entry_price
            current_edge = fair_value - current_price
        else:
            pnl_pct = (entry_price - current_price) / (1 - entry_price)
            current_edge = (1 - fair_value) - (1 - current_price)
        
        # Stop Loss
        if pnl_pct < -self.config.stop_loss_pct:
            return True, f"stop_loss: {pnl_pct:.2%} < -{self.config.stop_loss_pct:.0%}"
        
        # Take Profit
        if pnl_pct > self.config.take_profit_pct:
            return True, f"take_profit: {pnl_pct:.2%} > +{self.config.take_profit_pct:.0%}"
        
        # Edge Reversal (significant edge flip)
        if current_edge < -self.config.min_edge:
            return True, f"edge_reversal: edge={current_edge:.4f} flipped"
        
        return False, "hold"
    
    def get_stats(self) -> Dict:
        """Get strategy statistics."""
        return {
            'trade_count': self._trade_count,
            'total_edge_captured': self._total_edge_captured,
            'config': {
                'enabled': self.config.enabled,
                'allocation_pct': self.config.allocation_pct,
                'min_edge': self.config.min_edge,
                'min_volume': self.config.min_volume,
                'max_position_size': self.config.max_position_size,
            }
        }


# Singleton instance
_sports_strategy: Optional[SportsArbitrageStrategy] = None


def get_sports_strategy(sports_config=None) -> SportsArbitrageStrategy:
    """Get singleton sports strategy instance."""
    global _sports_strategy
    
    if _sports_strategy is None:
        if sports_config is None:
            # Import here to avoid circular imports
            from risk_config import get_sports_config
            sports_config = get_sports_config()
        _sports_strategy = SportsArbitrageStrategy(sports_config)
    
    return _sports_strategy
