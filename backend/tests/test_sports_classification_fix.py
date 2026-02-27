"""
Test Sports Classification Fix
==============================

Tests that sports markets are correctly classified even when:
1. The question field doesn't contain sports keywords
2. The market has category='Sports' but question is generic
3. The market has tags but no category field

This test verifies the P0 bug fix for sports markets leaking into HFT lane.
"""

import sys
sys.path.insert(0, '/app/backend')

from services.tag_library_service import TagLibraryService


def test_classify_market_with_category_field():
    """Test that classify_market uses the category field correctly."""
    tag_lib = TagLibraryService()
    
    # Test 1: Market with category='Sports' (capital S) but no sports keywords in question
    market_with_sports_category = {
        'id': 'test-001',
        'category': 'Sports',  # Capital S - as API returns
        'question': 'Will X happen?',  # No sports keywords
        'tags': []
    }
    
    result = tag_lib.classify_market(market_with_sports_category)
    assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
    assert result.source == 'api_category', f"Expected 'api_category', got '{result.source}'"
    assert tag_lib.is_sports_market(market_with_sports_category) == True, "Should be sports market"
    print("✓ Test 1 PASSED: Market with category='Sports' correctly identified")


def test_classify_market_lowercase_category():
    """Test that classify_market handles lowercase category."""
    tag_lib = TagLibraryService()
    
    # Test 2: Market with category='sports' (lowercase)
    market_with_lowercase = {
        'id': 'test-002',
        'category': 'sports',  # lowercase
        'question': 'Generic question here',
        'tags': []
    }
    
    result = tag_lib.classify_market(market_with_lowercase)
    assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
    assert tag_lib.is_sports_market(market_with_lowercase) == True, "Should be sports market"
    print("✓ Test 2 PASSED: Market with category='sports' (lowercase) correctly identified")


def test_classify_market_question_only_fails():
    """Test that passing only question (BUG scenario) fails to detect sports."""
    tag_lib = TagLibraryService()
    
    # Test 3: Only passing question (simulating the BUG)
    # This is what the code WAS doing before the fix
    market_question_only = {
        'question': 'Will X happen?'  # No category field!
    }
    
    result = tag_lib.classify_market(market_question_only)
    # This SHOULD return 'default' because there's no category info
    assert result.category == 'default', f"Expected 'default', got '{result.category}'"
    assert tag_lib.is_sports_market(market_question_only) == False, "Should NOT be sports market"
    print("✓ Test 3 PASSED: Question-only market correctly returns 'default' (not sports)")


def test_classify_market_with_sports_tags():
    """Test that markets with sports tags are correctly classified."""
    tag_lib = TagLibraryService()
    
    # Test 4: Market with NBA tag
    market_with_tags = {
        'id': 'test-004',
        'category': '',  # Empty category
        'question': 'Will team win?',
        'tags': [{'slug': 'nba'}]  # NBA tag
    }
    
    result = tag_lib.classify_market(market_with_tags)
    assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
    assert result.source == 'tag_library', f"Expected 'tag_library', got '{result.source}'"
    print("✓ Test 4 PASSED: Market with sports tags correctly identified")


def test_hft_sports_filter():
    """Test that HFT engine correctly filters sports markets."""
    from trading.hft_engine_v2 import is_sports_market
    
    # Test 5: Sports market should be filtered by HFT
    sports_market = {
        'id': 'test-005',
        'category': 'Sports',
        'question': 'Will X win?',
        'tags': []
    }
    
    # This should return True (market IS sports, should be routed to SPORTS lane)
    assert is_sports_market(sports_market) == True, "HFT should identify this as sports market"
    print("✓ Test 5 PASSED: HFT engine correctly identifies sports market")
    
    # Test 6: Non-sports market should NOT be filtered
    crypto_market = {
        'id': 'test-006',
        'category': 'crypto',
        'question': 'Will Bitcoin reach 100k?',
        'tags': []
    }
    
    assert is_sports_market(crypto_market) == False, "HFT should NOT identify crypto as sports"
    print("✓ Test 6 PASSED: HFT engine correctly identifies non-sports market")


def test_esports_classification():
    """Test that esports is handled correctly."""
    tag_lib = TagLibraryService()
    
    # Test 7: Esports market
    esports_market = {
        'id': 'test-007',
        'category': 'esports',
        'question': 'Will team win tournament?',
        'tags': []
    }
    
    result = tag_lib.classify_market(esports_market)
    # Esports maps to sports category with esports sub-category
    assert result.category == 'sports', f"Expected 'sports' for esports, got '{result.category}'"
    print("✓ Test 7 PASSED: Esports market correctly classified as sports")


def test_asset_class_fallback():
    """Test that asset_class field is used when API category is 'other'."""
    tag_lib = TagLibraryService()
    
    # Test 8: Market with category='other' but asset_class='sports'
    market_with_asset_class = {
        'id': 'test-008',
        'category': 'other',  # Unhelpful API category
        'asset_class': 'sports',  # Set by polymarket_api.py using TagLibraryService
        'question': 'Pelicans vs. Jazz',  # Sports matchup
        'tags': []
    }
    
    result = tag_lib.classify_market(market_with_asset_class)
    assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
    assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
    assert tag_lib.is_sports_market(market_with_asset_class) == True, "Should be sports market"
    print("✓ Test 8 PASSED: Market with asset_class='sports' correctly identified")
    
    # Test 9: Market with category='other' and asset_class='crypto'
    crypto_market = {
        'id': 'test-009',
        'category': 'other',
        'asset_class': 'crypto',
        'question': 'Will X happen?',
        'tags': []
    }
    
    result2 = tag_lib.classify_market(crypto_market)
    assert result2.category == 'crypto', f"Expected 'crypto', got '{result2.category}'"
    assert tag_lib.is_sports_market(crypto_market) == False, "Crypto should NOT be sports"
    print("✓ Test 9 PASSED: Market with asset_class='crypto' correctly identified (not sports)")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("RUNNING SPORTS CLASSIFICATION FIX TESTS")
    print("="*60 + "\n")
    
    test_classify_market_with_category_field()
    test_classify_market_lowercase_category()
    test_classify_market_question_only_fails()
    test_classify_market_with_sports_tags()
    test_hft_sports_filter()
    test_esports_classification()
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60 + "\n")


if __name__ == '__main__':
    run_all_tests()
