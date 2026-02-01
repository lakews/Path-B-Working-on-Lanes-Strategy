"""
EVENT BAYESIAN UPDATER
======================

QUARANTINE: This module is ONLY for the NEWS/EMERGENT lane.
DO NOT import into HFT, Alpha, Sports, or Gamma lanes.

Purpose: Update market beliefs based on breaking news events.
Uses a different prior structure than Alpha (event-specific).

Key Concept: Bayes Factor
- BF > 3.0 = Strong evidence (inject to cache)
- BF > 10.0 = Very strong evidence (high priority)
- BF < 3.0 = Insufficient evidence (skip injection)

Math: Classic Bayesian inference with news-specific likelihood models.
"""

import logging
import math
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class NewsImpact(Enum):
    """Classification of news impact on market"""
    RESOLUTION = "resolution"      # News directly resolves the market
    STRONG_SIGNAL = "strong"       # Strong directional signal
    MODERATE_SIGNAL = "moderate"   # Moderate signal
    WEAK_SIGNAL = "weak"           # Weak/noisy signal
    IRRELEVANT = "irrelevant"      # No impact on this market


@dataclass
class EventPosterior:
    """Result of Event Bayesian update"""
    prior: float                  # P(YES) before news
    posterior: float              # P(YES) after news
    bayes_factor: float           # Strength of evidence
    news_impact: NewsImpact       # Classification
    direction: str                # 'YES', 'NO', or 'NEUTRAL'
    confidence: float             # How confident in this update
    market_id: str                # Which market this applies to
    news_headline: str            # The triggering news
    source: str                   # News source
    timestamp: datetime           # When processed
    ttl_seconds: int              # How long this signal is valid
    
    def to_dict(self) -> Dict:
        return {
            'prior': round(self.prior, 4),
            'posterior': round(self.posterior, 4),
            'bayes_factor': round(self.bayes_factor, 4),
            'news_impact': self.news_impact.value,
            'direction': self.direction,
            'confidence': round(self.confidence, 4),
            'market_id': self.market_id,
            'news_headline': self.news_headline[:200],
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'ttl_seconds': self.ttl_seconds
        }
    
    def is_actionable(self, min_bayes_factor: float = 3.0) -> bool:
        """Check if this signal is strong enough to act on"""
        return self.bayes_factor >= min_bayes_factor


