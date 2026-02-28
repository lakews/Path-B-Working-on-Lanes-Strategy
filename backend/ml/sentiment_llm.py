"""
Hybrid Smart-Cache LLM Sentiment Module for APEX TRADER

This module implements the "Hybrid Smart-Cache" strategy for LLM sentiment analysis:
- "Hot" Markets (High Volume): Refresh LLM opinion more frequently (configurable)
- "Cold" Markets (Low Volume): Refresh LLM opinion less frequently (configurable)
- Result: 100% market coverage without 100% of the cost

Architecture Position: Step 1 (Data Collection)
- Inputs: Market Question, Description, Categories, Volume
- Outputs: sentiment_value (0.0–1.0), confidence (0.0–1.0)
- Downstream: Fed to Weighted Fusion Engine (Step 3)
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
from config import config

logger = logging.getLogger(__name__)

# ==============================================================================
# DEFAULT CONFIGURATION (Can be updated at runtime)
# ==============================================================================

# Note: hot_market_volume_threshold now loaded from RISK config (Task 26)
DEFAULT_CONFIG = {
    'hot_market_ttl_seconds': 600,        # 10 minutes for high-volume markets
    'cold_market_ttl_seconds': 3600,      # 60 minutes for low-volume markets
    'hot_market_volume_threshold': 50000, # Default - will be overridden by RISK
    'llm_timeout_seconds': 10.0,
    'estimated_cost_per_call': 0.002,     # ~$0.002 per GPT-4o-mini call
}


# ==============================================================================
# SMART CACHE IMPLEMENTATION
# ==============================================================================

class SmartLLMCache:
    """
    Intelligent cache that adjusts TTL based on market activity.
    
    Hot markets (high volume) = shorter TTL (catch breaking news)
    Cold markets (low volume) = longer TTL (save money)
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._config = DEFAULT_CONFIG.copy()
        
        # Load hot market threshold from RISK (Task 26: Unified SSOT)
        try:
            from risk_config import RISK
            self._config['hot_market_volume_threshold'] = RISK.HOT_MARKET_VOLUME_THRESHOLD
        except ImportError:
            pass  # Use default
        
        self._stats = {
            'hits': 0,
            'misses': 0,
            'hot_refreshes': 0,
            'cold_refreshes': 0,
            'hot_market_calls': 0,
            'cold_market_calls': 0,
        }
    
    def update_config(self, new_config: Dict) -> Dict:
        """Update cache configuration"""
        for key in ['hot_market_ttl_seconds', 'cold_market_ttl_seconds', 
                    'hot_market_volume_threshold', 'llm_timeout_seconds',
                    'estimated_cost_per_call']:
            if key in new_config:
                self._config[key] = new_config[key]
        return self._config.copy()
    
    def get_config(self) -> Dict:
        """Get current configuration"""
        return self._config.copy()
    
    def _get_ttl(self, volume_24h: float) -> int:
        """Determine TTL based on market volume"""
        if volume_24h >= self._config['hot_market_volume_threshold']:
            return self._config['hot_market_ttl_seconds']
        return self._config['cold_market_ttl_seconds']
    
    def _is_hot_market(self, volume_24h: float) -> bool:
        """Check if market qualifies as hot"""
        return volume_24h >= self._config['hot_market_volume_threshold']
    
    def _is_expired(self, entry: Dict, volume_24h: float) -> bool:
        """Check if cache entry is expired based on current volume"""
        ttl = self._get_ttl(volume_24h)
        age = (datetime.now(timezone.utc) - entry['timestamp']).total_seconds()
        return age > ttl
    
    def get(self, market_id: str, volume_24h: float) -> Optional[Tuple[float, float]]:
        """
        Get cached sentiment if not expired.
        
        Args:
            market_id: Unique market identifier
            volume_24h: Current 24h volume (determines TTL)
            
        Returns:
            Tuple of (sentiment, confidence) or None if cache miss/expired
        """
        if market_id not in self._cache:
            self._stats['misses'] += 1
            return None
        
        entry = self._cache[market_id]
        
        if self._is_expired(entry, volume_24h):
            self._stats['misses'] += 1
            is_hot = self._is_hot_market(volume_24h)
            if is_hot:
                self._stats['hot_refreshes'] += 1
            else:
                self._stats['cold_refreshes'] += 1
            return None
        
        self._stats['hits'] += 1
        return (entry['sentiment'], entry['confidence'])
    
    def set(self, market_id: str, sentiment: float, confidence: float, 
            reasoning: str = "", volume_24h: float = 0):
        """Store sentiment in cache with timestamp and market type"""
        is_hot = self._is_hot_market(volume_24h)
        
        self._cache[market_id] = {
            'sentiment': sentiment,
            'confidence': confidence,
            'reasoning': reasoning,
            'timestamp': datetime.now(timezone.utc),
            'volume_24h': volume_24h,
            'is_hot_market': is_hot,
        }
        
        # Track call types
        if is_hot:
            self._stats['hot_market_calls'] += 1
        else:
            self._stats['cold_market_calls'] += 1
    
    def get_reasoning(self, market_id: str) -> str:
        """Get cached reasoning for a market"""
        if market_id in self._cache:
            return self._cache[market_id].get('reasoning', '')
        return ''
    
    def get_stats(self) -> Dict:
        """Get cache performance statistics with cost savings"""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0
        
        # Calculate cost savings
        cost_per_call = self._config['estimated_cost_per_call']
        api_calls_made = self._stats['hot_market_calls'] + self._stats['cold_market_calls']
        api_calls_saved = self._stats['hits']
        cost_saved = api_calls_saved * cost_per_call
        cost_spent = api_calls_made * cost_per_call
        
        # Count hot vs cold markets in cache
        hot_markets = sum(1 for m in self._cache.values() if m.get('is_hot_market', False))
        cold_markets = len(self._cache) - hot_markets
        
        return {
            **self._stats,
            'total_requests': total,
            'hit_rate': round(hit_rate, 3),
            'cache_size': len(self._cache),
            'hot_markets_cached': hot_markets,
            'cold_markets_cached': cold_markets,
            'api_calls_made': api_calls_made,
            'api_calls_saved': api_calls_saved,
            'estimated_cost_spent': round(cost_spent, 4),
            'estimated_cost_saved': round(cost_saved, 4),
        }
    
    def clear_expired(self, default_volume: float = 0):
        """Remove all expired entries"""
        now = datetime.now(timezone.utc)
        expired = []
        for market_id, entry in self._cache.items():
            volume = entry.get('volume_24h', default_volume)
            if self._is_expired(entry, volume):
                expired.append(market_id)
        
        for market_id in expired:
            del self._cache[market_id]
        
        return len(expired)
    
    def get_cache_entries(self) -> Dict:
        """Get all cache entries with metadata"""
        now = datetime.now(timezone.utc)
        entries = {}
        for market_id, entry in self._cache.items():
            age = (now - entry['timestamp']).total_seconds()
            ttl = self._get_ttl(entry.get('volume_24h', 0))
            entries[market_id[:16]] = {
                'sentiment': entry['sentiment'],
                'confidence': entry['confidence'],
                'is_hot': entry.get('is_hot_market', False),
                'age_seconds': round(age),
                'ttl_seconds': ttl,
                'expires_in': max(0, ttl - age),
                'volume_24h': entry.get('volume_24h', 0),
            }
        return entries


