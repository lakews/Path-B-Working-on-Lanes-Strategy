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
"""

import asyncio
import aiohttp
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Exa.ai API configuration
EXA_API_BASE = "https://api.exa.ai"
EXA_SEARCH_ENDPOINT = f"{EXA_API_BASE}/search"


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
    
    Usage:
        poller = NewsPoller()
        events = await poller.poll_news("Bitcoin ETF approval")
        for event in events:
            # Process with LLM and Bayesian updater
            ...
    """
    
    def __init__(self):
        self.api_key = os.environ.get('EXA_API_KEY')
        if not self.api_key:
            logger.warning("[NEWS POLLER] EXA_API_KEY not configured - news polling disabled")
            logger.warning("[NEWS POLLER] To enable: export EXA_API_KEY='your-key-here'")
        else:
            logger.info("[NEWS POLLER] Exa.ai API key configured ✓")
        
        # Polling configuration
        self.default_num_results = 5
        self.use_autoprompt = True
        self.include_text = True
        
        # Source reliability scores
        self.source_reliability = {
            'apnews.com': 0.95,
            'reuters.com': 0.95,
            'bloomberg.com': 0.90,
            'wsj.com': 0.90,
            'nytimes.com': 0.85,
            'coindesk.com': 0.85,
            'cointelegraph.com': 0.80,
            'decrypt.co': 0.80,
            'theblock.co': 0.85,
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
        Poll Exa.ai for news related to a query.
        
        Args:
            query: Search query (e.g., "Bitcoin ETF approval SEC")
            num_results: Number of results to return
            hours_back: How far back to search (default 24 hours)
            
        Returns:
            List of NewsEvent objects
        """
        self._stats['total_polls'] += 1
        self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
        
        if not self.api_key:
            logger.warning("[NEWS POLLER] Skipping poll - no API key configured")
            return []
        
        num_results = num_results or self.default_num_results
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Content-Type': 'application/json',
                    'x-api-key': self.api_key
                }
                
                payload = {
                    'query': query,
                    'numResults': num_results,
                    'useAutoprompt': self.use_autoprompt,
                    'contents': {
                        'text': self.include_text
                    },
                    'type': 'neural',  # Neural search for semantic matching
                }
                
                logger.info(f"[NEWS POLLER] Searching: '{query}' (last {hours_back}h, {num_results} results)")
                
                async with session.post(
                    EXA_SEARCH_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        results = data.get('results', [])
                        
                        events = []
                        for result in results:
                            # Extract source domain from URL
                            url = result.get('url', '')
                            source = self._extract_source(url)
                            
                            event = NewsEvent(
                                title=result.get('title', ''),
                                url=url,
                                source=source,
                                published_date=result.get('publishedDate'),
                                text=result.get('text', ''),
                                score=result.get('score', 0.0),
                                query=query
                            )
                            events.append(event)
                        
                        self._stats['successful_polls'] += 1
                        self._stats['total_events_found'] += len(events)
                        
                        logger.info(f"[NEWS POLLER] Found {len(events)} news events for '{query}'")
                        for event in events[:3]:
                            logger.debug(f"  - {event.title[:60]}... ({event.source})")
                        
                        return events
                    
                    elif response.status == 401:
                        logger.error("[NEWS POLLER] Invalid API key - check EXA_API_KEY")
                        self._stats['failed_polls'] += 1
                        self._stats['last_error'] = "Invalid API key"
                        return []
                    
                    elif response.status == 429:
                        logger.warning("[NEWS POLLER] Rate limited - backing off")
                        self._stats['failed_polls'] += 1
                        self._stats['last_error'] = "Rate limited"
                        return []
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"[NEWS POLLER] API error {response.status}: {error_text[:200]}")
                        self._stats['failed_polls'] += 1
                        self._stats['last_error'] = f"HTTP {response.status}"
                        return []
        
        except asyncio.TimeoutError:
            logger.error("[NEWS POLLER] Request timed out")
            self._stats['failed_polls'] += 1
            self._stats['last_error'] = "Timeout"
            return []
        
        except aiohttp.ClientError as e:
            logger.error(f"[NEWS POLLER] Network error: {e}")
            self._stats['failed_polls'] += 1
            self._stats['last_error'] = f"Network error: {str(e)}"
            return []
        
        except Exception as e:
            logger.error(f"[NEWS POLLER] Unexpected error: {e}")
            self._stats['failed_polls'] += 1
            self._stats['last_error'] = str(e)
            return []
    
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
