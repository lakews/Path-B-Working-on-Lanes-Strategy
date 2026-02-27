"""
Enhanced Sentiment Analysis with LLM + Cross-Market Correlation
Combines multiple data sources for comprehensive market sentiment

Updated: Integrated Hybrid Smart-Cache LLM Module
- Hot markets (high volume): 10 min cache TTL
- Cold markets (low volume): 60 min cache TTL
- Result: 100% market coverage without 100% of the cost

Updated: Category-Aware Fusion (Task: Stop LLM Hallucination)
- Sports: 80% Real Odds API + 20% Order Flow (0% LLM/GitHub)
- Politics: 90% Order Flow + 10% LLM (0% GitHub)
- Crypto: Maintain existing fusion weights
- Fallback: 100% Order Flow if API fails
"""
import asyncio
import logging
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
from config import config

logger = logging.getLogger(__name__)


# Import the new Smart LLM module
try:
    from ml.sentiment_llm import get_smart_llm_analyzer, get_llm_sentiment
    SMART_LLM_AVAILABLE = True
    logger.info("Smart LLM module loaded successfully")
except ImportError as e:
    SMART_LLM_AVAILABLE = False
    logger.warning(f"Smart LLM module not available: {e}")


# Import Sports Odds API module (Real arbitrage data - no hallucination)
try:
    from sentiment.sports_odds import get_sports_odds_analyzer
    SPORTS_ODDS_AVAILABLE = True
    logger.info("Sports Odds API module loaded successfully")
except ImportError as e:
    SPORTS_ODDS_AVAILABLE = False
    logger.warning(f"Sports Odds API module not available: {e}")


class CrossMarketCorrelation:
    """
    Tracks price movements across related markets to identify correlation patterns.
    
    If multiple markets in the same category are moving in the same direction,
    it strengthens the sentiment signal.
    """
    
    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        # Track price history by category
        self.category_prices: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        # Track overall market direction
        self.category_momentum: Dict[str, float] = {}
        # Related market groups (markets that tend to move together)
        self.market_groups = {
            'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol'],
            'trump': ['trump', 'donald', 'maga', 'republican'],
            'biden': ['biden', 'democrat', 'democratic'],
            'fed': ['fed', 'interest rate', 'inflation', 'federal reserve', 'fomc'],
            'ai': ['ai', 'artificial intelligence', 'openai', 'chatgpt', 'google', 'microsoft'],
            'sports_nba': ['nba', 'basketball', 'lakers', 'celtics', 'warriors'],
            'sports_nfl': ['nfl', 'football', 'superbowl', 'chiefs', 'eagles'],
        }
    
    def update_price(self, market_id: str, category: str, question: str, price: float):
        """Update price history for a market"""
        # Add to category tracking
        prices = self.category_prices[category][market_id]
        prices.append(price)
        
        # Keep only recent prices
        if len(prices) > self.window_size:
            self.category_prices[category][market_id] = prices[-self.window_size:]
        
        # Update category momentum
        self._update_category_momentum(category)
    
    def _update_category_momentum(self, category: str):
        """Calculate overall momentum for a category"""
        if category not in self.category_prices:
            self.category_momentum[category] = 0.0
            return
        
        momentums = []
        for market_id, prices in self.category_prices[category].items():
            if len(prices) >= 2:
                # Calculate price change
                recent = prices[-1]
                older = prices[-min(5, len(prices))]  # Compare to 5 ticks ago
                if older > 0:
                    momentum = (recent - older) / older
                    momentums.append(momentum)
        
        if momentums:
            # Average momentum across category
            self.category_momentum[category] = np.mean(momentums)
        else:
            self.category_momentum[category] = 0.0
    
    def get_correlation_signal(self, market_id: str, category: str, question: str, current_price: float) -> Dict:
        """
        Get correlation-based sentiment adjustment.
        
        Returns:
        - correlation_sentiment: 0-1 sentiment based on related market movements
        - correlation_strength: how strong the correlation signal is
        - related_markets_moving: direction of related markets
        """
        # Update this market's price
        self.update_price(market_id, category, question, current_price)
        
        # Get category momentum
        category_momentum = self.category_momentum.get(category, 0.0)
        
        # Find related market groups
        question_lower = question.lower()
        related_momentum = []
        related_groups = []
        
        for group_name, keywords in self.market_groups.items():
            if any(kw in question_lower for kw in keywords):
                related_groups.append(group_name)
                # Check if other markets in this group are moving
                for cat, markets in self.category_prices.items():
                    for mid, prices in markets.items():
                        if mid != market_id and len(prices) >= 2:
                            # Check if this market matches the group
                            recent = prices[-1]
                            older = prices[-min(5, len(prices))]
                            if older > 0:
                                mom = (recent - older) / older
                                related_momentum.append(mom)
        
        # Calculate correlation sentiment
        if related_momentum:
            avg_related = np.mean(related_momentum)
            # Convert momentum to sentiment (positive momentum = bullish)
            correlation_sentiment = 0.5 + (avg_related * 5)  # Scale up
            correlation_sentiment = max(0.1, min(0.9, correlation_sentiment))
            correlation_strength = min(1.0, len(related_momentum) / 10)  # More markets = stronger signal
        else:
            # Fall back to category momentum
            correlation_sentiment = 0.5 + (category_momentum * 5)
            correlation_sentiment = max(0.1, min(0.9, correlation_sentiment))
            correlation_strength = 0.3  # Lower confidence without related markets
        
        # Check if market is moving WITH or AGAINST the trend
        if len(self.category_prices[category].get(market_id, [])) >= 2:
            prices = self.category_prices[category][market_id]
            own_momentum = (prices[-1] - prices[-2]) / max(0.001, prices[-2])
            
            # If moving with category, boost confidence
            if (own_momentum > 0 and category_momentum > 0) or (own_momentum < 0 and category_momentum < 0):
                correlation_strength = min(1.0, correlation_strength * 1.3)
        
        return {
            'correlation_sentiment': round(correlation_sentiment, 4),
            'correlation_strength': round(correlation_strength, 4),
            'category_momentum': round(category_momentum, 4),
            'related_groups': related_groups,
            'markets_tracked': len(self.category_prices.get(category, {}))
        }


