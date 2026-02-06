"""
WEBHOOK SOURCES SERVICE
=======================

Lane 5 News Enhancement: Multiple webhook sources for real-time news.

Four Sources:
1. APIFY TWITTER SCRAPER - @AP, @WojESPN, @ShamsCharania, @Polymarket
2. WHALE WEBHOOK - Internal Polymarket WebSocket monitor (>$5k trades)
3. CRYPTOPANIC RSS - Real-time crypto news via RSS feed (FREE, no delay!)
4. CRYPTOPANIC API - DISABLED (24h delay on free tier = toxic for trading)

Architecture:
    WebhookSources -> NewsInjector -> LLM -> EventBayes -> SignalCache -> HFT

Created: February 2026
Updated: February 2026 - Swapped CryptoPanic API for RSS (real-time)
"""

import asyncio
import aiohttp
import logging
import os
import feedparser
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Callable, Any, Set
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WebhookSourceType(Enum):
    APIFY_TWITTER = "apify_twitter"
    WHALE_ALERT = "whale_alert"
    CRYPTOPANIC_RSS = "cryptopanic_rss"  # Real-time RSS feed
    CRYPTOPANIC_API = "cryptopanic_api"  # DISABLED - 24h delay


@dataclass
class WebhookNews:
    """Standardized news format from any webhook source"""
    headline: str
    content: str
    source: str
    source_type: WebhookSourceType
    url: str
    priority: str  # 'critical', 'high', 'normal'
    metadata: Dict
    timestamp: datetime
    
    def to_news_payload(self) -> Dict:
        """Convert to NewsInjector payload format"""
        return {
            'headline': self.headline,
            'content': self.content,
            'source': self.source,
            'url': self.url,
            'priority': self.priority,
            'source_type': self.source_type.value,
            'metadata': self.metadata
        }


# =============================================================================
# 1. APIFY TWITTER SCRAPER
# =============================================================================

