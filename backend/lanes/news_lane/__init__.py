"""
NEWS LANE MODULE
================

NEWS Lane (Lane 5) implementation with MongoDB integration.

Features:
- MongoDB signal reading (PATH A from DualPathNewsInjector)
- 5-factor ConvictionEnhancer
- Kelly tiering based on conviction
- Whale alignment checking
- Source credibility scoring
"""

from lanes.news_lane.news_sniper_mongodb import (
    NewsSniper,
    ConvictionEnhancer,
    NewsImpactLevel,
    MarketRegime,
    init_news_sniper,
    get_news_sniper
)

__all__ = [
    'NewsSniper',
    'ConvictionEnhancer',
    'NewsImpactLevel',
    'MarketRegime',
    'init_news_sniper',
    'get_news_sniper'
]