# ==============================================================================
# LLM SENTIMENT ANALYZER
# ==============================================================================

class SmartLLMSentimentAnalyzer:
    """
    LLM Sentiment Analyzer with Smart Caching.
    
    Uses GPT-4o-mini via Emergent integration with intelligent caching
    based on market activity levels.
    """
    
    def __init__(self):
        self._cache = SmartLLMCache()
        self._gpt_chat = None
        self._initialized = False
        self._init_error = None
        self._call_count = 0
        
    def _ensure_initialized(self):
        """Lazy initialization of LLM client"""
        if self._initialized:
            return self._gpt_chat is not None
        
        self._initialized = True
        
        try:
            from emergentintegrations.llm.chat import LlmChat
            
            system_prompt = """You are an expert prediction market analyst. Your job is to estimate TRUE probabilities for prediction market questions.

ANALYSIS FRAMEWORK:
1. Base Rate: Historical frequency of similar events
2. Current Evidence: Recent news, data, or developments
3. Market Context: Is current price justified or mispriced?
4. Time Factor: How deadline affects probability
5. Contrarian Check: What could the market be missing?

CALIBRATION GUIDELINES:
- 0.00-0.10: Near impossible (< 10% chance)
- 0.10-0.30: Unlikely (10-30% chance)
- 0.30-0.50: Somewhat unlikely (30-50% chance)
- 0.50: Maximum uncertainty / coin flip
- 0.50-0.70: Somewhat likely (50-70% chance)
- 0.70-0.90: Likely (70-90% chance)
- 0.90-1.00: Near certain (> 90% chance)

RESPONSE: Return ONLY a decimal number between 0.00 and 1.00."""

            self._gpt_chat = LlmChat(
                api_key=config.EMERGENT_LLM_KEY,
                session_id=f"apex_smart_llm_{datetime.now().strftime('%Y%m%d_%H')}",
                system_message=system_prompt
            ).with_model("openai", "gpt-4o-mini")
            
            logger.info("Smart LLM Sentiment Analyzer initialized successfully")
            return True
            
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"Could not initialize Smart LLM: {e}")
            return False
    
    def update_config(self, new_config: Dict) -> Dict:
        """Update cache configuration"""
        return self._cache.update_config(new_config)
    
    def get_config(self) -> Dict:
        """Get current configuration"""
        return self._cache.get_config()
    
    def _build_prompt(self, question: str, description: str, category: str, 
                      current_price: float, volume_24h: float) -> str:
        """Build context-aware analysis prompt"""
        
        # Determine market activity level for context
        is_hot = self._cache._is_hot_market(volume_24h)
        activity = "HIGH ACTIVITY" if is_hot else "LOW ACTIVITY"
        
        prompt = f"""PREDICTION MARKET ANALYSIS

Question: {question}
Category: {category}
Description: {description[:500] if description else 'N/A'}

Market Data:
- Current Price: {current_price:.3f} ({current_price*100:.1f}% implied probability)
- 24h Volume: ${volume_24h:,.0f} ({activity})

Task: Estimate the TRUE probability of this outcome.

Consider:
1. Is the market price ({current_price:.1%}) reasonable?
2. What factors might be over/under-weighted?
3. Any recent developments that could shift probability?

Return ONLY a number between 0.00 and 1.00:"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> float:
        """Extract probability from LLM response with robust parsing"""
        try:
            # Clean the response
            text = response_text.strip()
            
            # Try to find decimal numbers
            patterns = [
                r'0\.\d+',      # 0.XX
                r'1\.0+',       # 1.0, 1.00
                r'\b([0-9])\b', # Single digit
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                if matches:
                    value = float(matches[0])
                    # Clamp to valid range
                    return max(0.01, min(0.99, value))
            
            # If we got a percentage like "75%"
            pct_match = re.search(r'(\d+)%', text)
            if pct_match:
                return max(0.01, min(0.99, float(pct_match.group(1)) / 100))
            
            # Default to neutral if parsing fails
            logger.warning(f"Could not parse LLM response: {text[:100]}")
            return 0.5
            
        except Exception as e:
            logger.warning(f"LLM response parsing error: {e}")
            return 0.5
    
    def _calculate_confidence(self, llm_sentiment: float, market_price: float, 
                              volume_24h: float) -> float:
        """
        Calculate confidence based on:
        1. Divergence from market price (more divergence = more potential alpha = higher confidence)
        2. Market volume (higher volume = more reliable market = lower confidence in divergence)
        """
        # Base confidence
        confidence = 0.3
        
        # Price divergence component
        price_diff = abs(llm_sentiment - market_price)
        divergence_confidence = price_diff * 0.6  # Up to 0.6 additional confidence
        
        # Volume adjustment (high volume markets are more efficient)
        if self._cache._is_hot_market(volume_24h):
            # Hot market: reduce confidence in divergence (market is likely efficient)
            volume_factor = 0.7
        else:
            # Cold market: higher confidence in divergence (potential inefficiency)
            volume_factor = 1.0
        
        confidence += divergence_confidence * volume_factor
        
        # Clamp confidence
        return max(0.1, min(0.9, confidence))
    
    async def get_sentiment(self, market_data: Dict) -> Tuple[float, float]:
        """
        Get LLM sentiment for a market with smart caching.
        
        Args:
            market_data: Dict containing:
                - id: Market identifier
                - question: Market question
                - description: Market description (optional)
                - category: Market category
                - yes_price: Current YES price
                - volume_24h: 24-hour volume
        
        Returns:
            Tuple of (sentiment, confidence)
            - sentiment: 0.0-1.0 probability estimate
            - confidence: 0.0-1.0 confidence in the estimate
            
        Safety: Returns (0.5, 0.0) on any error (neutral with zero weight)
        """
        market_id = market_data.get('id', '')
        volume_24h = float(market_data.get('volume_24h', 0) or 0)
        
        # Check cache first
        cached = self._cache.get(market_id, volume_24h)
        if cached is not None:
            logger.debug(f"LLM cache HIT for {market_id[:16]}")
            return cached
        
        # Ensure LLM is initialized
        if not self._ensure_initialized():
            logger.debug("LLM not available, returning neutral")
            return (0.5, 0.0)
        
        # Extract market data
        question = market_data.get('question', '')
        description = market_data.get('description', '')
        category = market_data.get('category', 'unknown')
        current_price = float(market_data.get('yes_price', 0.5) or 0.5)
        
        try:
            from emergentintegrations.llm.chat import UserMessage
            
            # Build prompt
            prompt = self._build_prompt(question, description, category, current_price, volume_24h)
            
            # Get timeout from config
            timeout = self._cache.get_config().get('llm_timeout_seconds', 10.0)
            
            # Call LLM with timeout
            message = UserMessage(text=prompt)
            response = await asyncio.wait_for(
                self._gpt_chat.send_message(message),
                timeout=timeout
            )
            
            # Extract response text
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Parse sentiment
            sentiment = self._parse_response(response_text)
            
            # Calculate confidence
            confidence = self._calculate_confidence(sentiment, current_price, volume_24h)
            
            # Cache result
            self._cache.set(market_id, sentiment, confidence, response_text[:200], volume_24h)
            
            self._call_count += 1
            logger.debug(f"LLM sentiment for {market_id[:16]}: {sentiment:.2f} (conf: {confidence:.2f})")
            
            return (sentiment, confidence)
            
        except asyncio.TimeoutError:
            logger.warning(f"LLM timeout for {market_id[:16]}")
            return (0.5, 0.0)
            
        except Exception as e:
            logger.warning(f"LLM sentiment error: {e}")
            return (0.5, 0.0)
    
    def get_cached_reasoning(self, market_id: str) -> str:
        """Get the cached reasoning for a market"""
        return self._cache.get_reasoning(market_id)
    
    def get_stats(self) -> Dict:
        """Get analyzer statistics"""
        cache_stats = self._cache.get_stats()
        return {
            **cache_stats,
            'llm_calls': self._call_count,
            'llm_initialized': self._gpt_chat is not None,
            'init_error': self._init_error,
            'config': self._cache.get_config()
        }
    
    def get_cache_entries(self) -> Dict:
        """Get all cache entries"""
        return self._cache.get_cache_entries()
    
    def clear_expired_cache(self) -> int:
        """Clear expired cache entries, returns count of cleared entries"""
        return self._cache.clear_expired()


# ==============================================================================
# SINGLETON INSTANCE & PUBLIC API
# ==============================================================================

_smart_llm_analyzer: Optional[SmartLLMSentimentAnalyzer] = None

def get_smart_llm_analyzer() -> SmartLLMSentimentAnalyzer:
    """Get singleton instance of Smart LLM Sentiment Analyzer"""
    global _smart_llm_analyzer
    if _smart_llm_analyzer is None:
        _smart_llm_analyzer = SmartLLMSentimentAnalyzer()
    return _smart_llm_analyzer


async def get_llm_sentiment(market_data: Dict) -> Tuple[float, float]:
    """
    Convenience function to get LLM sentiment.
    
    This is the main entry point for the sentiment_llm module.
    
    Args:
        market_data: Dict with market information
        
    Returns:
        Tuple of (sentiment, confidence)
        
    Example:
        sentiment, confidence = await get_llm_sentiment({
            'id': 'market_123',
            'question': 'Will Bitcoin reach $100k?',
            'category': 'crypto',
            'yes_price': 0.35,
            'volume_24h': 500000
        })
    """
    analyzer = get_smart_llm_analyzer()
    return await analyzer.get_sentiment(market_data)
