"""
DUAL-PATH NEWS INJECTOR SERVICE
================================

Markets-First Architecture - Optimized

Dual-path news processing:
- PATH A: PATH A Ultimate (keyword matching + LLM analysis + 7 optimizations)
- PATH B: Broadcast ALL markets → HFT opportunities

Features:
- O(1) keyword lookup via reverse index
- 1,445+ category keywords for detection
- 7 optimizations: dedup, early termination, clustering, adaptive TTL, priority queue, Bayes multipliers, hot-swap
- MongoDB for signal storage (NO Redis)
- Both paths run in parallel (non-blocking)

CRITICAL: This service runs PARALLEL to existing 5-lane system.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class DualPathNewsInjector:
    """
    Dual-path news processing:
    - PATH A: PATH A Ultimate (optimized keyword matching + LLM)
    - PATH B: Broadcast ALL markets → HFT opportunities
    """
    
    def __init__(
        self,
        polymarket_scanner: Any,
        llm_service: Any,
        db_mongo: Any,
        embedding_model: Any = None  # Kept for backward compatibility, no longer used
    ):
        self.scanner = polymarket_scanner
        self.llm = llm_service
        self.db = db_mongo
        
        self._running = False
        
        self.stats = {
            'news_processed': 0,
            'path_a_signals': 0,
            'path_b_broadcasts': 0,
            'llm_calls': 0,
            'mongodb_writes': 0,
            'errors': 0
        }
        
        # PATH A: News-to-Market Matching & Signal Generation Engine
        self.path_a_engine = None
        try:
            from .path_a_engine import PathAEngine
            from config import path_a_config
            self.path_a_engine = PathAEngine(
                polymarket_scanner=polymarket_scanner,
                llm_service=llm_service,
                mongo_db=db_mongo,
                config=path_a_config.PATH_A_CONFIG
            )
            logger.info("[DUAL PATH] ✓ PATH A Engine initialized")
        except Exception as e:
            logger.error(f"[DUAL PATH] Failed to initialize PATH A: {e}")
    
    async def process_news_event(self, news: Dict) -> Tuple[List[Dict], int]:
        """
        Main entry point for news events.
        Processes through both paths.
        
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
            
            if not headline:
                logger.warning("[NEWS INJECTOR] Empty headline received")
                return [], 0
            
            logger.info(f"[NEWS INJECTOR] Processing: {headline[:60]}...")
            
            # PATH B: Immediate broadcast (always runs first for speed)
            logger.debug("[NEWS INJECTOR] Starting PATH B (broadcast)...")
            path_b_count = await self._process_path_b(headline, source, urgency)
            self.stats['path_b_broadcasts'] += path_b_count
            logger.info(f"[NEWS INJECTOR] ✓ PATH B: {path_b_count} opportunities")
            
            # PATH A: PATH A Ultimate (keyword matching + LLM + optimizations)
            path_a_signals = []
            if self.path_a_engine:
                try:
                    if urgency == 'breaking':
                        # Fire and forget for breaking news (speed critical)
                        asyncio.create_task(self._process_path_a_async(news))
                        logger.info("[NEWS INJECTOR] ✓ PATH A: Deferred to background (breaking)")
                    else:
                        result = await self.path_a_engine.process_news_event(news)
                        signals_count = result.get('signals_generated', 0)
                        self.stats['path_a_signals'] += signals_count
                        self.stats['llm_calls'] += result.get('matched_markets', 0) - result.get('optimizations_applied', []).count('early_termination')
                        
                        logger.info(
                            f"[NEWS INJECTOR] ✓ PATH A: {signals_count} signals "
                            f"(matched={result.get('matched_markets', 0)}, "
                            f"latency={result.get('latency_ms', 0)}ms, "
                            f"optimizations={result.get('optimizations_applied', [])})"
                        )
                except Exception as e:
                    logger.error(f"[NEWS INJECTOR] PATH A error: {e}")
            else:
                logger.warning("[NEWS INJECTOR] PATH A not available (path_a_engine is None)")
            
            self.stats['news_processed'] += 1
            return path_a_signals, path_b_count
        
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"[NEWS INJECTOR] News injection error: {e}", exc_info=True)
            return [], 0
    
    async def _process_path_a_async(self, news: Dict):
        """PATH A async for background execution (breaking news)"""
        try:
            if self.path_a_engine:
                result = await self.path_a_engine.process_news_event(news)
                signals_count = result.get('signals_generated', 0)
                self.stats['path_a_signals'] += signals_count
                logger.info(f"[NEWS INJECTOR] ✓ PATH A (async): {signals_count} signals")
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] PATH A async error: {e}")
    
    async def _process_path_b(
        self, headline: str, source: str, urgency: str
    ) -> int:
        """PATH B: Broadcast ALL markets as opportunities for HFT"""
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
                    'expires_at': now + timedelta(seconds=30)  # 30s TTL
                }
                
                opportunities.append(opportunity)
            
            # Batch insert to MongoDB
            if opportunities and self.db is not None:
                try:
                    await self.db.hft_opportunities.insert_many(opportunities)
                    self.stats['mongodb_writes'] += len(opportunities)
                    logger.debug(f"[NEWS INJECTOR] PATH B: {len(opportunities)} opportunities written to MongoDB")
                except Exception as db_err:
                    logger.error(f"[NEWS INJECTOR] PATH B MongoDB write error: {db_err}")
            elif self.db is None:
                logger.warning(f"[NEWS INJECTOR] PATH B: db is None! {len(opportunities)} opportunities NOT stored")
            
            return len(opportunities)
        
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] PATH B error: {e}")
            return 0
    
    def get_stats(self) -> Dict:
        """Return statistics including PATH A (PATH A) stats"""
        base_stats = {
            **self.stats,
            'running': self._running
        }
        
        # Include PATH A detailed stats
        if self.path_a_engine:
            path_a_stats = self.path_a_engine.get_stats()
            base_stats['path_a_details'] = {
                'index_size': path_a_stats.get('index_size', 0),
                'markets_cached': path_a_stats.get('markets_cached', 0),
                'dedup_prevented': path_a_stats.get('dedup_prevented', 0),
                'early_terminations': path_a_stats.get('early_terminations', 0),
                'llm_calls_saved': path_a_stats.get('llm_calls_saved', 0),
                'clustering_groups': path_a_stats.get('clustering_groups', 0),
                'avg_latency_ms': path_a_stats.get('avg_latency_ms', 0),
                'last_refresh': path_a_stats.get('last_refresh')
            }
        
        return base_stats


# Singleton instance
_news_injector_instance: Optional[DualPathNewsInjector] = None


def get_dual_path_news_injector() -> Optional[DualPathNewsInjector]:
    """Get the singleton news injector instance"""
    return _news_injector_instance


async def init_dual_path_news_injector(
    polymarket_scanner: Any,
    llm_service: Any,
    db_mongo: Any,
    embedding_model: Any = None  # Kept for backward compatibility
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
