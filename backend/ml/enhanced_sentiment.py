"""
Enhanced Sentiment Analysis with LLM + Cross-Market Correlation
Combines multiple data sources for comprehensive market sentiment

Updated: Integrated Hybrid Smart-Cache LLM Module
- Hot markets (high volume): 10 min cache TTL
- Cold markets (low volume): 60 min cache TTL
- Result: 100% market coverage without 100% of the cost
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
    
    Smart Cache Strategy:
    - Hot markets (high volume): 10 min cache TTL
    - Cold markets (low volume): 60 min cache TTL
    - Result: 100% market coverage without 100% of the cost
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
    
    async def analyze(self, market_data: Dict, trades: List = None, order_book: Dict = None) -> Dict:
        """
        Comprehensive sentiment analysis combining all sources.
        
        Args:
            market_data: Market info (price, volume, etc.)
            trades: Optional recent trades for Polymarket sentiment
            order_book: Optional order book for spread analysis
        
        Returns:
        {
            'llm_sentiment': float,      # LLM-based analysis
            'llm_confidence': float,     # LLM confidence
            'correlation_sentiment': float,  # Cross-market correlation
            'correlation_strength': float,   # Correlation confidence
            'polymarket_sentiment': float,   # Polymarket-native signals
            'polymarket_momentum': dict,     # Sentiment momentum (1h/6h/24h)
            'combined_sentiment': float,     # Final fused sentiment
            'combined_confidence': float,    # Overall confidence
            'analysis_source': str,          # What sources were used
        }
        """
        market_id = market_data.get('id', '')
        question = market_data.get('question', '')
        category = market_data.get('category', 'unknown')
        yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
        
        result = {
            'llm_sentiment': 0.5,
            'llm_confidence': 0.0,
            'llm_reasoning': '',
            'correlation_sentiment': 0.5,
            'correlation_strength': 0.0,
            'polymarket_sentiment': 0.5,
            'polymarket_confidence': 0.0,
            'polymarket_momentum': {},
            'combined_sentiment': 0.5,
            'combined_confidence': 0.0,
            'analysis_source': 'none'
        }
        
        sources_used = []
        
        # ================================================================
        # 1. POLYMARKET-NATIVE SENTIMENT (NEW - No external API needed)
        # ================================================================
        if self.polymarket_sentiment:
            try:
                poly_result = await self.polymarket_sentiment.analyze_market(
                    market_id=market_id,
                    market_data=market_data,
                    trades=trades,
                    order_book=order_book
                )
                
                result['polymarket_sentiment'] = poly_result.get('combined_score', 0.5)
                result['polymarket_momentum'] = poly_result.get('sentiment_momentum', {})
                result['polymarket_signals'] = poly_result.get('signals', {})
                result['polymarket_interpretation'] = poly_result.get('interpretation', '')
                
                # Confidence based on data quality
                data_quality = poly_result.get('data_quality', {})
                poly_confidence = 0.3  # Base confidence
                if data_quality.get('has_trades'):
                    poly_confidence += 0.2
                if data_quality.get('has_order_book'):
                    poly_confidence += 0.2
                if data_quality.get('price_history_points', 0) > 10:
                    poly_confidence += 0.15
                if data_quality.get('trade_history_points', 0) > 20:
                    poly_confidence += 0.15
                
                result['polymarket_confidence'] = min(0.9, poly_confidence)
                sources_used.append('polymarket')
                
            except Exception as e:
                logger.debug(f"Polymarket sentiment error: {e}")
        
        # ================================================================
        # 2. LLM SENTIMENT (HYBRID SMART-CACHE)
        # ================================================================
        # Uses the new Smart LLM module with activity-based caching:
        # - Hot markets (>$50k volume): 10 min cache
        # - Cold markets (<$50k volume): 60 min cache
        if self.smart_llm:
            try:
                llm_sentiment, llm_confidence = await self.smart_llm.get_sentiment(market_data)
                result['llm_sentiment'] = llm_sentiment
                result['llm_confidence'] = llm_confidence
                result['llm_reasoning'] = self.smart_llm.get_cached_reasoning(market_id)
                
                if llm_confidence > 0:
                    sources_used.append('llm')
                    
            except Exception as e:
                logger.debug(f"Smart LLM sentiment error: {e}")
            sources_used.append('llm')
        
        # ================================================================
        # 3. CROSS-MARKET CORRELATION
        # ================================================================
        correlation_result = self.correlation_tracker.get_correlation_signal(
            market_id, category, question, yes_price
        )
        result['correlation_sentiment'] = correlation_result['correlation_sentiment']
        result['correlation_strength'] = correlation_result['correlation_strength']
        result['category_momentum'] = correlation_result['category_momentum']
        result['related_groups'] = correlation_result['related_groups']
        sources_used.append('correlation')
        
        # ================================================================
        # 4. GITHUB SENTIMENT (for crypto/tech markets)
        # ================================================================
        github_sentiment = 0.5
        github_confidence = 0.0
        
        if self.github_sentiment:
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
        
        # ================================================================
        # 5. COMBINE ALL SIGNALS
        # ================================================================
        # Dynamic weighting based on confidence
        poly_weight = result.get('polymarket_confidence', 0) * 0.30   # Polymarket: 30% max
        llm_weight = result['llm_confidence'] * 0.35                   # LLM: 35% max  
        corr_weight = result['correlation_strength'] * 0.15            # Correlation: 15% max
        github_weight = github_confidence * 0.20                       # GitHub: 20% max (for crypto/tech)
        
        total_weight = poly_weight + llm_weight + corr_weight + github_weight
        
        if total_weight > 0:
            result['combined_sentiment'] = (
                result.get('polymarket_sentiment', 0.5) * poly_weight +
                result['llm_sentiment'] * llm_weight +
                result['correlation_sentiment'] * corr_weight +
                github_sentiment * github_weight
            ) / total_weight
            result['combined_confidence'] = min(0.95, total_weight)
        else:
            # No external signals - use price as fallback
            result['combined_sentiment'] = yes_price
            result['combined_confidence'] = 0.1
        
        result['analysis_source'] = '+'.join(sources_used) if sources_used else 'fallback'
        
        # Add weight breakdown for debugging
        result['weight_breakdown'] = {
            'polymarket': round(poly_weight, 3),
            'llm': round(llm_weight, 3),
            'correlation': round(corr_weight, 3),
            'github': round(github_weight, 3),
            'total': round(total_weight, 3)
        }
        
        return result
    
    async def _get_llm_sentiment(self, market_id: str, question: str, category: str, current_price: float) -> Optional[Dict]:
        """Get LLM sentiment with caching and rate limiting"""
        
        # Check cache first
        cached = self.llm_cache.get(market_id)
        if cached:
            logger.debug(f"LLM sentiment cache hit for {market_id[:16]}")
            return cached
        
        # Rate limiting check
        now = datetime.now(timezone.utc)
        time_since_last = (now - self.last_llm_call).total_seconds()
        
        if time_since_last < self.min_llm_interval:
            logger.debug("LLM rate limited - skipping")
            return None
        
        if not self.gpt_chat:
            return None
        
        try:
            from emergentintegrations.llm.chat import UserMessage
            
            # Build context-aware prompt with more detail
            prompt = f"""PREDICTION MARKET ANALYSIS

