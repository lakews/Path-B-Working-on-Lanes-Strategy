"""
DUAL-PATH NEWS INJECTOR SERVICE
================================

Markets-First Architecture - Phase 1

Dual-path news processing: PATH A creates signals, PATH B broadcasts opportunities.
Both write to MongoDB (NO Redis).

PATH A: Semantic search (5-10 markets) → LLM analysis → Signal creation
PATH B: Broadcast ALL 400-900 markets → HFT opportunities

Features:
- Adaptive TTL based on market regime (Optimization 2A)
- MongoDB replaces Redis for signal caching
- Both paths run in parallel (non-blocking)
- Zero breaking changes to existing system

CRITICAL: This service runs PARALLEL to existing 5-lane system.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import numpy as np

try:
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    # Fallback implementation if sklearn not installed
    def cosine_similarity(a: List, b: List) -> List[List[float]]:
        """Simple cosine similarity implementation"""
        a = np.array(a)
        b = np.array(b)
        if a.ndim == 1:
            a = a.reshape(1, -1)
        if b.ndim == 1:
            b = b.reshape(1, -1)
        
        dot_product = np.dot(a, b.T)
        norm_a = np.linalg.norm(a, axis=1, keepdims=True)
        norm_b = np.linalg.norm(b, axis=1, keepdims=True)
        
        if norm_a.any() and norm_b.any():
            return (dot_product / (norm_a * norm_b.T)).tolist()
        return [[0.0]]

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime for adaptive TTL (Optimization 2A)"""
    QUIET = "quiet"
    NORMAL = "normal"
    VOLATILE = "volatile"
    CRISIS = "crisis"


