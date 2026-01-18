"""
Market Classifier for Prediction Markets

Categorizes markets by:
1. Native API tags (primary)
2. Regex keyword fallback (secondary)

Returns category for use in Ambiguity Matrix (Oracle Risk) calculations.
"""
import re
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# Oracle/Resolution Risk Ambiguity Matrix - DEFAULT VALUES
# Higher multiplier = lower risk (more reliable resolution)
# Lower multiplier = higher risk (subjective/ambiguous resolution)
# These can be overridden via configuration
DEFAULT_AMBIGUITY_MATRIX = {
    # Trustless / API-resolvable (1.0x - no discount)
    'sports': 1.0,       # Official APIs, box scores - zero ambiguity
    'crypto': 1.0,       # Chainlink/Pyth oracles, Binance close - binary
    
    # High scrutiny but some dispute potential
    'finance': 0.95,     # Official economic data, some revision risk
    
    # Political - high dispute potential
    'politics_election': 0.90,    # Elections - high scrutiny but delays possible
    'politics_appointment': 0.75, # Appointments/Bills - "confirmation" vs "nomination" semantics
    'politics': 0.85,    # General politics fallback
    
    # Culture/Entertainment - mostly clear
    'entertainment': 0.70,  # Awards, leaks happen but mostly clear
    
    # Social/Tweets - HIGH dispute risk
    'social': 0.50,      # "Did he mean X?" - linguistic ambiguity
    
    # Geopolitical - EXTREME ambiguity
    'conflict': 0.40,    # "Ceasefire" definitions are incredibly vague
    'war': 0.40,         # Fog of war, definitions messy
    
    # Science/Tech - varies
    'science': 0.80,     # Clear milestones usually
    
    # Unknown/Other
    'unknown': 0.60,     # Conservative default
}

# Runtime configurable matrix (will be populated from DB)
AMBIGUITY_MATRIX = DEFAULT_AMBIGUITY_MATRIX.copy()


def update_ambiguity_matrix(custom_matrix: Dict[str, float]) -> None:
    """
    Update the ambiguity matrix with custom values from configuration.
    Only updates keys that exist in the default matrix.
    
    Args:
        custom_matrix: Dict of category -> multiplier overrides
    """
    global AMBIGUITY_MATRIX
    AMBIGUITY_MATRIX = DEFAULT_AMBIGUITY_MATRIX.copy()
    if custom_matrix:
        for key, value in custom_matrix.items():
            if key in DEFAULT_AMBIGUITY_MATRIX:
                # Clamp to valid range 0.1 - 1.0
                AMBIGUITY_MATRIX[key] = max(0.1, min(1.0, float(value)))
                logger.info(f"Updated oracle multiplier: {key} = {AMBIGUITY_MATRIX[key]}")


def get_ambiguity_matrix() -> Dict[str, float]:
    """Get current ambiguity matrix (for API/UI)."""
    return AMBIGUITY_MATRIX.copy()


def get_default_ambiguity_matrix() -> Dict[str, float]:
    """Get default ambiguity matrix (for reset)."""
    return DEFAULT_AMBIGUITY_MATRIX.copy()

# Keyword patterns for regex classification
CATEGORY_PATTERNS = {
    'crypto': [
        r'\b(bitcoin|btc|ethereum|eth|crypto|solana|sol|doge|dogecoin)\b',
        r'\b(blockchain|defi|nft|token|coin)\b',
        r'\$\d+[km]?\s*(bitcoin|btc|eth)',
    ],
    'sports': [
        r'\b(nfl|nba|mlb|nhl|ncaa|mls|epl|ufc|wwe)\b',
        r'\b(game|match|championship|playoff|super bowl|world series|finals)\b',
        r'\b(win|defeat|beat|score|points|goals)\b.*\b(team|game|match)\b',
    ],
    'politics_election': [
        r'\b(election|electoral|vote|ballot|primary|caucus)\b',
        r'\b(president|governor|senator|congressman|mayor)\s*(elect|win)',
        r'\b(democrat|republican|gop)\b.*\b(win|lose|elect)\b',
    ],
    'politics_appointment': [
        r'\b(confirm|nominate|appoint|cabinet|secretary|justice)\b',
        r'\b(bill|legislation|law|pass|veto)\b',
    ],
    'politics': [
        r'\b(trump|biden|harris|congress|senate|house)\b',
        r'\b(political|policy|government|administration)\b',
    ],
    'conflict': [
        r'\b(war|invasion|ceasefire|truce|military|attack)\b',
        r'\b(ukraine|russia|israel|gaza|hamas|iran)\b',
        r'\b(troops|soldiers|combat|strike|bomb)\b',
    ],
    'social': [
        r'\b(tweet|post|say|said|word|statement)\b',
        r'\b(elon|musk|twitter|x\.com)\b.*\b(tweet|post)\b',
        r'\bwill\s+\w+\s+say\b',
    ],
    'finance': [
        r'\b(fed|federal reserve|interest rate|inflation|gdp|unemployment)\b',
        r'\b(s&p|dow|nasdaq|stock|market|recession|tariff)\b',
        r'\b(price|close|above|below)\s*\$?\d+',
    ],
    'entertainment': [
        r'\b(oscar|grammy|emmy|tony|golden globe|academy)\b',
        r'\b(movie|film|album|box office|celebrity)\b',
        r'\b(netflix|hbo|disney|streaming)\b',
    ],
    'science': [
        r'\b(spacex|nasa|rocket|launch|mars|moon)\b',
        r'\b(ai|artificial intelligence|openai|gpt|llm)\b',
        r'\b(climate|research|discovery|breakthrough)\b',
    ],
}


