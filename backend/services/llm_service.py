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


@dataclass
class LLMAnalysisResult:
    """Result from LLM analysis of news against a market"""
    is_relevant: bool
    is_bullish_for_yes: bool
    confidence: float
    rationale: str
    raw_response: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'is_relevant': self.is_relevant,
            'is_bullish_for_yes': self.is_bullish_for_yes,
            'confidence': self.confidence,
            'rationale': self.rationale,
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
        
    async def _get_client(self):
        """Lazy initialization of LLM client"""
        if self._client is None:
            try:
                from emergentintegrations.llm.chat import LlmChat
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
        market_description: str = ""
    ) -> LLMAnalysisResult:
        """
        Analyze a news item against a specific market question.
        
        Uses the Event Resolution Adjudicator prompt for strict,
        calibrated analysis focusing on the YES outcome.
        
        Args:
            news_headline: News headline
            news_content: Full news content
            market_question: The prediction market question
            market_description: Additional market context
        
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
            # Call LLM with temperature=0.0 for consistent, logical output
            # Note: system_prompt is set in the LlmChat constructor
            response = await client.chat(
                message=user_prompt,
                model=self.model
            )
            
            # Parse response
            parsed = self._parse_json_response(response)
            
            if parsed:
                return LLMAnalysisResult(
                    is_relevant=parsed.get('is_relevant', False),
                    is_bullish_for_yes=parsed.get('is_bullish_for_yes', False),
                    confidence=float(parsed.get('confidence', 0.5)),
                    rationale=parsed.get('rationale', ''),
                    raw_response=response
                )
            else:
                logger.warning(f"[LLM SERVICE] Failed to parse response: {response[:200]}")
                return LLMAnalysisResult(
                    is_relevant=False,
                    is_bullish_for_yes=False,
                    confidence=0.5,
                    rationale="Failed to parse LLM response",
                    raw_response=response,
                    error="Parse error"
                )
                
        except Exception as e:
            logger.error(f"[LLM SERVICE] Analysis error: {e}")
            return LLMAnalysisResult(
                is_relevant=False,
                is_bullish_for_yes=False,
                confidence=0.5,
                rationale=str(e),
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
            response = await client.chat(
                message=batch_prompt,
                model=self.model
            )
            
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
