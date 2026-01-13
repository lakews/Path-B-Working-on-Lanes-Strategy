import logging
from typing import Dict, Tuple
from datetime import datetime, timezone
from database import get_db
from config import config
from emergentintegrations.llm.chat import LlmChat, UserMessage
import asyncio
import uuid

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """GPT-5.2 + Gemini fusion for sentiment analysis"""
    
    def __init__(self):
        self.db = get_db()
        self.gpt_chat = None
        self.gemini_chat = None
        self._init_models()
        
    def _init_models(self):
        """Initialize LLM models"""
        try:
            self.gpt_chat = LlmChat(
                api_key=config.EMERGENT_LLM_KEY,
                session_id="apex_gpt_sentiment",
                system_message="You are a financial sentiment analyzer. Analyze market sentiment and return a score between 0 (very bearish) and 1 (very bullish). Be concise and return only the numerical score."
            ).with_model("openai", "gpt-5.2")
            
            self.gemini_chat = LlmChat(
                api_key=config.EMERGENT_LLM_KEY,
                session_id="apex_gemini_sentiment",
                system_message="You are a prediction market sentiment analyzer. Analyze the market question and related context. Return a sentiment score between 0 (very negative) and 1 (very positive) with brief reasoning."
            ).with_model("gemini", "gemini-3-flash-preview")
            
            logger.info("Sentiment models initialized")
        except Exception as e:
            logger.error(f"Error initializing sentiment models: {e}")
    
    async def analyze_sentiment(self, market_data: Dict, news_context: str = "") -> Tuple[float, float]:
        """Analyze sentiment using GPT-5.2 + Gemini fusion
        Returns: (sentiment_score, confidence)
        """
        try:
            question = market_data.get('question', '')
            category = market_data.get('category', 'finance')
            
            gpt_score = await self._gpt_sentiment(question, news_context, category)
            gemini_score = await self._gemini_sentiment(question, news_context, category)
            
            fused_score = (gpt_score * 0.6) + (gemini_score * 0.4)
            
            agreement = 1.0 - abs(gpt_score - gemini_score)
            confidence = min(agreement, 0.95)
            
            await self._store_signal(market_data.get('id'), fused_score, confidence)
            
            return fused_score, confidence
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return 0.5, 0.0
    
    async def _gpt_sentiment(self, question: str, context: str, category: str) -> float:
        """Get sentiment from GPT-5.2"""
        try:
            prompt = f"""Market: {question}
Category: {category}
Context: {context}

Analyze sentiment and return a single number between 0 and 1."""
            
            message = UserMessage(text=prompt)
            response = await self.gpt_chat.send_message(message)
            
            score = self._extract_score(response)
            return score
            
        except Exception as e:
            logger.error(f"Error in GPT sentiment: {e}")
            return 0.5
    
    async def _gemini_sentiment(self, question: str, context: str, category: str) -> float:
        """Get sentiment from Gemini"""
        try:
            prompt = f"""Prediction Market Question: {question}
Category: {category}
Additional Context: {context}

Provide a sentiment score (0-1) for this market's positive outcome probability."""
            
            message = UserMessage(text=prompt)
            response = await self.gemini_chat.send_message(message)
            
            score = self._extract_score(response)
            return score
            
        except Exception as e:
            logger.error(f"Error in Gemini sentiment: {e}")
            return 0.5
    
    def _extract_score(self, response: str) -> float:
        """Extract numerical score from LLM response"""
        try:
            import re
            numbers = re.findall(r'\b0\.\d+|\b1\.0|\b[01]\b', response)
            if numbers:
                score = float(numbers[0])
                return min(max(score, 0.0), 1.0)
            return 0.5
        except Exception as e:
            logger.error(f"Error extracting score: {e}")
            return 0.5
    
    async def _store_signal(self, market_id: str, score: float, confidence: float):
        """Store sentiment signal"""
        try:
            await self.db.signals.insert_one({
                "id": str(uuid.uuid4()),
                "market_id": market_id,
                "signal_type": "sentiment",
                "confidence": confidence,
                "source": "gpt_gemini_fusion",
                "value": score,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing sentiment signal: {e}")