class ApifyTwitterSource:
    """
    Polls Apify Twitter Scraper for tweets from key accounts.
    
    Targets:
    - @AP (Associated Press) - Breaking news
    - @WojESPN (Adrian Wojnarowski) - NBA insider
    - @ShamsCharania (Shams Charania) - NBA insider  
    - @Polymarket - Official resolution sources
    
    Cost: ~$49/month for regular polling
    """
    
    # High-value Twitter accounts for prediction markets
    TARGET_ACCOUNTS = [
        'AP',              # Associated Press - breaking news
        'WojESPN',         # Adrian Wojnarowski - NBA insider
        'ShamsCharania',   # Shams Charania - NBA insider
        'Polymarket',      # Official Polymarket account
        'Reuters',         # Reuters breaking news
        'WSJ',             # Wall Street Journal
        'FiveThirtyEight', # Election/polling data
    ]
    
    # Keywords that indicate high-priority news
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'OFFICIAL', 'CONFIRMED', 'WINNER', 'ELECTED', 'PASSED', 'RESOLVED'],
        'high': ['Sources:', 'per sources', 'I\'m told', 'Expected to', 'Planning to', 'Breaking:'],
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('APIFY_API_KEY')
        self.base_url = "https://api.apify.com/v2"
        self.actor_id = "apidojo/tweet-scraper"  # Apify's Twitter scraper actor
        self.last_tweet_ids: Dict[str, str] = {}  # Track last seen tweet per account
        self._enabled = bool(self.api_key)
        
        if self._enabled:
            logger.info(f"[APIFY] Twitter source initialized for {len(self.TARGET_ACCOUNTS)} accounts")
        else:
            logger.warning("[APIFY] No API key - Twitter source disabled")
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def _classify_priority(self, text: str) -> str:
        """Classify tweet priority based on keywords"""
        text_upper = text.upper()
        
        for keyword in self.PRIORITY_KEYWORDS['critical']:
            if keyword.upper() in text_upper:
                return 'critical'
        
        for keyword in self.PRIORITY_KEYWORDS['high']:
            if keyword.lower() in text.lower():
                return 'high'
        
        return 'normal'
    
    async def fetch_recent_tweets(self, hours_back: int = 1) -> List[WebhookNews]:
        """
        Fetch recent tweets from target accounts using Apify.
        
        Uses Apify's Twitter Scraper actor to get tweets.
        """
        if not self._enabled:
            return []
        
        all_news = []
        
        try:
            async with aiohttp.ClientSession() as session:
                for account in self.TARGET_ACCOUNTS:
                    try:
                        # Run the Apify actor for this account
                        news_items = await self._fetch_account_tweets(session, account, hours_back)
                        all_news.extend(news_items)
                        
                        # Rate limit between accounts
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"[APIFY] Error fetching @{account}: {e}")
                        continue
            
            logger.info(f"[APIFY] Fetched {len(all_news)} tweets from {len(self.TARGET_ACCOUNTS)} accounts")
            return all_news
            
        except Exception as e:
            logger.error(f"[APIFY] Fetch error: {e}")
            return []
    
    async def _fetch_account_tweets(
        self, 
        session: aiohttp.ClientSession, 
        account: str,
        hours_back: int
    ) -> List[WebhookNews]:
        """Fetch tweets from a single account"""
        
        # Apify actor input
        actor_input = {
            "handles": [account],
            "tweetsDesired": 10,
            "proxyConfig": {"useApifyProxy": True},
        }
        
        # Start actor run
        run_url = f"{self.base_url}/acts/{self.actor_id}/runs"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        async with session.post(run_url, json=actor_input, headers=headers) as resp:
            if resp.status != 201:
                logger.warning(f"[APIFY] Failed to start actor for @{account}: {resp.status}")
                return []
            
            run_data = await resp.json()
            run_id = run_data.get('data', {}).get('id')
        
        if not run_id:
            return []
        
        # Wait for completion (with timeout)
        status_url = f"{self.base_url}/actor-runs/{run_id}"
        for _ in range(30):  # 30 second timeout
            await asyncio.sleep(1)
            
            async with session.get(status_url, headers=headers) as resp:
                if resp.status != 200:
                    continue
                status_data = await resp.json()
                status = status_data.get('data', {}).get('status')
                
                if status == 'SUCCEEDED':
                    break
                elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                    logger.warning(f"[APIFY] Actor run failed for @{account}: {status}")
                    return []
        
        # Get results from dataset
        dataset_id = status_data.get('data', {}).get('defaultDatasetId')
        if not dataset_id:
            return []
        
        dataset_url = f"{self.base_url}/datasets/{dataset_id}/items"
        async with session.get(dataset_url, headers=headers) as resp:
            if resp.status != 200:
                return []
            tweets = await resp.json()
        
        # Convert to WebhookNews format
        news_items = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        for tweet in tweets:
            try:
                # Parse tweet timestamp
                created_at_str = tweet.get('createdAt', '')
                if created_at_str:
                    tweet_time = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                else:
                    tweet_time = datetime.now(timezone.utc)
                
                # Skip old tweets
                if tweet_time < cutoff_time:
                    continue
                
                tweet_text = tweet.get('text', '')
                tweet_id = tweet.get('id', '')
                
                # Skip if we've seen this tweet
                if self.last_tweet_ids.get(account) == tweet_id:
                    continue
                
                self.last_tweet_ids[account] = tweet_id
                
                news_items.append(WebhookNews(
                    headline=f"@{account}: {tweet_text[:100]}",
                    content=tweet_text,
                    source=f"twitter.com/{account}",
                    source_type=WebhookSourceType.APIFY_TWITTER,
                    url=f"https://twitter.com/{account}/status/{tweet_id}",
                    priority=self._classify_priority(tweet_text),
                    metadata={
                        'account': account,
                        'tweet_id': tweet_id,
                        'likes': tweet.get('likeCount', 0),
                        'retweets': tweet.get('retweetCount', 0),
                    },
                    timestamp=tweet_time
                ))
                
            except Exception as e:
                logger.debug(f"[APIFY] Error parsing tweet: {e}")
                continue
        
        return news_items


