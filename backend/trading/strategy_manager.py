"""
Strategy Manager - Two-Speed Hybrid Architecture (HFT + Alpha)

Manages capital allocation between two distinct trading paths:
1. HFT Path: High-frequency market making with tight spreads
2. Alpha Path: Slower, ML-driven directional trades

This separation ensures the execution loop never waits for slow operations.

NOTE: All allocation percentages are read from the database configuration.
      The Settings UI is the SINGLE SOURCE OF TRUTH for these values.
"""
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    HFT = "hft"           # Fast path: Market making, inventory management
    ALPHA = "alpha"       # Slow path: ML-driven directional
    HYBRID = "hybrid"     # Both paths active


@dataclass
class StrategyAllocation:
    """Capital allocation for a strategy type."""
    strategy_type: StrategyType
    capital_usd: float
    max_position_usd: float
    max_positions: int
    current_deployed: float = 0.0
    current_positions: int = 0
    
    @property
    def available_capital(self) -> float:
        return max(0, self.capital_usd - self.current_deployed)
    
    @property
    def can_open_position(self) -> bool:
        return (
            self.current_positions < self.max_positions and
            self.available_capital >= self.max_position_usd * 0.1
        )


@dataclass
class MarketAllocation:
    """Per-market allocation limits."""
    market_id: str
    hft_allocation: StrategyAllocation
    alpha_allocation: StrategyAllocation
    
    def get_allocation(self, strategy_type: StrategyType) -> StrategyAllocation:
        if strategy_type == StrategyType.HFT:
            return self.hft_allocation
        return self.alpha_allocation