Question: {question}
Category: {category}
Current Market Price: {current_price:.3f} (This is what traders currently believe)

Analyze this prediction market and estimate the TRUE probability of the outcome.

Consider:
- Is the market price reasonable given current events?
- What factors might traders be over/under-weighting?
- Any recent news that could shift probability?

Return ONLY a number between 0.00 and 1.00:"""
            
            self.last_llm_call = now
            self.llm_calls_count += 1
            
            # Call LLM with timeout (send_message is already async)
            message = UserMessage(text=prompt)
            response = await asyncio.wait_for(
                self.gpt_chat.send_message(message),
                timeout=5.0
            )
            
            # Ensure response is a string
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Parse response
            sentiment = self._extract_score(response_text)
            
            # Calculate confidence based on how different from market price
            # If LLM agrees with market, lower confidence (not adding value)
            # If LLM disagrees, higher confidence (potential alpha)
            price_diff = abs(sentiment - current_price)
            confidence = 0.3 + (price_diff * 0.7)  # 0.3-1.0 range
            confidence = min(0.9, confidence)
            
            result = {
                'sentiment': sentiment,
                'confidence': confidence,
                'reasoning': response_text[:200] if len(response_text) > 200 else response_text
            }
            
            # Cache result
            self.llm_cache.set(market_id, result)
            
            logger.debug(f"LLM sentiment for {market_id[:16]}: {sentiment:.2f} (conf: {confidence:.2f})")
            return result
            
        except asyncio.TimeoutError:
            logger.debug(f"LLM timeout for {market_id[:16]}")
            return None
        except Exception as e:
            logger.warning(f"LLM sentiment error: {e}")
            return None
    
    def _extract_score(self, response: str) -> float:
        """Extract numerical score from LLM response"""
        import re
        try:
            # Look for decimal numbers
            numbers = re.findall(r'0\.\d+|1\.0|0|1', response)
            if numbers:
                score = float(numbers[0])
                return min(max(score, 0.0), 1.0)
            return 0.5
        except:
            return 0.5


# Singleton instance
_enhanced_sentiment = None

def get_enhanced_sentiment_analyzer() -> EnhancedSentimentAnalyzer:
    """Get singleton instance of enhanced sentiment analyzer"""
    global _enhanced_sentiment
    if _enhanced_sentiment is None:
        _enhanced_sentiment = EnhancedSentimentAnalyzer()
    return _enhanced_sentiment