# =============================================================================
# 2. WHALE WEBHOOK (Internal Polymarket Monitor)
# =============================================================================

class WhaleAlertSource:
    """
    Internal service that monitors Polymarket WebSocket for large trades.
    
    When a trade > $5,000 occurs, it generates a webhook-style alert
    that gets processed through the news pipeline.
    
    Logic: Large trades often indicate insider knowledge or strong conviction.
    
    Cost: Free (uses existing WebSocket connection)
    """
    
    def __init__(self, threshold_usd: float = None):
        self.threshold_usd = threshold_usd or float(os.environ.get('WHALE_THRESHOLD_USD', '5000'))
        self._callback: Optional[Callable] = None
        self._enabled = True
        self._recent_alerts: List[Dict] = []  # Track recent alerts to avoid duplicates
        
        logger.info(f"[WHALE] Alert source initialized with threshold ${self.threshold_usd:,.0f}")
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def set_callback(self, callback: Callable):
        """Set callback function to be called when whale trade detected"""
        self._callback = callback
    
    async def process_trade(self, trade_data: Dict) -> Optional[WebhookNews]:
        """
        Process a trade from Polymarket WebSocket.
        
        Called by the WebSocket handler for each trade.
        Returns WebhookNews if trade exceeds threshold.
        """
        try:
            # Extract trade details
            size_usd = float(trade_data.get('size', 0)) * float(trade_data.get('price', 0))
            
            if size_usd < self.threshold_usd:
                return None
            
            market_id = trade_data.get('market', trade_data.get('asset_id', 'unknown'))
            side = trade_data.get('side', 'unknown').upper()
            price = float(trade_data.get('price', 0))
            
            # Create alert
            headline = f"🐋 WHALE ALERT: ${size_usd:,.0f} {side} @ {price:.2f}c"
            
            # Determine priority based on size
            if size_usd >= 50000:
                priority = 'critical'
            elif size_usd >= 20000:
                priority = 'high'
            else:
                priority = 'normal'
            
            news = WebhookNews(
                headline=headline,
                content=f"Large trade detected on Polymarket. {side} position worth ${size_usd:,.0f} at price {price:.2f} cents. Market: {market_id[:20]}...",
                source="polymarket_websocket",
                source_type=WebhookSourceType.WHALE_ALERT,
                url=f"https://polymarket.com/event/{market_id}",
                priority=priority,
                metadata={
                    'market_id': market_id,
                    'side': side,
                    'price': price,
                    'size_usd': size_usd,
                    'threshold': self.threshold_usd,
                },
                timestamp=datetime.now(timezone.utc)
            )
            
            # Track recent alerts
            self._recent_alerts.append({
                'market_id': market_id,
                'size_usd': size_usd,
                'timestamp': datetime.now(timezone.utc)
            })
            self._recent_alerts = self._recent_alerts[-100:]  # Keep last 100
            
            logger.info(f"[WHALE] 🐋 Alert: ${size_usd:,.0f} {side} on {market_id[:16]}...")
            
            # Trigger callback if set
            if self._callback:
                asyncio.create_task(self._callback(news))
            
            return news
            
        except Exception as e:
            logger.error(f"[WHALE] Error processing trade: {e}")
            return None
    
    def get_recent_alerts(self) -> List[Dict]:
        """Get recent whale alerts"""
        return self._recent_alerts.copy()


# =============================================================================
# 3. CRYPTOPANIC RSS (Real-time, FREE!)
# =============================================================================

