"""
EMERGENT SIGNAL CACHE
=====================

Simple in-memory cache for Lane 5 news signals.
Shared between NewsInjector (writes) and PaperTrader (reads).

Features:
- TTL support (signals expire)
- Async-compatible
- Thread-safe with asyncio.Lock

For production, this could be replaced with Redis.
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with TTL support"""
    value: Any
    expires_at: datetime
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at


class EmergentSignalCache:
    """
    In-memory signal cache for Lane 5.
    
    This is the bridge between:
    - NewsInjector (writes signals after LLM + Bayes analysis)
    - PaperTrader (reads signals for execution)
    
    Key format: emergent_signal:{market_id}
    """
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'writes': 0,
            'expirations': 0
        }
        logger.info("[SIGNAL CACHE] Initialized")
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300  # Default 5 minutes
    ):
        """
        Set a value in the cache with TTL.
        
        Args:
            key: Cache key (e.g., "emergent_signal:market_123")
            value: The signal data dict
            ttl: Time-to-live in seconds
        """
        async with self._lock:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            self._stats['writes'] += 1
            
            logger.debug(f"[SIGNAL CACHE] SET {key} | TTL: {ttl}s")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Returns None if key doesn't exist or has expired.
        """
        async with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats['misses'] += 1
                return None
            
            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._stats['expirations'] += 1
                self._stats['misses'] += 1
                return None
            
            self._stats['hits'] += 1
            return entry.value
    
    async def delete(self, key: str) -> bool:
        """Delete a key from the cache"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def keys(self, pattern: str = "*") -> list:
        """Get all keys matching a pattern (simple prefix match)"""
        async with self._lock:
            if pattern == "*":
                return list(self._cache.keys())
            
            prefix = pattern.rstrip("*")
            return [k for k in self._cache.keys() if k.startswith(prefix)]
    
    async def cleanup_expired(self):
        """Remove all expired entries"""
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [
                k for k, v in self._cache.items()
                if v.expires_at < now
            ]
            for k in expired:
                del self._cache[k]
                self._stats['expirations'] += 1
            
            if expired:
                logger.debug(f"[SIGNAL CACHE] Cleaned up {len(expired)} expired entries")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            **self._stats,
            'size': len(self._cache),
            'hit_rate': self._stats['hits'] / max(self._stats['hits'] + self._stats['misses'], 1)
        }
    
    async def get_all_signals(self) -> Dict[str, Any]:
        """Get all non-expired emergent signals"""
        async with self._lock:
            result = {}
            now = datetime.now(timezone.utc)
            
            for key, entry in self._cache.items():
                if key.startswith("emergent_signal:") and not entry.is_expired():
                    market_id = key.replace("emergent_signal:", "")
                    result[market_id] = entry.value
            
            return result


# Singleton instance
_signal_cache: Optional[EmergentSignalCache] = None


def get_signal_cache() -> EmergentSignalCache:
    """Get or create the signal cache singleton"""
    global _signal_cache
    if _signal_cache is None:
        _signal_cache = EmergentSignalCache()
    return _signal_cache
