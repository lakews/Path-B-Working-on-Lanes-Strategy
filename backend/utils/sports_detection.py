"""
Sports Market Detection - Single Source of Truth

All lanes use this module to detect sports markets and route them
to the dedicated SPORTS lane instead of HFT/Alpha/News Sniper.

Polymarket doesn't provide category for active markets, so we use
keyword + pattern matching.
"""

import re
from typing import Dict

# Categories from Polymarket API (when available)
SPORTS_CATEGORIES = {'sports', 'esports'}

# Comprehensive sports keywords
SPORTS_KEYWORDS = {
    # Leagues/Organizations
    'nba', 'nfl', 'mlb', 'nhl', 'mls', 'ncaa', 'uefa', 'fifa', 'pga', 'atp', 'wta',
    'ufc', 'boxing', 'f1', 'nascar', 'premier league', 'la liga', 'bundesliga',
    'serie a', 'ligue 1', 'champions league', 'world cup', 'olympics', 'euroleague',
    # Sports terms
    'championship', 'playoff', 'finals', 'super bowl', 'world series',
    'stanley cup', 'mvp', 'scoring title', 'batting average', 'home runs',
    # NBA Teams (all 30)
    'lakers', 'celtics', 'warriors', 'bulls', 'heat', 'knicks', 'nets', 'sixers',
    'suns', 'bucks', 'cavaliers', 'mavericks', 'nuggets', 'clippers', 'timberwolves',
    'grizzlies', 'pelicans', 'thunder', 'blazers', 'kings', 'spurs', 'raptors',
    'wizards', 'hawks', 'hornets', 'pacers', 'pistons', 'magic', 'rockets', 'jazz',
    # NFL Teams
    'cowboys', 'patriots', 'chiefs', 'eagles', '49ers', 'packers', 'steelers',
    'broncos', 'raiders', 'chargers', 'ravens', 'bills', 'dolphins', 'jets',
    'bengals', 'browns', 'titans', 'colts', 'texans', 'jaguars', 'commanders',
    'giants', 'saints', 'falcons', 'panthers', 'buccaneers', 'cardinals', 'rams',
    'seahawks', 'vikings', 'bears', 'lions',
    # MLB Teams
    'yankees', 'dodgers', 'red sox', 'cubs', 'mets', 'astros', 'braves', 'phillies',
    'padres', 'rangers', 'orioles', 'twins', 'mariners', 'guardians', 'royals',
    'tigers', 'white sox', 'athletics', 'angels', 'marlins', 'nationals', 'pirates',
    'reds', 'brewers', 'cardinals', 'rockies', 'diamondbacks', 'rays', 'blue jays',
    # Soccer Teams (Major European)
    'real madrid', 'barcelona', 'manchester united', 'manchester city', 'liverpool',
    'chelsea', 'arsenal', 'tottenham', 'bayern', 'dortmund', 'juventus', 'inter',
    'ac milan', 'roma', 'napoli', 'psg', 'marseille', 'lyon', 'atletico', 'sevilla',
    'valencia', 'villarreal', 'ajax', 'benfica', 'porto', 'sporting',
    # Player names (star athletes)
    'doncic', 'lebron', 'curry', 'giannis', 'jokic', 'embiid', 'tatum', 'durant',
    'mahomes', 'allen', 'burrow', 'jackson', 'hurts', 'kelce',
    'ohtani', 'judge', 'trout', 'betts', 'soto', 'acuna',
    'messi', 'ronaldo', 'mbappe', 'haaland', 'bellingham',
}

# Pattern-based detection (catches "Team A vs. Team B" format)
SPORTS_VS_PATTERN = re.compile(r'\bvs\.?\s', re.IGNORECASE)


def is_sports_market(market_data: Dict) -> bool:
    """
    Detect if a market is sports-related.
    
    Args:
        market_data: Dict with 'question' and optionally 'category' fields
        
    Returns:
        True if sports market, False otherwise
    """
    # Primary: Use category field if available
    category = (market_data.get('category') or '').lower()
    if category in SPORTS_CATEGORIES:
        return True
    
    question = (market_data.get('question') or '').lower()
    
    # Pattern check: "X vs. Y" or "X vs Y" is almost always sports
    if SPORTS_VS_PATTERN.search(question):
        return True
    
    # Keyword matching
    for keyword in SPORTS_KEYWORDS:
        if keyword in question:
            return True
    
    return False


def is_sports_question(question: str) -> bool:
    """
    Simple question-only check for sports detection.
    
    Args:
        question: Market question string
        
    Returns:
        True if sports-related, False otherwise
    """
    q_lower = question.lower()
    
    # Pattern check
    if SPORTS_VS_PATTERN.search(q_lower):
        return True
    
    # Keyword check
    for keyword in SPORTS_KEYWORDS:
        if keyword in q_lower:
            return True
    
    return False