class StrategyManager:
    """
    Manages Two-Speed Hybrid Architecture for trading.
    
    HFT Path (Fast):
    - Market making with inventory skew
    - OFI-based quote adjustments  
    - Sub-second decision making
    - Uses cached signals only (never waits for LLM)
    
    Alpha Path (Slow):
    - ML/LLM sentiment analysis
    - Bayesian posterior calculation
    - Directional trades based on edge
    - Can wait for signal generation
    
    NOTE: All configuration values come from the database (Settings UI).
          Use StrategyManager.from_config(db_config) to create instances.
    """
    
    # Fallback defaults (only used if DB config is missing)
    DEFAULT_HFT_ALLOCATION_PCT = 40    # 40% of capital to HFT
    DEFAULT_ALPHA_ALLOCATION_PCT = 60  # 60% of capital to Alpha
    DEFAULT_HFT_MAX_POSITION_PCT = 10  # 10% per position for HFT
    DEFAULT_ALPHA_MAX_POSITION_PCT = 25  # 25% per position for Alpha
    DEFAULT_HFT_MAX_POSITIONS = 3      # 3 positions per market for HFT
    DEFAULT_ALPHA_MAX_POSITIONS = 1    # 1 position per market for Alpha
    
    def __init__(
        self,
        total_capital: float,
        hft_allocation_pct: float,
        alpha_allocation_pct: float,
        hft_max_position_pct: float = DEFAULT_HFT_MAX_POSITION_PCT,
        alpha_max_position_pct: float = DEFAULT_ALPHA_MAX_POSITION_PCT,
        hft_max_positions: int = DEFAULT_HFT_MAX_POSITIONS,
        alpha_max_positions: int = DEFAULT_ALPHA_MAX_POSITIONS,
        config: Optional[Dict] = None
    ):
        """
        Initialize strategy manager.
        
        Args:
            total_capital: Total trading capital in USD (deployed capital)
            hft_allocation_pct: Percentage allocated to HFT (0 to 100)
            alpha_allocation_pct: Percentage allocated to Alpha (0 to 100)
            hft_max_position_pct: Max position size as % of HFT capital
            alpha_max_position_pct: Max position size as % of Alpha capital
            hft_max_positions: Max positions per market for HFT
            alpha_max_positions: Max positions per market for Alpha
            config: Optional configuration overrides
        """
        # Convert percentages to decimals if needed
        if hft_allocation_pct > 1:
            hft_allocation_pct /= 100
        if alpha_allocation_pct > 1:
            alpha_allocation_pct /= 100
        if hft_max_position_pct > 1:
            hft_max_position_pct /= 100
        if alpha_max_position_pct > 1:
            alpha_max_position_pct /= 100
        
        # Validate allocations
        if hft_allocation_pct + alpha_allocation_pct > 1.0:
            logger.warning("Allocations exceed 100%, normalizing...")
            total = hft_allocation_pct + alpha_allocation_pct
            hft_allocation_pct /= total
            alpha_allocation_pct /= total
        
        self.total_capital = total_capital
        self.hft_allocation_pct = hft_allocation_pct
        self.alpha_allocation_pct = alpha_allocation_pct
        self.hft_max_position_pct = hft_max_position_pct
        self.alpha_max_position_pct = alpha_max_position_pct
        self.hft_max_positions = hft_max_positions
        self.alpha_max_positions = alpha_max_positions
        self.config = config or {}
        
        # Calculate capital allocations
        self.hft_capital = total_capital * hft_allocation_pct
        self.alpha_capital = total_capital * alpha_allocation_pct
        self.reserve_capital = total_capital * (1.0 - hft_allocation_pct - alpha_allocation_pct)
        
        # Track per-market allocations
        self._market_allocations: Dict[str, MarketAllocation] = {}
        
        # Global tracking
        self.hft_deployed = 0.0
        self.alpha_deployed = 0.0
        
        logger.info(
            f"StrategyManager initialized: "
            f"HFT=${self.hft_capital:,.0f} ({hft_allocation_pct:.0%}), "
            f"Alpha=${self.alpha_capital:,.0f} ({alpha_allocation_pct:.0%}), "
            f"Reserve=${self.reserve_capital:,.0f}"
        )
    
    @classmethod
    def from_config(cls, db_config: Dict) -> 'StrategyManager':
        """
        Create StrategyManager from database configuration.
        
        This is the preferred way to instantiate - reads from Settings UI.
        
        Args:
            db_config: Configuration dict from database (via /api/config)
            
        Returns:
            Configured StrategyManager instance
        """
        # Get deployed capital
        initial_capital = db_config.get('initial_capital', 10000)
        deployment_pct = db_config.get('capital_deployment_pct', 80)
        if deployment_pct > 1:
            deployment_pct /= 100
        deployed_capital = initial_capital * deployment_pct
        
        # Get HFT/Alpha allocations from config (Settings UI is source of truth)
        hft_allocation = db_config.get('hft_allocation_pct', cls.DEFAULT_HFT_ALLOCATION_PCT)
        alpha_allocation = db_config.get('alpha_allocation_pct', cls.DEFAULT_ALPHA_ALLOCATION_PCT)
        hft_max_pos = db_config.get('hft_max_position_pct', cls.DEFAULT_HFT_MAX_POSITION_PCT)
        alpha_max_pos = db_config.get('alpha_max_position_pct', cls.DEFAULT_ALPHA_MAX_POSITION_PCT)
        hft_max_positions = db_config.get('hft_max_positions', cls.DEFAULT_HFT_MAX_POSITIONS)
        alpha_max_positions = db_config.get('alpha_max_positions', cls.DEFAULT_ALPHA_MAX_POSITIONS)
        
        logger.info(
            f"Creating StrategyManager from config: "
            f"HFT={hft_allocation}%, Alpha={alpha_allocation}%, "
            f"Deployed=${deployed_capital:,.0f}"
        )
        
        return cls(
            total_capital=deployed_capital,
            hft_allocation_pct=hft_allocation,
            alpha_allocation_pct=alpha_allocation,
            hft_max_position_pct=hft_max_pos,
            alpha_max_position_pct=alpha_max_pos,
            hft_max_positions=hft_max_positions,
            alpha_max_positions=alpha_max_positions,
            config=db_config
        )
    
    def allocate_funds(
        self,
        market_id: str,
        market_data: Optional[Dict] = None
    ) -> MarketAllocation:
        """
        Get or create capital allocation for a market.
        
        Returns distinct position limits for HFT vs Alpha strategies.
        
        Args:
            market_id: Market identifier
            market_data: Optional market data for dynamic allocation
            
        Returns:
            MarketAllocation with HFT and Alpha allocations
        """
        if market_id in self._market_allocations:
            return self._market_allocations[market_id]
        
        # Calculate position sizes based on strategy type
        hft_max_position = self.hft_capital * self.hft_max_position_pct
        alpha_max_position = self.alpha_capital * self.alpha_max_position_pct
        
        # Apply market-specific adjustments if data available
        if market_data:
            liquidity = market_data.get('liquidity', 0)
            # volume_24h available for future use (e.g., volume-weighted sizing)
            _ = market_data.get('volume_24h', 0)
            
            # Reduce position size for illiquid markets
            liquidity_factor = min(1.0, liquidity / 50000) if liquidity > 0 else 0.5
            hft_max_position *= liquidity_factor
            alpha_max_position *= liquidity_factor
        
        # Create allocations
        hft_allocation = StrategyAllocation(
            strategy_type=StrategyType.HFT,
            capital_usd=self.hft_capital,
            max_position_usd=hft_max_position,
            max_positions=self.hft_max_positions
        )
        
        alpha_allocation = StrategyAllocation(
            strategy_type=StrategyType.ALPHA,
            capital_usd=self.alpha_capital,
            max_position_usd=alpha_max_position,
            max_positions=self.alpha_max_positions
        )
        
        allocation = MarketAllocation(
            market_id=market_id,
            hft_allocation=hft_allocation,
            alpha_allocation=alpha_allocation
        )
        
        self._market_allocations[market_id] = allocation
        
        logger.debug(
            f"Allocated for {market_id}: "
            f"HFT max=${hft_max_position:.0f}, Alpha max=${alpha_max_position:.0f}"
        )
        
        return allocation
    
    def get_strategy_for_signal(
        self,
        signals: Dict,
        market_data: Dict
    ) -> Tuple[StrategyType, str]:
        """
        Determine which strategy path to use based on signals.
        
        Fast signals (OFI, inventory) → HFT path
        Slow signals (sentiment, Bayesian) → Alpha path
        
        Returns:
            Tuple of (StrategyType, reason)
        """
        # Check for HFT opportunities (fast path)
        ofi = signals.get('ofi', 0)
        inventory_ratio = signals.get('inventory_ratio', 0)
        spread = market_data.get('spread', 0.05)
        
        # HFT conditions: tight spread + OFI signal + inventory capacity
        if spread < 0.03 and abs(ofi) > 0.4 and abs(inventory_ratio) < 0.7:
            return StrategyType.HFT, "tight_spread_ofi_signal"
        
        # Check for Alpha opportunities (slow path)
        sentiment = signals.get('sentiment', 0.5)
        confidence = signals.get('confidence', 0)
        bayesian_posterior = signals.get('bayesian_posterior', 0.5)
        
        # Alpha conditions: strong directional signal
        if abs(sentiment - 0.5) > 0.15 and confidence > 0.5:
            return StrategyType.ALPHA, "strong_sentiment_signal"
        
        if abs(bayesian_posterior - 0.5) > 0.20:
            return StrategyType.ALPHA, "bayesian_mispricing"
        
        # Default to HFT for market making
        return StrategyType.HFT, "default_market_making"
    
    def update_deployment(
        self,
        strategy_type: StrategyType,
        amount: float,
        market_id: str
    ):
        """
        Update deployed capital tracking.
        
        Args:
            strategy_type: HFT or Alpha
            amount: Positive for new position, negative for closed
            market_id: Market identifier
        """
        if strategy_type == StrategyType.HFT:
            self.hft_deployed += amount
        else:
            self.alpha_deployed += amount
        
        # Update market-specific tracking
        if market_id in self._market_allocations:
            allocation = self._market_allocations[market_id]
            target = allocation.get_allocation(strategy_type)
            target.current_deployed += amount
            if amount > 0:
                target.current_positions += 1
            elif amount < 0:
                target.current_positions = max(0, target.current_positions - 1)
    
    def get_utilization(self) -> Dict:
        """Get current capital utilization stats."""
        return {
            'total_capital': self.total_capital,
            'hft': {
                'allocated': self.hft_capital,
                'deployed': self.hft_deployed,
                'utilization_pct': self.hft_deployed / self.hft_capital if self.hft_capital > 0 else 0,
                'available': self.hft_capital - self.hft_deployed
            },
            'alpha': {
                'allocated': self.alpha_capital,
                'deployed': self.alpha_deployed,
                'utilization_pct': self.alpha_deployed / self.alpha_capital if self.alpha_capital > 0 else 0,
                'available': self.alpha_capital - self.alpha_deployed
            },
            'reserve': self.reserve_capital,
            'total_deployed': self.hft_deployed + self.alpha_deployed,
            'total_utilization_pct': (self.hft_deployed + self.alpha_deployed) / self.total_capital if self.total_capital > 0 else 0
        }
    
    def rebalance(self, new_hft_pct: float, new_alpha_pct: float):
        """
        Rebalance capital allocation between strategies.
        
        This should be called during quiet periods, not during active trading.
        """
        if new_hft_pct + new_alpha_pct > 1.0:
            logger.warning("Rebalance allocations exceed 100%, normalizing...")
            total = new_hft_pct + new_alpha_pct
            new_hft_pct /= total
            new_alpha_pct /= total
        
        self.hft_allocation_pct = new_hft_pct
        self.alpha_allocation_pct = new_alpha_pct
        
        self.hft_capital = self.total_capital * new_hft_pct
        self.alpha_capital = self.total_capital * new_alpha_pct
        self.reserve_capital = self.total_capital * (1.0 - new_hft_pct - new_alpha_pct)
        
        logger.info(
            f"Rebalanced: HFT={new_hft_pct:.0%} (${self.hft_capital:,.0f}), "
            f"Alpha={new_alpha_pct:.0%} (${self.alpha_capital:,.0f})"
        )
