"""
LANES MODULE
============

Trading lanes for the 5-lane architecture:
- HFT Lane (handled by hft_engine_v2)
- ALPHA Lane (handled by paper_trader Alpha loop)
- GAMMA Lane (handled by paper_trader)
- SPORTS Lane (handled by paper_trader)
- NEWS Lane (news_sniper_mongodb)
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