class DualPathNewsInjector:
    """
    Dual-path news processing: PATH A creates signals, PATH B broadcasts opportunities.
    Both write to MongoDB (NO Redis).
    """
    
    # Base TTL by signal strength (seconds) - INCREASED for cost optimization
    BASE_TTL = {
        'resolution': 900,   # 15 min (was 10 min) - resolution news stays relevant longer
        'strong': 600,       # 10 min (was 5 min) - strong signals are worth keeping
        'moderate': 300,     # 5 min (was 3 min) - moderate signals get more time
        'weak': 120          # 2 min (was 1 min) - weak signals still worth a look
    }
    
    # Regime multipliers for adaptive TTL
    REGIME_MULTIPLIERS = {
        MarketRegime.QUIET: 2.0,      # Keep much longer in quiet markets
        MarketRegime.NORMAL: 1.5,     # Keep longer (was 1.0)
        MarketRegime.VOLATILE: 1.0,   # Standard (was 0.6)
        MarketRegime.CRISIS: 0.5      # Still fast but not extreme (was 0.3)
    }
    
    def __init__(
        self,
        polymarket_scanner: Any,
        llm_service: Any,
        db_mongo: Any,
        embedding_model: Any = None
    ):
        self.scanner = polymarket_scanner
        self.llm = llm_service
        self.db = db_mongo
        self.embedding_model = embedding_model
        
        self._running = False
        
        self.stats = {
            'news_processed': 0,
            'path_a_signals': 0,
            'path_b_broadcasts': 0,
            'llm_calls': 0,
            'mongodb_writes': 0,
            'errors': 0,
            'arch_c_signals': 0
        }
        
        # Initialize Architecture C Ultimate
        self.arch_c_index = None
        try:
            from .reverse_market_index_ultimate import ReverseMarketIndexUltimate
            from config import arch_c_config
            self.arch_c_index = ReverseMarketIndexUltimate(
                polymarket_scanner=polymarket_scanner,
                llm_service=llm_service,
                mongo_db=db_mongo,
                config=arch_c_config.ARCH_C_CONFIG
            )
            logger.info("[DUAL PATH] Architecture C Ultimate initialized")
        except Exception as e:
            logger.warning(f"[DUAL PATH] Could not init Architecture C: {e}")
    
    async def process_news_event(self, news: Dict) -> Tuple[List[Dict], int]:
        """
        Main entry point for news events.
        Processes through both paths in parallel.
        
        Args:
            news: Dict with keys:
                - headline: str (required)
                - source: str (optional, default 'unknown')
                - urgency: str (optional, 'normal', 'high', 'breaking')
                - content: str (optional)
        
        Returns: (path_a_signals, path_b_count)
        """
        try:
            headline = news.get('headline', '')
            source = news.get('source', 'unknown')
            urgency = news.get('urgency', 'normal')
            content = news.get('content', '')
            
            if not headline:
                logger.warning("[NEWS INJECTOR] Empty headline received")
                return [], 0
            
            logger.info(f"[NEWS INJECTOR] Processing: {headline[:60]}...")
            
            # Generate news embedding (shared by both paths)
            news_embedding = None
            if self.embedding_model:
                try:
                    news_embedding = await self.embedding_model.embed(headline)
                except Exception as e:
                    logger.error(f"[NEWS INJECTOR] Embedding error: {e}")
            
            # PATH B: Immediate broadcast (always runs first for speed)
            logger.info("[NEWS INJECTOR] Starting PATH B (broadcast)...")
            path_b_count = await self._process_path_b(headline, source, urgency)
            self.stats['path_b_broadcasts'] += path_b_count
            logger.info(f"[NEWS INJECTOR] ✓ PATH B: {path_b_count} opportunities")
            
            # PATH A: Can be deferred if breaking news
            if urgency == 'breaking':
                # Fire and forget for breaking news (speed critical)
                asyncio.create_task(
                    self._process_path_a_async(headline, source, news_embedding, content)
                )
                path_a_signals = []
                logger.info("[NEWS INJECTOR] ✓ PATH A: Deferred to background (breaking)")
            else:
                logger.info("[NEWS INJECTOR] Starting PATH A (semantic search)...")
                path_a_signals = await self._process_path_a(
                    headline, source, news_embedding, content
                )
                logger.info(f"[NEWS INJECTOR] ✓ PATH A: {len(path_a_signals)} signals")
            
            self.stats['news_processed'] += 1
            return path_a_signals, path_b_count
        
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[NEWS INJECTOR] News injection error: {e}", exc_info=True)
            return [], 0
    
    async def _process_path_a(
        self, headline: str, source: str, news_embedding: Optional[np.ndarray], content: str = ''
    ) -> List[Dict]:
        """PATH A: Semantic search + LLM analysis"""
        try:
            if not self.scanner:
                logger.warning("[NEWS INJECTOR] No scanner available for PATH A")
                return []
            
            cached_markets = self.scanner.get_cached_markets()
            cached_embeddings = self.scanner.get_embeddings()
            
            if not cached_markets:
                logger.warning("[NEWS INJECTOR] No cached markets for PATH A")
                return []
            
            # Semantic search: find top 3 most relevant markets (reduced from 10 to save LLM costs)
            # Only markets with >0.4 similarity will be analyzed (based on embedding analysis)
            # 0.4+ typically indicates genuinely related content
            relevant = self._semantic_search(
                news_embedding, cached_embeddings, cached_markets, top_k=3, min_similarity=0.4
            )
            
            logger.info(f"[NEWS INJECTOR] Found {len(relevant)} relevant markets via semantic search")
            
            if not relevant:
                return []
            
            # LLM analyzes each relevant market
            signals = []
            for market in relevant:
                try:
                    market_question = market.get('question', 'Unknown')
                    logger.info(f"[NEWS INJECTOR] PATH A: Analyzing market '{market_question[:50]}...' against news '{headline[:40]}...'")
                    
                    conviction = await self._llm_analyze_market(
                        headline, market, source, content
                    )
                    if conviction:
                        logger.info(f"[NEWS INJECTOR] PATH A: ✓ Signal generated - direction={conviction.get('direction')}, BF={conviction.get('bayes_factor'):.2f}")
                        signals.append(conviction)
                        self.stats['llm_calls'] += 1
                    else:
                        logger.debug(f"[NEWS INJECTOR] PATH A: ✗ No signal (LLM returned not relevant)")
                except Exception as e:
                    logger.error(f"[NEWS INJECTOR] LLM error for market: {e}")
                    continue
            
            # Cache signals with ADAPTIVE TTL to MongoDB
            for signal in signals:
                market_id = signal.get('market_id')
                market = cached_markets.get(market_id, {})
                await self._cache_signal_mongodb(signal, market)
            
            self.stats['path_a_signals'] += len(signals)
            return signals
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] PATH A error: {e}")
            return []
    
    async def _process_path_a_async(
        self, headline: str, source: str, news_embedding: Optional[np.ndarray], content: str = ''
    ):
        """PATH A async for background execution"""
        try:
            signals = await self._process_path_a(headline, source, news_embedding, content)
            logger.info(f"[NEWS INJECTOR] ✓ PATH A (async): {len(signals)} signals")
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] PATH A async error: {e}")
    
    def _semantic_search(
        self, news_embedding: Optional[np.ndarray], market_embeddings: Dict,
        markets: Dict, top_k: int = 3, min_similarity: float = 0.3
    ) -> List[Dict]:
        """
        Find top K relevant markets using cosine similarity.
        
        Args:
            news_embedding: Embedding vector for the news item
            market_embeddings: Dict of market_id -> embedding vector
            markets: Dict of market_id -> market data
            top_k: Maximum number of markets to return (default 3 to reduce LLM costs)
            min_similarity: Minimum similarity threshold (default 0.3 to skip irrelevant)
        """
        try:
            if news_embedding is None or len(market_embeddings) == 0:
                # Fall back to returning top markets by volume if no embeddings available
                sorted_markets = sorted(
                    markets.values(), 
                    key=lambda m: m.get('volume_24h', 0), 
                    reverse=True
                )
                return sorted_markets[:top_k]
            
            similarities = {}
            
            for market_id, market_emb in market_embeddings.items():
                try:
                    if market_emb is None:
                        continue
                    sim = cosine_similarity([news_embedding], [market_emb])[0][0]
                    # Only include if above minimum threshold
                    if sim >= min_similarity:
                        similarities[market_id] = sim
                except Exception:
                    continue
            
            if not similarities:
                logger.debug(f"[NEWS INJECTOR] No markets above {min_similarity:.0%} similarity threshold")
                return []
            
            # Sort by similarity and get top K
            top_ids = sorted(
                similarities.items(), key=lambda x: x[1], reverse=True
            )[:top_k]
            
            logger.debug(f"[NEWS INJECTOR] Semantic search: {len(similarities)} above threshold, returning top {len(top_ids)}")
            
            return [markets[mid] for mid, _ in top_ids if mid in markets]
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] Semantic search error: {e}")
            return []
    
    async def _llm_analyze_market(
        self, headline: str, market: Dict, source: str, content: str = ''
    ) -> Optional[Dict]:
        """LLM analyzes market impact from news"""
        try:
            if self.llm is None:
                # Fallback: simple keyword matching
                return self._simple_analysis(headline, market, source)
            
            market_question = market.get('question', 'Unknown')
            market_description = market.get('description', '')
            
            # Use the existing EmergentLLMService's analyze_news_for_market method
            try:
                result = await self.llm.analyze_news_for_market(
                    news_headline=headline,
                    news_content=content[:500] if content else '',
                    market_question=market_question,
                    market_description=market_description
                )
                
                # Convert LLMAnalysisResult to our signal format
                if result.error or not result.is_relevant:
                    logger.debug(f"[NEWS INJECTOR] LLM returned not relevant: error={result.error}, is_relevant={result.is_relevant}")
                    return None
                
                logger.info(f"[NEWS INJECTOR] LLM found relevant! confidence={result.confidence}, is_bullish={result.is_bullish_for_yes}, direction={result.direction}")
                
                # Convert confidence to bayes_factor (simple mapping)
                # confidence 0.5 = BF 1, confidence 0.75 = BF 3, confidence 0.95 = BF 10
                bayes_factor = 1.0
                if result.confidence >= 0.95:
                    bayes_factor = 10.0
                elif result.confidence >= 0.75:
                    bayes_factor = 3.0 + (result.confidence - 0.75) * 28  # 3 to 10
                elif result.confidence >= 0.60:
                    bayes_factor = 1.5 + (result.confidence - 0.60) * 10  # 1.5 to 3
                else:
                    bayes_factor = 1.0 + (result.confidence - 0.50) * 5  # 1 to 1.5
                
                market_id = market.get('market_id') or market.get('id')
                
                return {
                    'market_id': market_id,
                    'market_question': market_question,
                    'news_headline': headline,
                    'news_source': source,
                    'timestamp': datetime.now(timezone.utc),
                    'bayes_factor': bayes_factor,
                    'direction': result.direction,
                    'confidence': result.confidence,
                    'sentiment': result.confidence if result.is_bullish_for_yes else (1 - result.confidence),
                    'impact_level': result.impact,
                    'type': 'path_a',
                    'rationale': result.rationale
                }
                
            except AttributeError:
                # LLM service doesn't have the expected method, fall back
                return self._simple_analysis(headline, market, source)
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] LLM analysis error: {e}")
            return None
    
    def _simple_analysis(self, headline: str, market: Dict, source: str) -> Optional[Dict]:
        """Fallback simple keyword-based analysis"""
        headline_lower = headline.lower()
        question_lower = market.get('question', '').lower()
        
        # Check for keyword overlap
        headline_words = set(headline_lower.split())
        question_words = set(question_lower.split())
        overlap = headline_words & question_words
        
        # Remove common words
        common_words = {'will', 'the', 'a', 'an', 'to', 'be', 'in', 'on', 'by', 'for', 'of', 'is', 'at'}
        overlap = overlap - common_words
        
        if len(overlap) < 2:
            return None  # Not relevant enough
        
        market_id = market.get('market_id') or market.get('id')
        
        return {
            'market_id': market_id,
            'market_question': market.get('question', ''),
            'news_headline': headline,
            'news_source': source,
            'timestamp': datetime.now(timezone.utc),
            'bayes_factor': 3.0,  # Conservative default
            'direction': 'YES',
            'confidence': 0.6,
            'sentiment': 0.6,
            'impact_level': 'moderate',
            'type': 'path_a'
        }
    
    def _detect_market_regime(self, market_data: Dict) -> MarketRegime:
        """Detect market regime from volatility + volume"""
        vol = market_data.get('volatility', 0.8)
        volume = market_data.get('volume_24h', 10000)
        price_change_1h = market_data.get('price_change_1h_pct', 0)
        
        if abs(price_change_1h) > 20 or vol > 2.0:
            return MarketRegime.CRISIS
        
        if vol > 1.5 or abs(price_change_1h) > 5:
            return MarketRegime.VOLATILE
        
        if vol < 0.5 and volume < 5000:
            return MarketRegime.QUIET
        
        return MarketRegime.NORMAL
    
    def _calculate_adaptive_ttl(
        self, signal: Dict, market_data: Dict
    ) -> int:
        """Calculate adaptive TTL (Optimization 2A)"""
        impact = signal.get('impact_level', 'moderate')
        base_ttl = self.BASE_TTL.get(impact, 180)
        
        regime = self._detect_market_regime(market_data)
        
        mult = self.REGIME_MULTIPLIERS.get(regime, 1.0)
        adaptive_ttl = int(base_ttl * mult)
        
        # Clamp: 60s to 30min (increased max from 20min for cost savings)
        adaptive_ttl = max(60, min(adaptive_ttl, 1800))
        
        return adaptive_ttl
    
    async def _cache_signal_mongodb(
        self, signal: Dict, market_data: Dict
    ):
        """Cache signal to MongoDB with adaptive TTL"""
        try:
            if self.db is None:
                logger.warning("[NEWS INJECTOR] MongoDB db is None, skipping signal cache")
                return
            
            ttl = self._calculate_adaptive_ttl(signal, market_data)
            regime = self._detect_market_regime(market_data)
            
            doc = {
                'market_id': signal['market_id'],
                'type': 'path_a',
                'market_question': signal.get('market_question', ''),
                'news_headline': signal.get('news_headline', ''),
                'news_source': signal.get('news_source', 'unknown'),
                'timestamp': signal.get('timestamp', datetime.now(timezone.utc)),
                'bayes_factor': signal.get('bayes_factor', 0),
                'direction': signal.get('direction', 'YES'),
                'confidence': signal.get('confidence', 0.5),
                'sentiment': signal.get('sentiment', 0.5),
                'impact_level': signal.get('impact_level', 'low'),
                'adaptive_ttl': ttl,
                'market_regime': regime.value,
                'expires_at': datetime.now(timezone.utc) + timedelta(seconds=ttl),
                'created_at': datetime.now(timezone.utc)
            }
            
            logger.info(f"[NEWS INJECTOR] Writing PATH A signal to MongoDB: {signal['market_id'][:16]}...")
            await self.db.signals.update_one(
                {
                    'market_id': signal['market_id'],
                    'type': 'path_a'
                },
                {'$set': doc},
                upsert=True
            )
            
            self.stats['mongodb_writes'] += 1
            logger.info(f"[NEWS INJECTOR] ✓ Cached signal: {signal['market_id'][:16]}... (TTL: {ttl}s, Regime: {regime.value})")
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] MongoDB cache error: {e}")
    
    async def _process_path_b(
        self, headline: str, source: str, urgency: str
    ) -> int:
        """PATH B: Broadcast ALL markets as opportunities"""
        try:
            if not self.scanner:
                logger.warning("[NEWS INJECTOR] No scanner available for PATH B")
                return 0
            
            cached_markets = self.scanner.get_cached_markets()
            
            if not cached_markets:
                logger.warning("[NEWS INJECTOR] No cached markets for PATH B")
                return 0
            
            opportunities = []
            now = datetime.now(timezone.utc)
            
            for market_id, market in cached_markets.items():
                opportunity = {
                    'market_id': market_id,
                    'market_question': market.get('question', ''),
                    'market_price': market.get('price', market.get('yes_price', 0.5)),
                    'market_volume_24h': market.get('volume_24h', 0),
                    'market_liquidity': market.get('liquidity', 0),
                    'market_category': market.get('category', 'Other'),
                    'market_data_quality': market.get('_data_quality', {}),
                    
                    'news_headline': headline,
                    'news_source': source,
                    'news_urgency': urgency,
                    'timestamp': now,
                    
                    'type': 'path_b',
                    'requires_fast_execution': urgency in ['high', 'breaking'],
                    
                    'created_at': now,
                    'expires_at': now + timedelta(seconds=30)  # 30s TTL (increased from 10s)
                }
                
                opportunities.append(opportunity)
            
            # Batch insert to MongoDB
            if opportunities and self.db is not None:
                try:
                    await self.db.hft_opportunities.insert_many(opportunities)
                    self.stats['mongodb_writes'] += len(opportunities)
                    logger.info(f"[NEWS INJECTOR] PATH B: {len(opportunities)} opportunities WRITTEN to MongoDB")
                except Exception as db_err:
                    logger.error(f"[NEWS INJECTOR] PATH B MongoDB write error: {db_err}")
            elif self.db is None:
                logger.warning(f"[NEWS INJECTOR] PATH B: db is None! {len(opportunities)} opportunities NOT stored")
            
            logger.info(f"[NEWS INJECTOR] PATH B: {len(opportunities)} opportunities broadcasted")
            return len(opportunities)
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] PATH B error: {e}")
            return 0
    
    def get_stats(self) -> Dict:
        """Return statistics"""
        return {
            **self.stats,
            'running': self._running
        }


# Singleton instance
_news_injector_instance: Optional[DualPathNewsInjector] = None


def get_dual_path_news_injector() -> Optional[DualPathNewsInjector]:
    """Get the singleton news injector instance"""
    return _news_injector_instance


async def init_dual_path_news_injector(
    polymarket_scanner: Any,
    llm_service: Any,
    db_mongo: Any,
    embedding_model: Any = None
) -> DualPathNewsInjector:
    """Initialize and return the DualPathNewsInjector"""
    global _news_injector_instance
    
    _news_injector_instance = DualPathNewsInjector(
        polymarket_scanner=polymarket_scanner,
        llm_service=llm_service,
        db_mongo=db_mongo,
        embedding_model=embedding_model
    )
    
    return _news_injector_instance
