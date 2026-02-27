"""
Sports Market Detection - DEPRECATED
=====================================

This module has been superseded by the TagLibraryService which provides:
- 99%+ accurate classification via pre-curated tag library
- Sub-category granularity (basketball, soccer, mma, etc.)
- P&L and risk controls by category/sub-category

All functions now delegate to TagLibraryService for consistency.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def is_sports_market(market_data: Dict) -> bool:
    """
    Detect if a market is sports-related.
    
    DEPRECATED: Use TagLibraryService.is_sports_market() directly.
    
    This function now delegates to TagLibraryService for accurate classification.
    
    Args:
        market_data: Dict with 'question' and optionally 'category', 'tags' fields
        
    Returns:
        True if sports market, False otherwise
    """
    try:
        from services.tag_library_service import get_tag_library_service
        tag_library = get_tag_library_service()
        return tag_library.is_sports_market(market_data)
    except Exception as e:
        logger.debug(f"TagLibraryService unavailable, using fallback: {e}")
        # Minimal fallback if service unavailable
        category = (market_data.get('category') or '').lower()
        return category in {'sports', 'esports'}


def is_sports_question(question: str) -> bool:
    """
    Simple question-only check for sports detection.
    
    DEPRECATED: Use TagLibraryService.classify_market() directly.
    
    Args:
        question: Market question string
        
    Returns:
        True if sports-related, False otherwise
    """
    return is_sports_market({'question': question})


def get_market_category(market_data: Dict) -> tuple:
    """
    Get market category and sub-category using TagLibraryService.
    
    Args:
        market_data: Dict with market info
        
    Returns:
        Tuple of (category, sub_category)
    """
    try:
        from services.tag_library_service import get_tag_library_service
        tag_library = get_tag_library_service()
        result = tag_library.classify_market(market_data)
        return (result.category, result.sub_category)
    except Exception:
        return ('default', 'default')
