"""
Real Social Media Sentiment Analysis Module
Uses Finnhub for stock/crypto sentiment and news, plus LLM analysis
"""
import logging
import aiohttp
import asyncio
import os
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import re

logger = logging.getLogger(__name__)

# Finnhub API key from environment
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "demo")


class SocialSentimentAnalyzer:
    """Real-time social sentiment analysis using multiple data sources"""
    
    def __init__(self):
        self._db = None
        self.finnhub_base = "https://finnhub.io/api/v1"
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 300  # 5 minutes
        
        # Mapping prediction market topics to tradable symbols
        self.topic_symbol_map = {
            "bitcoin": "BINANCE:BTCUSDT",
            "btc": "BINANCE:BTCUSDT",
            "ethereum": "BINANCE:ETHUSDT",
            "eth": "BINANCE:ETHUSDT",
            "crypto": "BINANCE:BTCUSDT",
            "tesla": "TSLA",
            "apple": "AAPL",
            "google": "GOOGL",
            "fed": "SPY",
            "interest rate": "SPY",
            "inflation": "SPY",
            "stock market": "SPY",
            "s&p": "SPY",
        }
    
    @property
    def db(self):
        if self._db is None:
            from database import get_db
            self._db = get_db()
        return self._db
    
    async def analyze_market_sentiment(self, market_data: Dict) -> Dict:
        """
        Comprehensive sentiment analysis for a prediction market
        Returns: {
            'overall_sentiment': float (0-1),
            'confidence': float (0-1),
            'news_sentiment': float,
            'social_sentiment': float,
            'news_count': int,
            'trending_score': float,
            'sources': list
        }
        """
        try:
            question = market_data.get('question', '')
            category = market_data.get('category', 'unknown')
            market_id = market_data.get('id', '')
            
            # Check cache first
            cache_key = f"sentiment_{market_id}"
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if datetime.now(timezone.utc).timestamp() - cached['timestamp'] < self.cache_ttl:
                    return cached['data']
            
            # Extract relevant symbol from market question
            symbol = self._extract_symbol(question, category)
            
            # Gather sentiment from multiple sources
            news_sentiment = await self._get_news_sentiment(question, symbol)
            social_sentiment = await self._get_social_buzz(symbol)
            keyword_sentiment = self._analyze_keywords(question)
            
            # Fuse sentiments with weighted average
            weights = {
                'news': 0.4,
                'social': 0.3,
                'keyword': 0.3
            }
            
            overall = (
                news_sentiment['score'] * weights['news'] +
                social_sentiment['score'] * weights['social'] +
                keyword_sentiment['score'] * weights['keyword']
            )
            
            # Calculate confidence based on data availability
            data_points = sum([
                1 if news_sentiment['count'] > 0 else 0,
                1 if social_sentiment['buzz'] > 0 else 0,
                1  # keyword always available
            ])
            confidence = min(data_points / 3 * 0.8 + 0.2, 0.95)
            
            result = {
                'overall_sentiment': round(overall, 4),
                'confidence': round(confidence, 4),
                'news_sentiment': news_sentiment['score'],
                'news_count': news_sentiment['count'],
                'social_sentiment': social_sentiment['score'],
                'social_buzz': social_sentiment['buzz'],
                'keyword_sentiment': keyword_sentiment['score'],
                'trending_score': social_sentiment.get('change', 0),
                'symbol_analyzed': symbol,
                'sources': news_sentiment.get('sources', []),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Cache result
            self.cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now(timezone.utc).timestamp()
            }
            
            # Store in database
            await self._store_sentiment(market_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in social sentiment analysis: {e}")
            return {
                'overall_sentiment': 0.5,
                'confidence': 0.1,
                'news_sentiment': 0.5,
                'social_sentiment': 0.5,
                'error': str(e)
            }
    
    def _extract_symbol(self, question: str, category: str) -> Optional[str]:
        """Extract tradable symbol from market question"""
        question_lower = question.lower()
        
        # Check topic mappings
        for topic, symbol in self.topic_symbol_map.items():
            if topic in question_lower:
                return symbol
        
        # Category-based defaults
        category_defaults = {
            'crypto': 'BINANCE:BTCUSDT',
            'finance': 'SPY',
            'politics': None,  # No direct symbol
            'sports': None,
            'entertainment': None
        }
        
        return category_defaults.get(category)
    
    async def _get_news_sentiment(self, question: str, symbol: Optional[str]) -> Dict:
        """Get news sentiment from Finnhub"""
        try:
            async with aiohttp.ClientSession() as session:
                if symbol and not symbol.startswith('BINANCE'):
                    # Get company news sentiment
                    url = f"{self.finnhub_base}/news-sentiment?symbol={symbol}&token={FINNHUB_API_KEY}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            sentiment = data.get('sentiment', {})
                            return {
                                'score': sentiment.get('bullishPercent', 50) / 100,
                                'count': data.get('buzz', {}).get('articlesInLastWeek', 0),
                                'sources': ['finnhub_news']
                            }
                
                # Fallback to general news for the topic
                # Extract keywords from question
                keywords = self._extract_keywords(question)
                
                url = f"{self.finnhub_base}/news?category=general&token={FINNHUB_API_KEY}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        news_items = await resp.json()
                        
                        # Filter and score news by relevance
                        relevant_count = 0
                        positive_count = 0
                        
                        for item in news_items[:50]:
                            headline = item.get('headline', '').lower()
                            summary = item.get('summary', '').lower()
                            
                            # Check relevance
                            if any(kw in headline or kw in summary for kw in keywords):
                                relevant_count += 1
                                # Simple sentiment heuristic
                                if any(w in headline for w in ['surge', 'rise', 'gain', 'up', 'positive', 'bullish', 'win']):
                                    positive_count += 1
                                elif any(w in headline for w in ['drop', 'fall', 'crash', 'down', 'negative', 'bearish', 'lose']):
                                    pass  # negative
                                else:
                                    positive_count += 0.5  # neutral
                        
                        score = positive_count / max(relevant_count, 1)
                        return {
                            'score': score,
                            'count': relevant_count,
                            'sources': ['finnhub_general_news']
                        }
                
                return {'score': 0.5, 'count': 0, 'sources': []}
                
        except Exception as e:
            logger.error(f"Error getting news sentiment: {e}")
            return {'score': 0.5, 'count': 0, 'sources': []}
    
    async def _get_social_buzz(self, symbol: Optional[str]) -> Dict:
        """Get social media buzz metrics"""
        try:
            if not symbol or symbol.startswith('BINANCE'):
                return {'score': 0.5, 'buzz': 0, 'change': 0}
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.finnhub_base}/stock/social-sentiment?symbol={symbol}&token={FINNHUB_API_KEY}"
                
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        twitter = data.get('twitter', [])
                        reddit = data.get('reddit', [])
                        
                        # Calculate aggregate sentiment
                        total_mentions = 0
                        positive_score = 0
                        
                        for item in twitter[-7:]:  # Last 7 days
                            mentions = item.get('atTime', 0)
                            score = item.get('score', 0)
                            total_mentions += mentions
                            positive_score += score * mentions
                        
                        for item in reddit[-7:]:
                            mentions = item.get('atTime', 0)
                            score = item.get('score', 0)
                            total_mentions += mentions
                            positive_score += score * mentions
                        
                        avg_score = positive_score / max(total_mentions, 1)
                        # Normalize score to 0-1
                        normalized = (avg_score + 1) / 2  # Assuming score is -1 to 1
                        
                        return {
                            'score': round(normalized, 4),
                            'buzz': total_mentions,
                            'change': data.get('change', 0)
                        }
                    
                    return {'score': 0.5, 'buzz': 0, 'change': 0}
                    
        except Exception as e:
            logger.error(f"Error getting social buzz: {e}")
            return {'score': 0.5, 'buzz': 0, 'change': 0}
    
    def _analyze_keywords(self, question: str) -> Dict:
        """Keyword-based sentiment analysis"""
        question_lower = question.lower()
        
        # Positive indicators
        positive_keywords = [
            'will', 'win', 'increase', 'rise', 'above', 'over', 'success',
            'positive', 'gain', 'approve', 'pass', 'yes', 'bullish', 'higher'
        ]
        
        # Negative indicators  
        negative_keywords = [
            'fail', 'lose', 'decrease', 'fall', 'below', 'under', 'failure',
            'negative', 'drop', 'reject', 'no', 'bearish', 'lower', 'crash'
        ]
        
        # Neutral/uncertainty indicators
        uncertain_keywords = [
            'whether', 'if', 'might', 'could', 'may', 'possibly', 'uncertain'
        ]
        
        positive_count = sum(1 for kw in positive_keywords if kw in question_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in question_lower)
        uncertain_count = sum(1 for kw in uncertain_keywords if kw in question_lower)
        
        total = positive_count + negative_count + 1
        score = (positive_count + 0.5) / total  # Slight positive bias
        
        # Reduce confidence if uncertain
        if uncertain_count > 0:
            score = score * 0.9 + 0.05
        
        return {
            'score': round(score, 4),
            'positive_keywords': positive_count,
            'negative_keywords': negative_count
        }
    
    def _extract_keywords(self, question: str) -> List[str]:
        """Extract important keywords from question"""
        # Remove common words
        stop_words = {'will', 'the', 'be', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'by', 'is', 'are'}
        
        words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
        keywords = [w for w in words if w not in stop_words]
        
        return keywords[:5]  # Top 5 keywords
    
    async def _store_sentiment(self, market_id: str, result: Dict):
        """Store sentiment analysis result"""
        try:
            await self.db.social_sentiment.update_one(
                {"market_id": market_id},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "market_id": market_id,
                    **result
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error storing sentiment: {e}")
    
    async def get_trending_topics(self, limit: int = 10) -> List[Dict]:
        """Get currently trending topics from news"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.finnhub_base}/news?category=general&token={FINNHUB_API_KEY}"
                
                async with session.get(url) as resp:
                    if resp.status == 200:
                        news_items = await resp.json()
                        
                        # Count topic frequency
                        topic_counts = {}
                        for item in news_items[:100]:
                            category = item.get('category', 'general')
                            topic_counts[category] = topic_counts.get(category, 0) + 1
                        
                        # Sort by frequency
                        trending = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
                        
                        return [
                            {'topic': t[0], 'count': t[1], 'score': t[1] / len(news_items)}
                            for t in trending[:limit]
                        ]
                    
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting trending topics: {e}")
            return []


# Singleton instance
social_sentiment_analyzer = SocialSentimentAnalyzer()
