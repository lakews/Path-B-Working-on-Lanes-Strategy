"""
Async Signal Cache - Decouples Slow LLM Signals from Fast Execution Loop

CRITICAL PRINCIPLE: The execution loop must NEVER wait for an LLM call.

This module runs LLM sentiment analysis in a background thread/task and
updates a cache. The main execution loop reads from this cache instantly.

Cache Structure:
- TTL-based expiration (signals go stale)
- Per-market sentiment values
- Thread-safe access
- Async background updates
"""
import logging
import asyncio
import threading
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import time

logger = logging.getLogger(__name__)


@dataclass
class CachedSignal:
    """A cached signal value with metadata."""
    value: float
    confidence: float
    timestamp: datetime
    source: str
    ttl_seconds: int = 300  # 5 minute default TTL
    
    @property
    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds
    
    @property
    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()
    
    @property
    def freshness(self) -> float:
        """Returns 1.0 for fresh, 0.0 for expired."""
        age_ratio = self.age_seconds / self.ttl_seconds
        return max(0.0, 1.0 - age_ratio)


@dataclass
class MarketSignalCache:
    """Cache of all signals for a single market."""
    market_id: str
    llm_sentiment: Optional[CachedSignal] = None
    polymarket_sentiment: Optional[CachedSignal] = None
    github_sentiment: Optional[CachedSignal] = None
    correlation_sentiment: Optional[CachedSignal] = None
    bayesian_posterior: Optional[CachedSignal] = None
    
    def get_combined_sentiment(self) -> Tuple[float, float]:
        """
        Get combined sentiment from all cached sources.
        Returns (sentiment, confidence) tuple.
        
        Uses weighted average based on freshness and source confidence.
        """
        signals = []
        
        # Weights by source (same as signal_fusion.py)
        source_weights = {
            'llm': 0.35,
            'polymarket': 0.30,
            'correlation': 0.15,
            'github': 0.20
        }
        
        if self.llm_sentiment and not self.llm_sentiment.is_expired:
            signals.append((
                self.llm_sentiment.value,
                self.llm_sentiment.confidence * self.llm_sentiment.freshness,
                source_weights['llm']
            ))
        
        if self.polymarket_sentiment and not self.polymarket_sentiment.is_expired:
            signals.append((
                self.polymarket_sentiment.value,
                self.polymarket_sentiment.confidence * self.polymarket_sentiment.freshness,
                source_weights['polymarket']
            ))
        
        if self.correlation_sentiment and not self.correlation_sentiment.is_expired:
            signals.append((
                self.correlation_sentiment.value,
                self.correlation_sentiment.confidence * self.correlation_sentiment.freshness,
                source_weights['correlation']
            ))
        
        if self.github_sentiment and not self.github_sentiment.is_expired:
            signals.append((
                self.github_sentiment.value,
                self.github_sentiment.confidence * self.github_sentiment.freshness,
                source_weights['github']
            ))
        
        if not signals:
            return 0.5, 0.0  # Neutral with no confidence
        
        # Weighted average
        total_weight = sum(conf * weight for _, conf, weight in signals)
        if total_weight == 0:
            return 0.5, 0.0
        
        combined_sentiment = sum(val * conf * weight for val, conf, weight in signals) / total_weight
        combined_confidence = min(0.95, total_weight)
        
        return combined_sentiment, combined_confidence


