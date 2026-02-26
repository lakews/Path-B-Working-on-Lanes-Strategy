"""
LLM SERVICE - Emergent Lane (Lane 5)
=====================================

This module handles all LLM interactions for the News/Emergent lane.
Uses the Event Resolution Adjudicator prompt for strict, calibrated analysis.

Key Features:
- YES Literalism Rule: Evaluates impact on YES outcome specifically
- Sector-specific evidence weighting
- Bayesian confidence calibration (0.50 = noise, 0.95 = resolution)
- Strict JSON output schema

CRITICAL: Use temperature=0.0 for consistent, logical outputs.
"""

import logging
import json
import re
import os
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# SYSTEM PROMPT: Event Resolution Adjudicator
# =============================================================================

SYSTEM_PROMPT_EMERGENT = """
### Role & Objective
You are the **Event Resolution Adjudicator** for a high-frequency prediction market algorithm. Your sole purpose is to determine if the provided **News Text** constitutes concrete **Evidence** that alters the probability of the **Market Question** resolving to "YES".

---

## Core Logic: The "YES" Literalism Rule
You must evaluate the impact strictly on the **YES outcome** of the specific contract, not the general sentiment of the subject.

**Scenario A (Inverse Correlation):**
- Question: "Will Bitcoin DROP below $60k?"
- News: "Bitcoin rallies to $72k on ETF approval."
- Analysis: Good for Bitcoin, but FATAL for the YES share.
- Output: `is_bullish_for_yes: false`

**Scenario B (Literal Wording):**
- Question: "Will SpaceX launch Starship by Friday?"
- News: "SpaceX delays launch due to wind."
- Analysis: The event (launch) is not happening within the timeframe.
- Output: `is_bullish_for_yes: false`

---

## Sector-Specific Evidence Guide

### 1. Politics & Macro (Elections, Fed Rates, Bills)
- **High Value:** Official White House/Fed statements, Passed Bills, Concession Speeches.
- **Low Value:** Op-Eds, Campaign rallies, "Anonymous sources".

### 2. Culture & Entertainment (Box Office, Awards, Cancellations)
- **High Value:** Variety/Deadline "Exclusive", Verified Artist Tweets, Official Studio Press Releases.
- **Low Value:** Fan theories, Reddit threads, Tabloid gossip.

### 3. Science & Tech (Space, Climate, AI)
- **High Value:** FAA Licenses, NOAA/NHC Advisories, Company Engineering Blogs.
- **Low Value:** YouTube commentary, Influencer predictions.

---

## Bayesian Confidence Scale (Calibration)
Assign confidence strictly based on **Evidentiary Weight**:

- **0.50 (Noise):** Irrelevant, stale news, or pure opinion. (Bot will NOT trade).
- **0.60 (Weak Signal):** Credible rumors ("Sources say"), strong correlated asset moves, or "leading indicators" (e.g., Early polls).
- **0.75 (Strong Signal):** Direct quotes from key decision-makers, preliminary data releases, reputable mainstream reporting (Bloomberg, Reuters, AP).
- **0.95 (Resolution):** The event has concluded. The result is known facts (e.g., "The bill has passed", "The game is over").

---

## JSON Output Schema
Return ONLY this raw JSON object. No markdown, no code blocks.

{
  "is_relevant": boolean,        // Is this text actually about the specific subject in the question?
  "is_bullish_for_yes": boolean, // TRUE = Evidence supports "YES" winning. FALSE = Evidence supports "NO".
  "confidence": float,           // 0.50 to 0.99. Be conservative.
  "rationale": "string"          // Max 15 words. Focus on the causal link (e.g. 'Official denial reduces probability of dropout').
}
"""


# =============================================================================
# SYSTEM PROMPT: Sentiment Signal Analyzer (Tier 2 - Looser)
# =============================================================================

