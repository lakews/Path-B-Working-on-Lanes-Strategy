"""
POLYMARKET-OPTIMIZED NEWS SOURCES
=================================

Phase 1 & 2 News Sources for Architecture C (PATH A)

Sources:
1. Finnhub News API - Finance, Crypto, Market news (you have the key!)
2. AP News RSS - Politics, Breaking news (free)
3. Federal Reserve RSS - FOMC decisions (free)  
4. Reuters RSS - All categories (free)
5. ESPN RSS - Sports news (free)

All sources feed into DualPathNewsInjector → PATH A (Architecture C) + PATH B

Created: February 2026
"""

import asyncio
import aiohttp
import feedparser
import logging
import os
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

logger = logging.getLogger(__name__)


class NewsSourceType(Enum):
    FINNHUB = "finnhub"
    AP_RSS = "ap_rss"
    REUTERS_RSS = "reuters_rss"
    FED_RSS = "fed_rss"
    ESPN_RSS = "espn_rss"
    POLITICO_RSS = "politico_rss"
    COINDESK_RSS = "coindesk_rss"


@dataclass
class NewsItem:
    """Standardized news format"""
    headline: str
    content: str
    source: str
    source_type: NewsSourceType
    url: str
    category: str
    priority: str  # 'critical', 'high', 'normal'
    timestamp: datetime
    
    def to_payload(self) -> Dict:
        """Convert to DualPathNewsInjector format"""
        return {
            'headline': self.headline,
            'content': self.content,
            'source': self.source,
            'url': self.url,
            'urgency': self.priority,
            'category': self.category,
            'source_type': self.source_type.value,
            'timestamp': self.timestamp.isoformat()
        }


# =============================================================================
# 1. FINNHUB NEWS API
# =============================================================================

class FinnhubNewsSource:
    """
    Finnhub News API - Finance, Crypto, Market news
    
    Categories covered:
    - general: Market news
    - forex: Currency news
    - crypto: Cryptocurrency news
    - merger: M&A news
    
    Free tier: 60 API calls/minute
    """
    
    # Priority keywords for Polymarket relevance
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'OFFICIAL', 'CONFIRMED', 'FED', 'FOMC', 
                     'RATE CUT', 'RATE HIKE', 'ETF APPROVED', 'HALVING'],
        'high': ['SEC', 'REGULATION', 'BITCOIN', 'ETHEREUM', 'TRUMP', 'BIDEN', 
                 'ELECTION', 'INFLATION', 'GDP', 'JOBS REPORT']
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('FINNHUB_API_KEY')
        self.base_url = "https://finnhub.io/api/v1"
        self._enabled = bool(self.api_key)
        self.last_fetch_time: Optional[datetime] = None
        self._seen_ids: set = set()  # Dedup within session
        
        if self._enabled:
            logger.info("[FINNHUB] ✓ News source initialized")
        else:
            logger.warning("[FINNHUB] No API key - source disabled")
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def _classify_priority(self, text: str) -> str:
        """Classify news priority based on keywords"""
        text_upper = text.upper()
        
        for keyword in self.PRIORITY_KEYWORDS['critical']:
            if keyword in text_upper:
                return 'critical'
        
        for keyword in self.PRIORITY_KEYWORDS['high']:
            if keyword in text_upper:
                return 'high'
        
        return 'normal'
    
    def _detect_category(self, headline: str, finnhub_category: str) -> str:
        """Map to Polymarket categories"""
        headline_lower = headline.lower()
        
        # Crypto detection
        crypto_keywords = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'token', 
                          'blockchain', 'defi', 'nft', 'binance', 'coinbase']
        if any(kw in headline_lower for kw in crypto_keywords) or finnhub_category == 'crypto':
            return 'CRYPTO'
        
        # Politics detection
        politics_keywords = ['trump', 'biden', 'election', 'congress', 'senate', 
                            'white house', 'democrat', 'republican', 'vote']
        if any(kw in headline_lower for kw in politics_keywords):
            return 'POLITICS'
        
        # Finance detection
        finance_keywords = ['fed', 'fomc', 'rate', 'inflation', 'gdp', 'jobs', 
                           'treasury', 'yield', 'stock', 'market']
        if any(kw in headline_lower for kw in finance_keywords):
            return 'FINANCE'
        
        return 'GENERAL'
    
    async def fetch_news(self, category: str = 'general', limit: int = 20) -> List[NewsItem]:
        """
        Fetch news from Finnhub API
        
        Args:
            category: 'general', 'forex', 'crypto', 'merger'
            limit: Max news items to return
        """
        if not self._enabled:
            return []
        
        news_items = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch general market news
                url = f"{self.base_url}/news?category={category}&token={self.api_key}"
                
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for item in data[:limit]:
                            news_id = str(item.get('id', ''))
                            
                            # Skip if already seen
                            if news_id in self._seen_ids:
                                continue
                            self._seen_ids.add(news_id)
                            
                            headline = item.get('headline', '')
                            if not headline:
                                continue
                            
                            # Parse timestamp
                            timestamp = datetime.fromtimestamp(
                                item.get('datetime', 0), 
                                tz=timezone.utc
                            )
                            
                            # Skip old news (>6 hours)
                            age = datetime.now(timezone.utc) - timestamp
                            if age > timedelta(hours=6):
                                continue
                            
                            news_items.append(NewsItem(
                                headline=headline,
                                content=item.get('summary', ''),
                                source=f"Finnhub/{item.get('source', 'unknown')}",
                                source_type=NewsSourceType.FINNHUB,
                                url=item.get('url', ''),
                                category=self._detect_category(headline, category),
                                priority=self._classify_priority(headline),
                                timestamp=timestamp
                            ))
                    else:
                        logger.warning(f"[FINNHUB] API returned {response.status}")
            
            # Keep seen_ids manageable
            if len(self._seen_ids) > 1000:
                self._seen_ids = set(list(self._seen_ids)[-500:])
            
            self.last_fetch_time = datetime.now(timezone.utc)
            logger.info(f"[FINNHUB] Fetched {len(news_items)} news items (category: {category})")
            return news_items
            
        except Exception as e:
            logger.error(f"[FINNHUB] Fetch error: {e}")
            return []
    
    async def fetch_all_categories(self) -> List[NewsItem]:
        """Fetch news from all relevant categories"""
        all_news = []
        categories = ['general', 'crypto']
        
        for category in categories:
            news = await self.fetch_news(category=category, limit=15)
            all_news.extend(news)
            await asyncio.sleep(0.5)  # Rate limit
        
        return all_news


