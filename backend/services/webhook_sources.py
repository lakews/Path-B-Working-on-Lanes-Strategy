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
    Apify/CryptoPanic -> NewsInjector -> LLM -> EventBayes -> SignalCache -> HFT
    Whale Alerts -> DIRECT INJECTION -> SignalCache -> HFT (skip LLM - already quantified)

Created: February 2026
Updated: February 2026 - Whale Alert Direct Injection (skip LLM for speed)
"""

import asyncio
import aiohttp
import logging
import os
from typing import Dict, List, Optional, Callable, Any
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
    
    # ==========================================================================
    # TARGET ACCOUNTS (Merged: Politics + Sports + Crypto Alpha)
    # ==========================================================================
    # 
    # POLITICAL / BREAKING NEWS
    # -------------------------
    # @AP              - Associated Press (gold standard)
    # @Reuters         - Reuters (gold standard)
    # @WSJ             - Wall Street Journal
    # @FiveThirtyEight - Election/polling data
    #
    # SPORTS INSIDERS
    # ---------------
    # @WojESPN         - Adrian Wojnarowski (NBA)
    # @ShamsCharania   - Shams Charania (NBA)
    #
    # PREDICTION MARKETS
    # ------------------
    # @Polymarket      - Official Polymarket account
    #
    # CRYPTO ALPHA (NEW - High Signal)
    # --------------------------------
    # @Tier10k         - Essential: Fast breaking financial news
    # @WuBlockchain    - Essential: Asian market flows/regulation
    # @WatcherGuru     - Fastest headlines (sometimes noisy)
    # @CoinDesk        - Standard major reporting
    # @Cointelegraph   - Standard major reporting
    # @Tree_of_Alpha   - High signal trader news
    # @TheBlock__      - Deep industry reporting
    # @db              - Deltaone (Bloomberg terminal feed, extremely fast)
    #
    TARGET_ACCOUNTS = [
        # === BREAKING NEWS (Politics/General) ===
        'AP',              # Associated Press - breaking news
        'Reuters',         # Reuters breaking news
        'WSJ',             # Wall Street Journal
        'FiveThirtyEight', # Election/polling data
        
        # === SPORTS INSIDERS ===
        'WojESPN',         # Adrian Wojnarowski - NBA insider
        'ShamsCharania',   # Shams Charania - NBA insider
        
        # === PREDICTION MARKETS ===
        'Polymarket',      # Official Polymarket account
        
        # === CRYPTO ALPHA (High Signal) ===
        'Tier10k',         # Essential: Fast breaking financial news
        'WuBlockchain',    # Essential: Asian market flows/regulation
        'WatcherGuru',     # Fastest crypto headlines
        'CoinDesk',        # Standard major crypto reporting
        'Cointelegraph',   # Standard major crypto reporting
        'Tree_of_Alpha',   # High signal trader news
        'TheBlock__',      # Deep crypto industry reporting
        'db',              # Deltaone - Bloomberg terminal feed
    ]
    
    # Keywords that indicate high-priority news
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'OFFICIAL', 'CONFIRMED', 'WINNER', 'ELECTED', 'PASSED', 'RESOLVED'],
        'high': ['Sources:', 'per sources', 'I\'m told', 'Expected to', 'Planning to', 'Breaking:'],
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('APIFY_API_KEY')
        self.base_url = "https://api.apify.com/v2"
        # NOTE: Apify uses ~ not / for actor IDs in API calls
        self.actor_id = "apidojo~tweet-scraper"  # Tweet Scraper V2
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
    
    async def fetch_recent_tweets(self, hours_back: int = 1, max_concurrent: int = 5) -> List[WebhookNews]:
        """
        Fetch recent tweets from target accounts using Apify.
        
        Uses Apify's Twitter Scraper actor to get tweets.
        Now runs multiple accounts in parallel for speed.
        
        Args:
            hours_back: How many hours of tweets to fetch
            max_concurrent: Max parallel Apify actor runs (default 5)
        """
        if not self._enabled:
            return []
        
        all_news = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use semaphore to limit concurrent requests
                semaphore = asyncio.Semaphore(max_concurrent)
                
                async def fetch_with_semaphore(account: str) -> List[WebhookNews]:
                    async with semaphore:
                        try:
                            return await self._fetch_account_tweets(session, account, hours_back)
                        except asyncio.TimeoutError:
                            logger.warning(f"[APIFY] Timeout fetching @{account}")
                            return []
                        except Exception as e:
                            logger.error(f"[APIFY] Error fetching @{account}: {e}")
                            return []
                
                # Fetch all accounts in parallel (limited by semaphore)
                tasks = [fetch_with_semaphore(account) for account in self.TARGET_ACCOUNTS]
                
                # Wait for all with overall timeout of 60 seconds
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=60.0
                    )
                    
                    for result in results:
                        if isinstance(result, list):
                            all_news.extend(result)
                        elif isinstance(result, Exception):
                            logger.debug(f"[APIFY] Task exception: {result}")
                            
                except asyncio.TimeoutError:
                    logger.warning("[APIFY] Overall fetch timeout (60s) - returning partial results")
            
            logger.info(f"[APIFY] Fetched {len(all_news)} tweets from {len(self.TARGET_ACCOUNTS)} accounts")
            return all_news
            
        except Exception as e:
            logger.error(f"[APIFY] Fetch error: {e}")
            return []
    
    async def _fetch_account_tweets(
        self, 
        session: aiohttp.ClientSession, 
        account: str,
        hours_back: int,
        timeout_seconds: int = 15
    ) -> List[WebhookNews]:
        """Fetch tweets from a single account using apidojo/tweet-scraper"""
        
        # apidojo/tweet-scraper V2 input format (startUrls is most reliable)
        actor_input = {
            "startUrls": [f"https://twitter.com/{account}"],
            "maxTweets": 5,  # Reduced from 10 for faster completion
            "sort": "Latest",
            "proxyConfig": {"useApifyProxy": True},
        }
        
        # Start actor run
        run_url = f"{self.base_url}/acts/{self.actor_id}/runs"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            async with session.post(run_url, json=actor_input, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 201:
                    logger.warning(f"[APIFY] Failed to start actor for @{account}: {resp.status}")
                    return []
                
                run_data = await resp.json()
                run_id = run_data.get('data', {}).get('id')
        except asyncio.TimeoutError:
            logger.warning(f"[APIFY] Timeout starting actor for @{account}")
            return []
        
        if not run_id:
            return []
        
        # Wait for completion (with reduced timeout)
        status_url = f"{self.base_url}/actor-runs/{run_id}"
        status_data = None
        for _ in range(timeout_seconds):  # Reduced timeout per account
            await asyncio.sleep(1)
            
            try:
                async with session.get(status_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        continue
                    status_data = await resp.json()
                    status = status_data.get('data', {}).get('status')
                    
                    if status == 'SUCCEEDED':
                        break
                    elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                        logger.warning(f"[APIFY] Actor run failed for @{account}: {status}")
                        return []
            except asyncio.TimeoutError:
                continue
        
        # Get results from dataset
        dataset_id = status_data.get('data', {}).get('defaultDatasetId')
        if not dataset_id:
            return []
        
        dataset_url = f"{self.base_url}/datasets/{dataset_id}/items"
        async with session.get(dataset_url, headers=headers) as resp:
            if resp.status != 200:
                return []
            tweets = await resp.json()
        
        # Log raw structure for debugging (first item only)
        if tweets:
            logger.info(f"[APIFY] Raw tweet keys for @{account}: {list(tweets[0].keys())[:10]}")
        
        # Convert to WebhookNews format using robust extraction
        news_items = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        for tweet in tweets:
            try:
                # Extract tweet data using robust helper (handles multiple schemas)
                extracted = self._extract_tweet_data(tweet)
                
                if not extracted:
                    logger.debug("[APIFY] Could not extract data from tweet structure")
                    continue
                
                tweet_text = extracted['text']
                tweet_id = extracted['id']
                tweet_time = extracted['timestamp']
                
                # Skip old tweets
                if tweet_time < cutoff_time:
                    continue
                
                # Skip empty tweets
                if not tweet_text.strip():
                    continue
                
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
                        'likes': extracted.get('likes', 0),
                        'retweets': extracted.get('retweets', 0),
                        'schema': extracted.get('schema', 'unknown'),
                    },
                    timestamp=tweet_time
                ))
                
            except Exception as e:
                logger.debug(f"[APIFY] Error parsing tweet: {e}")
                continue
        
        return news_items
    
    def _extract_tweet_data(self, item: Dict) -> Optional[Dict]:
        """
        Robust tweet data extraction that handles multiple JSON schemas.
        
        apidojo/tweet-scraper returns complex nested structures that can vary:
        - Standard format: item['text'], item['id'], item['createdAt']
        - Legacy format: item['legacy']['full_text']
        - GraphQL format: item['content']['itemContent']['tweet_results']['result']['legacy']
        
        Returns dict with: text, id, timestamp, likes, retweets, schema
        """
        
        # ====================================================================
        # SCHEMA 1: Standard/Simple format (most common)
        # Keys: text, id, createdAt, likeCount, retweetCount
        # ====================================================================
        if 'text' in item and 'id' in item:
            try:
                timestamp = self._parse_timestamp(item.get('createdAt', ''))
                return {
                    'text': item.get('text', '') or item.get('full_text', ''),
                    'id': str(item.get('id', '')),
                    'timestamp': timestamp,
                    'likes': item.get('likeCount', 0) or item.get('favorite_count', 0),
                    'retweets': item.get('retweetCount', 0) or item.get('retweet_count', 0),
                    'schema': 'standard',
                }
            except Exception:
                pass
        
        # ====================================================================
        # SCHEMA 2: Legacy nested format
        # Keys: legacy.full_text, legacy.id_str, legacy.created_at
        # ====================================================================
        if 'legacy' in item:
            try:
                legacy = item['legacy']
                timestamp = self._parse_timestamp(legacy.get('created_at', ''))
                return {
                    'text': legacy.get('full_text', '') or legacy.get('text', ''),
                    'id': str(legacy.get('id_str', '') or item.get('rest_id', '')),
                    'timestamp': timestamp,
                    'likes': legacy.get('favorite_count', 0),
                    'retweets': legacy.get('retweet_count', 0),
                    'schema': 'legacy',
                }
            except Exception:
                pass
        
        # ====================================================================
        # SCHEMA 3: GraphQL deep nested format
        # Path: content.itemContent.tweet_results.result.legacy
        # ====================================================================
        if 'content' in item:
            try:
                # Navigate the deep path
                content = item.get('content', {})
                item_content = content.get('itemContent', {})
                tweet_results = item_content.get('tweet_results', {})
                result = tweet_results.get('result', {})
                legacy = result.get('legacy', {})
                
                if legacy:
                    timestamp = self._parse_timestamp(legacy.get('created_at', ''))
                    return {
                        'text': legacy.get('full_text', '') or legacy.get('text', ''),
                        'id': str(legacy.get('id_str', '') or result.get('rest_id', '')),
                        'timestamp': timestamp,
                        'likes': legacy.get('favorite_count', 0),
                        'retweets': legacy.get('retweet_count', 0),
                        'schema': 'graphql',
                    }
            except Exception:
                pass
        
        # ====================================================================
        # SCHEMA 4: Apidojo V2 specific format
        # Keys: full_text, id_str, created_at (at root level)
        # ====================================================================
        if 'full_text' in item:
            try:
                timestamp = self._parse_timestamp(item.get('created_at', ''))
                return {
                    'text': item.get('full_text', ''),
                    'id': str(item.get('id_str', '') or item.get('id', '')),
                    'timestamp': timestamp,
                    'likes': item.get('favorite_count', 0),
                    'retweets': item.get('retweet_count', 0),
                    'schema': 'apidojo_v2',
                }
            except Exception:
                pass
        
        # ====================================================================
        # SCHEMA 5: Tweet object wrapper
        # Keys: tweet.text, tweet.id, tweet.created_at
        # ====================================================================
        if 'tweet' in item:
            try:
                tweet = item['tweet']
                return self._extract_tweet_data(tweet)  # Recursive call
            except Exception:
                pass
        
        # ====================================================================
        # FALLBACK: Log unknown structure for debugging
        # ====================================================================
        logger.warning(f"[APIFY] Unknown tweet schema. Keys: {list(item.keys())[:15]}")
        
        # Last resort: try to find any text-like field
        for key in ['text', 'full_text', 'body', 'content', 'message']:
            if key in item and isinstance(item[key], str) and len(item[key]) > 10:
                return {
                    'text': item[key],
                    'id': str(item.get('id', item.get('id_str', 'unknown'))),
                    'timestamp': datetime.now(timezone.utc),
                    'likes': 0,
                    'retweets': 0,
                    'schema': 'fallback',
                }
        
        return None
    
    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse timestamp from various formats"""
        if not ts_str:
            return datetime.now(timezone.utc)
        
        # Try ISO format first (2024-01-15T10:30:00Z)
        try:
            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        except:
            pass
        
        # Try Twitter's format (Mon Jan 15 10:30:00 +0000 2024)
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(ts_str)
        except:
            pass
        
        # Try common formats
        formats = [
            '%a %b %d %H:%M:%S %z %Y',  # Twitter format
            '%Y-%m-%dT%H:%M:%S.%fZ',     # ISO with milliseconds
            '%Y-%m-%d %H:%M:%S',          # Simple datetime
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ts_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                continue
        
        return datetime.now(timezone.utc)


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
# 3. CRYPTOPANIC RSS (DEPRECATED - Returns HTML, not RSS)
# =============================================================================

class CryptoPanicRSSSource:
    """
    ⚠️ DEPRECATED: CryptoPanic RSS feed no longer works.
    
    CryptoPanic has disabled public RSS - now returns HTML instead of XML.
    This was likely done to push users to their paid API.
    
    Use CryptoPanicAPISource instead (works, but has 24h delay on free tier).
    """
    
    def __init__(self):
        self._enabled = False  # Disabled - RSS is dead
        logger.warning("[CRYPTOPANIC RSS] ⚠️ DEPRECATED - RSS endpoint returns HTML, not XML")
        logger.warning("[CRYPTOPANIC RSS] Using API instead (note: 24h delay on free tier)")
    
    def is_enabled(self) -> bool:
        return False
    
    async def fetch_news(self) -> List[WebhookNews]:
        return []
    
    def get_stats(self) -> Dict:
        return {'status': 'deprecated', 'reason': 'RSS endpoint disabled by CryptoPanic'}


# =============================================================================
# 4. CRYPTOPANIC API (24h delay on free tier, but it works)
# =============================================================================

class CryptoPanicAPISource:
    """
    CryptoPanic API for crypto news.
    
    ⚠️ PAUSED: Waiting for Premium subscription.
    
    Current Issues:
    - Free tier (DEVELOPER) has 24-HOUR DELAY on news
    - RSS endpoint deprecated (returns HTML)
    
    To reactivate: 
    1. Upgrade to GROWTH plan ($199/mo) for real-time API
    2. Set CRYPTOPANIC_ENABLED=true in .env
    
    The codebase is preserved for future reactivation.
    """
    
    BASE_URL = "https://cryptopanic.com/api/developer/v2"
    
    PRIORITY_KEYWORDS = {
        'critical': ['BREAKING', 'JUST IN', 'URGENT', 'HACK', 'EXPLOIT', 'CRASH'],
        'high': ['SEC', 'ETF', 'APPROVED', 'REJECTED', 'REGULATION', 'BAN', 
                 'BITCOIN', 'ETHEREUM', 'BINANCE', 'COINBASE'],
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('CRYPTOPANIC_API_KEY')
        
        # Check enable flag (PAUSED by default)
        enabled_flag = os.environ.get('CRYPTOPANIC_ENABLED', 'false').lower()
        self._enabled = self.api_key and enabled_flag in ('true', '1', 'yes')
        
        self._last_fetch_id: Optional[str] = None
        self._stats = {
            'polls': 0,
            'items_found': 0,
            'last_poll': None,
        }
        
        if not self.api_key:
            logger.info("[CRYPTOPANIC API] No API key configured")
        elif not self._enabled:
            logger.info("[CRYPTOPANIC API] ⏸️ PAUSED (CRYPTOPANIC_ENABLED=false)")
            logger.info("[CRYPTOPANIC API] Waiting for Premium subscription. Codebase preserved.")
        else:
            logger.info("[CRYPTOPANIC API] ✅ Enabled (⚠️ 24h delay on free tier)")
    
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
    
    async def fetch_news(self, limit: int = 20) -> List[WebhookNews]:
        """Fetch news from CryptoPanic API"""
        if not self._enabled:
            return []
        
        self._stats['polls'] += 1
        self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/posts/"
                params = {
                    "auth_token": self.api_key,
                    "public": "true",
                }
                
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status != 200:
                        logger.warning(f"[CRYPTOPANIC API] Error: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    results = data.get('results', [])
                
                self._stats['items_found'] = len(results)
                
                news_items = []
                for item in results[:limit]:
                    try:
                        item_id = str(item.get('id', ''))
                        
                        # Skip if seen
                        if item_id == self._last_fetch_id:
                            break
                        
                        if not news_items:
                            self._last_fetch_id = item_id
                        
                        # Parse timestamp
                        published_at = item.get('published_at', '')
                        if published_at:
                            timestamp = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        else:
                            timestamp = datetime.now(timezone.utc)
                        
                        # Get source
                        source_info = item.get('source', {})
                        source_domain = source_info.get('domain', 'cryptopanic.com')
                        
                        # Get currencies
                        currencies = [c.get('code', '') for c in item.get('currencies', [])]
                        
                        title = item.get('title', '')
                        
                        news_items.append(WebhookNews(
                            headline=title,
                            content=f"{title} - Currencies: {', '.join(currencies[:5]) or 'crypto'}",
                            source=source_domain,
                            source_type=WebhookSourceType.CRYPTOPANIC_API,
                            url=item.get('url', ''),
                            priority=self._classify_priority(title),
                            metadata={
                                'cryptopanic_id': item_id,
                                'currencies': currencies,
                                'votes': item.get('votes', {}),
                            },
                            timestamp=timestamp
                        ))
                        
                    except Exception as e:
                        logger.debug(f"[CRYPTOPANIC API] Parse error: {e}")
                        continue
                
                if news_items:
                    logger.info(f"[CRYPTOPANIC API] Fetched {len(news_items)} items (⚠️ 24h delayed)")
                
                return news_items
                
        except Exception as e:
            logger.error(f"[CRYPTOPANIC API] Error: {e}")
            return []
    
    def get_stats(self) -> Dict:
        return {
            **self._stats,
            'delay_warning': '24h on free tier',
        }


# =============================================================================
# LEGACY: CryptoPanicSource (alias to API)
# =============================================================================

class CryptoPanicSource(CryptoPanicAPISource):
    """Legacy alias - use CryptoPanicAPISource"""
    pass


# =============================================================================
# UNIFIED WEBHOOK SOURCES MANAGER
# =============================================================================

class WebhookSourcesManager:
    """
    Manages all webhook sources and coordinates polling.
    
    Active Sources:
    - Apify Twitter: @AP, @WojESPN, etc. (→ LLM → Bayes → Cache)
    - Whale Alert: Polymarket large trades (→ DIRECT Cache injection, skip LLM)
    - CryptoPanic API: Crypto news (⚠️ 24h delay on free tier)
    
    Deprecated:
    - CryptoPanic RSS: Endpoint returns HTML, no longer works
    
    Whale Alert Optimization:
    - Whale trades are already quantified (size, side, price)
    - No LLM interpretation needed - the trade IS the signal
    - Direct injection saves ~3-5 seconds latency
    """
    
    def __init__(
        self, 
        news_callback: Optional[Callable] = None,
        signal_cache: Optional[Any] = None
    ):
        """
        Args:
            news_callback: Async function to call with WebhookNews items
                          Typically NewsInjector.process_news()
            signal_cache: Optional AsyncSignalCache for direct whale injection
                          If provided, whale alerts bypass LLM entirely
        """
        self.news_callback = news_callback
        self.signal_cache = signal_cache  # For direct whale injection
        
        # Initialize sources
        self.apify = ApifyTwitterSource()
        self.whale = WhaleAlertSource()
        self.cryptopanic_api = CryptoPanicAPISource()  # API works (24h delay)
        self.cryptopanic_rss = CryptoPanicRSSSource()  # RSS deprecated (returns HTML)
        
        # Legacy alias
        self.cryptopanic = self.cryptopanic_api
        
        # Set up whale callback (ALWAYS - for direct injection even without news_callback)
        self.whale.set_callback(self._handle_whale_alert)
        
        # Polling state
        self.is_running = False
        self._poll_tasks: List[asyncio.Task] = []
        
        # Stats
        self._stats = {
            'apify_polls': 0,
            'apify_items': 0,
            'whale_alerts': 0,
            'cryptopanic_api_polls': 0,
            'cryptopanic_api_items': 0,
            'last_poll': None,
            'errors': 0,
        }
        
        logger.info("[WEBHOOK SOURCES] Manager initialized")
        logger.info(f"  - Apify Twitter: {'✅ Enabled' if self.apify.is_enabled() else '❌ Disabled'} ({len(self.apify.TARGET_ACCOUNTS)} accounts)")
        logger.info(f"  - Whale Alerts: {'✅ Enabled' if self.whale.is_enabled() else '❌ Disabled'}")
        logger.info(f"  - CryptoPanic API: {'⏸️ PAUSED' if not self.cryptopanic_api.is_enabled() else '✅ Enabled (⚠️ 24h delay)'}")
        logger.info("  - CryptoPanic RSS: ❌ Deprecated (returns HTML)")
        logger.info(f"  - Whale Direct Injection: {'✅ Enabled (skip LLM)' if signal_cache else '❌ Disabled (using LLM path)'}")
    
    async def _handle_whale_alert(self, news: WebhookNews):
        """
        Handle whale alert from internal monitor.
        
        OPTIMIZATION: If signal_cache is available, bypass LLM entirely.
        
        Why skip LLM for whale alerts?
        - The trade IS the signal (already quantified: size, side, price)
        - LLM would just confirm "yes, a big trade is relevant"
        - Saves 3-5 seconds latency
        
        Signal calculation:
        - Direction: BUY = bullish (YES), SELL = bearish (NO)
        - Confidence: Based on trade size ($5k=0.5, $50k+=0.9)
        - Bayes Factor: Size-weighted (larger trade = stronger evidence)
        """
        self._stats['whale_alerts'] += 1
        
        # Try to get signal_cache if not set (lazy initialization)
        if self.signal_cache is None:
            try:
                from services.signal_cache import get_signal_cache
                self.signal_cache = get_signal_cache()
                logger.info("[WHALE] Signal cache acquired via lazy init")
            except Exception as e:
                logger.debug(f"[WHALE] Could not get signal cache: {e}")
        
        # Extract trade metadata
        metadata = news.metadata
        market_id = metadata.get('market_id', '')
        side = metadata.get('side', 'BUY').upper()
        size_usd = float(metadata.get('size_usd', 0))
        price = float(metadata.get('price', 0.5))
        
        # DIRECT INJECTION PATH (skip LLM)
        if self.signal_cache and market_id:
            try:
                # Calculate confidence based on trade size
                # $5k = 0.50, $10k = 0.60, $20k = 0.70, $50k+ = 0.90
                if size_usd >= 50000:
                    confidence = 0.90
                elif size_usd >= 20000:
                    confidence = 0.75
                elif size_usd >= 10000:
                    confidence = 0.65
                else:
                    confidence = 0.55
                
                # Determine direction from trade side
                # BUY = bullish for YES, SELL = bearish for YES
                direction = 'YES' if side == 'BUY' else 'NO'
                
                # Calculate Bayes Factor based on size and confidence
                # BF = confidence / (1 - confidence)
                # Adjusted by size weight (cap at 10.0)
                size_multiplier = min(size_usd / 10000, 3.0)  # 1x at $10k, 3x at $30k+
                bayes_factor = min((confidence / (1 - confidence)) * size_multiplier, 10.0)
                
                # Calculate posterior (simple Bayesian update from market price)
                prior = price if direction == 'YES' else (1 - price)
                posterior = (prior * bayes_factor) / (prior * bayes_factor + (1 - prior))
                posterior = max(0.01, min(0.99, posterior))
                
                # Build signal payload
                signal = {
                    'direction': direction,
                    'posterior': posterior,
                    'prior': prior,
                    'bayes_factor': bayes_factor,
                    'confidence': confidence,
                    'news_headline': news.headline,
                    'source': 'whale_alert_direct',
                    'source_reliability': 0.85,  # High reliability - actual trade data
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat(),  # 2 min TTL
                    'is_resolution': False,
                    'metadata': {
                        'size_usd': size_usd,
                        'trade_side': side,
                        'trade_price': price,
                        'injection_type': 'direct'
                    }
                }
                
                # Inject directly to cache
                cache_key = f"emergent_signal:{market_id}"
                await self.signal_cache.set(cache_key, signal, ttl=120)
                
                logger.info(
                    f"[WHALE DIRECT] 🐋⚡ INJECTED: {market_id[:16]}... | "
                    f"${size_usd:,.0f} {side} | Direction: {direction} | "
                    f"BF: {bayes_factor:.2f} | Confidence: {confidence:.0%} | "
                    f"(LLM bypassed, ~3s saved)"
                )
                
                self._stats['whale_direct_injections'] = self._stats.get('whale_direct_injections', 0) + 1
                return
                
            except Exception as e:
                logger.error(f"[WHALE DIRECT] Injection failed, falling back to LLM: {e}")
                # Fall through to LLM path
        
        # FALLBACK: LLM PATH (if no signal_cache or direct injection fails)
        if self.news_callback:
            try:
                await self.news_callback(news.to_news_payload())
                logger.info(f"[WHALE] Processed via LLM path: {news.headline[:50]}...")
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
    
    async def _poll_cryptopanic_api(self, interval_seconds: int = 300):
        """Poll CryptoPanic API (default every 5 minutes)"""
        logger.info(f"[WEBHOOK SOURCES] CryptoPanic API poll loop started ({interval_seconds}s interval)")
        logger.info("  ⚠️ Note: Free tier has 24h delay - useful for research, not real-time trading")
        
        while self.is_running:
            try:
                if self.cryptopanic_api.is_enabled():
                    news_items = await self.cryptopanic_api.fetch_news(limit=10)
                    self._stats['cryptopanic_api_polls'] += 1
                    self._stats['cryptopanic_api_items'] += len(news_items)
                    self._stats['last_poll'] = datetime.now(timezone.utc).isoformat()
                    
                    for news in news_items:
                        if self.news_callback:
                            await self.news_callback(news.to_news_payload())
                        await asyncio.sleep(0.3)  # Rate limit
                
            except Exception as e:
                logger.error(f"[WEBHOOK SOURCES] CryptoPanic API poll error: {e}")
                self._stats['errors'] += 1
            
            await asyncio.sleep(interval_seconds)
    
    async def start(self):
        """Start all polling loops"""
        if self.is_running:
            logger.warning("[WEBHOOK SOURCES] Already running")
            return
        
        self.is_running = True
        
        # Start poll tasks (only enabled sources)
        self._poll_tasks = [
            asyncio.create_task(self._poll_apify(interval_seconds=300)),  # 5 min
        ]
        
        # Only start CryptoPanic if enabled (not paused)
        if self.cryptopanic_api.is_enabled():
            self._poll_tasks.append(
                asyncio.create_task(self._poll_cryptopanic_api(interval_seconds=300))
            )
        
        logger.info("[WEBHOOK SOURCES] Polling loops started:")
        logger.info(f"  📰 Apify Twitter: every 5 min ({len(self.apify.TARGET_ACCOUNTS)} accounts)")
        logger.info("  🐋 Whale Alerts: real-time via WebSocket")
        if self.cryptopanic_api.is_enabled():
            logger.info("  📰 CryptoPanic API: every 5 min (⚠️ 24h delayed)")
        else:
            logger.info("  ⏸️ CryptoPanic: PAUSED (set CRYPTOPANIC_ENABLED=true to activate)")
    
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
                'cryptopanic_api_enabled': self.cryptopanic_api.is_enabled(),
                'cryptopanic_rss_enabled': False,  # Deprecated
            },
            'whale_threshold': self.whale.threshold_usd,
            'whale_recent_alerts': len(self.whale.get_recent_alerts()),
            'cryptopanic_api_stats': self.cryptopanic_api.get_stats(),
            'notes': {
                'cryptopanic_rss': 'DEPRECATED - endpoint returns HTML',
                'cryptopanic_api': '24h delay on free tier',
            }
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_webhook_sources_manager: Optional[WebhookSourcesManager] = None


def get_webhook_sources_manager(
    news_callback: Optional[Callable] = None,
    signal_cache: Optional[Any] = None
) -> WebhookSourcesManager:
    """
    Get or create the WebhookSourcesManager instance.
    
    Args:
        news_callback: Function to process news through LLM pipeline
        signal_cache: AsyncSignalCache for whale alert direct injection
                      If provided, whale alerts skip LLM (~3s faster)
    """
    global _webhook_sources_manager
    if _webhook_sources_manager is None:
        _webhook_sources_manager = WebhookSourcesManager(
            news_callback=news_callback,
            signal_cache=signal_cache
        )
    elif signal_cache is not None and _webhook_sources_manager.signal_cache is None:
        # Allow setting signal_cache after initial creation
        _webhook_sources_manager.signal_cache = signal_cache
        logger.info("[WEBHOOK SOURCES] Signal cache attached for whale direct injection")
    return _webhook_sources_manager