SYSTEM_PROMPT_SENTIMENT = """
### Role & Objective
You are a **Market Sentiment Analyzer** for a prediction market trading system. Your purpose is to determine if the provided **News Text** provides ANY information that could shift the probability of the **Market Question** - even if it's not a resolution event.

---

## Core Logic: Probability Shift Detection
Unlike resolution analysis, you are looking for **leading indicators** and **sentiment shifts**:

1. **Direct mentions** of the market subject (even without resolution)
2. **Correlated events** that historically impact similar outcomes
3. **Expert opinions** from credible sources
4. **Momentum indicators** (polls, market moves, public sentiment)

---

## What Counts as Relevant

### HIGH RELEVANCE (is_relevant: true)
- News directly mentions the subject of the market question
- News about closely related events (e.g., primary results for election markets)
- Official statements from key stakeholders
- Significant data releases (polls, prices, statistics)
- Expert analysis from credible sources

### LOW RELEVANCE (is_relevant: false)
- News about completely unrelated topics
- Old/stale news (>24 hours old without new developments)
- Pure speculation without any factual basis
- News about different entities with similar names

---

## Confidence Scale (Sentiment-Adjusted)

- **0.50 (No Signal):** Truly irrelevant or stale news
- **0.55-0.60 (Weak Signal):** Tangentially related, correlated asset moves, general sentiment
- **0.65-0.70 (Moderate Signal):** Direct mention, credible rumors, preliminary data
- **0.75-0.85 (Strong Signal):** Official statements, concrete developments, strong correlation
- **0.90+ (Near Resolution):** Event almost certain, overwhelming evidence

---

## JSON Output Schema
Return ONLY this raw JSON object. No markdown, no code blocks.

{
  "is_relevant": boolean,        // Does this news provide ANY useful signal about the market?
  "is_bullish_for_yes": boolean, // TRUE = Increases YES probability. FALSE = Decreases YES probability.
  "confidence": float,           // 0.50 to 0.95. 
  "signal_type": "string",       // "RESOLUTION", "STRONG", "MODERATE", "WEAK", or "NOISE"
  "rationale": "string"          // Max 20 words. Explain the connection.
}
"""


@dataclass
class LLMAnalysisResult:
    """Result from LLM analysis of news against a market"""
    is_relevant: bool
    is_bullish_for_yes: bool
    confidence: float
    rationale: str
    signal_type: str = "NOISE"  # RESOLUTION, STRONG, MODERATE, WEAK, NOISE
    raw_response: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'is_relevant': self.is_relevant,
            'is_bullish_for_yes': self.is_bullish_for_yes,
            'confidence': self.confidence,
            'rationale': self.rationale,
            'signal_type': self.signal_type,
            'error': self.error
        }
    
    @property
    def direction(self) -> str:
        """Convert to trading direction"""
        if not self.is_relevant or self.confidence <= 0.50:
            return 'NEUTRAL'
        return 'YES' if self.is_bullish_for_yes else 'NO'
    
    @property
    def impact(self) -> str:
        """Convert confidence to impact level for EventBayes"""
        if self.confidence >= 0.95:
            return 'resolution'
        elif self.confidence >= 0.75:
            return 'strong'
        elif self.confidence >= 0.60:
            return 'moderate'
        else:
            return 'weak'