class AsyncSignalCache:
    """
    Thread-safe async signal cache for decoupling slow signals from execution.
    
    Usage:
        cache = AsyncSignalCache()
        cache.start_background_updater(analyzer)
        
        # In execution loop (instant, never blocks):
        sentiment, confidence = cache.get_sentiment(market_id)
    """
    
    # Default TTLs by signal type
    DEFAULT_TTLS = {
        'llm': 600,           # 10 minutes - LLM calls are expensive
        'polymarket': 60,     # 1 minute - fast to update
        'github': 3600,       # 1 hour - slow changing
        'correlation': 120,   # 2 minutes
        'bayesian': 300       # 5 minutes
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the cache."""
        self.config = config or {}
        self._cache: Dict[str, MarketSignalCache] = {}
        self._lock = threading.RLock()
        self._update_task: Optional[asyncio.Task] = None
        self._running = False
        self._analyzer = None
        
        # Stats
        self.cache_hits = 0
        self.cache_misses = 0
        self.updates_completed = 0
        self.update_errors = 0
        
        # Markets to track
        self._tracked_markets: set = set()
        
        logger.info("AsyncSignalCache initialized")
    
    def _get_or_create_market_cache(self, market_id: str) -> MarketSignalCache:
        """Get or create cache entry for market."""
        with self._lock:
            if market_id not in self._cache:
                self._cache[market_id] = MarketSignalCache(market_id=market_id)
            return self._cache[market_id]
    
    def update_signal(
        self,
        market_id: str,
        signal_type: str,
        value: float,
        confidence: float,
        source: str = "unknown"
    ):
        """
        Update a cached signal (thread-safe).
        
        Args:
            market_id: Market identifier
            signal_type: One of 'llm', 'polymarket', 'github', 'correlation', 'bayesian'
            value: Signal value (0.0 to 1.0 for sentiment)
            confidence: Confidence score (0.0 to 1.0)
            source: Source identifier for debugging
        """
        ttl = self.DEFAULT_TTLS.get(signal_type, 300)
        
        signal = CachedSignal(
            value=value,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
            source=source,
            ttl_seconds=ttl
        )
        
        with self._lock:
            cache = self._get_or_create_market_cache(market_id)
            
            if signal_type == 'llm':
                cache.llm_sentiment = signal
            elif signal_type == 'polymarket':
                cache.polymarket_sentiment = signal
            elif signal_type == 'github':
                cache.github_sentiment = signal
            elif signal_type == 'correlation':
                cache.correlation_sentiment = signal
            elif signal_type == 'bayesian':
                cache.bayesian_posterior = signal
        
        logger.debug(f"Updated {signal_type} for {market_id}: {value:.3f} (conf={confidence:.2f})")
    
    def get_sentiment(
        self,
        market_id: str,
        require_llm: bool = False
    ) -> Tuple[float, float]:
        """
        Get cached sentiment for market (instant, never blocks).
        
        This is the main method called by the execution loop.
        
        Args:
            market_id: Market identifier
            require_llm: If True, returns (0.5, 0) if LLM signal is missing/stale
            
        Returns:
            Tuple of (sentiment, confidence)
        """
        with self._lock:
            if market_id not in self._cache:
                self.cache_misses += 1
                return 0.5, 0.0
            
            cache = self._cache[market_id]
            
            if require_llm:
                if cache.llm_sentiment is None or cache.llm_sentiment.is_expired:
                    self.cache_misses += 1
                    return 0.5, 0.0
            
            self.cache_hits += 1
            return cache.get_combined_sentiment()
    
    def get_signal(
        self,
        market_id: str,
        signal_type: str
    ) -> Tuple[float, float, float]:
        """
        Get specific cached signal.
        
        Returns:
            Tuple of (value, confidence, freshness)
        """
        with self._lock:
            if market_id not in self._cache:
                return 0.5, 0.0, 0.0
            
            cache = self._cache[market_id]
            signal = None
            
            if signal_type == 'llm':
                signal = cache.llm_sentiment
            elif signal_type == 'polymarket':
                signal = cache.polymarket_sentiment
            elif signal_type == 'github':
                signal = cache.github_sentiment
            elif signal_type == 'correlation':
                signal = cache.correlation_sentiment
            elif signal_type == 'bayesian':
                signal = cache.bayesian_posterior
            
            if signal is None or signal.is_expired:
                return 0.5, 0.0, 0.0
            
            return signal.value, signal.confidence, signal.freshness
    
    def track_market(self, market_id: str):
        """Add market to background update list."""
        self._tracked_markets.add(market_id)
    
    def untrack_market(self, market_id: str):
        """Remove market from background update list."""
        self._tracked_markets.discard(market_id)
    
    async def start_background_updater(
        self,
        sentiment_analyzer,
        update_interval_seconds: float = 60.0
    ):
        """
        Start background task to update LLM sentiments.
        
        This runs in a separate async task and updates the cache periodically.
        The execution loop never waits for this - it just reads from cache.
        """
        self._analyzer = sentiment_analyzer
        self._running = True
        
        async def _update_loop():
            while self._running:
                try:
                    # Update sentiment for all tracked markets
                    markets_to_update = list(self._tracked_markets)
                    
                    for market_id in markets_to_update:
                        if not self._running:
                            break
                        
                        try:
                            # Get market data from cache or skip
                            market_data = self._get_market_data(market_id)
                            if market_data:
                                sentiment, confidence = await self._analyzer.analyze_sentiment(market_data)
                                self.update_signal(
                                    market_id=market_id,
                                    signal_type='llm',
                                    value=sentiment,
                                    confidence=confidence,
                                    source='background_updater'
                                )
                                self.updates_completed += 1
                        except Exception as e:
                            logger.warning(f"Error updating sentiment for {market_id}: {e}")
                            self.update_errors += 1
                        
                        # Small delay between markets to avoid rate limits
                        await asyncio.sleep(0.5)
                    
                    # Wait for next update cycle
                    await asyncio.sleep(update_interval_seconds)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Background updater error: {e}")
                    await asyncio.sleep(5)  # Brief pause on error
        
        self._update_task = asyncio.create_task(_update_loop())
        logger.info(f"Background signal updater started (interval={update_interval_seconds}s)")
    
    def _get_market_data(self, market_id: str) -> Optional[Dict]:
        """Get market data for sentiment analysis (placeholder - should be connected to data source)."""
        # This should be connected to your market data source
        # For now, return None to skip updates for markets without data
        return None
    
    async def stop_background_updater(self):
        """Stop the background update task."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Background signal updater stopped")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total_requests = self.cache_hits + self.cache_misses
            hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0
            
            return {
                'markets_cached': len(self._cache),
                'markets_tracked': len(self._tracked_markets),
                'cache_hits': self.cache_hits,
                'cache_misses': self.cache_misses,
                'hit_rate': hit_rate,
                'updates_completed': self.updates_completed,
                'update_errors': self.update_errors,
                'is_running': self._running
            }
    
    def clear_expired(self):
        """Remove expired entries from cache."""
        with self._lock:
            for market_id, cache in list(self._cache.items()):
                # Check if all signals are expired
                all_expired = True
                for signal in [
                    cache.llm_sentiment,
                    cache.polymarket_sentiment,
                    cache.github_sentiment,
                    cache.correlation_sentiment,
                    cache.bayesian_posterior
                ]:
                    if signal and not signal.is_expired:
                        all_expired = False
                        break
                
                if all_expired and market_id not in self._tracked_markets:
                    del self._cache[market_id]


# Global singleton instance
_signal_cache: Optional[AsyncSignalCache] = None


def get_signal_cache() -> AsyncSignalCache:
    """Get the global signal cache instance."""
    global _signal_cache
    if _signal_cache is None:
        _signal_cache = AsyncSignalCache()
    return _signal_cache
