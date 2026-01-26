"""
APEX TRADER - Unified Portfolio Manager (Task 23)
=================================================

The central "Architect" class for all position sizing decisions.
This is the ONLY entry point for calculating trade sizes.

Hierarchy of Safety:
1. Allocated Capital → Virtual sub-account (80% of wallet)
2. Price Zones (Hard Override) → Whale (<$0.10) vs Core (≥$0.10)
3. Strategy Regime → Alpha (Kelly), HFT (Maker Unit), Gamma (Whale Unit)
4. Liquidity → Never consume >10% of order book depth
5. Exposure → Enforce Sector and Event concentration limits

Input → Physics (Allocation) → Safety (Zones) → Strategy (Kelly) → Reality (Liquidity) → Output

Usage:
    from trading.portfolio_manager import PortfolioManager
    
    pm = PortfolioManager()
    size = pm.calculate_target_size(
        price=0.45,
        regime='TAKER',
        signal_strength=0.65,
        wallet_balance=10000,
        liquidity_at_price=5000,
        sector='politics'
    )
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from risk_config import RISK, MarketRegime

logger = logging.getLogger(__name__)


class TradingRegime(Enum):
    """Trading regime for strategy selection."""
    TAKER = "TAKER"      # Alpha directional (Kelly-based)
    MAKER = "MAKER"      # HFT market making (unit-based)
    WHALE = "WHALE"      # Gamma scalping (fixed small unit)


@dataclass
class SizingResult:
    """Result of position sizing calculation with full audit trail."""
    target_size: float           # Final position size in USD
    zone: str                    # 'WHALE' or 'CORE'
    regime: str                  # 'TAKER', 'MAKER', or 'WHALE'
    
    # Capital hierarchy
    wallet_balance: float
    deployed_capital: float      # After allocation %
    zone_max_usd: float         # Hard cap from zone
    zone_max_from_pct: float    # Cap from % rule
    
    # Strategy-specific
    raw_target: float           # Before liquidity/exposure limits
    kelly_fraction: Optional[float] = None
    
    # Applied limits
    liquidity_cap: float = 0.0
    event_cap: float = 0.0
    sector_cap: float = 0.0
    
    # Rejection reason (if size is 0)
    reject_reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/debugging."""
        return {
            'target_size': round(self.target_size, 2),
            'zone': self.zone,
            'regime': self.regime,
            'wallet_balance': round(self.wallet_balance, 2),
            'deployed_capital': round(self.deployed_capital, 2),
            'zone_max_usd': round(self.zone_max_usd, 2),
            'zone_max_from_pct': round(self.zone_max_from_pct, 2),
            'raw_target': round(self.raw_target, 2),
            'kelly_fraction': round(self.kelly_fraction, 4) if self.kelly_fraction else None,
            'liquidity_cap': round(self.liquidity_cap, 2),
            'event_cap': round(self.event_cap, 2),
            'sector_cap': round(self.sector_cap, 2),
            'reject_reason': self.reject_reason,
        }


