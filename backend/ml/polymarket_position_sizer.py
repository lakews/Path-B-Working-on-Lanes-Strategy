"""
Polymarket-Optimized Position Sizing Engine

A complete rewrite of position sizing for PREDICTION MARKETS.
Replaces the incorrect ATR/Standard Kelly approach with:

1. Binary Kelly Criterion (fee-adjusted)
2. Edge-Retention Liquidity Clamping (order book walk)
3. Utilization Brake (power curve: (1-x)^1.5)
4. Time/Duration Penalty
5. Oracle/Ambiguity Risk Matrix
6. Correlation Dampener
7. Sector Caps

This engine is designed for continuous trading where sizing must adapt
to portfolio state (50 trades vs 500 trades).
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from database import get_db
from ml.market_classifier import (
    classify_market, 
    get_oracle_risk_multiplier,
    get_detailed_classification
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURABLE DEFAULTS (can be overridden from DB/API)
# =============================================================================

DEFAULT_CONFIG = {
    # Fee configuration
    'polymarket_fee_pct': 0.02,  # 2% exit fee
    
    # Kelly configuration
    'kelly_multiplier': 0.25,   # Quarter Kelly (conservative)
    'base_trade_anchor': 200,   # Base unit = 0.5% of equity (1/200)
    
    # Utilization brake
    'utilization_exponent': 1.5,
    'utilization_hard_stop': 0.95,  # Stop at 95% utilization
    
    # Liquidity clamping
    'edge_retention_pct': 0.20,  # Allow 20% edge erosion from slippage
    
    # Time penalty
    'time_penalty_max_days': 90,  # 90 days = max penalty
    'time_penalty_floor': 0.50,   # Minimum 0.5x for long-dated bets
    
    # Position limits
    'min_bet_floor': 5.00,        # Minimum $5 bet
    # NOTE: max_single_position_pct is now passed from user config, not hardcoded here
    
    # Sector caps (configurable)
    'sector_caps': {
        'crypto': 0.20,       # 20% max in crypto
        'politics': 0.25,     # 25% max in politics
        'sports': 0.30,       # 30% max in sports
        'finance': 0.20,      # 20% max in finance
        'entertainment': 0.15,
        'science': 0.15,
        'conflict': 0.10,     # 10% max in war/conflict
        'social': 0.10,       # 10% max in social/tweets
        'unknown': 0.15,
    },
}

# Event cap configuration
EVENT_CAP_CONFIG = {
    'max_event_exposure_pct': 0.15,  # Max 15% of deployed capital per event
    'similarity_threshold': 0.60,    # Questions with >60% word overlap are same event (lowered from 0.7 to capture price variants)
}


class PolymarketPositionSizer:
    """
    Position sizing engine optimized for prediction markets.
    
    Key Concepts:
    - Equity = Cash + Sum(Position * Current Market Price)
    - Deployed = Sum(Position Cost Basis)
    - Utilization = Deployed / Equity
    
    The sizing formula:
    1. Calculate Binary Kelly base size
    2. Apply Utilization Brake (1 - utilization)^1.5
    3. Apply Time Penalty (long-dated = smaller)
    4. Apply Oracle Risk (subjective markets = smaller)
    5. Apply Correlation Dampener (overlapping positions)
    6. Clamp to Liquidity Cap (order book depth)
    7. Clamp to Sector Cap (max allocation per category)
    8. Clamp to Event Cap (max allocation per correlated event)
    9. Apply Min Bet Floor (skip if < $5)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.event_config = {**EVENT_CAP_CONFIG}
        self._version = "v2.1_event_cap"  # Version indicator
        logger.info(f"[SIZER] Initialized PolymarketPositionSizer {self._version}")
        
        # Try to get DB, but don't fail if not available
        try:
            self.db = get_db()
        except Exception as e:
            logger.debug(f"Could not get DB connection: {e}")
            self.db = None
        
        # Load user config from database
        self._load_config_from_db()
    
    def _load_config_from_db(self):
        """Load configurable parameters from database."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, schedule the load
                asyncio.create_task(self._async_load_config())
            else:
                loop.run_until_complete(self._async_load_config())
        except Exception as e:
            logger.debug(f"Could not load config from DB: {e}")
    
    async def _async_load_config(self):
        """Async config loader."""
        if self.db is None:
            return
        try:
            user_config = await self.db.user_config.find_one(
                {"type": "position_sizing_v2"},
                {"_id": 0}
            )
            if user_config:
                # Merge with defaults
                if 'polymarket_fee_pct' in user_config:
                    self.config['polymarket_fee_pct'] = float(user_config['polymarket_fee_pct'])
                if 'sector_caps' in user_config:
                    self.config['sector_caps'].update(user_config['sector_caps'])
                logger.info("Loaded position sizing config from DB")
        except Exception as e:
            logger.debug(f"Could not load position sizing config: {e}")
    
    async def save_config(self):
        """Save current config to database."""
        if self.db is None:
            return
        try:
            await self.db.user_config.update_one(
                {"type": "position_sizing_v2"},
                {"$set": {
                    "polymarket_fee_pct": self.config['polymarket_fee_pct'],
                    "sector_caps": self.config['sector_caps'],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Could not save position sizing config: {e}")
    
    # =========================================================================
    # CORE SIZING FUNCTION
    # =========================================================================
    
    def calculate_position_size(
        self,
        # Portfolio state
        equity: float,
        deployed_capital: float,
        
        # Trade parameters
        model_probability: float,
        ask_price: float,
        order_book_asks: List[Dict],  # [{"price": 0.42, "size": 1000}, ...]
        
        # Market metadata
        days_to_expiry: Optional[float],
        market_category: str,
        market_age_hours: Optional[float],
        market_question: str = "",
        market_tags: Optional[List[str]] = None,
        
        # Portfolio context
        open_positions: List[Dict] = None,  # Current open positions
        sector_exposure: Optional[Dict[str, float]] = None,  # {category: usd_amount}
        
        # User config - single source of truth
        max_position_size_pct: float = 0.03,  # From user config (default 3%)
        max_deployable_capital: float = None,  # From user config (initial_capital × capital_deployment_pct)
    ) -> Dict:
        """
        Calculate optimal position size for a Polymarket trade.
        
        Args:
            equity: Total portfolio value (cash + positions at market value)
            deployed_capital: Currently deployed capital (sum of position cost bases)
            max_position_size_pct: Max single position as decimal (0.03 = 3%). 
                                   This comes from user config and is the single source of truth.
            max_deployable_capital: Maximum capital allowed to be deployed (from user config).
                                    This is initial_capital × capital_deployment_pct.
                                    All sizing calculations use this as the base, not total equity.
        
        Returns:
            Dict with:
                - position_size: Final USD amount to bet
                - should_trade: Boolean
                - breakdown: Dict explaining each factor
        """
        open_positions = open_positions or []
        sector_exposure = sector_exposure or {}
        
        # Use max_deployable_capital as the sizing base (single source of truth)
        # If not provided, fall back to equity (backward compatibility)
        sizing_base = max_deployable_capital if max_deployable_capital is not None else equity
        
        # Get oracle risk classification
        classification = get_detailed_classification(
            market_question, market_tags, "", market_age_hours
        )
        
        # Infer category if not provided
        if not market_category or market_category == 'unknown':
            market_category = classification['category']
        
        # =================================================================
        # STEP 1: Calculate Effective Price (with fees)
        # =================================================================
        effective_price = self._calculate_effective_price(ask_price)
        
        # =================================================================
        # STEP 2: Calculate Edge
        # =================================================================
        edge = model_probability - effective_price
        logger.info(f"[SIZER CALC] edge={edge:.4f} = model_prob={model_probability:.4f} - eff_price={effective_price:.4f}")
        
        # No edge = no trade
        if edge <= 0:
            return self._no_trade_result("no_edge", f"Edge {edge:.4f} <= 0")
        
        # =================================================================
        # STEP 3: Binary Kelly Base Size
        # Uses sizing_base (max deployable capital from user config)
        # =================================================================
        kelly_fraction = self._calculate_binary_kelly(edge, effective_price)
        kelly_base = sizing_base * kelly_fraction * self.config['kelly_multiplier']
        
        # =================================================================
        # STEP 4: Utilization Brake
        # Utilization = deployed / max_deployable (not total equity)
        # =================================================================
        utilization = deployed_capital / sizing_base if sizing_base > 0 else 1.0
        utilization_mult = self._calculate_utilization_brake(utilization)
        
        if utilization_mult <= 0:
            return self._no_trade_result("utilization_stop", f"Utilization {utilization:.2%} >= hard stop")
        
        # =================================================================
        # STEP 5: Edge-Retention Liquidity Cap
        # =================================================================
        liquidity_cap = self._calculate_liquidity_cap(edge, ask_price, order_book_asks)
        
        # =================================================================
        # STEP 6: Time/Duration Penalty
        # =================================================================
        time_penalty = self._calculate_time_penalty(days_to_expiry)
        
        # =================================================================
        # STEP 7: Oracle/Ambiguity Risk
        # =================================================================
        oracle_mult = classification['final_multiplier']
        
        # =================================================================
        # STEP 8: Correlation Dampener
        # =================================================================
        correlation_mult, n_correlated = self._calculate_correlation_dampener(
            market_category, market_tags or [], open_positions
        )
        
        # =================================================================
        # STEP 9: Calculate Adjusted Size
        # =================================================================
        kelly_adjusted = kelly_base * utilization_mult * time_penalty * oracle_mult * correlation_mult
        logger.info(f"[SIZER ADJ] kelly_base={kelly_base:.2f} × util={utilization_mult:.3f} × time={time_penalty:.3f} × oracle={oracle_mult:.3f} × corr={correlation_mult:.3f} = {kelly_adjusted:.2f}")
        
        # =================================================================
        # STEP 10: Apply Liquidity Cap
        # =================================================================
        size_before_sector = min(kelly_adjusted, liquidity_cap)
        
        # =================================================================
        # STEP 11: Apply Sector Cap (uses sizing_base, not equity)
        # =================================================================
        sector_cap = self._calculate_sector_cap(sizing_base, market_category, sector_exposure)
        size_after_sector = min(size_before_sector, sector_cap)
        
        # =================================================================
        # STEP 11.5: Apply Event Cap (correlated markets)
        # =================================================================
        event_cap, current_event_exposure, related_positions = self._calculate_event_cap(
            sizing_base, market_question, open_positions
        )
        size_after_event = min(size_after_sector, event_cap)
        
        logger.info(f"[SIZER CAPS] adj={kelly_adjusted:.2f}, liq_cap={liquidity_cap:.2f}, sector_cap={sector_cap:.2f}, event_cap={event_cap:.2f} (related:{related_positions}), after_event={size_after_event:.2f}")
        
        # =================================================================
        # STEP 12: Apply Hard Limits (uses sizing_base, not equity)
        # =================================================================
        # Max single position from user config (single source of truth)
        max_single = sizing_base * max_position_size_pct
        final_size = min(size_after_event, max_single)
        
        logger.debug(f"[SIZER DEBUG] kelly_base={kelly_base:.2f}, util_mult={utilization_mult:.4f}, time_pen={time_penalty:.4f}, oracle={oracle_mult:.4f}, final={final_size:.2f}")
        
        # Min bet floor
        if final_size < self.config['min_bet_floor']:
            logger.info(f"[SIZER] Below min: kelly_base={kelly_base:.2f} × util={utilization_mult:.4f} × time={time_penalty:.4f} × oracle={oracle_mult:.4f} = {kelly_adjusted:.2f}, final={final_size:.2f}")
            return self._no_trade_result(
                "below_min_bet",
                f"Final size ${final_size:.2f} < min ${self.config['min_bet_floor']}"
            )
        
        # Round to 2 decimals
        final_size = round(final_size, 2)
        
        # =================================================================
        # BUILD RESULT
        # =================================================================
        return {
            'position_size': final_size,
            'should_trade': True,
            'breakdown': {
                # Input parameters
                'model_probability': model_probability,
                'ask_price': ask_price,
                'effective_price': round(effective_price, 4),
                'edge': round(edge, 4),
                'edge_pct': round(edge * 100, 2),
                
                # Kelly calculation
                'kelly_fraction': round(kelly_fraction, 4),
                'kelly_base': round(kelly_base, 2),
                
                # Multipliers
                'utilization': round(utilization, 4),
                'utilization_mult': round(utilization_mult, 4),
                'time_penalty': round(time_penalty, 4),
                'oracle_mult': round(oracle_mult, 4),
                'correlation_mult': round(correlation_mult, 4),
                'n_correlated_positions': n_correlated,
                
                # Caps
                'liquidity_cap': round(liquidity_cap, 2),
                'sector_cap': round(sector_cap, 2),
                'event_cap': round(event_cap, 2),
                'event_exposure': round(current_event_exposure, 2),
                'related_positions': related_positions,
                'max_single_position': round(max_single, 2),
                
                # Intermediate values
                'kelly_adjusted': round(kelly_adjusted, 2),
                'size_before_sector': round(size_before_sector, 2),
                'size_after_sector': round(size_after_sector, 2),
                'size_after_event': round(size_after_event, 2),
                
                # Classification
                'category': market_category,
                'category_reasoning': classification['reasoning'],
                'new_market_penalty_applied': classification['new_market_penalty'] < 1.0,
                
                # Final
                'final_size': final_size,
                
                # Portfolio state (show both for transparency)
                'equity': round(equity, 2),
                'sizing_base': round(sizing_base, 2),  # Max deployable capital used for sizing
                'deployed': round(deployed_capital, 2),
                'days_to_expiry': days_to_expiry,
            }
        }
    
    # =========================================================================
    # COMPONENT CALCULATIONS
    # =========================================================================
    
    def _calculate_effective_price(self, ask_price: float) -> float:
        """
        Calculate effective entry price including fees.
        
        Effective Price = Ask + (Ask × Fee%)
        
        This is critical for Kelly - if Mid is 0.40 but Ask is 0.42 with 2% fee,
        your break-even is 0.44, not 0.40.
        """
        fee_pct = self.config['polymarket_fee_pct']
        return ask_price + (ask_price * fee_pct)
    
    def _calculate_binary_kelly(self, edge: float, effective_price: float) -> float:
        """
        Binary Kelly Criterion for prediction markets.
        
        For binary (0/1) outcomes:
        Kelly = edge / (1 - effective_price)
        
        Where edge = model_probability - effective_price
        
        This replaces the standard Kelly formula which assumes continuous returns.
        """
        if effective_price >= 1.0:
            return 0.0
        
        kelly = edge / (1 - effective_price)
        
        # Clamp to reasonable range
        return max(0.0, min(kelly, 1.0))
    
    def _calculate_utilization_brake(self, utilization: float) -> float:
        """
        Calculate utilization brake multiplier.
        
        Formula: (1 - utilization)^1.5
        
        This convex curve:
        - 0% utilization → 1.00x (full throttle)
        - 20% utilization → 0.71x (still aggressive)
        - 50% utilization → 0.35x (drastic cut)
        - 80% utilization → 0.09x (sniper mode)
        - 95% utilization → 0.00x (hard stop)
        
        The power function (1.5) ensures we don't run out of cash but also
        don't sit idle early in the session.
        """
        hard_stop = self.config['utilization_hard_stop']
        exponent = self.config['utilization_exponent']
        
        if utilization >= hard_stop:
            return 0.0
        
        return (1 - utilization) ** exponent
    
    def _calculate_liquidity_cap(
        self, 
        edge: float, 
        ask_price: float, 
        order_book_asks: List[Dict]
    ) -> float:
        """
        Calculate Edge-Retention Liquidity Cap.
        
        Algorithm:
        1. Calculate max slippage we'll tolerate (20% of edge)
        2. Calculate max price we'll buy at
        3. Sum all asks up to that price
        
        NOTE: In practice, Polymarket's order book structure may not provide
        enough liquidity data at the current price level. When this happens,
        we use a generous default to avoid blocking good trades.
        """
        # Default: 10% of equity (will be further capped by other limits)
        DEFAULT_LIQUIDITY_CAP = 10000.0  # $10K - generous default
        
        if not order_book_asks or edge <= 0:
            return DEFAULT_LIQUIDITY_CAP
        
        retention_pct = self.config['edge_retention_pct']
        max_slippage = edge * retention_pct
        max_fill_price = ask_price + max_slippage
        
        # Walk the order book
        liquidity_cap = 0.0
        for order in order_book_asks:
            order_price = float(order.get('price', 0))
            order_size = float(order.get('size', 0))
            
            if order_price <= max_fill_price:
                liquidity_cap += order_size
            else:
                break  # Order book is sorted, stop when price exceeds max
        
        # If we found no liquidity at acceptable prices, use the default
        # This happens when the order book doesn't include the current best ask
        if liquidity_cap < 1.0:
            return DEFAULT_LIQUIDITY_CAP
        
        return max(liquidity_cap, 0.0)
    
    def _calculate_time_penalty(self, days_to_expiry: Optional[float]) -> float:
        """
        Calculate time/duration penalty for long-dated bets.
        
        Formula: max(floor, 1.0 - (days / max_days) * 0.5)
        
        Examples:
        - 7 days → 0.96x (almost full)
        - 30 days → 0.83x
        - 60 days → 0.67x
        - 90 days → 0.50x (floor)
        
        Capital lock-up has opportunity cost - penalize accordingly.
        """
        if days_to_expiry is None:
            return 0.8  # Unknown expiry - conservative
        
        if days_to_expiry <= 0:
            return 0.0  # Expired market
        
        max_days = self.config['time_penalty_max_days']
        floor = self.config['time_penalty_floor']
        
        penalty = 1.0 - (days_to_expiry / max_days) * 0.5
        return max(floor, penalty)
    
    def _calculate_correlation_dampener(
        self,
        category: str,
        tags: List[str],
        open_positions: List[Dict]
    ) -> Tuple[float, int]:
        """
        Calculate correlation dampener for overlapping positions.
        
        If you have 5 bets on "Republicans win Senate/House/Presidency",
        you don't have 5 diversified bets - you have 1 giant bet.
        
        Formula: 1 / (1 + N_correlated)
        
        Returns: (multiplier, n_correlated)
        """
        if not open_positions:
            return 1.0, 0
        
        n_correlated = 0
        tags_lower = [t.lower() for t in tags]
        
        for pos in open_positions:
            pos_category = pos.get('category', pos.get('asset_class', ''))
            pos_tags = pos.get('tags', [])
            pos_tags_lower = [t.lower() for t in pos_tags]
            
            # Check category overlap
            if pos_category and pos_category.lower() == category.lower():
                n_correlated += 1
                continue
            
            # Check tag overlap
            if tags_lower and pos_tags_lower:
                overlap = set(tags_lower) & set(pos_tags_lower)
                if overlap:
                    n_correlated += 1
        
        if n_correlated == 0:
            return 1.0, 0
        
        return 1.0 / (1 + n_correlated), n_correlated
    
    def _calculate_sector_cap(
        self,
        sizing_base: float,
        category: str,
        sector_exposure: Dict[str, float]
    ) -> float:
        """
        Calculate remaining sector cap.
        
        Args:
            sizing_base: Max deployable capital (from user config)
            category: Market category
            sector_exposure: Current exposure per category
        
        Returns remaining room in that sector.
        Each sector has a max allocation (e.g., 20% crypto) of the sizing_base.
        """
        sector_caps = self.config['sector_caps']
        cap_pct = sector_caps.get(category, sector_caps.get('unknown', 0.15))
        
        max_sector_usd = sizing_base * cap_pct
        current_exposure = sector_exposure.get(category, 0.0)
        
        remaining = max_sector_usd - current_exposure
        return max(0.0, remaining)
    
    def _calculate_event_cap(
        self,
        sizing_base: float,
        market_question: str,
        open_positions: List[Dict]
    ) -> tuple:
        """
        Calculate remaining event cap for correlated markets.
        
        Prevents over-betting on correlated outcomes (e.g., multiple candidates
        in the same election, multiple outcomes for the same Fed meeting).
        
        Args:
            sizing_base: Max deployable capital
            market_question: Question for current market
            open_positions: List of open position dicts with 'question' field
            
        Returns:
            Tuple of (remaining_cap, current_event_exposure, related_positions_count)
        """
        max_event_pct = self.event_config.get('max_event_exposure_pct', 0.15)
        similarity_threshold = self.event_config.get('similarity_threshold', 0.7)
        
        max_event_usd = sizing_base * max_event_pct
        
        # Find related positions by question similarity
        current_event_exposure = 0.0
        related_count = 0
        
        for pos in open_positions:
            pos_question = pos.get('question', pos.get('market_question', ''))
            if not pos_question:
                continue
                
            similarity = self._calculate_question_similarity(market_question, pos_question)
            if similarity >= similarity_threshold:
                current_event_exposure += pos.get('size', 0)
                related_count += 1
                
        remaining = max_event_usd - current_event_exposure
        return max(0.0, remaining), current_event_exposure, related_count
    
    def _calculate_question_similarity(self, q1: str, q2: str) -> float:
        """
        Calculate similarity between two market questions.
        
        Uses word overlap with normalization for common event detection.
        Questions about the same event (e.g., "Fed rate 25bps" vs "Fed rate 50bps")
        will have high similarity.
        
        Returns: Similarity score 0.0 to 1.0
        """
        if not q1 or not q2:
            return 0.0
            
        # Normalize and tokenize
        def tokenize(text: str) -> set:
            # Remove punctuation and lowercase
            import re
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            # Remove common words and numbers that don't identify the event
            stopwords = {'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'by', 'be', 'is', 'are', 'was', 'were', 'yes', 'no', 'before', 'after', 'reach', 'price'}
            tokens = set(text.split())
            return tokens - stopwords
        
        tokens1 = tokenize(q1)
        tokens2 = tokenize(q2)
        
        if not tokens1 or not tokens2:
            return 0.0
            
        # Jaccard similarity
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        
        if not union:
            return 0.0
            
        return len(intersection) / len(union)
    
    def _no_trade_result(self, reason: str, detail: str) -> Dict:
        """Return a no-trade result with explanation."""
        return {
            'position_size': 0.0,
            'should_trade': False,
            'breakdown': {
                'reject_reason': reason,
                'reject_detail': detail,
            }
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_polymarket_sizer: Optional[PolymarketPositionSizer] = None


def get_polymarket_position_sizer() -> PolymarketPositionSizer:
    """Get or create singleton sizer instance."""
    global _polymarket_sizer
    if _polymarket_sizer is None:
        _polymarket_sizer = PolymarketPositionSizer()
    return _polymarket_sizer


async def init_polymarket_position_sizer():
    """Initialize position sizer and load config."""
    sizer = get_polymarket_position_sizer()
    await sizer._async_load_config()
    return sizer