class CryptoPanicRSSSource:
    """
    Real-time CryptoPanic news via RSS feed.
    
    This replaces the API poller which has a 24-hour delay on the free tier.
    The RSS feed is FREE and provides REAL-TIME news!
    
    RSS Feed: https://cryptopanic.com/news/rss/
    Polling: Every 5 minutes (300 seconds)
    
    Features:
    - No API key required
    - Real-time news (no 24h delay)
    - Deduplication via seen_links set
    - First-run startup protection (don't spam old news)
    """
    
    RSS_URL = "https://cryptopanic.com/news/rss/"
    
    # Priority keywords for crypto news
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'URGENT', 'HACK', 'EXPLOIT', 'CRASH', 'DUMP'],
        'high': ['SEC', 'ETF', 'APPROVED', 'REJECTED', 'REGULATION', 'BAN', 'LAWSUIT', 
                 'BITCOIN', 'ETHEREUM', 'BINANCE', 'COINBASE', 'FED', 'RATE'],
    }
    
    def __init__(self):
        self._enabled = True
        self._seen_links: Set[str] = set()
        self._first_run = True
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._stats = {
            'polls': 0,
            'items_found': 0,
            'new_items': 0,
            'last_poll': None,
        }
        
        logger.info("[CRYPTOPANIC RSS] ✅ Real-time RSS source initialized (FREE, no delay!)")
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def _classify_priority(self, title: str) -> str:
        """Classify news priority based on keywords"""
        title_upper = title.upper()
        
        for keyword in self.PRIORITY_KEYWORDS['critical']:
            if keyword in title_upper:
                return 'critical'
        
        for keyword in self.PRIORITY_KEYWORDS['high']:
            if keyword in title_upper:
                return 'high'
        
        return 'normal'
    
    def _parse_feed_sync(self) -> List[Dict]:
        """Synchronous feed parsing (runs in executor)"""
        try:
            feed = feedparser.parse(self.RSS_URL)
            return feed.entries
        except Exception as e:
            logger.error(f"[CRYPTOPANIC RSS] Parse error: {e}")
            return []
    
    async def fetch_news(self) -> List[WebhookNews]:
        """
        Fetch news from CryptoPanic RSS feed.
        
        On first run: Populates seen_links without returning items (prevents old news spam).
        On subsequent runs: Returns only NEW items not in seen_links.
        """
        self._stats['polls'] += 1
        self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
        
        try:
            # Parse feed in executor (non-blocking)
            loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(self._executor, self._parse_feed_sync)
            
            self._stats['items_found'] = len(entries)
            
            if not entries:
                logger.warning("[CRYPTOPANIC RSS] No entries in feed")
                return []
            
            # First run: populate seen_links, don't return anything
            if self._first_run:
                for entry in entries:
                    link = entry.get('link', '')
                    if link:
                        self._seen_links.add(link)
                
                self._first_run = False
                logger.info(f"[CRYPTOPANIC RSS] First run: cached {len(self._seen_links)} existing links (no alerts sent)")
                return []
            
            # Subsequent runs: find new items
            new_items = []
            for entry in entries:
                link = entry.get('link', '')
                
                # Skip if already seen
                if link in self._seen_links:
                    continue
                
                # Mark as seen
                self._seen_links.add(link)
                
                # Keep seen_links bounded (max 1000)
                if len(self._seen_links) > 1000:
                    # Remove oldest (convert to list, slice, back to set)
                    self._seen_links = set(list(self._seen_links)[-500:])
                
                title = entry.get('title', '')
                source = entry.get('source', {}).get('title', 'CryptoPanic') if isinstance(entry.get('source'), dict) else 'CryptoPanic'
                
                # Parse published date
                published = entry.get('published_parsed')
                if published:
                    try:
                        timestamp = datetime(*published[:6], tzinfo=timezone.utc)
                    except:
                        timestamp = datetime.now(timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                
                news = WebhookNews(
                    headline=title,
                    content=entry.get('summary', title),
                    source=source,
                    source_type=WebhookSourceType.CRYPTOPANIC_RSS,
                    url=link,
                    priority=self._classify_priority(title),
                    metadata={
                        'rss_id': entry.get('id', link),
                        'tags': [tag.get('term', '') for tag in entry.get('tags', [])],
                    },
                    timestamp=timestamp
                )
                new_items.append(news)
            
            self._stats['new_items'] += len(new_items)
            
            if new_items:
                logger.info(f"[CRYPTOPANIC RSS] 📰 Found {len(new_items)} NEW items")
                for item in new_items[:3]:
                    logger.info(f"  → {item.headline[:60]}... [{item.priority}]")
            
            return new_items
            
        except Exception as e:
            logger.error(f"[CRYPTOPANIC RSS] Error: {e}")
            return []
    
    def get_stats(self) -> Dict:
        return {
            **self._stats,
            'seen_links_count': len(self._seen_links),
            'first_run_complete': not self._first_run,
        }


# =============================================================================
# 4. CRYPTOPANIC API (DISABLED - 24h delay is toxic for trading)
# =============================================================================

class CryptoPanicAPISource:
    """
    ⚠️ DISABLED: CryptoPanic API Poller
    
    The free tier (DEVELOPER) has a 24-HOUR DELAY on news.
    This is TOXIC for trading - by the time we get the news, it's already priced in.
    
    Use CryptoPanicRSSSource instead (real-time, free).
    
    To re-enable: Upgrade to GROWTH plan ($199/mo) for real-time API access.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        # DISABLED - Do not use API with 24h delay
        self._enabled = False
        logger.warning("[CRYPTOPANIC API] ⚠️ DISABLED - 24h delay is toxic for trading. Using RSS instead.")
    
    def is_enabled(self) -> bool:
        return False  # Always disabled
    
    async def fetch_recent_news(self, limit: int = 20) -> List[WebhookNews]:
        # Return empty - API is disabled
        return []


# =============================================================================
# LEGACY: CryptoPanicSource (aliased to disabled API for backwards compatibility)
# =============================================================================

class CryptoPanicSource(CryptoPanicAPISource):
    """
    Legacy alias - redirects to disabled API source.
    Use CryptoPanicRSSSource for real-time news.
    """
    pass


# =============================================================================
# UNIFIED WEBHOOK SOURCES MANAGER
# =============================================================================

class WebhookSourcesManager:
    """
    Manages all webhook sources and coordinates polling.
    
    Active Sources:
    - Apify Twitter: @AP, @WojESPN, etc.
    - Whale Alert: Polymarket large trades
    - CryptoPanic RSS: Real-time crypto news (FREE!)
    
    Disabled:
    - CryptoPanic API: 24h delay = toxic for trading
    """
    
    def __init__(self, news_callback: Optional[Callable] = None):
        """
        Args:
            news_callback: Async function to call with WebhookNews items
                          Typically NewsInjector.process_news()
        """
        self.news_callback = news_callback
        
        # Initialize sources
        self.apify = ApifyTwitterSource()
        self.whale = WhaleAlertSource()
        self.cryptopanic_rss = CryptoPanicRSSSource()  # Real-time RSS (active)
        self.cryptopanic_api = CryptoPanicAPISource()  # API disabled (24h delay)
        
        # Legacy alias
        self.cryptopanic = self.cryptopanic_rss
        
        # Set up whale callback
        if news_callback:
            self.whale.set_callback(self._handle_whale_alert)
        
        # Polling state
        self.is_running = False
        self._poll_tasks: List[asyncio.Task] = []
        
        # Stats
        self._stats = {
            'apify_polls': 0,
            'apify_items': 0,
            'whale_alerts': 0,
            'cryptopanic_rss_polls': 0,
            'cryptopanic_rss_items': 0,
            'last_poll': None,
            'errors': 0,
        }
        
        logger.info(f"[WEBHOOK SOURCES] Manager initialized")
        logger.info(f"  - Apify Twitter: {'✅ Enabled' if self.apify.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - Whale Alerts: {'✅ Enabled' if self.whale.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - CryptoPanic RSS: {'✅ Enabled (REAL-TIME!)' if self.cryptopanic_rss.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - CryptoPanic API: ❌ Disabled (24h delay = toxic)")
    
    async def _handle_whale_alert(self, news: WebhookNews):
        """Handle whale alert from internal monitor"""
        self._stats['whale_alerts'] += 1
        
        if self.news_callback:
            try:
                await self.news_callback(news.to_news_payload())
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] Error processing whale alert: {e}")
                self._stats['errors'] += 1
    
    async def _poll_apify(self, interval_seconds: int = 300):
        """Poll Apify Twitter scraper (default every 5 minutes)"""
        logger.info(f"[WEBHOOK SOURCES] Apify poll loop started ({interval_seconds}s interval)")
        
        while self.is_running:
            try:
                if self.apify.is_enabled():
                    news_items = await self.apify.fetch_recent_tweets(hours_back=1)
                    self._stats['apify_polls'] += 1
                    self._stats['apify_items'] += len(news_items)
                    
                    for news in news_items:
                        if self.news_callback:
                            await self.news_callback(news.to_news_payload())
                        await asyncio.sleep(0.5)  # Rate limit
                
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] Apify poll error: {e}")
                self._stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def _poll_cryptopanic_rss(self, interval_seconds: int = 300):
        """Poll CryptoPanic RSS feed (default every 5 minutes)"""
        logger.info(f"[WEBHOOK SOURCES] CryptoPanic RSS poll loop started ({interval_seconds}s interval)")
        
        while self.is_running:
            try:
                news_items = await self.cryptopanic_rss.fetch_news()
                self._stats['cryptopanic_rss_polls'] += 1
                self._stats['cryptopanic_rss_items'] += len(news_items)
                self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
                
                for news in news_items:
                    if self.news_callback:
                        await self.news_callback(news.to_news_payload())
                    await asyncio.sleep(0.3)  # Rate limit
                
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] CryptoPanic RSS poll error: {e}")
                self._stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def start(self):
        """Start all polling loops"""
        if self.is_running:
            logger.warning("[WEBHOOK SOURCES] Already running")
            return
        
        self.is_running = True
        
        # Start poll tasks
        self._poll_tasks = [
            asyncio.create_task(self._poll_apify(interval_seconds=300)),           # 5 min
            asyncio.create_task(self._poll_cryptopanic_rss(interval_seconds=300)), # 5 min
        ]
        
        logger.info("[WEBHOOK SOURCES] All polling loops started")
        logger.info("  📰 Apify Twitter: every 5 min")
        logger.info("  📰 CryptoPanic RSS: every 5 min (REAL-TIME news!)")
        logger.info("  🐋 Whale Alerts: real-time via WebSocket")
    
    async def stop(self):
        """Stop all polling loops"""
        self.is_running = False
        
        for task in self._poll_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._poll_tasks = []
        logger.info("[WEBHOOK SOURCES] All polling loops stopped")
    
    def process_websocket_trade(self, trade_data: Dict):
        """
        Called by Polymarket WebSocket handler for each trade.
        Checks if trade qualifies as whale alert.
        """
        asyncio.create_task(self.whale.process_trade(trade_data))
    
    def get_stats(self) -> Dict:
        """Get webhook sources statistics"""
        return {
            **self._stats,
            'sources': {
                'apify_enabled': self.apify.is_enabled(),
                'whale_enabled': self.whale.is_enabled(),
                'cryptopanic_rss_enabled': self.cryptopanic_rss.is_enabled(),
                'cryptopanic_api_enabled': False,  # Always disabled
            },
            'whale_threshold': self.whale.threshold_usd,
            'whale_recent_alerts': len(self.whale.get_recent_alerts()),
            'cryptopanic_rss_stats': self.cryptopanic_rss.get_stats(),
        }
        
        logger.info(f"[WEBHOOK SOURCES] Manager initialized")
        logger.info(f"  - Apify Twitter: {'✅ Enabled' if self.apify.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - Whale Alerts: {'✅ Enabled' if self.whale.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - CryptoPanic: {'✅ Enabled' if self.cryptopanic.is_enabled() else '❌ Disabled'}")
    
    async def _handle_whale_alert(self, news: WebhookNews):
        """Handle whale alert from internal monitor"""
        self._stats['whale_alerts'] += 1
        
        if self.news_callback:
            try:
                await self.news_callback(news.to_news_payload())
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] Error processing whale alert: {e}")
                self._stats['errors'] += 1
    
    async def _poll_apify(self, interval_seconds: int = 300):
        """Poll Apify Twitter scraper (default every 5 minutes)"""
        logger.info(f"[WEBHOOK SOURCES] Apify poll loop started ({interval_seconds}s interval)")
        
        while self.is_running:
            try:
                if self.apify.is_enabled():
                    news_items = await self.apify.fetch_recent_tweets(hours_back=1)
                    self._stats['apify_polls'] += 1
                    self._stats['apify_items'] += len(news_items)
                    
                    for news in news_items:
                        if self.news_callback:
                            await self.news_callback(news.to_news_payload())
                        await asyncio.sleep(0.5)  # Rate limit
                
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] Apify poll error: {e}")
                self._stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def _poll_cryptopanic(self, interval_seconds: int = 60):
        """Poll CryptoPanic API (default every 60 seconds)"""
        logger.info(f"[WEBHOOK SOURCES] CryptoPanic poll loop started ({interval_seconds}s interval)")
        
        while self.is_running:
            try:
                if self.cryptopanic.is_enabled():
                    news_items = await self.cryptopanic.fetch_recent_news(limit=10)
                    self._stats['cryptopanic_polls'] += 1
                    self._stats['cryptopanic_items'] += len(news_items)
                    self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
                    
                    for news in news_items:
                        if self.news_callback:
                            await self.news_callback(news.to_news_payload())
                        await asyncio.sleep(0.3)  # Rate limit
                
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] CryptoPanic poll error: {e}")
                self._stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def start(self):
        """Start all polling loops"""
        if self.is_running:
            logger.warning("[WEBHOOK SOURCES] Already running")
            return
        
        self.is_running = True
        
        # Start poll tasks
        self._poll_tasks = [
            asyncio.create_task(self._poll_apify(interval_seconds=300)),      # 5 min
            asyncio.create_task(self._poll_cryptopanic(interval_seconds=60)), # 1 min
        ]
        
        logger.info("[WEBHOOK SOURCES] All polling loops started")
    
    async def stop(self):
        """Stop all polling loops"""
        self.is_running = False
        
        for task in self._poll_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._poll_tasks = []
        logger.info("[WEBHOOK SOURCES] All polling loops stopped")
    
    def process_websocket_trade(self, trade_data: Dict):
        """
        Called by Polymarket WebSocket handler for each trade.
        Checks if trade qualifies as whale alert.
        """
        asyncio.create_task(self.whale.process_trade(trade_data))
    
    def get_stats(self) -> Dict:
        """Get webhook sources statistics"""
        return {
            **self._stats,
            'sources': {
                'apify_enabled': self.apify.is_enabled(),
                'whale_enabled': self.whale.is_enabled(),
                'cryptopanic_enabled': self.cryptopanic.is_enabled(),
            },
            'whale_threshold': self.whale.threshold_usd,
            'whale_recent_alerts': len(self.whale.get_recent_alerts()),
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_webhook_sources_manager: Optional[WebhookSourcesManager] = None


def get_webhook_sources_manager(news_callback: Optional[Callable] = None) -> WebhookSourcesManager:
    """Get or create the WebhookSourcesManager instance"""
    global _webhook_sources_manager
    if _webhook_sources_manager is None:
        _webhook_sources_manager = WebhookSourcesManager(news_callback=news_callback)
    return _webhook_sources_manager