class EventBayesianUpdater:
    """
    Bayesian updater for news events.
    
    Unlike Alpha (which fuses multiple signals continuously),
    this processes discrete news events and calculates the
    Bayes Factor to determine if the news is actionable.
    """
    
    # Default configuration
    DEFAULT_CONFIG = {
        'min_bayes_factor': 3.0,          # Minimum BF to inject signal
        'strong_bayes_factor': 10.0,      # BF for high-priority injection
        'resolution_likelihood': 0.95,     # P(news | YES true) for resolution news
        'strong_signal_likelihood': 0.80,  # P(news | YES true) for strong signals
        'moderate_signal_likelihood': 0.65,
        'weak_signal_likelihood': 0.55,
        'base_ttl_seconds': 300,           # 5 min default TTL
        'resolution_ttl_seconds': 3600,    # 1 hour for resolution news
    }
    
    # News source reliability weights
    SOURCE_RELIABILITY = {
        'apnews.com': 0.95,
        'reuters.com': 0.95,
        'bloomberg.com': 0.90,
        'bbc.com': 0.90,
        'coindesk.com': 0.85,
        'theblock.co': 0.85,
        'fivethirtyeight.com': 0.90,
        'polymarket.com': 0.80,  # User comments, less reliable
        'twitter.com': 0.60,
        'x.com': 0.60,
        'unknown': 0.50
    }
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
    
    def _get_source_reliability(self, source: str) -> float:
        """Get reliability weight for a news source"""
        source_lower = source.lower()
        for domain, reliability in self.SOURCE_RELIABILITY.items():
            if domain in source_lower:
                return reliability
        return self.SOURCE_RELIABILITY['unknown']
    
    def _classify_news_impact(
        self,
        news_text: str,
        market_question: str,
        llm_classification: Optional[Dict] = None
    ) -> NewsImpact:
        """
        Classify the impact of news on a specific market.
        
        Args:
            news_text: The news headline/content
            market_question: The market question
            llm_classification: Optional pre-computed LLM classification
        
        Returns:
            NewsImpact enum
        """
        if llm_classification:
            impact_str = llm_classification.get('impact', 'weak').lower()
            if impact_str == 'resolution':
                return NewsImpact.RESOLUTION
            elif impact_str in ['strong', 'high']:
                return NewsImpact.STRONG_SIGNAL
            elif impact_str in ['moderate', 'medium']:
                return NewsImpact.MODERATE_SIGNAL
            elif impact_str in ['weak', 'low']:
                return NewsImpact.WEAK_SIGNAL
            else:
                return NewsImpact.IRRELEVANT
        
        # Fallback: keyword-based classification
        resolution_keywords = ['wins', 'elected', 'confirmed', 'announced', 'official', 'final']
        strong_keywords = ['likely', 'expected', 'breaking', 'sources say', 'reported']
        
        news_lower = news_text.lower()
        
        if any(kw in news_lower for kw in resolution_keywords):
            return NewsImpact.STRONG_SIGNAL
        elif any(kw in news_lower for kw in strong_keywords):
            return NewsImpact.MODERATE_SIGNAL
        else:
            return NewsImpact.WEAK_SIGNAL
    
    def _get_likelihood_for_impact(self, impact: NewsImpact) -> float:
        """Get likelihood value based on news impact classification"""
        if impact == NewsImpact.RESOLUTION:
            return self.config['resolution_likelihood']
        elif impact == NewsImpact.STRONG_SIGNAL:
            return self.config['strong_signal_likelihood']
        elif impact == NewsImpact.MODERATE_SIGNAL:
            return self.config['moderate_signal_likelihood']
        elif impact == NewsImpact.WEAK_SIGNAL:
            return self.config['weak_signal_likelihood']
        else:
            return 0.5  # Neutral
    
    def _calculate_bayes_factor(
        self,
        likelihood_yes: float,
        likelihood_no: float
    ) -> float:
        """
        Calculate Bayes Factor.
        
        BF = P(news | YES true) / P(news | NO true)
        
        BF > 1: Evidence supports YES
        BF < 1: Evidence supports NO
        BF = 1: No evidence either way
        """
        if likelihood_no < 0.001:
            return 100.0  # Cap at 100
        return likelihood_yes / likelihood_no
    
    def update(
        self,
        market_id: str,
        market_question: str,
        current_price: float,
        news_headline: str,
        news_content: str = "",
        news_source: str = "unknown",
        llm_analysis: Optional[Dict] = None
    ) -> EventPosterior:
        """
        Update belief about a market based on news.
        
        Args:
            market_id: Polymarket market ID
            market_question: The market question
            current_price: Current YES price (our prior)
            news_headline: News headline
            news_content: Full news content (optional)
            news_source: URL or name of source
            llm_analysis: Pre-computed LLM analysis with keys:
                - 'direction': 'YES', 'NO', or 'NEUTRAL'
                - 'impact': 'resolution', 'strong', 'moderate', 'weak', 'irrelevant'
                - 'confidence': 0-1
        
        Returns:
            EventPosterior with update result
        """
        # Prior is current market price
        prior = current_price
        
        # Get source reliability
        source_reliability = self._get_source_reliability(news_source)
        
        # Classify news impact
        impact = self._classify_news_impact(
            news_headline + " " + news_content,
            market_question,
            llm_analysis
        )
        
        # Determine direction from LLM analysis or default to neutral
        direction = 'NEUTRAL'
        if llm_analysis:
            direction = llm_analysis.get('direction', 'NEUTRAL').upper()
        
        # Get base likelihood for this impact level
        base_likelihood = self._get_likelihood_for_impact(impact)
        
        # Adjust likelihood by source reliability
        adjusted_likelihood = 0.5 + (base_likelihood - 0.5) * source_reliability
        
        # Calculate likelihoods for YES and NO
        if direction == 'YES':
            likelihood_yes = adjusted_likelihood
            likelihood_no = 1 - adjusted_likelihood
        elif direction == 'NO':
            likelihood_yes = 1 - adjusted_likelihood
            likelihood_no = adjusted_likelihood
        else:
            # Neutral - no update
            likelihood_yes = 0.5
            likelihood_no = 0.5
        
        # Calculate Bayes Factor
        bayes_factor = self._calculate_bayes_factor(likelihood_yes, likelihood_no)
        
        # Calculate posterior using Bayes' theorem
        # P(YES | news) = P(news | YES) * P(YES) / P(news)
        # where P(news) = P(news | YES) * P(YES) + P(news | NO) * P(NO)
        p_news = likelihood_yes * prior + likelihood_no * (1 - prior)
        
        if p_news > 0.001:
            posterior = (likelihood_yes * prior) / p_news
        else:
            posterior = prior  # No update if P(news) is too low
        
        # Clamp posterior
        posterior = max(0.01, min(0.99, posterior))
        
        # Calculate confidence
        confidence = abs(posterior - prior) * source_reliability
        if llm_analysis and 'confidence' in llm_analysis:
            confidence = min(confidence, llm_analysis['confidence'])
        
        # Determine TTL based on impact
        if impact == NewsImpact.RESOLUTION:
            ttl = self.config['resolution_ttl_seconds']
        else:
            ttl = self.config['base_ttl_seconds']
        
        return EventPosterior(
            prior=prior,
            posterior=posterior,
            bayes_factor=bayes_factor if direction == 'YES' else 1/bayes_factor if bayes_factor > 0 else 0,
            news_impact=impact,
            direction=direction,
            confidence=confidence,
            market_id=market_id,
            news_headline=news_headline,
            source=news_source,
            timestamp=datetime.now(timezone.utc),
            ttl_seconds=ttl
        )
    
    def batch_update(
        self,
        markets: List[Dict],
        news_item: Dict,
        llm_analyses: Dict[str, Dict]
    ) -> List[EventPosterior]:
        """
        Update multiple markets based on a single news item.
        
        Args:
            markets: List of market dicts with 'id', 'question', 'yes_price'
            news_item: Dict with 'headline', 'content', 'source'
            llm_analyses: Dict mapping market_id to LLM analysis
        
        Returns:
            List of EventPosterior for markets with actionable signals
        """
        results = []
        
        for market in markets:
            market_id = market.get('id', '')
            llm_analysis = llm_analyses.get(market_id)
            
            # Skip if no LLM analysis for this market
            if not llm_analysis:
                continue
            
            posterior = self.update(
                market_id=market_id,
                market_question=market.get('question', ''),
                current_price=market.get('yes_price', 0.5),
                news_headline=news_item.get('headline', ''),
                news_content=news_item.get('content', ''),
                news_source=news_item.get('source', 'unknown'),
                llm_analysis=llm_analysis
            )
            
            # Only include actionable signals
            if posterior.is_actionable(self.config['min_bayes_factor']):
                results.append(posterior)
        
        return results


# Singleton instance
_event_bayes: Optional[EventBayesianUpdater] = None


def get_event_bayes(config: Optional[Dict] = None) -> EventBayesianUpdater:
    """Get or create the Event Bayesian updater instance"""
    global _event_bayes
    if _event_bayes is None or config is not None:
        _event_bayes = EventBayesianUpdater(config)
    return _event_bayes
