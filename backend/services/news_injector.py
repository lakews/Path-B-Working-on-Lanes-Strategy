"""
NEWS INJECTOR SERVICE
=====================

Lane 5: NEWS/EMERGENT - The Bridge

This service handles both:
1. PUSH (Webhook): Immediate processing of incoming news alerts
2. PULL (Exa.ai): Periodic polling for relevant news

The Async Injection Pattern:
- Background thread receives news
- LLM parses and extracts market relevance
- EventBayesianUpdater calculates Bayes Factor
- If BF > threshold, inject to AsyncSignalCache
- HFT loop reads cache and executes at speed

CRITICAL: Errors in this module MUST NOT crash the HFT loop.
All external calls are wrapped in try/except.
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import aiohttp

# Internal imports
from bayesian_math.event_bayes import EventBayesianUpdater, EventPosterior, get_event_bayes
from services.llm_service import get_llm_service, EmergentLLMService, LLMAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Structured news item"""
    headline: str
    content: str
    source: str
    url: str
    published_at: datetime
    relevance_score: float = 0.0
    matched_markets: List[str] = None
    
    def __post_init__(self):
        if self.matched_markets is None:
            self.matched_markets = []


@dataclass 
class InjectedSignal:
    """Signal ready for cache injection"""
    market_id: str
    direction: str              # 'YES' or 'NO'
    posterior: float
    bayes_factor: float
    confidence: float
    news_headline: str
    source: str
    ttl_seconds: int
    timestamp: datetime
    
    def to_cache_value(self) -> Dict:
        return {
            'direction': self.direction,
            'posterior': self.posterior,
            'bayes_factor': self.bayes_factor,
            'confidence': self.confidence,
            'news_headline': self.news_headline[:200],
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'expires_at': (self.timestamp + timedelta(seconds=self.ttl_seconds)).isoformat()
        }


class NewsInjector:
    """
    News processing and signal injection service.
    
    Implements the Async Injection Pattern:
    - Slow analysis runs in background
    - Fast execution via cache read
    """
    
    # Configuration
    DEFAULT_CONFIG = {
        # Bayes thresholds
        'min_bayes_factor': 3.0,          # Minimum to inject
        'strong_bayes_factor': 10.0,      # High priority
        
        # Exa.ai polling
        'exa_poll_interval_seconds': 60,  # Poll every 60s
        'exa_max_results': 10,            # Max results per poll
        
        # Sources to search
        'priority_sources': [
            'apnews.com',
            'reuters.com',
            'bloomberg.com',
            'bbc.com',
            'coindesk.com',
            'theblock.co',
            'fivethirtyeight.com',
            'polymarket.com'
        ],
        
        # Cache TTL
        'default_ttl_seconds': 300,       # 5 minutes
        'resolution_ttl_seconds': 3600,   # 1 hour for resolution news
        
        # Rate limiting
        'max_injections_per_minute': 20,
        
        # LLM model for analysis
        'llm_model': 'gpt-4o-mini'
    }
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        signal_cache: Any = None,
        market_fetcher: Any = None
    ):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.signal_cache = signal_cache
        self.market_fetcher = market_fetcher  # Function to get active markets
        
        # Event Bayesian updater (isolated module)
        self.event_bayes = get_event_bayes({
            'min_bayes_factor': self.config['min_bayes_factor']
        })
        
        # LLM service for news analysis (uses Event Resolution Adjudicator prompt)
        self.llm_service = get_llm_service(model=self.config['llm_model'])
        
        # State
        self.is_running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._injection_count = 0
        self._last_injection_reset = datetime.now(timezone.utc)
        
        # Exa.ai client (lazy init)
        self._exa_api_key = os.environ.get('EXA_API_KEY')
        
        logger.info(f"[NEWS INJECTOR] Initialized with config: {self.config}")
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits for injections"""
        now = datetime.now(timezone.utc)
        
        # Reset counter every minute
        if (now - self._last_injection_reset).total_seconds() > 60:
            self._injection_count = 0
            self._last_injection_reset = now
        
        return self._injection_count < self.config['max_injections_per_minute']
    
    async def _analyze_news_with_llm(
        self,
        news: NewsItem,
        markets: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Use LLM to analyze news relevance to markets.
        
        Uses the Event Resolution Adjudicator prompt for strict,
        calibrated analysis focusing on the YES outcome.
        
        Returns:
            Dict mapping market_id to analysis:
            {
                'market_id': {
                    'direction': 'YES' | 'NO' | 'NEUTRAL',
                    'impact': 'resolution' | 'strong' | 'moderate' | 'weak' | 'irrelevant',
                    'confidence': 0.0-1.0,
                    'reasoning': str
                }
            }
        """
        try:
            # Use batch analysis for efficiency
            results = await self.llm_service.batch_analyze(
                news_headline=news.headline,
                news_content=news.content,
                markets=markets[:20]  # Limit to 20 markets
            )
            
            # Convert LLMAnalysisResult to the format expected by EventBayes
            analyses = {}
            for market_id, result in results.items():
                if result.is_relevant and result.confidence > 0.50:
                    analyses[market_id] = {
                        'direction': result.direction,
                        'impact': result.impact,
                        'confidence': result.confidence,
                        'reasoning': result.rationale
                    }
            
            return analyses
            
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] LLM analysis failed: {e}")
            return {}
    
    async def _fetch_from_exa(self, query: str) -> List[NewsItem]:
        """
        Fetch news from Exa.ai neural search.
        
        CRITICAL: Errors here must not propagate.
        """
        if not self._exa_api_key:
            logger.debug("[NEWS INJECTOR] No Exa API key, skipping fetch")
            return []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Exa.ai search endpoint
                url = "https://api.exa.ai/search"
                
                headers = {
                    "Authorization": f"Bearer {self._exa_api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "query": query,
                    "numResults": self.config['exa_max_results'],
                    "useAutoprompt": True,
                    "type": "neural",
                    "includeDomains": self.config['priority_sources'],
                    "startPublishedDate": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
                    "contents": {
                        "text": {"maxCharacters": 1000}
                    }
                }
                
                async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        news_items = []
                        for result in data.get('results', []):
                            news_items.append(NewsItem(
                                headline=result.get('title', ''),
                                content=result.get('text', ''),
                                source=result.get('url', ''),
                                url=result.get('url', ''),
                                published_at=datetime.fromisoformat(
                                    result.get('publishedDate', datetime.now(timezone.utc).isoformat()).replace('Z', '+00:00')
                                ),
                                relevance_score=result.get('score', 0.0)
                            ))
                        
                        logger.info(f"[NEWS INJECTOR] Exa returned {len(news_items)} results")
                        return news_items
                    else:
                        logger.warning(f"[NEWS INJECTOR] Exa API error: {resp.status}")
                        return []
                        
        except asyncio.TimeoutError:
            logger.warning("[NEWS INJECTOR] Exa API timeout")
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] Exa fetch failed: {e}")
        
        return []
    
    async def _inject_signal(self, signal: InjectedSignal):
        """
        Inject a signal into the AsyncSignalCache.
        
        Key format: emergent_signal:{market_id}
        """
        if not self.signal_cache:
            logger.warning("[NEWS INJECTOR] No signal cache configured")
            return
        
        if not self._check_rate_limit():
            logger.warning("[NEWS INJECTOR] Rate limit exceeded, skipping injection")
            return
        
        try:
            cache_key = f"emergent_signal:{signal.market_id}"
            cache_value = signal.to_cache_value()
            
            # Inject to cache with TTL
            await self.signal_cache.set(
                cache_key,
                cache_value,
                ttl=signal.ttl_seconds
            )
            
            self._injection_count += 1
            
            logger.info(
                f"[NEWS INJECTOR] Injected signal for {signal.market_id[:16]}... "
                f"| Direction: {signal.direction} | BF: {signal.bayes_factor:.2f} "
                f"| Headline: {signal.news_headline[:50]}..."
            )
            
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] Cache injection failed: {e}")
    
    async def process_news(self, news: NewsItem, markets: Optional[List[Dict]] = None):
        """
        Process a single news item and inject signals if actionable.
        
        This is the main entry point for both webhook and poll processing.
        
        CRITICAL: This method catches all exceptions to prevent crashes.
        """
        try:
            # Get active markets if not provided
            if markets is None:
                if self.market_fetcher:
                    markets = await self.market_fetcher()
                else:
                    logger.warning("[NEWS INJECTOR] No markets available")
                    return
            
            if not markets:
                return
            
            # Analyze news with LLM
            analyses = await self._analyze_news_with_llm(news, markets)
            
            if not analyses:
                logger.debug(f"[NEWS INJECTOR] No markets affected by: {news.headline[:50]}...")
                return
            
            # Process each affected market
            for market_id, analysis in analyses.items():
                # Find market data
                market = next((m for m in markets if m['id'] == market_id), None)
                if not market:
                    continue
                
                # Update with Event Bayesian
                posterior = self.event_bayes.update(
                    market_id=market_id,
                    market_question=market.get('question', ''),
                    current_price=market.get('yes_price', 0.5),
                    news_headline=news.headline,
                    news_content=news.content,
                    news_source=news.source,
                    llm_analysis=analysis
                )
                
                # Check if actionable
                if posterior.is_actionable(self.config['min_bayes_factor']):
                    signal = InjectedSignal(
                        market_id=market_id,
                        direction=posterior.direction,
                        posterior=posterior.posterior,
                        bayes_factor=posterior.bayes_factor,
                        confidence=posterior.confidence,
                        news_headline=news.headline,
                        source=news.source,
                        ttl_seconds=posterior.ttl_seconds,
                        timestamp=posterior.timestamp
                    )
                    
                    await self._inject_signal(signal)
                else:
                    logger.debug(
                        f"[NEWS INJECTOR] Signal too weak for {market_id[:16]}... "
                        f"| BF: {posterior.bayes_factor:.2f} < {self.config['min_bayes_factor']}"
                    )
                    
        except Exception as e:
            # CRITICAL: Log and continue, never crash
            logger.error(f"[NEWS INJECTOR] Error processing news: {e}")
    
    async def handle_webhook(self, payload: Dict) -> Dict:
        """
        Handle incoming webhook notification.
        
        Expected payload:
        {
            "headline": str,
            "content": str (optional),
            "source": str,
            "url": str (optional),
            "priority": "high" | "normal" (optional)
        }
        
        Returns:
            Dict with processing result
        """
        try:
            news = NewsItem(
                headline=payload.get('headline', ''),
                content=payload.get('content', ''),
                source=payload.get('source', 'webhook'),
                url=payload.get('url', ''),
                published_at=datetime.now(timezone.utc)
            )
            
            if not news.headline:
                return {"status": "error", "message": "Missing headline"}
            
            # Process immediately (high priority)
            await self.process_news(news)
            
            return {
                "status": "processed",
                "headline": news.headline[:100],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[NEWS INJECTOR] Webhook error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _poll_loop(self):
        """
        Background polling loop for Exa.ai.
        
        Runs continuously, fetching news and processing.
        """
        logger.info("[NEWS INJECTOR] Poll loop started")
        
        while self.is_running:
            try:
                # Build search query from active markets
                # This could be made smarter by extracting keywords from market questions
                query = "prediction market resolution news politics crypto sports"
                
                # Fetch from Exa
                news_items = await self._fetch_from_exa(query)
                
                # Process each item
                for news in news_items:
                    if not self.is_running:
                        break
                    await self.process_news(news)
                    
                    # Small delay between processing to avoid overwhelming LLM
                    await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"[NEWS INJECTOR] Poll loop error: {e}")
            
            # Wait for next poll interval
            await asyncio.sleep(self.config['exa_poll_interval_seconds'])
        
        logger.info("[NEWS INJECTOR] Poll loop stopped")
    
    async def start(self):
        """Start the news injector background polling"""
        if self.is_running:
            return
        
        self.is_running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("[NEWS INJECTOR] Started")
    
    async def stop(self):
        """Stop the news injector"""
        self.is_running = False
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[NEWS INJECTOR] Stopped")


# Singleton instance
_news_injector: Optional[NewsInjector] = None


def get_news_injector(
    config: Optional[Dict] = None,
    signal_cache: Any = None,
    market_fetcher: Any = None
) -> NewsInjector:
    """Get or create the News Injector instance"""
    global _news_injector
    if _news_injector is None:
        _news_injector = NewsInjector(
            config=config,
            signal_cache=signal_cache,
            market_fetcher=market_fetcher
        )
    return _news_injector


async def init_news_injector(
    config: Optional[Dict] = None,
    signal_cache: Any = None,
    market_fetcher: Any = None
) -> NewsInjector:
    """Initialize and start the News Injector"""
    injector = get_news_injector(config, signal_cache, market_fetcher)
    await injector.start()
    return injector