class EmergentLLMService:
    """
    LLM service for the Emergent/News lane.
    
    Uses the Event Resolution Adjudicator prompt for strict analysis.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = 'gpt-4o-mini'):
        self.model = model
        self._api_key = api_key or os.environ.get('EMERGENT_LLM_KEY') or os.environ.get('LLM_KEY')
        self._client = None
        self._UserMessage = None
        
    async def _get_client(self):
        """Lazy initialization of LLM client"""
        if self._client is None:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                self._UserMessage = UserMessage
                if self._api_key:
                    self._client = LlmChat(
                        api_key=self._api_key,
                        session_id="emergent_news_lane5",
                        system_message=SYSTEM_PROMPT_EMERGENT
                    )
                    logger.info(f"[LLM SERVICE] Initialized with model: {self.model}")
                else:
                    logger.warning("[LLM SERVICE] No API key found")
            except Exception as e:
                logger.error(f"[LLM SERVICE] Failed to init client: {e}")
        return self._client
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """
        Parse JSON from LLM response.
        
        Handles various response formats:
        - Raw JSON
        - JSON in markdown code blocks
        - JSON with extra text
        """
        # Try direct parse first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code block
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to extract JSON object from anywhere in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return None
    
    async def analyze_news_for_market(
        self,
        news_headline: str,
        news_content: str,
        market_question: str,
        market_description: str = "",
        use_sentiment_tier: bool = True
    ) -> LLMAnalysisResult:
        """
        Analyze a news item against a specific market question.
        
        TWO-TIER SYSTEM:
        - Tier 1: Event Resolution Adjudicator (strict, for resolution events)
        - Tier 2: Sentiment Signal Analyzer (looser, for leading indicators)
        
        If Tier 1 returns is_relevant=False and use_sentiment_tier=True,
        automatically falls back to Tier 2 for sentiment signals.
        
        Args:
            news_headline: News headline
            news_content: Full news content
            market_question: The prediction market question
            market_description: Additional market context
            use_sentiment_tier: Whether to use Tier 2 fallback (default True)
        
        Returns:
            LLMAnalysisResult with parsed analysis
        """
        client = await self._get_client()
        if not client:
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale="LLM service unavailable",
                signal_type="NOISE",
                error="No LLM client"
            )
        
        # Build the user prompt
        user_prompt = f"""Analyze this news against the market question.

**Market Question:** {market_question}
{f'**Market Description:** {market_description}' if market_description else ''}

**News Headline:** {news_headline}
**News Content:** {news_content[:1000]}

Respond with ONLY the JSON object as specified. No other text."""

        try:
            # TIER 1: Event Resolution Adjudicator (strict)
            user_msg = self._UserMessage(text=user_prompt)
            response = await client.send_message(user_msg)
            parsed = self._parse_json_response(response)
            
            if parsed and parsed.get('is_relevant', False):
                # Tier 1 found relevant - use strict analysis
                signal_type = "RESOLUTION" if parsed.get('confidence', 0) >= 0.90 else "STRONG"
                logger.info(f"[LLM SERVICE] Tier 1 HIT: is_relevant=True, confidence={parsed.get('confidence')}, signal_type={signal_type}")
                return LLMAnalysisResult(
                    is_relevant=True,
                    is_bullish_for_yes=parsed.get('is_bullish_for_yes', False),
                    confidence=float(parsed.get('confidence', 0.5)),
                    rationale=parsed.get('rationale', ''),
                    signal_type=signal_type,
                    raw_response=response
                )
            
            # TIER 2: Sentiment Signal Analyzer (if enabled and Tier 1 returned not relevant)
            if use_sentiment_tier:
                tier2_result = await self._analyze_sentiment_tier(
                    news_headline, news_content, market_question, market_description
                )
                if tier2_result.is_relevant:
                    logger.info(f"[LLM SERVICE] Tier 2 HIT: signal_type={tier2_result.signal_type}, confidence={tier2_result.confidence}")
                    return tier2_result
            
            # Both tiers returned not relevant
            logger.debug(f"[LLM SERVICE] No signal: Both tiers returned is_relevant=False")
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale="No actionable signal detected",
                signal_type="NOISE",
                raw_response=response
            )
                
        except Exception as e:
            logger.error(f"[LLM SERVICE] Analysis error: {e}")
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale=str(e),
                signal_type="NOISE",
                error=str(e)
            )
    
    async def _analyze_sentiment_tier(
        self,
        news_headline: str,
        news_content: str,
        market_question: str,
        market_description: str = ""
    ) -> LLMAnalysisResult:
        """
        Tier 2: Sentiment Signal Analyzer
        
        Uses a looser prompt to detect leading indicators and sentiment shifts
        that may not constitute resolution events but still provide trading signals.
        """
        client = await self._get_client()
        if not client:
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale="LLM service unavailable",
                signal_type="NOISE",
                error="No LLM client"
            )
        
        # Use the sentiment prompt
        user_prompt = f"""Analyze this news for market sentiment signals.

**Market Question:** {market_question}
{f'**Market Description:** {market_description}' if market_description else ''}

