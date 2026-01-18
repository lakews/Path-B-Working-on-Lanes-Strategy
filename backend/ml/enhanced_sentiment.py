"""
Enhanced Sentiment Analysis with LLM + Cross-Market Correlation
Combines multiple data sources for comprehensive market sentiment
"""
import asyncio
import logging
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
from config import config

logger = logging.getLogger(__name__)


class LLMSentimentCache:
    """Smart caching for LLM sentiment to minimize API calls"""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute default TTL
        self.cache: Dict[str, Dict] = {}
        self.ttl = ttl_seconds
    
    def get(self, market_id: str) -> Optional[Dict]:
        """Get cached sentiment if not expired"""
        if market_id in self.cache:
            entry = self.cache[market_id]
            if datetime.now(timezone.utc) - entry['timestamp'] < timedelta(seconds=self.ttl):
                return entry['data']
        return None
    
    def set(self, market_id: str, data: Dict):
        """Cache sentiment data"""
        self.cache[market_id] = {
            'data': data,
            'timestamp': datetime.now(timezone.utc)
        }
    
    def clear_expired(self):
        """Remove expired entries"""
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self.cache.items() 
                   if now - v['timestamp'] > timedelta(seconds=self.ttl)]
        for k in expired:
            del self.cache[k]


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
    1. LLM analysis (GPT-4o-mini via Emergent)
    2. Cross-market correlation
    3. Polymarket-native sentiment (order flow, volume momentum, whale signals)
    4. Smart caching to minimize API costs
    """
    
    def __init__(self):
        self._db = None
        self.llm_cache = LLMSentimentCache(ttl_seconds=300)  # 5 min cache
        self.correlation_tracker = CrossMarketCorrelation()
        self.llm_analyzer = None
        self._init_llm()
        
        # Initialize Polymarket sentiment extractor
        try:
            from ml.polymarket_sentiment import get_polymarket_sentiment_extractor
            self.polymarket_sentiment = get_polymarket_sentiment_extractor()
            logger.info("Polymarket sentiment extractor initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Polymarket sentiment: {e}")
            self.polymarket_sentiment = None
        
        # Rate limiting for LLM calls
        self.last_llm_call = datetime.now(timezone.utc)
        self.min_llm_interval = 1.0  # Minimum 1 second between LLM calls
        self.llm_calls_count = 0
        self.max_llm_calls_per_minute = 30  # Rate limit
    
    @property
    def db(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db
    
    def _init_llm(self):
        """Initialize LLM models with error handling"""
        try:
            from emergentintegrations.llm.chat import LlmChat
            
            system_prompt = """You are an expert prediction market analyst specializing in probability assessment. Your task is to analyze prediction market questions and provide independent probability estimates.

ANALYSIS FRAMEWORK:
1. **Base Rate**: What's the historical frequency of similar events?
2. **Current Evidence**: What recent news, data, or events are relevant?
3. **Market Context**: Is the current price justified or mispriced?
4. **Time Factor**: How does the deadline affect probability?
5. **Contrarian Check**: What could the market be missing?

RESPONSE FORMAT:
Return ONLY a decimal number between 0.00 and 1.00 representing probability.
- 0.00-0.10: Extremely unlikely (< 10% chance)
- 0.10-0.30: Unlikely (10-30% chance)
- 0.30-0.50: Somewhat unlikely (30-50% chance)  
- 0.50-0.70: Somewhat likely (50-70% chance)
- 0.70-0.90: Likely (70-90% chance)
- 0.90-1.00: Extremely likely (> 90% chance)

Be calibrated - if you're uncertain, stay closer to 0.50.
If current price seems reasonable, return a value close to it.
If you see clear mispricing, diverge from market price."""

            self.gpt_chat = LlmChat(
                api_key=config.EMERGENT_LLM_KEY,
                session_id=f"apex_sentiment_{datetime.now().strftime('%Y%m%d')}",
                system_message=system_prompt
            ).with_model("openai", "gpt-4o-mini")
            
            logger.info("Enhanced sentiment LLM initialized with tuned prompt")
        except Exception as e:
            logger.warning(f"Could not initialize LLM sentiment: {e}")
            self.gpt_chat = None
    
    async def analyze(self, market_data: Dict) -> Dict:
        """
        Comprehensive sentiment analysis combining all sources.
        
        Returns:
        {
            'llm_sentiment': float,      # LLM-based analysis
            'llm_confidence': float,     # LLM confidence
            'correlation_sentiment': float,  # Cross-market correlation
            'correlation_strength': float,   # Correlation confidence
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
            'combined_sentiment': 0.5,
            'combined_confidence': 0.0,
            'analysis_source': 'none'
        }
        
        sources_used = []
        
        # ================================================================
        # 1. LLM SENTIMENT (with caching)
        # ================================================================
        llm_result = await self._get_llm_sentiment(market_id, question, category, yes_price)
        if llm_result:
            result['llm_sentiment'] = llm_result['sentiment']
            result['llm_confidence'] = llm_result['confidence']
            result['llm_reasoning'] = llm_result.get('reasoning', '')
            sources_used.append('llm')
        
        # ================================================================
        # 2. CROSS-MARKET CORRELATION
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
        # 3. COMBINE SIGNALS
        # ================================================================
        # Weight by confidence
        llm_weight = result['llm_confidence'] * 0.6  # LLM gets 60% max weight
        corr_weight = result['correlation_strength'] * 0.4  # Correlation gets 40% max
        
        total_weight = llm_weight + corr_weight
        
        if total_weight > 0:
            result['combined_sentiment'] = (
                result['llm_sentiment'] * llm_weight +
                result['correlation_sentiment'] * corr_weight
            ) / total_weight
            result['combined_confidence'] = min(0.95, total_weight)
        else:
            # No external signals - use price as fallback
            result['combined_sentiment'] = yes_price
            result['combined_confidence'] = 0.1
        
        result['analysis_source'] = '+'.join(sources_used) if sources_used else 'fallback'
        
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
