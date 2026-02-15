"""
NEWS SNIPER - MONGODB-ONLY IMPLEMENTATION
==========================================

Lane 5: NEWS Lane with MongoDB Signal Integration

Reads PATH A signals from MongoDB (from DualPathNewsInjector)
instead of the legacy EmergentSignalCache.

Features:
1. ConvictionEnhancer - 5-factor conviction calculation
2. Kelly Tiering - Conviction-based position sizing
3. MongoDB Integration - Reads from signals collection
4. Whale Alignment - Checks if whales agree with signal direction
5. Source Credibility - Reuters/AP > Whale Alerts > Twitter
6. Time Decay - Fresher signals get more weight (NEW)

This module REPLACES the legacy news_sniper in paper_trader.py
"""

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


def calculate_time_decay(signal: Dict) -> float:
    """
    Calculate time decay factor for a signal based on its age.
    
    Fresher signals get weight closer to 1.0, older signals decay towards 0.5.
    Uses exponential decay: weight = 0.5 + 0.5 * exp(-age/half_life)
    
    Returns:
        float: Decay factor between 0.5 and 1.0
        - 1.0 = brand new signal (full weight)
        - 0.75 = signal at ~70% of TTL
        - 0.5 = signal at expiration (minimum weight)
    """
    try:
        now = datetime.now(timezone.utc)
        created_at = signal.get('created_at')
        expires_at = signal.get('expires_at')
        
        if not created_at or not expires_at:
            return 1.0  # No timing info, assume fresh
        
        # Handle string dates
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        
        # Ensure timezone aware
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        total_ttl = (expires_at - created_at).total_seconds()
        age = (now - created_at).total_seconds()
        
        if total_ttl <= 0:
            return 1.0
        
        # Calculate decay using exponential function
        # Half-life is 50% of TTL (signal loses half its extra weight at midpoint)
        half_life = total_ttl * 0.5
        
        # Decay from 1.0 to 0.5 (never goes below 0.5 - signal still has some value)
        decay = 0.5 + 0.5 * math.exp(-age / half_life)
        
        # Clamp between 0.5 and 1.0
        return max(0.5, min(1.0, decay))
        
    except Exception as e:
        logger.debug(f"[TIME DECAY] Error calculating decay: {e}")
        return 1.0  # Default to full weight on error


class NewsImpactLevel(Enum):
    """News impact classification"""
    EXTREME = "extreme"     # BF >= 10.0, Kelly 50%
    HIGH = "high"           # BF 6.0-10.0, Kelly 30%
    MODERATE = "moderate"   # BF 3.0-6.0, Kelly 15%
    LOW = "low"             # BF 1.0-3.0, Kelly 5%
    SKIP = "skip"           # BF < 1.0, Kelly 0%


class MarketRegime(Enum):
    """Market regime for conviction adjustment"""
    CRISIS = "crisis"       # High volatility, reduce conviction
    VOLATILE = "volatile"   # Above average volatility
    NORMAL = "normal"       # Baseline
    QUIET = "quiet"         # Low volatility, increase conviction