**News Headline:** {news_headline}
**News Content:** {news_content[:1000]}

Respond with ONLY the JSON object as specified. No other text."""

        try:
            # Create a new conversation with the sentiment prompt
            from emergentintegrations.llm.chat import LlmChat
            
            sentiment_chat = LlmChat(
                api_key=self._api_key,
                model=self.model,
                system_prompt=SYSTEM_PROMPT_SENTIMENT
            )
            
            user_msg = self._UserMessage(text=user_prompt)
            response = await sentiment_chat.send_message(user_msg)
            parsed = self._parse_json_response(response)
            
            if parsed:
                is_relevant = parsed.get('is_relevant', False)
                confidence = float(parsed.get('confidence', 0.5))
                signal_type = parsed.get('signal_type', 'NOISE')
                
                # Only return relevant if confidence > 0.55
                if is_relevant and confidence > 0.55:
                    return LLMAnalysisResult(
                        is_relevant=True,
                        is_bullish_for_yes=parsed.get('is_bullish_for_yes', False),
                        confidence=confidence,
                        rationale=parsed.get('rationale', ''),
                        signal_type=signal_type,
                        raw_response=response
                    )
            
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale="No sentiment signal",
                signal_type="NOISE",
                raw_response=response if response else ""
            )
                
        except Exception as e:
            logger.error(f"[LLM SERVICE] Tier 2 analysis error: {e}")
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale=str(e),
                signal_type="NOISE",
                error=str(e)
            )
    
    async def batch_analyze(
        self,
        news_headline: str,
        news_content: str,
        markets: List[Dict]
    ) -> Dict[str, LLMAnalysisResult]:
        """
        Analyze a news item against multiple markets.
        
        More efficient than individual calls for bulk analysis.
        
        Args:
            news_headline: News headline
            news_content: Full news content
            markets: List of market dicts with 'id', 'question', 'description'
        
        Returns:
            Dict mapping market_id to LLMAnalysisResult
        """
        client = await self._get_client()
        if not client:
            return {}
        
        # Build batch prompt
        market_list = "\n".join([
            f"- Market {i+1} (ID: {m['id'][:12]}...): {m.get('question', 'Unknown')}"
            for i, m in enumerate(markets[:15])  # Limit to 15 markets
        ])
        
        batch_prompt = f"""Analyze this news against multiple prediction markets.

**News Headline:** {news_headline}
**News Content:** {news_content[:800]}

**Markets to Analyze:**
{market_list}

For each RELEVANT market, provide analysis in this JSON format:
{{
  "analyses": [
    {{
      "market_index": 1,
      "is_relevant": true,
      "is_bullish_for_yes": true,
      "confidence": 0.75,
      "rationale": "Direct confirmation from official source"
    }}
  ]
}}

Only include markets where is_relevant=true. Respond with ONLY the JSON."""

        try:
            user_msg = self._UserMessage(text=batch_prompt)
            response = await client.send_message(user_msg)
            
            parsed = self._parse_json_response(response)
            
            if parsed and 'analyses' in parsed:
                results = {}
                for analysis in parsed['analyses']:
                    market_idx = analysis.get('market_index', 0) - 1
                    if 0 <= market_idx < len(markets):
                        market_id = markets[market_idx]['id']
                        results[market_id] = LLMAnalysisResult(
                            is_relevant=analysis.get('is_relevant', False),
                            is_bullish_for_yes=analysis.get('is_bullish_for_yes', False),
                            confidence=float(analysis.get('confidence', 0.5)),
                            rationale=analysis.get('rationale', ''),
                            raw_response=response
                        )
                return results
            
        except Exception as e:
            logger.error(f"[LLM SERVICE] Batch analysis error: {e}")
        
        return {}


# Singleton instance
_llm_service: Optional[EmergentLLMService] = None


def get_llm_service(api_key: Optional[str] = None, model: str = 'gpt-4o-mini') -> EmergentLLMService:
    """Get or create the LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = EmergentLLMService(api_key=api_key, model=model)
    return _llm_service