class EnhancedSentimentAnalyzer:
    """
    Ultimate sentiment analyzer combining:
    1. LLM analysis (GPT-4o-mini via Emergent) - NOW WITH SMART CACHING
    2. Cross-market correlation
    3. Polymarket-native sentiment (order flow, volume momentum, whale signals)
    4. GitHub sentiment (for crypto/tech markets)
    5. Hybrid Smart-Cache for cost optimization
    6. Sports Odds API (REAL arbitrage data - replaces LLM hallucination)
    
    CATEGORY-AWARE FUSION (Stops LLM Hallucination):
    - Sports: 80% Real Odds API + 20% Order Flow (LLM/GitHub DISABLED)
    - Politics: 90% Order Flow + 10% LLM (GitHub DISABLED)
    - Crypto: Full fusion (LLM + GitHub + Order Flow)
    - Default: 100% Order Flow on API failure
    """
    
    def __init__(self):
        self._db = None
        self.correlation_tracker = CrossMarketCorrelation()
        
        # Initialize Smart LLM Analyzer (replaces old rate-limited approach)
        self.smart_llm = None
        if SMART_LLM_AVAILABLE:
            try:
                self.smart_llm = get_smart_llm_analyzer()
                logger.info("Smart LLM Sentiment Analyzer initialized (Hybrid Smart-Cache)")
            except Exception as e:
                logger.warning(f"Could not initialize Smart LLM: {e}")
        
        # Initialize Sports Odds Analyzer (REAL DATA - No hallucination)
        self.sports_odds = None
        if SPORTS_ODDS_AVAILABLE:
            try:
                self.sports_odds = get_sports_odds_analyzer()
                logger.info("Sports Odds Analyzer initialized (Real Arbitrage Data)")
            except Exception as e:
                logger.warning(f"Could not initialize Sports Odds: {e}")
        
        # Initialize Polymarket sentiment extractor
        try:
            from ml.polymarket_sentiment import get_polymarket_sentiment_extractor
            self.polymarket_sentiment = get_polymarket_sentiment_extractor()
            logger.info("Polymarket sentiment extractor initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Polymarket sentiment: {e}")
            self.polymarket_sentiment = None
        
        # Initialize GitHub sentiment analyzer
        try:
            from ml.github_sentiment import get_github_sentiment_analyzer
            self.github_sentiment = get_github_sentiment_analyzer()
            logger.info("GitHub sentiment analyzer initialized")
        except Exception as e:
            logger.warning(f"Could not initialize GitHub sentiment: {e}")
            self.github_sentiment = None
    
    @property
    def db(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db
    
    def get_llm_stats(self) -> Dict:
        """Get Smart LLM cache statistics"""
        if self.smart_llm:
            return self.smart_llm.get_stats()
        return {'error': 'Smart LLM not initialized'}
    
    def get_llm_config(self) -> Dict:
        """Get Smart LLM cache configuration"""
        if self.smart_llm:
            return self.smart_llm.get_config()
        return {'error': 'Smart LLM not initialized'}
    
    def update_llm_config(self, new_config: Dict) -> Dict:
        """Update Smart LLM cache configuration"""
        if self.smart_llm:
            return self.smart_llm.update_config(new_config)
        return {'error': 'Smart LLM not initialized'}
    
    def get_llm_cache_entries(self) -> Dict:
        """Get all LLM cache entries"""
        if self.smart_llm:
            return self.smart_llm.get_cache_entries()
        return {'error': 'Smart LLM not initialized'}
    
    def get_sports_odds_stats(self) -> Dict:
        """Get Sports Odds API statistics"""
        if self.sports_odds:
            return self.sports_odds.get_api_stats()
        return {'error': 'Sports Odds not initialized'}
    
    def _detect_category(self, market_data: Dict) -> str:
        """
        Detect the true category of a market for proper signal weighting.
        
        Categories:
        - 'sports': Use real odds API, disable LLM
        - 'crypto': Use GitHub + LLM + Order Flow
        - 'politics': Use Order Flow + limited LLM
        - 'other': Default fusion
        """
        category = market_data.get('category', '').lower()
        question = market_data.get('question', '').lower()
        
        # Sports detection (expanded)
        sports_keywords = [
            'nba', 'nfl', 'mlb', 'nhl', 'mls', 'ufc', 'boxing',
            'lakers', 'celtics', 'warriors', 'chiefs', 'eagles', 'cowboys',
            'yankees', 'dodgers', 'astros', 'match', 'game', 'win against',
            'beat', 'defeat', 'premier league', 'champions league', 'world cup',
            'super bowl', 'playoffs', 'finals', 'championship', 'tournament',
            'tennis', 'golf', 'pga', 'atp', 'wta', 'f1', 'formula 1', 'nascar',
            'olympics', 'medal', 'esports', 'league of legends', 'dota', 'csgo'
        ]
        
        if category == 'sports' or any(kw in question for kw in sports_keywords):
            return 'sports'
        
        # Crypto detection
        crypto_keywords = [
            'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol',
            'cardano', 'polygon', 'avalanche', 'arbitrum', 'optimism', 'base',
            'defi', 'nft', 'blockchain', 'token', 'coin', 'binance', 'coinbase',
            'pectra', 'dencun', 'taproot', 'halving', 'merge'
        ]
        
        if category == 'crypto' or any(kw in question for kw in crypto_keywords):
            return 'crypto'
        
        # Politics detection
        politics_keywords = [
            'trump', 'biden', 'president', 'election', 'vote', 'congress',
            'senate', 'republican', 'democrat', 'gop', 'primary', 'nominee',
            'governor', 'mayor', 'cabinet', 'secretary', 'impeach', 'poll',
            'campaign', 'electoral', 'swing state', 'ballot', 'legislation'
        ]
        
        if category in ['politics', 'political'] or any(kw in question for kw in politics_keywords):
            return 'politics'
        
        return 'other'
    
    async def analyze(self, market_data: Dict, trades: List = None, order_book: Dict = None) -> Dict:
        """
        Comprehensive sentiment analysis with CATEGORY-AWARE FUSION.
        
        FUSION STRATEGY (Stops LLM Hallucination):
        - Sports: 80% Real Odds API + 20% Order Flow (LLM=0%, GitHub=0%)
        - Politics: 90% Order Flow + 10% LLM (GitHub=0%)
        - Crypto: Full fusion (30% Order Flow + 35% LLM + 20% GitHub + 15% Correlation)
        - Other/Fallback: 100% Order Flow
        
        Args:
            market_data: Market info (price, volume, etc.)
            trades: Optional recent trades for Polymarket sentiment
            order_book: Optional order book for spread analysis
        
        Returns:
            Dict with sentiment scores, confidence, and source breakdown
        """
        market_id = market_data.get('id', '')
        question = market_data.get('question', '')
        raw_category = market_data.get('category', 'unknown')
        yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
        
        # Detect TRUE category for proper weighting
        detected_category = self._detect_category(market_data)
        
        result = {
            'llm_sentiment': None,  # None = no data, don't default to 0.5
            'llm_confidence': 0.0,
            'llm_reasoning': '',
            'correlation_sentiment': None,
            'correlation_strength': 0.0,
            'polymarket_sentiment': None,  # None = no valid order flow
            'polymarket_confidence': 0.0,
            'polymarket_momentum': {},
            'sports_sentiment': None,
            'sports_confidence': 0.0,
            'github_sentiment': None,
            'github_confidence': 0.0,
            'combined_sentiment': None,  # None = skip trade
            'combined_confidence': 0.0,
            'analysis_source': 'none',
            'detected_category': detected_category,
            'raw_category': raw_category,
        }
        
        sources_used = []
        
        # ================================================================
        # 1. POLYMARKET-NATIVE SENTIMENT (Always collected - Order Flow)
        # ================================================================
        orderflow_valid = False
        if self.polymarket_sentiment:
            try:
                poly_result = await self.polymarket_sentiment.analyze_market(
                    market_id=market_id,
                    market_data=market_data,
                    trades=trades,
                    order_book=order_book
                )
                
                # Check if order flow returned valid data (not None)
                poly_score = poly_result.get('combined_score')
                if poly_score is not None:
                    result['polymarket_sentiment'] = poly_score
                    orderflow_valid = True
                else:
                    # No valid order flow data - don't default to 0.5
                    result['polymarket_sentiment'] = None
                    result['orderflow_invalid_reason'] = poly_result.get('reason', 'no_valid_signals')
                
                result['polymarket_momentum'] = poly_result.get('sentiment_momentum', {})
                result['polymarket_signals'] = poly_result.get('signals', {})
                result['polymarket_interpretation'] = poly_result.get('interpretation', '')
                
                # Confidence based on data quality
                data_quality = poly_result.get('data_quality', {})
                poly_confidence = 0.0 if not orderflow_valid else 0.3  # 0 if invalid
                if data_quality.get('has_trades'):
                    poly_confidence += 0.2
                if data_quality.get('has_order_book'):
                    poly_confidence += 0.2
                if data_quality.get('price_history_points', 0) > 10:
                    poly_confidence += 0.15
                if data_quality.get('trade_history_points', 0) > 20:
                    poly_confidence += 0.15
                
                result['polymarket_confidence'] = min(0.9, poly_confidence)
                if orderflow_valid:
                    sources_used.append('orderflow')
                
            except Exception as e:
                logger.debug(f"Polymarket sentiment error: {e}")
                result['polymarket_sentiment'] = None
                result['orderflow_invalid_reason'] = str(e)
        
        # ================================================================
        # 2. SPORTS ODDS API (ONLY for sports markets - REAL DATA)
        # ================================================================
        # Returns None if module is disabled (no API key)
        # In that case, we fallback gracefully to Order Flow
        sports_fair_value = 0.5
        sports_confidence = 0.0
        
        if detected_category == 'sports' and self.sports_odds:
            try:
                sports_result = await self.sports_odds.analyze_market(market_data)
                
                # Handle None return (module disabled or error)
                if sports_result is None:
                    logger.warning(
                        "Sports Odds unavailable (disabled or error). "
                        "Falling back to Order Flow."
                    )
                    result['sports_error'] = 'module_disabled_or_unavailable'
                    result['sports_fallback_reason'] = 'API key not configured or module inactive'
                
                elif sports_result.get('is_sports_market'):
                    sports_fair_value = sports_result.get('sports_fair_value', 0.5)
                    sports_confidence = sports_result.get('sports_confidence', 0.0)
                    
                    result['sports_sentiment'] = sports_fair_value
                    result['sports_confidence'] = sports_confidence
                    result['sports_matched_event'] = sports_result.get('matched_event')
                    result['sports_all_fair_values'] = sports_result.get('all_fair_values', {})
                    result['sports_bookmakers_used'] = sports_result.get('bookmakers_used', 0)
                    
                    if sports_confidence > 0:
                        sources_used.append('sports_odds')
                        logger.info(f"[SPORTS] Real odds for {question[:40]}: "
                                   f"fair_value={sports_fair_value:.3f}")
                else:
                    result['sports_error'] = sports_result.get('error', 'not_sports_market')
                    
            except Exception as e:
                logger.warning(f"Sports odds error: {e}. Falling back to Order Flow.")
                result['sports_error'] = str(e)
        
        # ================================================================
        # 3. LLM SENTIMENT (DISABLED for sports, limited for politics)
        # ================================================================
        if detected_category not in ['sports'] and self.smart_llm:
            try:
                llm_sentiment, llm_confidence = await self.smart_llm.get_sentiment(market_data)
                result['llm_sentiment'] = llm_sentiment
                result['llm_confidence'] = llm_confidence
                result['llm_reasoning'] = self.smart_llm.get_cached_reasoning(market_id)
                
                if llm_confidence > 0:
                    sources_used.append('llm')
                    
            except Exception as e:
                logger.debug(f"Smart LLM sentiment error: {e}")
        elif detected_category == 'sports':
            result['llm_disabled_reason'] = 'Sports markets use real odds API instead of LLM'
        
        # ================================================================
        # 4. CROSS-MARKET CORRELATION
        # ================================================================
        correlation_result = self.correlation_tracker.get_correlation_signal(
            market_id, raw_category, question, yes_price
        )
        result['correlation_sentiment'] = correlation_result['correlation_sentiment']
        result['correlation_strength'] = correlation_result['correlation_strength']
        result['category_momentum'] = correlation_result['category_momentum']
        result['related_groups'] = correlation_result['related_groups']
        
        # ================================================================
        # 5. GITHUB SENTIMENT (ONLY for crypto/tech markets)
        # ================================================================
        github_sentiment = 0.5
        github_confidence = 0.0
        
        if detected_category == 'crypto' and self.github_sentiment:
            try:
                github_result = await self.github_sentiment.analyze_market(market_data)
                
                if github_result.get('is_relevant'):
                    github_sentiment = github_result.get('github_sentiment', 0.5)
                    github_confidence = github_result.get('github_confidence', 0.0)
                    
                    result['github_sentiment'] = github_sentiment
                    result['github_confidence'] = github_confidence
                    result['github_signals'] = github_result.get('signals', {})
                    result['github_repos'] = github_result.get('repos_analyzed', [])
                    result['github_interpretation'] = github_result.get('interpretation', '')
                    
                    if github_confidence > 0.2:
                        sources_used.append('github')
                        
            except Exception as e:
                logger.debug(f"GitHub sentiment error: {e}")
        elif detected_category != 'crypto':
            result['github_disabled_reason'] = f'GitHub only used for crypto (detected: {detected_category})'
        
        # ================================================================
        # 6. CATEGORY-AWARE FUSION (THE KEY FIX)
        # ================================================================
        combined_sentiment = 0.5
        combined_confidence = 0.0
        weight_breakdown = {}
        
        if detected_category == 'sports':
            # ============================================================
            # SPORTS INTELLIGENT FALLBACK SYSTEM (Option B)
            # ============================================================
            # PRIORITY ORDER:
            # 1. Odds API available → 85% devigged odds + 15% order flow
            # 2. Sufficient Polymarket liquidity → 100% market-implied price
            # 3. Insufficient data → BLOCK (fair_value = None signals block)
            # ============================================================
            # BANNED SOURCES: LLM = 0%, GitHub = 0%, Social = 0%
            # RATIONALE: Cannot predict live scores with AI/code metrics
            # ============================================================
            
            # Extract market liquidity metrics for fallback decision
            volume_24h = float(market_data.get('volume_24h', 0) or 0)
            liquidity = float(market_data.get('liquidity', 0) or market_data.get('volume', 0) or 0)
            
            # Thresholds for intelligent fallback
            FALLBACK_MIN_VOLUME = 5000.0   # $5k 24h volume required for market-implied fallback
            FALLBACK_MIN_LIQUIDITY = 2000.0  # $2k liquidity required
            
            if sports_confidence > 0:
                # ============================================================
                # TIER 1: Real odds available - PRIMARY TRUTH SOURCE
                # ============================================================
                sports_weight = 0.85  # Primary truth from bookmakers
                orderflow_weight = 0.15  # Secondary truth from order book
                
                # Handle case where order flow is None (use 0.5 only for TIER 1 since we have real odds)
                orderflow_value = result['polymarket_sentiment']
                if orderflow_value is None:
                    # No order flow data, use 100% real odds
                    combined_sentiment = sports_fair_value
                    orderflow_weight = 0.0
                    sports_weight = 1.0
                    result['tier1_orderflow_unavailable'] = True
                else:
                    combined_sentiment = (
                        sports_fair_value * sports_weight +
                        orderflow_value * orderflow_weight
                    )
                
                combined_confidence = min(0.95, sports_confidence * 0.85 + result['polymarket_confidence'] * 0.15)
                
                weight_breakdown = {
                    'sports_odds': sports_weight,
                    'orderflow': orderflow_weight,
                    'llm': 0.0,  # BANNED
                    'github': 0.0,  # BANNED
                    'social': 0.0,  # BANNED
                    'correlation': 0.0,
                }
                result['fusion_strategy'] = f'SPORTS TIER-1: {int(sports_weight*100)}% Real Odds + {int(orderflow_weight*100)}% Order Flow'
                result['banned_sources'] = ['llm', 'github', 'social']
                result['sports_data_tier'] = 1
                
            elif volume_24h >= FALLBACK_MIN_VOLUME and liquidity >= FALLBACK_MIN_LIQUIDITY:
                # ============================================================
                # TIER 2: Odds API failed but market has sufficient liquidity
                # Use Polymarket implied price (70%) + Order Flow sentiment (30%)
                # ============================================================
                # Polymarket price IS the market-implied probability
                # Order flow adds validation via bid/ask imbalance, trade momentum
                # With deep liquidity, this combination is a reasonable proxy
                # ============================================================
                
                # Get market-implied price (primary signal)
                market_price = float(market_data.get('yes_price') or 0)
                
                # Get order flow sentiment (validation signal) - may be None if no valid data
                orderflow_sentiment = result['polymarket_sentiment']
                orderflow_confidence = result['polymarket_confidence']
                
                # BLOCK if market price is 0.5 (default, no real data)
                if abs(market_price - 0.5) < 0.01 or market_price == 0:
                    combined_sentiment = None  # Signal to BLOCK
                    combined_confidence = 0.0
                    weight_breakdown = {
                        'sports_odds': 0.0,
                        'orderflow': 0.0,
                        'llm': 0.0,
                        'github': 0.0,
                        'social': 0.0,
                        'correlation': 0.0,
                    }
                    result['fusion_strategy'] = 'SPORTS BLOCKED: Price=0.5 indicates no real market data'
                    result['sports_data_tier'] = 0
                    result['block_reason'] = 'polymarket_price_is_default'
                
                # BLOCK if order flow returned None (no valid signals)
                elif orderflow_sentiment is None:
                    combined_sentiment = None  # Signal to BLOCK
                    combined_confidence = 0.0
                    weight_breakdown = {
                        'sports_odds': 0.0,
                        'orderflow': 0.0,
                        'llm': 0.0,
                        'github': 0.0,
                        'social': 0.0,
                        'correlation': 0.0,
                    }
                    result['fusion_strategy'] = 'SPORTS BLOCKED: No valid order flow data'
                    result['sports_data_tier'] = 0
                    result['block_reason'] = result.get('orderflow_invalid_reason', 'orderflow_none')
                    logger.warning(f"[SPORTS BLOCKED] No valid order flow for {question[:30]}...")
                
                else:
                    # Valid data - combine market price + order flow
                    market_weight = 0.70
                    orderflow_weight = 0.30
                    
                    # If order flow has low confidence, rely more on market price
                    if orderflow_confidence < 0.4:
                        market_weight = 0.85
                        orderflow_weight = 0.15
                        logger.debug(f"[SPORTS TIER-2] Low orderflow confidence ({orderflow_confidence:.2f}), using 85/15 split")
                    
                    combined_sentiment = (
                        market_price * market_weight +
                        orderflow_sentiment * orderflow_weight
                    )
                    
                    # Lower confidence since no external odds validation
                    combined_confidence = min(0.60, orderflow_confidence * 0.5 + 0.3)
                    
                    weight_breakdown = {
                        'sports_odds': 0.0,  # API unavailable
                        'market_implied': market_weight,  # Primary signal
                        'orderflow': orderflow_weight,  # Validation signal
                        'llm': 0.0,  # STILL BANNED
                        'github': 0.0,
                        'social': 0.0,
                        'correlation': 0.0,
                    }
                    result['fusion_strategy'] = f'SPORTS TIER-2: {int(market_weight*100)}% Market + {int(orderflow_weight*100)}% OrderFlow (Vol=${volume_24h:.0f})'
                    result['sports_data_tier'] = 2
                    result['tier2_market_price'] = market_price
                    result['tier2_orderflow'] = orderflow_sentiment
                    result['tier2_orderflow_confidence'] = orderflow_confidence
                    result['fallback_reason'] = 'odds_api_unavailable_using_market_plus_orderflow'
                    logger.info(f"[SPORTS TIER-2] Market={market_price:.4f}*{market_weight:.0%} + "
                               f"OrderFlow={orderflow_sentiment:.4f}*{orderflow_weight:.0%} = {combined_sentiment:.4f}")
                
            else:
                # ============================================================
                # TIER 0: BLOCK - Insufficient data for safe trading
                # ============================================================
                # Odds API failed AND market lacks sufficient liquidity
                # Trading here is gambling, not arbitrage
                # ============================================================
                combined_sentiment = None  # Signal to BLOCK trade
                combined_confidence = 0.0
                
                weight_breakdown = {
                    'sports_odds': 0.0,
                    'orderflow': 0.0,
                    'llm': 0.0,
                    'github': 0.0,
                    'social': 0.0,
                    'correlation': 0.0,
                }
                result['fusion_strategy'] = f'SPORTS BLOCKED: Odds API down + Low liquidity (Vol=${volume_24h:.0f}<${FALLBACK_MIN_VOLUME:.0f})'
                result['sports_data_tier'] = 0
                result['block_reason'] = 'insufficient_data'
                result['api_fallback_reason'] = result.get('sports_error', 'API unavailable')
                logger.warning(f"[SPORTS BLOCKED] Odds API failed, insufficient liquidity: "
                              f"Vol=${volume_24h:.0f}<${FALLBACK_MIN_VOLUME:.0f}, "
                              f"Liq=${liquidity:.0f}<${FALLBACK_MIN_LIQUIDITY:.0f}")
                
        elif detected_category == 'politics':
            # ============================================================
            # POLITICS / ECONOMICS: 90% Order Flow + 10% LLM
            # ============================================================
            # BANNED SOURCES: GitHub = 0%, Social = 0% (unless very specific)
            # RATIONALE: GitHub activity does NOT influence political outcomes.
            #            LLM provides context only, not primary truth.
            # ============================================================
            orderflow_weight = 0.90
            llm_weight = 0.10 if result['llm_confidence'] > 0 else 0.0
            
            # Normalize if LLM unavailable
            if llm_weight == 0:
                orderflow_weight = 1.0
            
            combined_sentiment = (
                result['polymarket_sentiment'] * orderflow_weight +
                result['llm_sentiment'] * llm_weight
            )
            combined_confidence = min(0.90, result['polymarket_confidence'] * 0.9 + result['llm_confidence'] * 0.1)
            
            weight_breakdown = {
                'sports_odds': 0.0,
                'orderflow': orderflow_weight,
                'llm': llm_weight,
                'github': 0.0,  # BANNED
                'social': 0.0,  # BANNED (unless very specific)
                'correlation': 0.0,
            }
            result['fusion_strategy'] = 'POLITICS: 90% Order Flow + 10% LLM (GitHub/Social BANNED)'
            result['banned_sources'] = ['github', 'social']
            
        elif detected_category == 'crypto':
            # ============================================================
            # CRYPTO: Full Fusion (Order Flow + LLM + GitHub + Correlation)
            # This is the original strategy - crypto benefits from all signals
            # ============================================================
            poly_weight = result.get('polymarket_confidence', 0) * 0.30
            llm_weight = result['llm_confidence'] * 0.35
            corr_weight = result['correlation_strength'] * 0.15
            gh_weight = github_confidence * 0.20
            
            total_weight = poly_weight + llm_weight + corr_weight + gh_weight
            
            if total_weight > 0:
                combined_sentiment = (
                    result['polymarket_sentiment'] * poly_weight +
                    result['llm_sentiment'] * llm_weight +
                    result['correlation_sentiment'] * corr_weight +
                    github_sentiment * gh_weight
                ) / total_weight
                combined_confidence = min(0.95, total_weight)
            else:
                combined_sentiment = yes_price
                combined_confidence = 0.1
            
            weight_breakdown = {
                'sports_odds': 0.0,
                'orderflow': round(poly_weight / max(total_weight, 0.01), 3),
                'llm': round(llm_weight / max(total_weight, 0.01), 3),
                'github': round(gh_weight / max(total_weight, 0.01), 3),
                'correlation': round(corr_weight / max(total_weight, 0.01), 3),
            }
            result['fusion_strategy'] = 'CRYPTO: Full Fusion (30% Order Flow + 35% LLM + 20% GitHub + 15% Corr)'
            
        else:
            # ============================================================
            # OTHER/UNKNOWN: 100% Order Flow (safest default)
            # ============================================================
            combined_sentiment = result['polymarket_sentiment']
            combined_confidence = result['polymarket_confidence']
            
            weight_breakdown = {
                'sports_odds': 0.0,
                'orderflow': 1.0,
                'llm': 0.0,
                'github': 0.0,
                'correlation': 0.0,
            }
            result['fusion_strategy'] = f'OTHER ({detected_category}): 100% Order Flow (safe default)'
        
        result['combined_sentiment'] = combined_sentiment
        result['combined_confidence'] = combined_confidence
        result['weight_breakdown'] = weight_breakdown
        result['analysis_source'] = '+'.join(sources_used) if sources_used else 'fallback'
        
        # Log the fusion decision for debugging
        sentiment_str = f"{combined_sentiment:.3f}" if combined_sentiment is not None else "BLOCKED"
        logger.info(f"[FUSION] {question[:30]}... | "
                   f"Category={detected_category} | "
                   f"Combined={sentiment_str} | "
                   f"Strategy={result['fusion_strategy'][:50]}")
        
        return result


# Singleton instance
_enhanced_sentiment = None

def get_enhanced_sentiment_analyzer() -> EnhancedSentimentAnalyzer:
    """Get singleton instance of enhanced sentiment analyzer"""
    global _enhanced_sentiment
    if _enhanced_sentiment is None:
        _enhanced_sentiment = EnhancedSentimentAnalyzer()
    return _enhanced_sentiment