# =============================================================================
# 2. RSS FEED SOURCES
# =============================================================================

class RSSFeedSource:
    """
    Generic RSS feed parser for multiple news sources
    
    Supports:
    - AP News (Politics, Breaking)
    - Reuters (All categories)
    - Federal Reserve (FOMC)
    - ESPN (Sports)
    - Politico (Politics)
    - CoinDesk (Crypto)
    """
    
    # RSS Feed URLs
    FEEDS = {
        'ap_top': {
            'url': 'https://rsshub.app/apnews/topics/apf-topnews',
            'source_type': NewsSourceType.AP_RSS,
            'category': 'GENERAL',
            'source_name': 'AP News'
        },
        'ap_politics': {
            'url': 'https://rsshub.app/apnews/topics/apf-politics',
            'source_type': NewsSourceType.AP_RSS,
            'category': 'POLITICS',
            'source_name': 'AP Politics'
        },
        'reuters_world': {
            'url': 'https://rsshub.app/reuters/world',
            'source_type': NewsSourceType.REUTERS_RSS,
            'category': 'GEOPOLITICS',
            'source_name': 'Reuters World'
        },
        'reuters_business': {
            'url': 'https://rsshub.app/reuters/business',
            'source_type': NewsSourceType.REUTERS_RSS,
            'category': 'FINANCE',
            'source_name': 'Reuters Business'
        },
        'fed_press': {
            'url': 'https://www.federalreserve.gov/feeds/press_all.xml',
            'source_type': NewsSourceType.FED_RSS,
            'category': 'FINANCE',
            'source_name': 'Federal Reserve'
        },
        'espn_top': {
            'url': 'https://www.espn.com/espn/rss/news',
            'source_type': NewsSourceType.ESPN_RSS,
            'category': 'SPORTS',
            'source_name': 'ESPN'
        },
        'espn_nba': {
            'url': 'https://www.espn.com/espn/rss/nba/news',
            'source_type': NewsSourceType.ESPN_RSS,
            'category': 'SPORTS',
            'source_name': 'ESPN NBA'
        },
        'espn_nfl': {
            'url': 'https://www.espn.com/espn/rss/nfl/news',
            'source_type': NewsSourceType.ESPN_RSS,
            'category': 'SPORTS',
            'source_name': 'ESPN NFL'
        },
        'politico': {
            'url': 'https://rss.politico.com/politics-news.xml',
            'source_type': NewsSourceType.POLITICO_RSS,
            'category': 'POLITICS',
            'source_name': 'Politico'
        },
        'coindesk': {
            'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
            'source_type': NewsSourceType.COINDESK_RSS,
            'category': 'CRYPTO',
            'source_name': 'CoinDesk'
        }
    }
    
    # Priority keywords
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'OFFICIAL', 'CONFIRMED', 'WINNER',
                     'ELECTED', 'PASSED', 'FOMC', 'RATE DECISION', 'INJURY'],
        'high': ['SOURCES', 'EXPECTED', 'PLANNING', 'WILL', 'TRADE', 'SIGNS',
                 'OUT FOR', 'QUESTIONABLE', 'DAY-TO-DAY']
    }
    
    def __init__(self):
        self._enabled = True
        self._seen_urls: set = set()  # Dedup by URL
        self._executor = ThreadPoolExecutor(max_workers=4)
        self.stats = {
            'feeds_polled': 0,
            'items_fetched': 0,
            'errors': 0
        }
        logger.info(f"[RSS] ✓ RSS source initialized with {len(self.FEEDS)} feeds")
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def _classify_priority(self, text: str) -> str:
        """Classify news priority"""
        text_upper = text.upper()
        
        for keyword in self.PRIORITY_KEYWORDS['critical']:
            if keyword in text_upper:
                return 'critical'
        
        for keyword in self.PRIORITY_KEYWORDS['high']:
            if keyword in text_upper:
                return 'high'
        
        return 'normal'
    
    def _parse_feed_sync(self, feed_key: str) -> List[NewsItem]:
        """Parse a single RSS feed (sync, runs in executor)"""
        feed_config = self.FEEDS.get(feed_key)
        if not feed_config:
            return []
        
        news_items = []
        
        try:
            feed = feedparser.parse(feed_config['url'])
            
            for entry in feed.entries[:10]:  # Limit per feed
                url = entry.get('link', '')
                
                # Skip if already seen
                if url in self._seen_urls:
                    continue
                self._seen_urls.add(url)
                
                headline = entry.get('title', '')
                if not headline:
                    continue
                
                # Parse timestamp
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published:
                    timestamp = datetime(*published[:6], tzinfo=timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                
                # Skip old news (>4 hours)
                age = datetime.now(timezone.utc) - timestamp
                if age > timedelta(hours=4):
                    continue
                
                content = entry.get('summary', entry.get('description', ''))
                # Clean HTML tags
                import re
                content = re.sub(r'<[^>]+>', '', content)
                
                news_items.append(NewsItem(
                    headline=headline,
                    content=content[:500],  # Truncate
                    source=feed_config['source_name'],
                    source_type=feed_config['source_type'],
                    url=url,
                    category=feed_config['category'],
                    priority=self._classify_priority(headline),
                    timestamp=timestamp
                ))
            
            self.stats['feeds_polled'] += 1
            self.stats['items_fetched'] += len(news_items)
            
        except Exception as e:
            logger.error(f"[RSS] Error parsing {feed_key}: {e}")
            self.stats['errors'] += 1
        
        return news_items
    
    async def fetch_feed(self, feed_key: str) -> List[NewsItem]:
        """Fetch single RSS feed asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._parse_feed_sync, feed_key)
    
    async def fetch_all_feeds(self) -> List[NewsItem]:
        """Fetch all RSS feeds in parallel"""
        all_news = []
        
        # Fetch all feeds concurrently
        tasks = [self.fetch_feed(feed_key) for feed_key in self.FEEDS.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
            elif isinstance(result, Exception):
                logger.debug(f"[RSS] Feed error: {result}")
        
        # Keep seen_urls manageable
        if len(self._seen_urls) > 2000:
            self._seen_urls = set(list(self._seen_urls)[-1000:])
        
        logger.info(f"[RSS] Fetched {len(all_news)} news items from {len(self.FEEDS)} feeds")
        return all_news
    
    async def fetch_by_category(self, category: str) -> List[NewsItem]:
        """Fetch feeds matching a specific category"""
        matching_feeds = [
            key for key, config in self.FEEDS.items() 
            if config['category'] == category
        ]
        
        all_news = []
        for feed_key in matching_feeds:
            news = await self.fetch_feed(feed_key)
            all_news.extend(news)
        
        return all_news
    
    def get_stats(self) -> Dict:
        return self.stats


# =============================================================================
# 3. POLYMARKET NEWS AGGREGATOR (Combines all sources)
# =============================================================================

class PolymarketNewsAggregator:
    """
    Aggregates all news sources optimized for Polymarket prediction markets.
    
    Sources:
    - Finnhub API (Finance, Crypto)
    - RSS Feeds (AP, Reuters, Fed, ESPN, Politico, CoinDesk)
    
    Feeds into: DualPathNewsInjector → PATH A (Architecture C) + PATH B
    """
    
    def __init__(self):
        self.finnhub = FinnhubNewsSource()
        self.rss = RSSFeedSource()
        self.news_callback: Optional[Callable] = None
        self.is_running = False
        self._poll_tasks: List[asyncio.Task] = []
        
        self.stats = {
            'total_news_processed': 0,
            'finnhub_news': 0,
            'rss_news': 0,
            'errors': 0,
            'last_poll': None
        }
        
        logger.info("[NEWS AGG] ✓ Polymarket News Aggregator initialized")
        logger.info(f"  • Finnhub: {'✓ Enabled' if self.finnhub.is_enabled() else '✗ Disabled'}")
        logger.info(f"  • RSS Feeds: {len(self.rss.FEEDS)} feeds configured")
    
    def set_callback(self, callback: Callable):
        """Set the callback for processing news (DualPathNewsInjector.process_news_event)"""
        self.news_callback = callback
        logger.info("[NEWS AGG] News callback set")
    
    async def fetch_all_news(self) -> List[NewsItem]:
        """Fetch news from all sources"""
        all_news = []
        
        # Fetch Finnhub (if enabled)
        if self.finnhub.is_enabled():
            try:
                finnhub_news = await self.finnhub.fetch_all_categories()
                all_news.extend(finnhub_news)
                self.stats['finnhub_news'] += len(finnhub_news)
            except Exception as e:
                logger.error(f"[NEWS AGG] Finnhub error: {e}")
        
        # Fetch RSS feeds
        try:
            rss_news = await self.rss.fetch_all_feeds()
            all_news.extend(rss_news)
            self.stats['rss_news'] += len(rss_news)
        except Exception as e:
            logger.error(f"[NEWS AGG] RSS error: {e}")
        
        # Sort by timestamp (newest first)
        all_news.sort(key=lambda x: x.timestamp, reverse=True)
        
        self.stats['last_poll'] = datetime.now(timezone.utc).isoformat()
        return all_news
    
    async def _poll_loop(self, interval_seconds: int = 120):
        """Main polling loop - fetches all sources and sends to callback"""
        logger.info(f"[NEWS AGG] Starting poll loop ({interval_seconds}s interval)")
        
        while self.is_running:
            try:
                news_items = await self.fetch_all_news()
                
                if news_items and self.news_callback:
                    for news in news_items:
                        try:
                            await self.news_callback(news.to_payload())
                            self.stats['total_news_processed'] += 1
                            await asyncio.sleep(0.2)  # Rate limit
                        except Exception as e:
                            logger.error(f"[NEWS AGG] Callback error: {e}")
                            self.stats['errors'] += 1
                
                logger.info(
                    f"[NEWS AGG] Poll complete: {len(news_items)} items "
                    f"(Finnhub: {self.stats['finnhub_news']}, RSS: {self.stats['rss_news']})"
                )
                
            except Exception as e:
                logger.error(f"[NEWS AGG] Poll error: {e}")
                self.stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def start(self, interval_seconds: int = 120):
        """Start the news aggregator polling"""
        if self.is_running:
            logger.warning("[NEWS AGG] Already running")
            return
        
        self.is_running = True
        self._poll_tasks = [
            asyncio.create_task(self._poll_loop(interval_seconds))
        ]
        
        logger.info("[NEWS AGG] ✓ News aggregator started")
        logger.info(f"  • Poll interval: {interval_seconds}s")
        logger.info(f"  • Finnhub: {'Enabled' if self.finnhub.is_enabled() else 'Disabled'}")
        logger.info(f"  • RSS Feeds: {list(self.rss.FEEDS.keys())}")
    
    async def stop(self):
        """Stop the news aggregator"""
        self.is_running = False
        
        for task in self._poll_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._poll_tasks = []
        logger.info("[NEWS AGG] Stopped")
    
    def get_stats(self) -> Dict:
        """Get aggregator statistics"""
        return {
            **self.stats,
            'finnhub_enabled': self.finnhub.is_enabled(),
            'rss_stats': self.rss.get_stats(),
            'rss_feeds': list(self.rss.FEEDS.keys())
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_news_aggregator: Optional[PolymarketNewsAggregator] = None


def get_news_aggregator() -> PolymarketNewsAggregator:
    """Get or create the PolymarketNewsAggregator instance"""
    global _news_aggregator
    if _news_aggregator is None:
        _news_aggregator = PolymarketNewsAggregator()
    return _news_aggregator


async def init_news_aggregator(news_callback: Callable) -> PolymarketNewsAggregator:
    """Initialize and start the news aggregator"""
    aggregator = get_news_aggregator()
    aggregator.set_callback(news_callback)
    return aggregator