class PortfolioManager:
    """
    Unified Portfolio Manager - Central "Architect" for position sizing.
    
    This class consolidates all sizing logic from:
    - risk_config.py (hard limits)
    - config.py (deployment %)
    - polymarket_position_sizer.py (Kelly/Sector caps)
    
    Key Design:
    - Price Zone is a HARD OVERRIDE that cannot be bypassed by signals
    - Whale Zone: Force small unit size regardless of Kelly
    - Core Zone: Use Kelly-based sizing with caps
    - All trades pass through liquidity and exposure filters
    """
    
    def __init__(self, config: Optional[RISK.__class__] = None):
        """
        Initialize Portfolio Manager.
        
        Args:
            config: Risk configuration. Uses global RISK if not provided.
        """
        self.config = config or RISK
        
        # Statistics
        self.stats = {
            'total_sizing_requests': 0,
            'whale_zone_trades': 0,
            'core_zone_trades': 0,
            'rejected_dust': 0,
            'rejected_liquidity': 0,
            'rejected_sector': 0,
            'rejected_event': 0,
            'total_sized_usd': 0.0,
        }
        
        logger.info("🏛️ PortfolioManager initialized (Unified Sizing Engine)")
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def calculate_target_size(
        self,
        price: float,
        regime: str,
        signal_strength: float,
        wallet_balance: float,
        liquidity_at_price: float,
        current_exposure_token: float = 0.0,
        current_exposure_event: float = 0.0,
        current_exposure_sector: float = 0.0,
        sector: str = 'unknown',
        market_id: str = ''
    ) -> SizingResult:
        """
        Calculate target position size with full safety hierarchy.
        
        This is the ONLY entry point for sizing decisions.
        
        Args:
            price: Current asset price (0-1)
            regime: Trading regime ('TAKER', 'MAKER', 'WHALE')
            signal_strength: Signal strength (0.0 to 1.0)
            wallet_balance: Total wallet balance in USD
            liquidity_at_price: Available liquidity at price level
            current_exposure_token: Current USD exposure to this token
            current_exposure_event: Current USD exposure to this event
            current_exposure_sector: Current USD exposure to this sector
            sector: Market sector/category
            market_id: Market identifier for logging
            
        Returns:
            SizingResult with target size and audit trail
        """
        self.stats['total_sizing_requests'] += 1
        
        # =====================================================================
        # STEP 1: CALCULATE DEPLOYED CAPITAL
        # =====================================================================
        deployed_capital = wallet_balance * (self.config.ALLOCATED_CAPITAL_PCT / 100)
        
        # =====================================================================
        # STEP 2: DETERMINE ZONE AND APPLY HARD CAPS
        # =====================================================================
        zone, zone_max_usd, zone_max_from_pct = self._get_zone_limits(price, deployed_capital)
        
        # The effective zone cap is the minimum of absolute and percentage caps
        effective_zone_cap = min(zone_max_usd, zone_max_from_pct)
        
        # =====================================================================
        # STEP 3: APPLY STRATEGY-SPECIFIC SIZING
        # =====================================================================
        raw_target, kelly_fraction = self._apply_strategy_sizing(
            zone=zone,
            regime=regime,
            signal_strength=signal_strength,
            deployed_capital=deployed_capital,
            effective_zone_cap=effective_zone_cap
        )
        
        # =====================================================================
        # STEP 4: APPLY LIQUIDITY CLAMP
        # =====================================================================
        liquidity_cap = liquidity_at_price * self.config.MAX_LIQUIDITY_CONSUMPTION
        target_after_liq = min(raw_target, liquidity_cap) if liquidity_at_price > 0 else raw_target
        
        # =====================================================================
        # STEP 5: APPLY EXPOSURE LIMITS
        # =====================================================================
        # Event exposure cap
        event_cap = (deployed_capital * self.config.MAX_EVENT_EXPOSURE_PCT) - current_exposure_event
        event_cap = max(0, event_cap)
        
        # Sector exposure cap
        sector_limit = self.config.SECTOR_LIMITS.get(sector.lower(), 0.15)
        sector_cap = (deployed_capital * sector_limit) - current_exposure_sector
        sector_cap = max(0, sector_cap)
        
        # Apply exposure limits
        target_after_exposure = min(target_after_liq, event_cap, sector_cap)
        
        # =====================================================================
        # STEP 6: FINAL DUST FILTER
        # =====================================================================
        reject_reason = None
        final_target = target_after_exposure
        
        if final_target < self.config.MIN_TRADE_AMOUNT:
            reject_reason = f"below minimum ${self.config.MIN_TRADE_AMOUNT}"
            final_target = 0.0
            self.stats['rejected_dust'] += 1
        elif target_after_liq < raw_target * 0.5:
            # Significant liquidity reduction - flag it
            logger.debug(f"[PM] Liquidity reduced size by >50%: ${raw_target:.2f} -> ${target_after_liq:.2f}")
        
        # Track rejections
        if event_cap <= 0:
            reject_reason = f"event exposure maxed (${current_exposure_event:.0f})"
            self.stats['rejected_event'] += 1
        elif sector_cap <= 0:
            reject_reason = f"sector '{sector}' exposure maxed (${current_exposure_sector:.0f})"
            self.stats['rejected_sector'] += 1
        elif liquidity_cap < self.config.MIN_TRADE_AMOUNT and liquidity_at_price > 0:
            reject_reason = f"insufficient liquidity (${liquidity_at_price:.0f})"
            self.stats['rejected_liquidity'] += 1
        
        # =====================================================================
        # BUILD RESULT
        # =====================================================================
        result = SizingResult(
            target_size=round(final_target, 2),
            zone=zone,
            regime=regime,
            wallet_balance=wallet_balance,
            deployed_capital=deployed_capital,
            zone_max_usd=zone_max_usd,
            zone_max_from_pct=zone_max_from_pct,
            raw_target=raw_target,
            kelly_fraction=kelly_fraction,
            liquidity_cap=liquidity_cap,
            event_cap=event_cap,
            sector_cap=sector_cap,
            reject_reason=reject_reason,
        )
        
        # Update stats
        if final_target > 0:
            if zone == 'WHALE':
                self.stats['whale_zone_trades'] += 1
            else:
                self.stats['core_zone_trades'] += 1
            self.stats['total_sized_usd'] += final_target
        
        # Log significant trades
        if final_target > 0:
            logger.debug(
                f"[PM] Size: ${final_target:.2f} | Zone: {zone} | Regime: {regime} | "
                f"Signal: {signal_strength:.2f} | Liq: ${liquidity_at_price:.0f}"
            )
        
        return result
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def _get_zone_limits(self, price: float, deployed_capital: float) -> Tuple[str, float, float]:
        """
        Determine zone and return hard caps.
        
        Args:
            price: Current price (0-1)
            deployed_capital: Deployed capital in USD
            
        Returns:
            (zone, max_usd, max_from_pct)
        """
        if price < self.config.PRICE_ZONE_THRESHOLD:
            # WHALE ZONE: Strict small caps
            zone = 'WHALE'
            max_usd = self.config.WHALE_MAX_USD
            max_from_pct = deployed_capital * self.config.WHALE_MAX_PCT
        else:
            # CORE ZONE: Higher caps
            zone = 'CORE'
            max_usd = self.config.CORE_MAX_USD
            max_from_pct = deployed_capital * self.config.CORE_MAX_PCT
        
        return zone, max_usd, max_from_pct
    
    def _apply_strategy_sizing(
        self,
        zone: str,
        regime: str,
        signal_strength: float,
        deployed_capital: float,
        effective_zone_cap: float
    ) -> Tuple[float, Optional[float]]:
        """
        Apply strategy-specific sizing logic.
        
        Args:
            zone: 'WHALE' or 'CORE'
            regime: 'TAKER', 'MAKER', or 'WHALE'
            signal_strength: Signal strength (0-1)
            deployed_capital: Deployed capital in USD
            effective_zone_cap: Maximum from zone limits
            
        Returns:
            (raw_target, kelly_fraction)
        """
        kelly_fraction = None
        
        # =====================================================================
        # WHALE ZONE: IGNORE ML SIGNALS, FORCE UNIT SIZE
        # =====================================================================
        if zone == 'WHALE':
            # In whale zone, we use fixed unit sizing regardless of signal
            # This is a HARD OVERRIDE - no Kelly, no signal scaling
            raw_target = effective_zone_cap
            return raw_target, None
        
        # =====================================================================
        # CORE ZONE: APPLY STRATEGY-BASED SIZING
        # =====================================================================
        
        if regime == 'TAKER' or regime == TradingRegime.TAKER.value:
            # TAKER (Alpha): Kelly-based sizing
            kelly_fraction = self._calculate_kelly(signal_strength)
            raw_target = deployed_capital * kelly_fraction
            raw_target = min(raw_target, effective_zone_cap)
            
        elif regime == 'MAKER' or regime == TradingRegime.MAKER.value:
            # MAKER (HFT): Fixed unit sizing
            raw_target = deployed_capital * self.config.HFT_UNIT_PCT
            raw_target = min(raw_target, effective_zone_cap)
            kelly_fraction = self.config.HFT_UNIT_PCT
            
        elif regime == 'WHALE' or regime == TradingRegime.WHALE.value:
            # WHALE regime but core price - use whale sizing anyway
            raw_target = min(self.config.WHALE_MAX_USD, effective_zone_cap)
            
        else:
            # Unknown regime - use conservative default
            logger.warning(f"[PM] Unknown regime '{regime}', using minimum")
            raw_target = self.config.MIN_TRADE_AMOUNT
        
        return raw_target, kelly_fraction
    
    def _calculate_kelly(self, signal_strength: float) -> float:
        """
        Calculate Kelly fraction from signal strength.
        
        Binary Kelly formula simplified:
        - f* = p - (1-p) = 2p - 1 for even odds
        - We interpret signal_strength as win probability
        - Apply scaling factor and clamp to bounds
        
        Args:
            signal_strength: Win probability estimate (0-1)
            
        Returns:
            Kelly fraction (clamped to MIN/MAX bounds)
        """
        # Clamp signal to valid probability range
        p = max(0.0, min(1.0, signal_strength))
        
        # Skip if signal is too weak
        if p <= 0.5:
            return self.config.MIN_KELLY_FRACTION
        
        # Binary Kelly: f* = 2p - 1 (for even odds)
        full_kelly = 2 * p - 1
        
        # Apply scaling factor (Quarter Kelly)
        scaled_kelly = full_kelly * self.config.KELLY_SCALING_FACTOR
        
        # Clamp to bounds
        clamped_kelly = max(
            self.config.MIN_KELLY_FRACTION,
            min(scaled_kelly, self.config.MAX_KELLY_FRACTION)
        )
        
        return clamped_kelly
    
    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================
    
    def get_zone_for_price(self, price: float) -> str:
        """Get zone ('WHALE' or 'CORE') for a given price."""
        return 'WHALE' if price < self.config.PRICE_ZONE_THRESHOLD else 'CORE'
    
    def get_max_position_for_price(self, price: float, deployed_capital: float) -> float:
        """Get maximum position size for a price level."""
        zone, max_usd, max_from_pct = self._get_zone_limits(price, deployed_capital)
        return min(max_usd, max_from_pct)
    
    def get_sector_limit(self, sector: str) -> float:
        """Get sector allocation limit as decimal."""
        return self.config.SECTOR_LIMITS.get(sector.lower(), 0.15)
    
    def get_remaining_sector_capacity(
        self,
        sector: str,
        current_exposure: float,
        deployed_capital: float
    ) -> float:
        """Calculate remaining capacity for a sector."""
        limit = self.get_sector_limit(sector)
        max_allocation = deployed_capital * limit
        return max(0, max_allocation - current_exposure)
    
    def get_remaining_event_capacity(
        self,
        current_exposure: float,
        deployed_capital: float
    ) -> float:
        """Calculate remaining capacity for an event."""
        max_allocation = deployed_capital * self.config.MAX_EVENT_EXPOSURE_PCT
        return max(0, max_allocation - current_exposure)
    
    def get_stats(self) -> Dict:
        """Get portfolio manager statistics."""
        return {
            **self.stats,
            'config': {
                'allocated_capital_pct': self.config.ALLOCATED_CAPITAL_PCT,
                'whale_max_usd': self.config.WHALE_MAX_USD,
                'core_max_usd': self.config.CORE_MAX_USD,
                'kelly_scaling': self.config.KELLY_SCALING_FACTOR,
                'max_liquidity_consumption': self.config.MAX_LIQUIDITY_CONSUMPTION,
            }
        }
    
    def reset_stats(self):
        """Reset statistics."""
        for key in self.stats:
            if isinstance(self.stats[key], int):
                self.stats[key] = 0
            elif isinstance(self.stats[key], float):
                self.stats[key] = 0.0


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_portfolio_manager: Optional[PortfolioManager] = None

def get_portfolio_manager() -> PortfolioManager:
    """Get or create the singleton PortfolioManager instance."""
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager
