"""
NEWS POLLER SERVICE
===================

Lane 5 News Service for the 5-Lane Trading Architecture.
Polls external news sources (Exa.ai) and feeds signals into the trading system.

Architecture:
    NewsPoller -> EventBayesianUpdater -> EmergentSignalCache -> HFT Loop (news_sniper)
    
The NewsPoller:
1. Periodically polls Exa.ai for relevant news
2. Filters and scores articles by relevance
3. Returns structured events for LLM analysis

Updated: Feb 2026 - Now uses official exa-py SDK
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

# Official Exa SDK
try:
    from exa_py import Exa
    EXA_SDK_AVAILABLE = True
except ImportError:
    EXA_SDK_AVAILABLE = False
    Exa = None

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    """Structured news event for analysis"""
    title: str
    url: str
    source: str
    published_date: Optional[str]
    text: str
    score: float
    query: str
    
    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'published_date': self.published_date,
            'text': self.text[:500] if self.text else '',  # Truncate for LLM
            'score': self.score,
            'query': self.query,
            'fetched_at': datetime.now(timezone.utc).isoformat()
        }


class NewsPoller:
    """
    News polling service for Lane 5 (NEWS/EMERGENT).
    
    Polls Exa.ai for news related to prediction markets and returns
    structured events for LLM analysis and Bayesian updating.
    
    Uses the official exa-py SDK for reliable API access.
    
    Usage:
        poller = NewsPoller()
        events = await poller.poll_news("Bitcoin ETF approval")
        for event in events:
            # Process with LLM and Bayesian updater
            ...
    """
    
    # Prediction market relevant search queries
    DEFAULT_QUERIES = [
        "Federal Reserve interest rate decision impact markets",
        "presidential election prediction polling results",
        "cryptocurrency bitcoin ethereum regulation SEC",
        "sports betting odds NFL NBA major upset",
        "breaking news market moving events today",
        "technology company earnings announcement surprise",
        "geopolitical conflict escalation market impact",
    ]
    
    # Priority news sources for prediction markets
    PRIORITY_SOURCES = [
        'apnews.com',
        'reuters.com', 
        'bloomberg.com',
        'wsj.com',
        'nytimes.com',
        'bbc.com',
        'coindesk.com',
        'theblock.co',
        'fivethirtyeight.com',
        'espn.com',
        'polymarket.com',
    ]
    
    def __init__(self):
        self.api_key = os.environ.get('EXA_API_KEY')
        self._exa_client: Optional[Exa] = None
        
        if not self.api_key:
            logger.warning("[NEWS POLLER] EXA_API_KEY not configured - news polling disabled")
            logger.warning("[NEWS POLLER] To enable: Add EXA_API_KEY to backend/.env")
        elif not EXA_SDK_AVAILABLE:
            logger.error("[NEWS POLLER] exa-py SDK not installed. Run: pip install exa-py")
        else:
            try:
                self._exa_client = Exa(api_key=self.api_key)
                logger.info("[NEWS POLLER] ✅ Exa.ai SDK initialized successfully")
            except Exception as e:
                logger.error(f"[NEWS POLLER] Failed to initialize Exa client: {e}")
        
        # Polling configuration
        self.default_num_results = 10
        self.include_text = True
        
        # Source reliability scores
        self.source_reliability = {
            'apnews.com': 0.95,
            'reuters.com': 0.95,
            'bloomberg.com': 0.90,
            'wsj.com': 0.90,
            'nytimes.com': 0.85,
            'bbc.com': 0.90,
            'coindesk.com': 0.85,
            'cointelegraph.com': 0.80,
            'decrypt.co': 0.80,
            'theblock.co': 0.85,
            'fivethirtyeight.com': 0.90,
            'espn.com': 0.85,
            'twitter.com': 0.60,
            'x.com': 0.60,
            'reddit.com': 0.50,
        }
        
        # Stats tracking
        self._stats = {
            'total_polls': 0,
            'successful_polls': 0,
            'failed_polls': 0,
            'total_events_found': 0,
            'last_poll': None,
            'last_error': None,
        }
    
    async def poll_news(
        self, 
        query: str, 
        num_results: int = None,
        hours_back: int = 24
    ) -> List[NewsEvent]:
        """
        Poll Exa.ai for news related to a query using the official SDK.
        
        Args:
            query: Search query (e.g., "Bitcoin ETF approval SEC")
            num_results: Number of results to return
            hours_back: How far back to search (default 24 hours)
            
        Returns:
            List of NewsEvent objects
        """
        self._stats['total_polls'] += 1
        self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
        
        if not self._exa_client:
            logger.warning("[NEWS POLLER] Skipping poll - Exa client not initialized")
            return []
        
        num_results = num_results or self.default_num_results
        
        try:
            # Calculate date range
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(hours=hours_back)
            
            logger.info(f"[NEWS POLLER] 🔍 Searching: '{query}' (last {hours_back}h, {num_results} results)")
            
            # Use Exa SDK's search_and_contents for semantic search with text extraction
            # Run in executor since exa-py is synchronous
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._exa_client.search_and_contents(
                    query=query,
                    num_results=min(num_results, 100),  # Exa limits to 100
                    type="neural",  # Neural/semantic search
                    use_autoprompt=True,  # Let Exa optimize the query
                    start_published_date=start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    end_published_date=end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    text=True,  # Include article text
                )
            )
            
            events = []
            for result in results.results:
                # Extract source domain from URL
                source = self._extract_source(result.url)
                
                event = NewsEvent(
                    title=result.title or '',
                    url=result.url,
                    source=source,
                    published_date=result.published_date if hasattr(result, 'published_date') else None,
                    text=result.text if hasattr(result, 'text') and result.text else '',
                    score=result.score if hasattr(result, 'score') else 0.5,
                    query=query
                )
                events.append(event)
            
            self._stats['successful_polls'] += 1
            self._stats['total_events_found'] += len(events)
            
            logger.info(f"[NEWS POLLER] ✅ Found {len(events)} news events for '{query}'")
            for event in events[:3]:
                reliability = self.get_source_reliability(event.source)
                logger.info(f"  📰 {event.title[:60]}... ({event.source}, reliability: {reliability:.0%})")
            
            return events
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[NEWS POLLER] ❌ Error polling Exa: {error_msg}")
            self._stats['failed_polls'] += 1
            self._stats['last_error'] = error_msg
            
            # Check for specific error types
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                logger.error("[NEWS POLLER] Invalid API key - check EXA_API_KEY in .env")
            elif "429" in error_msg or "rate" in error_msg.lower():
                logger.warning("[NEWS POLLER] Rate limited - backing off")
            
            return []
    
    async def poll_all_queries(self, hours_back: int = 24) -> List[NewsEvent]:
        """
        Poll all default prediction market queries.
        
        Returns combined results from all queries, deduplicated by URL.
        """
        all_events = []
        seen_urls = set()
        
        for query in self.DEFAULT_QUERIES:
            try:
                events = await self.poll_news(query, hours_back=hours_back)
                
                for event in events:
                    if event.url not in seen_urls:
                        seen_urls.add(event.url)
                        all_events.append(event)
                
                # Small delay between queries to respect rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"[NEWS POLLER] Error with query '{query}': {e}")
                continue
        
        logger.info(f"[NEWS POLLER] 📊 Total unique events from all queries: {len(all_events)}")
        return all_events
    
    def _extract_source(self, url: str) -> str:
        """Extract source domain from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return 'unknown'
    
    def get_source_reliability(self, source: str) -> float:
        """Get reliability score for a news source"""
        source = source.lower()
        for known_source, score in self.source_reliability.items():
            if known_source in source:
                return score
        return 0.50  # Default for unknown sources
    
    def get_stats(self) -> Dict:
        """Get polling statistics"""
        return {
            **self._stats,
            'api_configured': bool(self.api_key),
            'success_rate': (
                self._stats['successful_polls'] / max(1, self._stats['total_polls'])
            )
        }
    
    def is_enabled(self) -> bool:
        """Check if news polling is enabled"""
        return bool(self.api_key)


# Singleton instance
_news_poller: Optional[NewsPoller] = None


def get_news_poller() -> NewsPoller:
    """Get or create the NewsPoller singleton"""
    global _news_poller
    if _news_poller is None:
        _news_poller = NewsPoller()
    return _news_poller
