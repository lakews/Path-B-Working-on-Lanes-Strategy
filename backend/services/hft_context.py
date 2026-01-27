"""
HFT Context Manager - The "Brain" for Async-Skewed-Adaptive HFT
================================================================

Architecture: Asynchronous Parameter Injection
- The Thinking Engine (Alpha Loop) WRITES market parameters
- The HFT Loop READS and executes with real-time volatility adaptation

This is a thread-safe Singleton that stores the AI's latest guidance for each market.
HFT NEVER trades blind - it always requires fresh context from the Thinking Engine.

Key Principles:
1. Non-blocking reads (HFT must never wait for AI)
2. Staleness checks (reject old data > 10 minutes)
3. Kill switch support (pause trading on command)
4. Volatility adaptation (widen spreads when vol spikes)

Author: APEX TRADER Quantitative Architecture Team
Date: January 2026
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from threading import Lock, RLock
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum age of context before considered stale (seconds)
MAX_CONTEXT_AGE_SECONDS = 600  # 10 minutes

# Default parameters when no specific guidance exists
DEFAULT_BASE_SPREAD_BPS = 50  # 0.5% default spread
DEFAULT_MAX_INVENTORY_SKEW = 0.3  # 30% max inventory imbalance


class ContextStatus(str, Enum):
    """Status of HFT context for a market."""
    ACTIVE = "ACTIVE"       # Normal trading allowed
    PAUSED = "PAUSED"       # Temporarily paused (e.g., news event)
    KILL = "KILL"           # Trading disabled (emergency)
    STALE = "STALE"         # Data too old, needs refresh


# =============================================================================
# MARKET PARAMETERS DATACLASS
# =============================================================================

@dataclass
class MarketParams:
    """
    AI-computed parameters for HFT execution on a specific market.
    
    Written by: Alpha Loop (Thinking Engine)
    Read by: HFT Loop (Execution Engine)
    """
    # Core pricing guidance
    fair_value: float           # The AI's estimated "True Price" (0.0-1.0)
    bias: float                 # -1.0 (Strong Bear) to +1.0 (Strong Bull)
    
    # Spread & risk parameters
    base_spread_bps: int        # Baseline spread in basis points (e.g., 10 = 0.1%)
    max_inventory_skew: float   # Max allowed inventory imbalance (0.0-1.0)
    
    # Volatility context
    reference_volatility: float # Volatility level at time of analysis
    
    # Control
    status: ContextStatus       # "ACTIVE", "PAUSED", "KILL"
    timestamp: float            # Unix timestamp for staleness checks
    
    # Metadata
    market_id: str = ""
    confidence: float = 0.5     # AI confidence in the fair_value (0.0-1.0)
    regime: str = "TAKER_TIGHT" # Market regime at analysis time
    signals: Dict = field(default_factory=dict)  # Raw signal data for debugging
    
    def is_stale(self) -> bool:
        """Check if this context is too old to use."""
        age = time.time() - self.timestamp
        return age > MAX_CONTEXT_AGE_SECONDS
    
    def get_age_seconds(self) -> float:
        """Get age of this context in seconds."""
        return time.time() - self.timestamp
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API/logging."""
        return {
            "market_id": self.market_id,
            "fair_value": round(self.fair_value, 4),
            "bias": round(self.bias, 3),
            "base_spread_bps": self.base_spread_bps,
            "max_inventory_skew": round(self.max_inventory_skew, 2),
            "reference_volatility": round(self.reference_volatility, 4),
            "status": self.status.value if isinstance(self.status, ContextStatus) else self.status,
            "timestamp": self.timestamp,
            "age_seconds": round(self.get_age_seconds(), 1),
            "is_stale": self.is_stale(),
            "confidence": round(self.confidence, 3),
            "regime": self.regime,
        }


# =============================================================================
# HFT CONTEXT SINGLETON
# =============================================================================