def classify_market(
    question: str,
    tags: Optional[List[str]] = None,
    description: str = ""
) -> str:
    """
    Classify a market into a category for oracle risk assessment.
    
    Priority:
    1. Native tags from API (most reliable)
    2. Regex patterns on question text (fallback)
    3. Default to 'unknown'
    
    Args:
        question: Market question text
        tags: Native tags from Polymarket API (e.g., ["Politics", "US Election"])
        description: Optional market description for additional context
        
    Returns:
        Category string matching AMBIGUITY_MATRIX keys
    """
    text = f"{question} {description}".lower()
    
    # Layer 1: Native Tags (most reliable)
    if tags:
        tags_lower = [t.lower() for t in tags]
        
        # Direct tag mappings
        if any('crypto' in t or 'bitcoin' in t for t in tags_lower):
            return 'crypto'
        if any('sport' in t for t in tags_lower):
            return 'sports'
        if any('election' in t for t in tags_lower):
            return 'politics_election'
        if any('politic' in t for t in tags_lower):
            return 'politics'
        if any('conflict' in t or 'war' in t for t in tags_lower):
            return 'conflict'
        if any('entertainment' in t or 'culture' in t for t in tags_lower):
            return 'entertainment'
        if any('science' in t or 'tech' in t for t in tags_lower):
            return 'science'
        if any('finance' in t or 'economic' in t for t in tags_lower):
            return 'finance'
    
    # Layer 2: Regex Pattern Matching on Question
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category
    
    # Default: Unknown (conservative 0.6x multiplier)
    return 'unknown'


def get_oracle_risk_multiplier(
    category: str,
    market_age_hours: Optional[float] = None
) -> float:
    """
    Get the oracle/resolution risk multiplier for position sizing.
    
    Applies:
    1. Base category multiplier from AMBIGUITY_MATRIX
    2. New market penalty (0.8x) if market < 48 hours old
    
    Args:
        category: Market category from classify_market()
        market_age_hours: Hours since market creation (optional)
        
    Returns:
        Risk multiplier (0.0 to 1.0)
    """
    base_mult = AMBIGUITY_MATRIX.get(category, AMBIGUITY_MATRIX['unknown'])
    
    # New Market Penalty: Markets < 48 hours old get 0.8x
    # Early markets often have rule clarifications or description updates
    if market_age_hours is not None and market_age_hours < 48:
        base_mult *= 0.8
        logger.debug(f"Applied new market penalty: {category} -> {base_mult:.3f}")
    
    return base_mult


def get_detailed_classification(
    question: str,
    tags: Optional[List[str]] = None,
    description: str = "",
    market_age_hours: Optional[float] = None
) -> Dict:
    """
    Get detailed classification with all risk factors.
    
    Returns:
        Dict with category, base_mult, new_market_penalty, final_mult
    """
    category = classify_market(question, tags, description)
    base_mult = AMBIGUITY_MATRIX.get(category, AMBIGUITY_MATRIX['unknown'])
    
    new_market_penalty = 1.0
    if market_age_hours is not None and market_age_hours < 48:
        new_market_penalty = 0.8
    
    final_mult = base_mult * new_market_penalty
    
    return {
        'category': category,
        'base_multiplier': base_mult,
        'new_market_penalty': new_market_penalty,
        'final_multiplier': final_mult,
        'market_age_hours': market_age_hours,
        'reasoning': _get_category_reasoning(category),
    }


def _get_category_reasoning(category: str) -> str:
    """Get human-readable reasoning for category risk level."""
    reasons = {
        'sports': 'Official box scores/APIs. Zero ambiguity.',
        'crypto': 'Resolved by oracles (Chainlink/Pyth) or exchange close. Binary.',
        'finance': 'Official economic data with minor revision risk.',
        'politics_election': 'High scrutiny but delays/lawsuits possible.',
        'politics_appointment': 'Confirmation vs Nomination semantics cause disputes.',
        'politics': 'Political events with moderate dispute potential.',
        'entertainment': 'Mostly clear, but leaks and subjective judging.',
        'social': '"Did he mean X?" High linguistic ambiguity.',
        'conflict': 'Ceasefire/victory definitions are incredibly vague.',
        'war': 'Fog of war, messy definitions.',
        'science': 'Clear milestones but timing uncertainty.',
        'unknown': 'Unknown category - conservative default.',
    }
    return reasons.get(category, 'Unknown category.')
