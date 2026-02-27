"""
Test Sports Classification Fix - Pytest Version
================================================

Tests that sports markets are correctly classified even when:
1. The question field doesn't contain sports keywords
2. The market has category='Sports' but question is generic
3. The market has tags but no category field

This test verifies the P0 bug fix for sports markets leaking into HFT lane.

Bug Root Cause:
- polymarket_scanner.py lines 300 and 492 were calling 
  tag_library.classify_market({'question': m.get('question', '')}) 
- This passed ONLY the question field, causing markets with category='Sports' 
  in the API response but generic questions to be misclassified as 'default'
- The fix passes the FULL market object so classify_market can use all 
  available data (tags, category field, question)
"""

import sys
import pytest

sys.path.insert(0, '/app/backend')

from services.tag_library_service import TagLibraryService


class TestSportsClassificationWithCategoryField:
    """Tests for sports classification using the category field from API"""
    
    def test_market_with_sports_category_capital_s(self):
        """Test that classify_market uses the category field correctly (capital S)."""
        tag_lib = TagLibraryService()
        
        # Market with category='Sports' (capital S) but no sports keywords in question
        market = {
            'id': 'test-001',
            'category': 'Sports',  # Capital S - as API returns
            'question': 'Will X happen?',  # No sports keywords
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert result.source == 'api_category', f"Expected 'api_category', got '{result.source}'"
        assert tag_lib.is_sports_market(market) == True, "Should be sports market"
    
    def test_market_with_sports_category_lowercase(self):
        """Test that classify_market handles lowercase category."""
        tag_lib = TagLibraryService()
        
        # Market with category='sports' (lowercase)
        market = {
            'id': 'test-002',
            'category': 'sports',  # lowercase
            'question': 'Generic question here',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert tag_lib.is_sports_market(market) == True, "Should be sports market"


class TestSportsClassificationBugScenario:
    """Tests that reproduce the original bug scenario"""
    
    def test_question_only_fails_to_detect_sports(self):
        """Test that passing only question (BUG scenario) fails to detect sports."""
        tag_lib = TagLibraryService()
        
        # Only passing question (simulating the BUG)
        # This is what the code WAS doing before the fix
        market_question_only = {
            'question': 'Will X happen?'  # No category field!
        }
        
        result = tag_lib.classify_market(market_question_only)
        # This SHOULD return 'default' because there's no category info
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
        assert tag_lib.is_sports_market(market_question_only) == False, "Should NOT be sports market"
    
    def test_full_market_object_detects_sports(self):
        """Test that passing full market object correctly detects sports."""
        tag_lib = TagLibraryService()
        
        # Full market object with category='Sports' but generic question
        full_market = {
            'id': 'test-full-001',
            'category': 'Sports',
            'question': 'Will X happen?',  # Generic question
            'tags': [],
            'volume_24h': 10000,
            'liquidity': 5000
        }
        
        result = tag_lib.classify_market(full_market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert tag_lib.is_sports_market(full_market) == True, "Should be sports market"


class TestSportsClassificationWithTags:
    """Tests for sports classification using tags"""
    
    def test_market_with_nba_tag(self):
        """Test that markets with NBA tag are correctly classified."""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-nba-001',
            'category': '',  # Empty category
            'question': 'Will team win?',
            'tags': [{'slug': 'nba'}]  # NBA tag
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert result.source == 'tag_library', f"Expected 'tag_library', got '{result.source}'"
    
    def test_market_with_nfl_tag(self):
        """Test that markets with NFL tag are correctly classified."""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-nfl-001',
            'category': '',
            'question': 'Will team win the game?',
            'tags': [{'slug': 'nfl'}]
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert result.sub_category == 'american-football', f"Expected 'american-football', got '{result.sub_category}'"
    
    def test_market_with_premier_league_tag(self):
        """Test that markets with Premier League tag are correctly classified."""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-pl-001',
            'category': '',
            'question': 'Will team win?',
            'tags': [{'slug': 'premier-league'}]
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"


class TestHFTEngineSportsFilter:
    """Tests for HFT engine sports market filtering"""
    
    def test_hft_identifies_sports_market(self):
        """Test that HFT engine correctly identifies sports markets."""
        from trading.hft_engine_v2 import is_sports_market
        
        sports_market = {
            'id': 'test-hft-001',
            'category': 'Sports',
            'question': 'Will X win?',
            'tags': []
        }
        
        # This should return True (market IS sports, should be routed to SPORTS lane)
        assert is_sports_market(sports_market) == True, "HFT should identify this as sports market"
    
    def test_hft_identifies_non_sports_market(self):
        """Test that HFT engine correctly identifies non-sports markets."""
        from trading.hft_engine_v2 import is_sports_market
        
        crypto_market = {
            'id': 'test-hft-002',
            'category': 'crypto',
            'question': 'Will Bitcoin reach 100k?',
            'tags': []
        }
        
        assert is_sports_market(crypto_market) == False, "HFT should NOT identify crypto as sports"
    
    def test_hft_identifies_politics_market(self):
        """Test that HFT engine correctly identifies politics markets as non-sports."""
        from trading.hft_engine_v2 import is_sports_market
        
        politics_market = {
            'id': 'test-hft-003',
            'category': 'politics',
            'question': 'Will Trump win?',
            'tags': []
        }
        
        assert is_sports_market(politics_market) == False, "HFT should NOT identify politics as sports"


class TestEsportsClassification:
    """Tests for esports classification"""
    
    def test_esports_classified_as_sports(self):
        """Test that esports is handled correctly."""
        tag_lib = TagLibraryService()
        
        esports_market = {
            'id': 'test-esports-001',
            'category': 'esports',
            'question': 'Will team win tournament?',
            'tags': []
        }
        
        result = tag_lib.classify_market(esports_market)
        # Esports maps to sports category with esports sub-category
        assert result.category == 'sports', f"Expected 'sports' for esports, got '{result.category}'"
    
    def test_esports_is_sports_market(self):
        """Test that esports markets are identified as sports markets."""
        tag_lib = TagLibraryService()
        
        esports_market = {
            'id': 'test-esports-002',
            'category': 'esports',
            'question': 'Will team win?',
            'tags': []
        }
        
        assert tag_lib.is_sports_market(esports_market) == True, "Esports should be identified as sports"


class TestNonSportsClassification:
    """Tests to ensure non-sports markets are NOT classified as sports"""
    
    def test_crypto_market_not_sports(self):
        """Test that crypto markets are not classified as sports."""
        tag_lib = TagLibraryService()
        
        crypto_market = {
            'id': 'test-crypto-001',
            'category': 'crypto',
            'question': 'Will Bitcoin reach 100k?',
            'tags': [{'slug': 'bitcoin'}]
        }
        
        result = tag_lib.classify_market(crypto_market)
        assert result.category == 'crypto', f"Expected 'crypto', got '{result.category}'"
        assert tag_lib.is_sports_market(crypto_market) == False, "Crypto should NOT be sports"
    
    def test_politics_market_not_sports(self):
        """Test that politics markets are not classified as sports."""
        tag_lib = TagLibraryService()
        
        politics_market = {
            'id': 'test-politics-001',
            'category': 'politics',
            'question': 'Will Trump win the election?',
            'tags': [{'slug': 'donald-trump'}]
        }
        
        result = tag_lib.classify_market(politics_market)
        assert result.category == 'politics', f"Expected 'politics', got '{result.category}'"
        assert tag_lib.is_sports_market(politics_market) == False, "Politics should NOT be sports"
    
    def test_economics_market_not_sports(self):
        """Test that economics markets are not classified as sports."""
        tag_lib = TagLibraryService()
        
        economics_market = {
            'id': 'test-economics-001',
            'category': 'economics',
            'question': 'Will Fed raise rates?',
            'tags': []
        }
        
        result = tag_lib.classify_market(economics_market)
        assert result.category == 'economics', f"Expected 'economics', got '{result.category}'"
        assert tag_lib.is_sports_market(economics_market) == False, "Economics should NOT be sports"


class TestEdgeCases:
    """Edge case tests for sports classification"""
    
    def test_empty_market_object(self):
        """Test classification of empty market object."""
        tag_lib = TagLibraryService()
        
        empty_market = {}
        
        result = tag_lib.classify_market(empty_market)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
        assert tag_lib.is_sports_market(empty_market) == False, "Empty market should NOT be sports"
    
    def test_none_category(self):
        """Test classification when category is None."""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-none-001',
            'category': None,
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
    
    def test_mixed_case_sports_category(self):
        """Test classification with mixed case 'SPORTS' category."""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-mixed-001',
            'category': 'SPORTS',  # All caps
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert tag_lib.is_sports_market(market) == True, "SPORTS (caps) should be sports market"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
