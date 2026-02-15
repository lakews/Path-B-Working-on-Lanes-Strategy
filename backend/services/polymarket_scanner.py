"""
POLYMARKET SCANNER SERVICE
===========================

Markets-First Architecture - Phase 1

Continuously scans and caches ALL viable Polymarkets for:
- WebSocket PRIMARY data source (<50ms latency)
- REST API FALLBACK if WebSocket fails
- Market data quality scoring (detects stale WS data)
- Pre-generates embeddings for semantic search
- Caches in MongoDB (persistent) + memory (fast)
- Tracks 400-900 markets continuously

CRITICAL: This service runs PARALLEL to existing 5-lane system.
Zero breaking changes to existing trading loops.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)


class WebSocketDataQualityScorer:
    """
    Score WebSocket market data freshness (Optimization 1A).
    Detects stale data if WebSocket connection is stuck.
    """
    
    def __init__(self, stale_threshold_ms: int = 5000):
        self.stale_threshold_ms = stale_threshold_ms
        self.market_update_times: Dict[str, float] = {}
        self.market_update_frequency: Dict[str, float] = {}
    
    def record_market_update(self, market_id: str, update_time: float):
        """Track when each market was last updated"""
        if market_id in self.market_update_times:
            time_delta = update_time - self.market_update_times[market_id]
            
            if market_id not in self.market_update_frequency:
                self.market_update_frequency[market_id] = time_delta
            else:
                # Exponential moving average
                self.market_update_frequency[market_id] = (
                    0.9 * self.market_update_frequency[market_id] + 0.1 * time_delta
                )
        
        self.market_update_times[market_id] = update_time
    
    def score_market_freshness(self, market_id: str, current_time: float) -> Dict:
        """Score market data freshness"""
        if market_id not in self.market_update_times:
            return {
                'is_fresh': False,
                'freshness_score': 0,
                'age_ms': None,
                'status': 'UNKNOWN'
            }
        
        age_ms = (current_time - self.market_update_times[market_id]) * 1000
        
        if age_ms > self.stale_threshold_ms:
            score = max(0, 1 - (age_ms / (self.stale_threshold_ms * 3)))
            return {
                'is_fresh': False,
                'freshness_score': score,
                'age_ms': age_ms,
                'status': 'STALE'
            }
        else:
            score = 1 - (age_ms / self.stale_threshold_ms)
            return {
                'is_fresh': True,
                'freshness_score': score,
                'age_ms': age_ms,
                'status': 'FRESH'
            }


class SimpleEmbeddingModel:
    """
    Simple TF-IDF based embedding model for semantic search.
    
    For production, this could be replaced with:
    - sentence-transformers
    - OpenAI embeddings
    - Local embedding models
    
    This implementation provides reasonable semantic similarity
    without external dependencies.
    """
    
    def __init__(self):
        self.vocabulary: Dict[str, int] = {}
        self.idf_weights: Dict[str, float] = {}
        self.dimension = 512  # Fixed embedding dimension
        
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        import re
        # Lowercase and split on non-alphanumeric
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        return tokens
    
    def _hash_token(self, token: str) -> int:
        """Hash token to fixed dimension index"""
        return hash(token) % self.dimension
    
    async def embed(self, text: str) -> np.ndarray:
        """Generate embedding vector for text"""
        tokens = self._tokenize(text)
        
        if not tokens:
            return np.zeros(self.dimension, dtype=np.float32)
        
        # Create sparse TF vector then project to dense
        embedding = np.zeros(self.dimension, dtype=np.float32)
        
        # Count token frequencies
        token_counts: Dict[str, int] = {}
        for token in tokens:
            token_counts[token] = token_counts.get(token, 0) + 1
        
        # Build embedding using hashed indices
        total_tokens = len(tokens)
        for token, count in token_counts.items():
            tf = count / total_tokens  # Term frequency
            idx = self._hash_token(token)
            embedding[idx] += tf
        
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
    
    async def batch_embed(self, texts: List[str]) -> List[np.ndarray]:
        """Embed multiple texts"""
        return [await self.embed(text) for text in texts]


class PolymarketScanner:
    """
    Continuously scans and caches ALL viable Polymarkets.
    
    Features:
    - WebSocket PRIMARY data source (<50ms latency)
    - REST API FALLBACK if WebSocket fails
    - Market data quality scoring (detects stale WS data)
    - Pre-generates embeddings for semantic search
    - Caches in MongoDB (persistent) + memory (fast)
    - Tracks 400-900 markets continuously
    """
    
    def __init__(
        self,
        db: Any,  # MongoDB database
        websocket_market_service: Any = None,  # From realtime_market_service
        gamma_api_client: Any = None,  # Fallback REST
        embedding_model: Any = None
    ):
        self.db = db
        self.websocket_svc = websocket_market_service
        self.gamma_api = gamma_api_client
        self.embedding_model = embedding_model or SimpleEmbeddingModel()
        
        self.quality_scorer = WebSocketDataQualityScorer(stale_threshold_ms=5000)
        
        # In-memory caches (fast <1ms access)
        self.cached_markets: Dict[str, Dict] = {}
        self.cached_embeddings: Dict[str, np.ndarray] = {}
        self.last_updated: Optional[datetime] = None
        
        # Scanner task
        self._scan_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.stats = {
            'scan_count': 0,
            'ws_markets_fetched': 0,
            'ws_stale_skipped': 0,
            'rest_fallback_used': 0,
            'markets_cached': 0,
            'embeddings_generated': 0,
            'mongodb_writes': 0
        }
    
    async def start_continuous_scan(self):
        """Main background daemon - runs continuously"""
        logger.info("[SCANNER] Starting continuous scan daemon...")
        self._running = True
        
        # Initial scan
        await self._perform_scan()
        
        while self._running:
            try:
                await asyncio.sleep(5)  # Quick refresh every 5 seconds
                await self._perform_scan()
            except asyncio.CancelledError:
                logger.info("[SCANNER] Scan daemon cancelled")
                break
            except Exception as e:
                logger.error(f"[SCANNER] Critical error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("[SCANNER] Continuous scan daemon stopped")
    
    async def stop(self):
        """Stop the scanner"""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info("[SCANNER] Stopped")
    
    async def _perform_scan(self):
        """Single scan cycle with WebSocket-first + REST fallback"""
        try:
            self.stats['scan_count'] += 1
            
            # STEP 1: Try WebSocket PRIMARY
            all_markets = await self._fetch_from_websocket()
            
            # Fallback to REST if needed
            if not all_markets or len(all_markets) < 50:
                logger.warning(f"[SCANNER] WebSocket returned {len(all_markets) if all_markets else 0} markets. Falling back to REST...")
                self.stats['rest_fallback_used'] += 1
                all_markets = await self._fetch_from_rest_api()
            
            if not all_markets:
                logger.warning("[SCANNER] No markets fetched from either source")
                return
            
            self.stats['ws_markets_fetched'] += len(all_markets)
            
            # STEP 2: Score freshness and filter stale
            now = datetime.now(timezone.utc).timestamp()
            valid_markets = []
            
            for market in all_markets:
                market_id = market.get('id') or market.get('condition_id')
                if not market_id:
                    continue
                    
                quality = self.quality_scorer.score_market_freshness(market_id, now)
                
                # Record update for quality scoring
                self.quality_scorer.record_market_update(market_id, now)
                
                # Skip stale markets only if they're truly stale (quality scoring active)
                if quality['status'] == 'STALE' and quality['age_ms'] and quality['age_ms'] > 10000:
                    self.stats['ws_stale_skipped'] += 1
                    continue
                
                market['_data_quality'] = quality
                market['market_id'] = market_id  # Normalize ID field
                valid_markets.append(market)
            
            # STEP 3: Filter invalid markets
            valid_markets = self._filter_valid_markets(valid_markets)
            
            if not valid_markets:
                logger.warning("[SCANNER] No valid markets after filtering")
                return
            
            # STEP 4: Generate embeddings (batch for efficiency)
            embeddings = await self._generate_embeddings(valid_markets)
            
            # STEP 5: Store in MongoDB
            await self._store_in_mongodb(valid_markets, embeddings)
            
            # STEP 6: Update in-memory caches
            for m in valid_markets:
                market_id = m.get('market_id') or m.get('id')
                self.cached_markets[market_id] = m
            self.cached_embeddings.update(embeddings)
            self.last_updated = datetime.now(timezone.utc)
            
            self.stats['markets_cached'] = len(self.cached_markets)
            
            logger.info(
                f"[SCANNER] ✓ Scan complete. {len(valid_markets)} markets cached. "
                f"(Total: {self.stats['scan_count']}, REST fallback: {self.stats['rest_fallback_used']})"
            )
        
        except Exception as e:
            logger.error(f"[SCANNER] Scan error: {e}", exc_info=True)
    
    async def _fetch_from_websocket(self) -> List[Dict]:
        """Fetch from WebSocket (PRIMARY)"""
        try:
            if not self.websocket_svc:
                return []
            
            # Use existing realtime_market_service pattern
            ws_markets = self.websocket_svc.get_markets(limit=200)
            
            if not ws_markets:
                return []
            
            # Record update times for quality scoring
            now = datetime.now(timezone.utc).timestamp()
            for market in ws_markets:
                market_id = market.get('id') or market.get('condition_id')
                if market_id:
                    self.quality_scorer.record_market_update(market_id, now)
            
            logger.debug(f"[SCANNER] WebSocket: {len(ws_markets)} markets")
            return ws_markets
        
        except Exception as e:
            logger.error(f"[SCANNER] WebSocket fetch error: {e}")
            return []
    
    async def _fetch_from_rest_api(self) -> List[Dict]:
        """Fetch from REST API (FALLBACK)"""
        try:
            if self.gamma_api:
                # Use injected gamma API client
                async with self.gamma_api as api:
                    markets = await api.get_markets(limit=500)
                    logger.debug(f"[SCANNER] REST API fallback: {len(markets)} markets")
                    return markets
            else:
                # Import and use PolymarketAPI directly
                from data.polymarket_api import PolymarketAPI
                async with PolymarketAPI() as api:
                    markets = await api.get_markets(limit=500)
                    logger.debug(f"[SCANNER] REST API fallback: {len(markets)} markets")
                    return markets
        
        except Exception as e:
            logger.error(f"[SCANNER] REST API fetch error: {e}")
            return []
    
    def _filter_valid_markets(self, markets: List[Dict]) -> List[Dict]:
        """Remove clearly invalid markets only"""
        filtered = []
        
        for market in markets:
            question = market.get('question', '').upper()
            
            # Skip if ambiguous
            if any(kw in question for kw in ['TBD', 'N/A', 'UNKNOWN', 'TBA', 'TBC']):
                continue
            
            # Skip if completely dead (no activity)
            volume = market.get('volume_24h', 0) or market.get('volume', 0) or 0
            liquidity = market.get('liquidity', 0) or 0
            if volume == 0 and liquidity == 0:
                continue
            
            # Skip if no valid price
            yes_price = market.get('yes_price')
            if yes_price is None or yes_price == 0:
                continue
            
            filtered.append(market)
        
        return filtered
    
    async def _generate_embeddings(self, markets: List[Dict]) -> Dict[str, np.ndarray]:
        """Generate embeddings for semantic search"""
        embeddings = {}
        
        for i, market in enumerate(markets):
            try:
                market_id = market.get('market_id') or market.get('id')
                market_text = market.get('question', 'Unknown')
                
                # Check if we already have this embedding cached
                if market_id in self.cached_embeddings:
                    embeddings[market_id] = self.cached_embeddings[market_id]
                    continue
                
                embedding = await self.embedding_model.embed(market_text)
                embeddings[market_id] = embedding
                self.stats['embeddings_generated'] += 1
                
                if (i + 1) % 100 == 0:
                    logger.debug(f"[SCANNER] Embedded {i + 1}/{len(markets)}")
            except Exception as e:
                logger.warning(f"[SCANNER] Embedding error for market: {e}")
                continue
        
        return embeddings
    
    async def _store_in_mongodb(self, markets: List[Dict], embeddings: Dict):
        """Store in MongoDB for persistence"""
        try:
            if self.db is None:
                logger.warning("[SCANNER] MongoDB db is None, skipping store")
                return
            
            logger.debug(f"[SCANNER] Storing {len(markets)} markets to MongoDB")
            bulk_ops = []
            for market in markets:
                market_id = market.get('market_id') or market.get('id')
                if not market_id:
                    continue
                
                # Convert numpy array to list for MongoDB storage
                embedding = embeddings.get(market_id)
                embedding_list = embedding.tolist() if embedding is not None else None
                
                # CRITICAL: Only use yes_price if it exists and is valid (not 0 or null)
                # DO NOT default to 0.5 as this causes massive P&L anomalies
                yes_price = market.get('yes_price')
                if yes_price is None or yes_price == 0:
                    # Skip markets without valid price - can't trade without price data
                    logger.debug(f"[SCANNER] Skipping {market_id[:16]} - no valid yes_price")
                    continue
                
                doc = {
                    'market_id': market_id,
                    'question': market.get('question', ''),
                    'description': market.get('description', ''),  # Rich context for news queries
                    'category': market.get('category', 'Other'),
                    'end_date': market.get('end_date'),  # For time-aware queries
                    'price': yes_price,  # No default - skip if missing
                    'bid_ask': {
                        'bid': yes_price - 0.01,
                        'ask': yes_price + 0.01
                    },
                    'liquidity': market.get('liquidity', 0),
                    'volume_24h': market.get('volume_24h', 0) or market.get('volume', 0),
                    'volatility': market.get('volatility', 0.05),  # Lower default volatility
                    'embedding': embedding_list,
                    '_data_quality': market.get('_data_quality', {}),
                    'cached_at': datetime.now(timezone.utc)
                }
                
                bulk_ops.append({
                    'filter': {'market_id': market_id},
                    'update': {'$set': doc},
                    'upsert': True
                })
            
            # Use bulk write for efficiency
            if bulk_ops:
                from pymongo import UpdateOne
                operations = [
                    UpdateOne(op['filter'], op['update'], upsert=op['upsert'])
                    for op in bulk_ops
                ]
                logger.debug(f"[SCANNER] Executing bulk_write with {len(operations)} operations")
                result = await self.db.polymarket_cache.bulk_write(operations)
                self.stats['mongodb_writes'] += result.modified_count + result.upserted_count
                logger.info(f"[SCANNER] MongoDB stored: modified={result.modified_count}, upserted={result.upserted_count}")
                
        except Exception as e:
            logger.error(f"[SCANNER] MongoDB store error: {e}")
    
    def get_cached_markets(self) -> Dict[str, Dict]:
        """Get all cached markets (in-memory, <1ms)"""
        return self.cached_markets
    
    def get_embeddings(self) -> Dict[str, np.ndarray]:
        """Get all embeddings (in-memory, <1ms)"""
        return self.cached_embeddings
    
    def get_cache_status(self) -> Dict:
        """Return cache health"""
        return {
            'markets_cached': len(self.cached_markets),
            'embeddings_cached': len(self.cached_embeddings),
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'is_fresh': (
                (datetime.now(timezone.utc) - self.last_updated).total_seconds() < 60
                if self.last_updated else False
            ),
            'stats': self.stats,
            'running': self._running
        }


# Singleton instance
_scanner_instance: Optional[PolymarketScanner] = None


def get_polymarket_scanner() -> Optional[PolymarketScanner]:
    """Get the singleton scanner instance"""
    return _scanner_instance


async def init_polymarket_scanner(
    db: Any,
    websocket_market_service: Any = None,
    gamma_api_client: Any = None,
    embedding_model: Any = None
) -> PolymarketScanner:
    """Initialize and return the PolymarketScanner"""
    global _scanner_instance
    
    _scanner_instance = PolymarketScanner(
        db=db,
        websocket_market_service=websocket_market_service,
        gamma_api_client=gamma_api_client,
        embedding_model=embedding_model
    )
    
    return _scanner_instance