class HFTContext:
    """
    Thread-safe singleton for HFT market context management.
    
    Usage:
        # Writing (from Alpha Loop):
        hft_context = get_hft_context()
        hft_context.update(market_id, fair_value=0.65, bias=0.3, ...)
        
        # Reading (from HFT Loop):
        params = hft_context.get(market_id)
        if params and params.status == ContextStatus.ACTIVE and not params.is_stale():
            # Execute with AI guidance
        else:
            # Do NOT trade blind - return None
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._data_lock = RLock()
        self._markets: Dict[str, MarketParams] = {}
        self._stats = {
            "total_updates": 0,
            "total_reads": 0,
            "stale_reads": 0,
            "kill_switches": 0,
            "active_markets": 0,
        }
        self._initialized = True
        logger.info("🧠 HFT Context Manager initialized")
    
    # =========================================================================
    # WRITE OPERATIONS (Called by Alpha/Thinking Engine)
    # =========================================================================
    
    def update(
        self,
        market_id: str,
        fair_value: float,
        bias: float,
        reference_volatility: float,
        confidence: float = 0.5,
        regime: str = "TAKER_TIGHT",
        signals: Dict = None,
        base_spread_bps: int = None,
        max_inventory_skew: float = None,
        status: ContextStatus = ContextStatus.ACTIVE,
    ) -> MarketParams:
        """
        Update HFT context for a market (called by Alpha Loop).
        
        Args:
            market_id: Market identifier
            fair_value: AI's estimated true price (0.0-1.0)
            bias: Directional bias (-1.0 to +1.0)
            reference_volatility: Volatility at analysis time
            confidence: AI confidence level (0.0-1.0)
            regime: Market regime classification
            signals: Raw signal data for debugging
            base_spread_bps: Override default spread (basis points)
            max_inventory_skew: Override default inventory limit
            status: Trading status for this market
        
        Returns:
            The created/updated MarketParams
        """
        with self._data_lock:
            # Calculate adaptive spread based on confidence and volatility
            if base_spread_bps is None:
                # Lower confidence = wider spread for safety
                confidence_adj = max(0.5, confidence)
                base_spread_bps = int(DEFAULT_BASE_SPREAD_BPS / confidence_adj)
                # Cap at reasonable bounds
                base_spread_bps = max(10, min(200, base_spread_bps))
            
            if max_inventory_skew is None:
                max_inventory_skew = DEFAULT_MAX_INVENTORY_SKEW
            
            params = MarketParams(
                market_id=market_id,
                fair_value=fair_value,
                bias=bias,
                base_spread_bps=base_spread_bps,
                max_inventory_skew=max_inventory_skew,
                reference_volatility=reference_volatility,
                status=status,
                timestamp=time.time(),
                confidence=confidence,
                regime=regime,
                signals=signals or {},
            )
            
            self._markets[market_id] = params
            self._stats["total_updates"] += 1
            self._stats["active_markets"] = len(self._markets)
            
            logger.debug(
                f"[HFT-CTX] Updated {market_id[:16]}... | "
                f"FV={fair_value:.4f} Bias={bias:+.2f} Spread={base_spread_bps}bps"
            )
            
            return params
    
    def update_from_analysis(self, market_id: str, analysis: Dict) -> Optional[MarketParams]:
        """
        Convenience method to update from Alpha analysis result.
        
        Implements CONFIDENCE SCALING (Phase 4 Optimization):
        - If volatility is extreme, reduce directional conviction
        - Forces HFT to rely more on wide spreads than directional bets
        
        Args:
            market_id: Market identifier
            analysis: Result dict from _run_alpha_analysis()
        
        Returns:
            MarketParams or None if analysis is invalid
        """
        if not analysis:
            return None
        
        # Extract fair value
        fair_value = analysis.get("fair_value", 0.5)
        
        # Calculate base bias from signals
        signals = analysis.get("signals", {})
        sentiment = signals.get("sentiment", 0.5)
        bayesian_posterior = signals.get("bayesian_posterior", 0.5)
        
        # Map sentiment (0-1) to bias (-1 to +1)
        # 0.5 sentiment = 0 bias (neutral)
        # 0.0 sentiment = -1 bias (strong bear)
        # 1.0 sentiment = +1 bias (strong bull)
        raw_bias = (sentiment - 0.5) * 2
        
        # Blend with bayesian posterior
        bayesian_bias = (bayesian_posterior - 0.5) * 2
        raw_bias = (raw_bias * 0.6) + (bayesian_bias * 0.4)
        
        # =============================================================
        # PHASE 4: CONFIDENCE SCALING
        # =============================================================
        # If volatility is extreme, reduce directional conviction
        # This forces HFT to rely more on wide spreads than directional bets
        #
        # Formula: Bias = Raw_Bias * (1 - (current_vol / max_historical_vol))
        #
        # When vol is normal (10% of max): scaling = 0.9, bias mostly preserved
        # When vol is 50% of max: scaling = 0.5, bias halved
        # When vol is extreme (100% of max): scaling = 0, bias = 0 (pure spread)
        
        current_volatility = signals.get("volatility", 0.01)
        
        # Historical max volatility thresholds by market type
        # These represent "panic mode" volatility levels
        MAX_HISTORICAL_VOLATILITY = 0.15  # 15% is extreme for prediction markets
        
        # Calculate volatility ratio (clamped to [0, 1])
        vol_ratio = min(1.0, current_volatility / MAX_HISTORICAL_VOLATILITY)
        
        # Confidence scaling factor: high vol = low conviction
        # Use sqrt to make scaling more gradual (not linear)
        # vol_ratio=0.1 → scaling=0.68 (preserved)
        # vol_ratio=0.5 → scaling=0.29 (reduced)
        # vol_ratio=1.0 → scaling=0 (neutral)
        vol_scaling = 1.0 - (vol_ratio ** 0.5)  # Square root for gradual decay
        
        # Apply confidence scaling to bias
        scaled_bias = raw_bias * vol_scaling
        
        # Also scale confidence itself
        raw_confidence = analysis.get("confidence", 0.5)
        scaled_confidence = raw_confidence * (0.5 + vol_scaling * 0.5)  # Min 50% confidence
        
        # Clamp to valid range
        bias = max(-1.0, min(1.0, scaled_bias))
        
        # Log if significant scaling occurred
        if abs(raw_bias - bias) > 0.1:
            logger.debug(
                f"[HFT-CTX] Confidence scaling: raw_bias={raw_bias:+.2f} → "
                f"scaled_bias={bias:+.2f} (vol_ratio={vol_ratio:.2f})"
            )
        
        # Extract volatility for reference
        reference_volatility = current_volatility
        confidence = scaled_confidence
        regime = analysis.get("regime", "TAKER_TIGHT")
        
        return self.update(
            market_id=market_id,
            fair_value=fair_value,
            bias=bias,
            reference_volatility=reference_volatility,
            confidence=confidence,
            regime=str(regime),
            signals=signals,
        )
    
    def kill(self, market_id: str, reason: str = "manual"):
        """Set KILL status for a market (emergency stop)."""
        with self._data_lock:
            if market_id in self._markets:
                self._markets[market_id].status = ContextStatus.KILL
                self._stats["kill_switches"] += 1
                logger.warning(f"🛑 [HFT-CTX] KILL switch activated for {market_id[:16]}... Reason: {reason}")
    
    def pause(self, market_id: str, reason: str = "manual"):
        """Set PAUSED status for a market (temporary halt)."""
        with self._data_lock:
            if market_id in self._markets:
                self._markets[market_id].status = ContextStatus.PAUSED
                logger.info(f"⏸️ [HFT-CTX] PAUSED {market_id[:16]}... Reason: {reason}")
    
    def resume(self, market_id: str):
        """Resume trading for a market."""
        with self._data_lock:
            if market_id in self._markets:
                self._markets[market_id].status = ContextStatus.ACTIVE
                logger.info(f"▶️ [HFT-CTX] RESUMED {market_id[:16]}...")
    
    def kill_all(self, reason: str = "global_emergency"):
        """Kill switch for ALL markets (emergency)."""
        with self._data_lock:
            for market_id in self._markets:
                self._markets[market_id].status = ContextStatus.KILL
            self._stats["kill_switches"] += len(self._markets)
            logger.critical(f"🚨 [HFT-CTX] GLOBAL KILL SWITCH! All {len(self._markets)} markets disabled. Reason: {reason}")
    
    # =========================================================================
    # READ OPERATIONS (Called by HFT Loop)
    # =========================================================================
    
    def get(self, market_id: str) -> Optional[MarketParams]:
        """
        Get HFT parameters for a market (called by HFT Loop).
        
        Returns None if:
        - Market has no context
        - Context is KILL status
        - Context is stale (> 10 minutes old)
        
        HFT should NEVER trade if this returns None.
        """
        with self._data_lock:
            self._stats["total_reads"] += 1
            
            params = self._markets.get(market_id)
            
            if params is None:
                return None
            
            # Check kill switch
            if params.status == ContextStatus.KILL:
                return None
            
            # Check staleness
            if params.is_stale():
                self._stats["stale_reads"] += 1
                logger.debug(f"[HFT-CTX] Stale context for {market_id[:16]}... (age: {params.get_age_seconds():.0f}s)")
                return None
            
            return params
    
    def get_all_active(self) -> Dict[str, MarketParams]:
        """Get all active (non-stale, non-killed) market params."""
        with self._data_lock:
            return {
                mid: params
                for mid, params in self._markets.items()
                if params.status == ContextStatus.ACTIVE and not params.is_stale()
            }
    
    def has_valid_context(self, market_id: str) -> bool:
        """Quick check if market has valid, tradeable context."""
        params = self.get(market_id)
        return params is not None and params.status == ContextStatus.ACTIVE
    
    # =========================================================================
    # STATS & MONITORING
    # =========================================================================
    
    def get_stats(self) -> Dict:
        """Get context manager statistics."""
        with self._data_lock:
            active_count = sum(
                1 for p in self._markets.values()
                if p.status == ContextStatus.ACTIVE and not p.is_stale()
            )
            stale_count = sum(1 for p in self._markets.values() if p.is_stale())
            killed_count = sum(1 for p in self._markets.values() if p.status == ContextStatus.KILL)
            
            return {
                **self._stats,
                "active_markets": active_count,
                "stale_markets": stale_count,
                "killed_markets": killed_count,
                "total_tracked": len(self._markets),
            }
    
    def clear(self):
        """Clear all market context (for testing/reset)."""
        with self._data_lock:
            self._markets.clear()
            logger.info("[HFT-CTX] Context cleared")
    
    def remove(self, market_id: str):
        """Remove context for a specific market."""
        with self._data_lock:
            if market_id in self._markets:
                del self._markets[market_id]


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_hft_context_instance: Optional[HFTContext] = None

def get_hft_context() -> HFTContext:
    """Get the global HFT Context singleton."""
    global _hft_context_instance
    if _hft_context_instance is None:
        _hft_context_instance = HFTContext()
    return _hft_context_instance


# =============================================================================
# VOLATILITY CALCULATOR (For Real-Time Adaptation)
# =============================================================================

class VolatilityCalculator:
    """
    Real-time volatility calculator for HFT spread adaptation.
    
    Uses a rolling window of price ticks to calculate current volatility,
    which is compared against the reference volatility from the Thinking Engine.
    """
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self._price_windows: Dict[str, list] = {}
        self._lock = Lock()
    
    def add_tick(self, market_id: str, price: float):
        """Add a price tick for volatility calculation."""
        with self._lock:
            if market_id not in self._price_windows:
                self._price_windows[market_id] = []
            
            window = self._price_windows[market_id]
            window.append(price)
            
            # Keep window size bounded
            if len(window) > self.window_size:
                self._price_windows[market_id] = window[-self.window_size:]
    
    def calculate_volatility(self, market_id: str) -> float:
        """
        Calculate current volatility (std dev of returns).
        
        Returns 0.0 if insufficient data.
        """
        with self._lock:
            window = self._price_windows.get(market_id, [])
            
            if len(window) < 5:
                return 0.0
            
            # Calculate returns
            returns = []
            for i in range(1, len(window)):
                if window[i-1] > 0:
                    ret = (window[i] - window[i-1]) / window[i-1]
                    returns.append(ret)
            
            if not returns:
                return 0.0
            
            # Standard deviation of returns
            import numpy as np
            return float(np.std(returns))
    
    def get_vol_multiplier(self, market_id: str, reference_vol: float) -> float:
        """
        Calculate volatility multiplier for spread adjustment.
        
        If current vol > reference vol, multiplier > 1.0 (widen spread)
        If current vol < reference vol, multiplier < 1.0 (tighten spread)
        
        Clamped to [0.5, 3.0] range for safety.
        """
        current_vol = self.calculate_volatility(market_id)
        
        if reference_vol <= 0 or current_vol <= 0:
            return 1.0
        
        multiplier = current_vol / reference_vol
        
        # Clamp to safe range
        return max(0.5, min(3.0, multiplier))
    
    def clear(self, market_id: str = None):
        """Clear price window for a market (or all if None)."""
        with self._lock:
            if market_id:
                self._price_windows.pop(market_id, None)
            else:
                self._price_windows.clear()


# Global volatility calculator
_vol_calculator: Optional[VolatilityCalculator] = None

def get_volatility_calculator() -> VolatilityCalculator:
    """Get the global volatility calculator."""
    global _vol_calculator
    if _vol_calculator is None:
        _vol_calculator = VolatilityCalculator()
    return _vol_calculator