class ConvictionEnhancer:
    """
    5-Factor Conviction Enhancement System
    
    Calculates conviction score from:
    1. Source Credibility (Reuters=1.25, Whale=1.35, Twitter=0.9)
    2. Liquidity Multiplier (higher liquidity = higher conviction)
    3. Whale Alignment (whales agree with direction = boost)
    4. Market Regime (crisis = reduce, quiet = boost)
    5. Bayes Factor (from PATH A signal)
    
    Final conviction = BF × Source × Liquidity × Whale × Regime
    """
    
    # Source credibility multipliers
    SOURCE_MULTIPLIERS = {
        # Tier 1: Highly credible financial sources
        'reuters': 1.25,
        'bloomberg': 1.25,
        'ap': 1.20,
        'wsj': 1.20,
        'ft': 1.20,
        
        # Tier 2: Crypto-specific credible sources
        'coindesk': 1.15,
        'theblock': 1.15,
        'decrypt': 1.10,
        
        # Tier 3: Whale alerts (on-chain data)
        'whale_alert': 1.35,
        'whale': 1.35,
        'onchain': 1.30,
        
        # Tier 4: Social media (lower trust)
        'twitter': 0.90,
        'x': 0.90,
        'reddit': 0.85,
        'telegram': 0.80,
        
        # Default
        'unknown': 1.0
    }
    
    # Regime multipliers
    REGIME_MULTIPLIERS = {
        MarketRegime.CRISIS: 0.7,     # Reduce conviction in crisis
        MarketRegime.VOLATILE: 0.9,   # Slightly reduce
        MarketRegime.NORMAL: 1.0,     # Baseline
        MarketRegime.QUIET: 1.1       # Boost in quiet markets
    }
    
    def __init__(self, whale_tracker=None, market_service=None):
        self.whale_tracker = whale_tracker
        self.market_service = market_service
    
    async def calculate_conviction(
        self,
        signal: Dict,
        market_data: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate enhanced conviction score using 5 factors.
        
        Args:
            signal: PATH A signal from MongoDB with bayes_factor, direction, etc.
            market_data: Market data with price, volume, liquidity
            
        Returns:
            Tuple of (conviction_score, breakdown_dict)
        """
        try:
            # Factor 1: Bayes Factor (base)
            bayes_factor = signal.get('bayes_factor', 1.0)
            
            # Factor 2: Source Credibility
            source = signal.get('news_source', 'unknown').lower()
            source_mult = self._get_source_multiplier(source)
            
            # Factor 3: Liquidity Multiplier
            liquidity_mult = self._calculate_liquidity_multiplier(market_data)
            
            # Factor 4: Whale Alignment
            whale_mult = await self._calculate_whale_alignment(
                market_data, 
                signal.get('direction', 'YES')
            )
            
            # Factor 5: Market Regime
            regime = self._detect_market_regime(market_data)
            regime_mult = self.REGIME_MULTIPLIERS.get(regime, 1.0)
            
            # Calculate final conviction
            conviction = bayes_factor * source_mult * liquidity_mult * whale_mult * regime_mult
            
            # Clamp to reasonable range [0, 20]
            conviction = max(0.0, min(20.0, conviction))
            
            breakdown = {
                'bayes_factor': bayes_factor,
                'source_multiplier': source_mult,
                'source': source,
                'liquidity_multiplier': liquidity_mult,
                'whale_multiplier': whale_mult,
                'regime_multiplier': regime_mult,
                'regime': regime.value,
                'final_conviction': conviction
            }
            
            logger.debug(
                f"[CONVICTION] BF={bayes_factor:.2f} × Source={source_mult:.2f} × "
                f"Liq={liquidity_mult:.2f} × Whale={whale_mult:.2f} × "
                f"Regime={regime_mult:.2f} = {conviction:.2f}"
            )
            
            return conviction, breakdown
            
        except Exception as e:
            logger.error(f"[CONVICTION] Error calculating conviction: {e}")
            # Fallback to raw Bayes Factor
            return signal.get('bayes_factor', 1.0), {'error': str(e)}
    
    def _get_source_multiplier(self, source: str) -> float:
        """Get credibility multiplier for news source"""
        source_lower = source.lower()
        
        # Check for exact match
        if source_lower in self.SOURCE_MULTIPLIERS:
            return self.SOURCE_MULTIPLIERS[source_lower]
        
        # Check for partial match
        for key, mult in self.SOURCE_MULTIPLIERS.items():
            if key in source_lower:
                return mult
        
        return self.SOURCE_MULTIPLIERS['unknown']
    
    def _calculate_liquidity_multiplier(self, market_data: Dict) -> float:
        """
        Calculate liquidity multiplier.
        Higher liquidity = more confidence in signal execution.
        """
        liquidity = float(market_data.get('liquidity', 0) or 0)
        volume_24h = float(market_data.get('volume_24h', market_data.get('volume', 0)) or 0)
        
        # Combine liquidity and volume
        combined = liquidity + volume_24h
        
        # Tiered multiplier
        if combined >= 100000:  # $100K+
            return 1.20
        elif combined >= 50000:  # $50K+
            return 1.10
        elif combined >= 10000:  # $10K+
            return 1.0
        elif combined >= 5000:   # $5K+
            return 0.90
        else:
            return 0.75  # Low liquidity penalty
    
    async def _calculate_whale_alignment(
        self, 
        market_data: Dict, 
        signal_direction: str
    ) -> float:
        """
        Check if whale activity aligns with signal direction.
        Alignment boosts conviction, disagreement reduces it.
        """
        if not self.whale_tracker:
            return 1.0  # Neutral if no whale data
        
        try:
            whale_data = await self.whale_tracker.detect_whale_activity(market_data)
            
            if not whale_data:
                return 1.0
            
            whale_direction = whale_data.get('whale_direction', 'neutral')
            whale_score = whale_data.get('whale_activity_score', 0)
            
            # No significant whale activity
            if whale_score < 0.3:
                return 1.0
            
            # Check alignment
            signal_is_bullish = signal_direction.upper() == 'YES'
            whale_is_bullish = whale_direction == 'bullish'
            whale_is_bearish = whale_direction == 'bearish'
            
            if signal_is_bullish and whale_is_bullish:
                return 1.0 + (whale_score * 0.35)  # Up to 1.35x boost
            elif not signal_is_bullish and whale_is_bearish:
                return 1.0 + (whale_score * 0.35)  # Up to 1.35x boost
            elif whale_direction == 'neutral':
                return 1.0  # Neutral
            else:
                # Disagreement - reduce conviction
                return 1.0 - (whale_score * 0.25)  # Down to 0.75x
                
        except Exception as e:
            logger.debug(f"[CONVICTION] Whale alignment error: {e}")
            return 1.0
    
    def _detect_market_regime(self, market_data: Dict) -> MarketRegime:
        """Detect current market regime from volatility and price movement"""
        volatility = float(market_data.get('volatility', 0.5) or 0.5)
        price_change = abs(float(market_data.get('price_change_1h_pct', 0) or 0))
        
        # Crisis detection
        if price_change > 20 or volatility > 2.0:
            return MarketRegime.CRISIS
        
        # Volatile
        if volatility > 1.5 or price_change > 5:
            return MarketRegime.VOLATILE
        
        # Quiet
        if volatility < 0.3 and price_change < 1:
            return MarketRegime.QUIET
        
        return MarketRegime.NORMAL


class NewsSniper:
    """
    NEWS Lane Implementation with MongoDB Integration
    
    Reads PATH A signals from MongoDB signals collection
    and executes trades based on conviction-enhanced sizing.
    
    This REPLACES the legacy _check_news_signal and _execute_news_sniper
    methods in paper_trader.py.
    """
    
    # Kelly tiers based on conviction score
    KELLY_TIERS = [
        (10.0, 0.50),   # Conviction >= 10 → 50% Kelly
        (8.0, 0.40),    # Conviction 8-10 → 40% Kelly
        (6.0, 0.30),    # Conviction 6-8 → 30% Kelly
        (3.0, 0.15),    # Conviction 3-6 → 15% Kelly
        (1.0, 0.05),    # Conviction 1-3 → 5% Kelly
        (0.0, 0.00),    # Conviction < 1 → Skip
    ]
    
    def __init__(
        self,
        db,
        paper_trader,
        whale_tracker=None,
        market_service=None,
        capital_allocation_pct: float = 0.03  # 3% of capital to NEWS lane
    ):
        self.db = db
        self.paper_trader = paper_trader
        self.capital_allocation_pct = capital_allocation_pct
        
        # Initialize ConvictionEnhancer
        self.conviction_enhancer = ConvictionEnhancer(
            whale_tracker=whale_tracker,
            market_service=market_service
        )
        
        # State
        self._running = False
        self._last_cycle_time = None
        
        # Statistics
        self.stats = {
            'cycles': 0,
            'signals_processed': 0,
            'trades_executed': 0,
            'trades_skipped_low_conviction': 0,
            'trades_skipped_no_edge': 0,
            'trades_skipped_position_exists': 0,
            'mongodb_reads': 0,
            'mongodb_errors': 0,
            'total_conviction_sum': 0.0,
            'errors': 0
        }
        
        logger.info("[NEWS SNIPER] Initialized with MongoDB integration")
        logger.info("  ├─ Signal Source: MongoDB signals collection (PATH A)")
        logger.info("  ├─ Conviction: 5-factor enhancement")
        logger.info("  └─ Kelly: Tiered (5%-50% based on conviction)")
    
    async def start_news_loop(self):
        """
        Main NEWS lane background loop.
        Runs every 2 seconds to check for fresh signals.
        """
        logger.info("[NEWS SNIPER] Starting MongoDB-integrated news loop...")
        self._running = True
        
        while self._running:
            try:
                cycle_start = datetime.now(timezone.utc)
                
                # Get active markets with fresh signals
                await self._process_news_signals()
                
                self.stats['cycles'] += 1
                self._last_cycle_time = (datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000
                
                # 2-second cycle
                await asyncio.sleep(2.0)
                
            except asyncio.CancelledError:
                logger.info("[NEWS SNIPER] Loop cancelled")
                break
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"[NEWS SNIPER] Loop error: {e}", exc_info=True)
                await asyncio.sleep(2.0)
        
        logger.info("[NEWS SNIPER] Loop stopped")
    
    async def stop(self):
        """Stop the NEWS sniper loop"""
        self._running = False
        logger.info("[NEWS SNIPER] Stop requested")
    
    async def _process_news_signals(self):
        """Process all fresh signals from MongoDB"""
        try:
            # Read fresh signals from MongoDB
            signals = await self._read_fresh_signals()
            
            if not signals:
                logger.debug("[NEWS SNIPER] No fresh PATH A signals found")
                return
            
            logger.info(f"[NEWS SNIPER] Found {len(signals)} fresh PATH A signals to process")
            self.stats['signals_processed'] += len(signals)
            
            for signal in signals:
                try:
                    await self._process_single_signal(signal)
                except Exception as e:
                    logger.warning(f"[NEWS SNIPER] Signal processing error: {e}")
                    continue
                    
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[NEWS SNIPER] Process signals error: {e}")
    
    async def _read_fresh_signals(self) -> List[Dict]:
        """
        Read PATH A signals from MongoDB that haven't expired.
        
        Returns fresh signals sorted by bayes_factor (highest first).
        """
        try:
            if self.db is None:
                return []
            
            cursor = self.db.signals.find(
                {
                    'type': 'path_a',
                    'expires_at': {'$gt': datetime.now(timezone.utc)}
                },
                {'_id': 0}
            ).sort('bayes_factor', -1).limit(50)  # Top 50 by BF
            
            signals = await cursor.to_list(length=50)
            self.stats['mongodb_reads'] += 1
            
            return signals
            
        except Exception as e:
            self.stats['mongodb_errors'] += 1
            logger.error(f"[NEWS SNIPER] MongoDB read error: {e}")
            return []
    
    async def _read_path_a_signal_for_market(self, market_id: str) -> Optional[Dict]:
        """
        Read PATH A signal for a specific market.
        
        Used when checking if a specific market has a fresh signal.
        """
        try:
            if self.db is None:
                return None
            
            signal = await self.db.signals.find_one(
                {
                    'market_id': market_id,
                    'type': 'path_a',
                    'expires_at': {'$gt': datetime.now(timezone.utc)}
                },
                {'_id': 0},
                sort=[('timestamp', -1)]
            )
            
            return signal
            
        except Exception as e:
            logger.debug(f"[NEWS SNIPER] Signal read error: {e}")
            return None
    
    async def _process_single_signal(self, signal: Dict):
        """Process a single PATH A signal"""
        try:
            market_id = signal.get('market_id', '')
            if not market_id:
                logger.debug("[NEWS SNIPER] Signal has no market_id, skipping")
                return
            
            # Check if we already have a position
            if self.paper_trader and market_id in getattr(self.paper_trader, 'paper_positions', {}):
                self.stats['trades_skipped_position_exists'] += 1
                logger.debug(f"[NEWS SNIPER] Position exists for {market_id[:16]}...")
                return
            
            # Get market data
            market_data = await self._get_market_data(market_id)
            if not market_data:
                logger.info(f"[NEWS SNIPER] No market data for {market_id[:16]}... (not in cache)")
                return
            
            # Calculate enhanced conviction
            conviction, breakdown = await self.conviction_enhancer.calculate_conviction(
                signal, market_data
            )
            
            self.stats['total_conviction_sum'] += conviction
            
            # Get Kelly fraction based on conviction tier
            kelly_fraction = self._conviction_to_kelly(conviction)
            
            logger.info(
                f"[NEWS SNIPER] Processing {market_id[:16]}... | "
                f"BF={signal.get('bayes_factor', 0):.1f}, Conv={conviction:.2f}, Kelly={kelly_fraction:.0%}"
            )
            
            if kelly_fraction == 0:
                self.stats['trades_skipped_low_conviction'] += 1
                logger.debug(
                    f"[NEWS SNIPER] Skipping {market_id[:16]}... | "
                    f"Conviction {conviction:.2f} too low"
                )
                return
            
            # Check edge
            direction = signal.get('direction', 'YES')
            # Support both 'yes_price' and 'price' field names
            yes_price = float(market_data.get('yes_price') or market_data.get('price', 0.5) or 0.5)
            no_price = 1 - yes_price
            confidence = signal.get('confidence', 0.5)
            
            # Edge = our confidence in direction - market price for that direction
            # confidence is the confidence IN THE SIGNAL'S DIRECTION
            if direction == 'YES':
                edge = confidence - yes_price
            else:
                edge = confidence - no_price  # confidence in NO - NO price
            
            logger.info(
                f"[NEWS SNIPER] Edge check {market_id[:16]}... | "
                f"Dir={direction}, Conf={confidence:.0%}, Price={yes_price if direction == 'YES' else no_price:.1%}, Edge={edge:.2%}"
            )
            
            if edge < 0.02:  # 2% minimum edge
                self.stats['trades_skipped_no_edge'] += 1
                logger.debug(
                    f"[NEWS SNIPER] Skipping {market_id[:16]}... | "
                    f"Edge {edge:.2%} < 2%"
                )
                return
            
            # Calculate position size
            position_size = self._calculate_position_size(
                kelly_fraction=kelly_fraction,
                confidence=confidence,
                conviction=conviction
            )
            
            if position_size < 5.0:  # $5 minimum
                return
            
            # Execute trade
            await self._execute_trade(
                market_id=market_id,
                market_data=market_data,
                signal=signal,
                direction=direction,
                position_size=position_size,
                conviction=conviction,
                breakdown=breakdown
            )
            # Note: stats['trades_executed'] is incremented in _execute_trade
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[NEWS SNIPER] Process signal error: {e}")
    
    def _conviction_to_kelly(self, conviction: float) -> float:
        """
        Convert conviction score to Kelly fraction using tiers.
        
        Tiers:
        - Conviction >= 10 → 50% Kelly
        - Conviction 8-10 → 40% Kelly
        - Conviction 6-8 → 30% Kelly
        - Conviction 3-6 → 15% Kelly
        - Conviction 1-3 → 5% Kelly
        - Conviction < 1 → 0% (skip)
        """
        for threshold, kelly in self.KELLY_TIERS:
            if conviction >= threshold:
                return kelly
        return 0.0
    
    def _calculate_position_size(
        self,
        kelly_fraction: float,
        confidence: float,
        conviction: float
    ) -> float:
        """Calculate position size respecting all constraints"""
        try:
            if not self.paper_trader:
                return 0.0
            
            # Get available capital
            available = getattr(self.paper_trader, 'current_capital', 0)
            if available <= 0:
                return 0.0
            
            # NEWS lane allocation (3%)
            news_capital = available * self.capital_allocation_pct
            
            # Apply Kelly sizing
            base_size = news_capital * kelly_fraction * confidence
            
            # Cap at 3% of total capital (from risk config)
            initial_capital = getattr(self.paper_trader, 'INITIAL_CAPITAL', 10000)
            max_position = initial_capital * 0.03
            
            position_size = min(base_size, max_position)
            
            return round(position_size, 2)
            
        except Exception as e:
            logger.debug(f"[NEWS SNIPER] Position size error: {e}")
            return 0.0
    
    async def _execute_trade(
        self,
        market_id: str,
        market_data: Dict,
        signal: Dict,
        direction: str,
        position_size: float,
        conviction: float,
        breakdown: Dict
    ):
        """Execute the NEWS sniper trade via paper_trader"""
        try:
            if not self.paper_trader:
                return
            
            logger.info(
                f"[NEWS SNIPER] EXECUTING | {market_id[:16]}... | "
                f"Dir: {direction} | Size: ${position_size:.2f} | "
                f"Conviction: {conviction:.2f} | "
                f"BF: {signal.get('bayes_factor', 0):.1f} | "
                f"Source: {signal.get('news_source', 'unknown')}"
            )
            
            # Use paper_trader's _execute_paper_entry method (the correct one)
            if hasattr(self.paper_trader, '_execute_paper_entry'):
                await self.paper_trader._execute_paper_entry(
                    market_id=market_id,
                    market_data=market_data,
                    side=direction,
                    size=position_size,
                    strategy='news_sniper',
                    signals={
                        'news_sniper': True,
                        'conviction': conviction,
                        'bayes_factor': signal.get('bayes_factor', 0),
                        'confidence': signal.get('confidence', 0.5),
                        'source': signal.get('news_source', 'unknown'),
                        'headline': signal.get('headline', '')[:100]
                    },
                    rl_action='NEWS_ENTRY',
                    rl_confidence=signal.get('confidence', 0.5),
                    sizing_breakdown={
                        'news_sniper_trade': True,
                        'conviction': conviction,
                        'bayes_factor': signal.get('bayes_factor', 0),
                        **breakdown
                    }
                )
                self.stats['trades_executed'] += 1
            else:
                logger.error("[NEWS SNIPER] paper_trader missing _execute_paper_entry method!")
                return
            
            logger.info(
                f"[NEWS SNIPER] ✅ TRADE COMPLETE | {market_id[:16]}... | "
                f"{direction} ${position_size:.2f}"
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[NEWS SNIPER] Execute error: {e}")
    
    async def _get_market_data(self, market_id: str) -> Optional[Dict]:
        """Get market data for a market ID"""
        try:
            # Try to get from paper_trader's market service (try both attribute names)
            if self.paper_trader:
                svc = getattr(self.paper_trader, 'market_data_service', None) or \
                      getattr(self.paper_trader, 'market_data_svc', None)
                if svc and hasattr(svc, 'get_market'):
                    result = await svc.get_market(market_id)
                    if result:
                        logger.debug(f"[NEWS SNIPER] Got market from service: {market_id[:16]}...")
                        return result
            
            # Fallback: check if we have it in polymarket_cache
            if self.db is not None:
                cached = await self.db.polymarket_cache.find_one(
                    {'market_id': market_id},
                    {'_id': 0}
                )
                if cached:
                    logger.debug(f"[NEWS SNIPER] Found in cache: {cached.get('question', '')[:30]}...")
                    # Normalize field names for compatibility
                    if 'price' in cached and 'yes_price' not in cached:
                        cached['yes_price'] = cached['price']
                    return cached
                else:
                    logger.debug(f"[NEWS SNIPER] Not found in polymarket_cache: {market_id[:16]}...")
            else:
                logger.warning(f"[NEWS SNIPER] self.db is None!")
            
            return None
            
        except Exception as e:
            logger.error(f"[NEWS SNIPER] Get market data error: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """Return NEWS sniper statistics"""
        avg_conviction = (
            self.stats['total_conviction_sum'] / max(1, self.stats['signals_processed'])
        )
        
        return {
            **self.stats,
            'running': self._running,
            'last_cycle_time_ms': self._last_cycle_time,
            'avg_conviction': round(avg_conviction, 2)
        }


# Singleton instance
_news_sniper_instance: Optional[NewsSniper] = None


def get_news_sniper() -> Optional[NewsSniper]:
    """Get the singleton NEWS sniper instance"""
    return _news_sniper_instance


async def init_news_sniper(
    db,
    paper_trader,
    whale_tracker=None,
    market_service=None
) -> NewsSniper:
    """Initialize and return the NEWS Sniper"""
    global _news_sniper_instance
    
    _news_sniper_instance = NewsSniper(
        db=db,
        paper_trader=paper_trader,
        whale_tracker=whale_tracker,
        market_service=market_service
    )
    
    return _news_sniper_instance
