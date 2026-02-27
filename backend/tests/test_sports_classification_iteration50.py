"""
Test Sports Classification Fix - Iteration 50
==============================================

Tests the LAYER 3.5 fix in TagLibraryService that checks asset_class field
when API category is 'other'. This addresses the bug where sports markets
like 'Pelicans vs. Jazz' were being traded by hft_liquidity_provision
instead of being routed to SPORTS lane.

Key test case: market with category='other', asset_class='sports', 
question='Pelicans vs. Jazz' should be classified as sports market.
"""

import sys
import pytest
sys.path.insert(0, '/app/backend')

from services.tag_library_service import TagLibraryService, get_tag_library_service


class TestLayer35AssetClassFallback:
    """Tests for LAYER 3.5 - asset_class fallback when category is 'other'"""
    
    def test_pelicans_vs_jazz_with_asset_class_sports(self):
        """
        CRITICAL TEST: The exact scenario from the bug report.
        Market with category='other' but asset_class='sports' should return sports.
        """
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'pelicans-jazz-001',
            'category': 'other',  # Polymarket API returns 'other' for many sports
            'asset_class': 'sports',  # Set by polymarket_api.py using TagLibraryService
            'question': 'Pelicans vs. Jazz',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
        assert tag_lib.is_sports_market(market) == True, "Should be sports market"
    
    def test_category_other_asset_class_sports_generic_question(self):
        """Test with generic question but asset_class='sports'"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-generic-001',
            'category': 'other',
            'asset_class': 'sports',
            'question': 'Will X happen?',  # No sports keywords
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
    
    def test_category_other_asset_class_crypto(self):
        """Test that asset_class='crypto' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-crypto-001',
            'category': 'other',
            'asset_class': 'crypto',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'crypto', f"Expected 'crypto', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
        assert tag_lib.is_sports_market(market) == False, "Crypto should NOT be sports"
    
    def test_category_other_asset_class_politics(self):
        """Test that asset_class='politics' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-politics-001',
            'category': 'other',
            'asset_class': 'politics',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'politics', f"Expected 'politics', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
        assert tag_lib.is_sports_market(market) == False, "Politics should NOT be sports"
    
    def test_category_other_no_asset_class_falls_to_keyword(self):
        """Test that without asset_class, it falls back to keyword matching"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-no-asset-001',
            'category': 'other',
            # No asset_class field
            'question': 'Will Lakers win?',  # Has sports keyword
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        # Should fall through to keyword matching and find 'Lakers'
        assert result.category == 'sports', f"Expected 'sports' from keyword, got '{result.category}'"
        assert result.source == 'keyword', f"Expected 'keyword', got '{result.source}'"
    
    def test_category_other_asset_class_empty_string(self):
        """Test that empty asset_class doesn't trigger LAYER 3.5"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-empty-asset-001',
            'category': 'other',
            'asset_class': '',  # Empty string
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        # Should fall through to keyword matching (default)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
    
    def test_category_other_asset_class_other(self):
        """Test that asset_class='other' doesn't trigger LAYER 3.5"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'test-other-asset-001',
            'category': 'other',
            'asset_class': 'other',  # Also 'other'
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        # Should fall through to keyword matching (default)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"


class TestHFTEngineSportsFilterWithAssetClass:
    """Tests that HFT engine correctly filters sports markets using asset_class"""
    
    def test_hft_filters_sports_market_with_asset_class(self):
        """HFT engine should filter sports market with asset_class='sports'"""
        from trading.hft_engine_v2 import is_sports_market
        
        market = {
            'id': 'hft-test-001',
            'category': 'other',
            'asset_class': 'sports',
            'question': 'Pelicans vs. Jazz',
            'tags': []
        }
        
        assert is_sports_market(market) == True, "HFT should identify this as sports market"
    
    def test_hft_does_not_filter_crypto_with_asset_class(self):
        """HFT engine should NOT filter crypto market"""
        from trading.hft_engine_v2 import is_sports_market
        
        market = {
            'id': 'hft-test-002',
            'category': 'other',
            'asset_class': 'crypto',
            'question': 'Will BTC reach 100k?',
            'tags': []
        }
        
        assert is_sports_market(market) == False, "HFT should NOT identify crypto as sports"
    
    def test_hft_filters_sports_with_category_sports(self):
        """HFT engine should filter market with category='Sports'"""
        from trading.hft_engine_v2 import is_sports_market
        
        market = {
            'id': 'hft-test-003',
            'category': 'Sports',  # Capital S
            'question': 'Will team win?',
            'tags': []
        }
        
        assert is_sports_market(market) == True, "HFT should identify this as sports market"


class TestMarketDataServiceCategoryClassification:
    """Tests that MarketDataService correctly classifies categories"""
    
    def test_market_data_service_get_market_category(self):
        """Test _get_market_category method uses TagLibraryService"""
        from unittest.mock import patch, MagicMock
        
        # Mock get_db to avoid database connection
        with patch('services.market_data_service.get_db') as mock_get_db:
            mock_get_db.return_value = MagicMock()
            
            from services.market_data_service import MarketDataService
            service = MarketDataService()
            
            # Test with asset_class='sports'
            market = {
                'id': 'mds-test-001',
                'category': 'other',
                'asset_class': 'sports',
                'question': 'Pelicans vs. Jazz',
                'tags': []
            }
            
            category = service._get_market_category(market)
            assert category == 'sports', f"Expected 'sports', got '{category}'"
    
    def test_market_data_service_normalize_market_data(self):
        """Test normalize_market_data sets correct category"""
        from unittest.mock import patch, MagicMock
        
        # Mock get_db to avoid database connection
        with patch('services.market_data_service.get_db') as mock_get_db:
            mock_get_db.return_value = MagicMock()
            
            from services.market_data_service import MarketDataService
            service = MarketDataService()
            
            raw_data = {
                'condition_id': 'test-condition-001',
                'category': 'other',
                'asset_class': 'sports',
                'question': 'Pelicans vs. Jazz',
                'yes_price': 0.5,
                'no_price': 0.5,
                'volume': 1000,
                'liquidity': 500,
                'tags': []
            }
            
            normalized = service.normalize_market_data(raw_data)
            assert normalized['category'] == 'sports', f"Expected 'sports', got '{normalized['category']}'"


class TestRealTimeMarketServiceCategoryClassification:
    """Tests that RealTimeMarketService correctly classifies categories"""
    
    def test_realtime_service_category_classification(self):
        """Test that get_markets returns properly classified markets"""
        from services.realtime_market_service import RealTimeMarketService
        
        service = RealTimeMarketService()
        
        # Manually add a market to cache for testing
        market = {
            'id': 'rtm-test-001',
            'category': 'other',  # Will be reclassified
            'asset_class': 'sports',
            'question': 'Pelicans vs. Jazz',
            'volume_24h': 1000,
            'tags': []
        }
        
        service._market_cache['rtm-test-001'] = market
        
        # Get markets should reclassify
        markets = service.get_markets(limit=10)
        
        # Find our test market
        test_market = next((m for m in markets if m['id'] == 'rtm-test-001'), None)
        assert test_market is not None, "Test market should be in results"
        assert test_market['category'] == 'sports', f"Expected 'sports', got '{test_market['category']}'"


class TestEdgeCasesLayer35:
    """Edge cases for LAYER 3.5 asset_class handling"""
    
    def test_asset_class_finance_not_used(self):
        """asset_class='finance' should not trigger LAYER 3.5 (excluded)"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-001',
            'category': 'other',
            'asset_class': 'finance',  # Excluded in LAYER 3.5
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        # Should fall through to keyword matching (default)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
    
    def test_asset_class_default_not_used(self):
        """asset_class='default' should not trigger LAYER 3.5 (excluded)"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-002',
            'category': 'other',
            'asset_class': 'default',  # Excluded in LAYER 3.5
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'default', f"Expected 'default', got '{result.category}'"
    
    def test_asset_class_geopolitics(self):
        """Test asset_class='geopolitics' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-003',
            'category': 'other',
            'asset_class': 'geopolitics',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'geopolitics', f"Expected 'geopolitics', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
    
    def test_asset_class_entertainment(self):
        """Test asset_class='entertainment' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-004',
            'category': 'other',
            'asset_class': 'entertainment',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'entertainment', f"Expected 'entertainment', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
    
    def test_asset_class_science_tech(self):
        """Test asset_class='science-tech' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-005',
            'category': 'other',
            'asset_class': 'science-tech',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'science-tech', f"Expected 'science-tech', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"
    
    def test_asset_class_economics(self):
        """Test asset_class='economics' works correctly"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'edge-006',
            'category': 'other',
            'asset_class': 'economics',
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'economics', f"Expected 'economics', got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"


class TestCategoryPriorityOrder:
    """Tests that category classification follows correct priority order"""
    
    def test_tags_take_priority_over_asset_class(self):
        """Tags (LAYER 2) should take priority over asset_class (LAYER 3.5)"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'priority-001',
            'category': 'other',
            'asset_class': 'crypto',  # Would classify as crypto
            'question': 'Will team win?',
            'tags': [{'slug': 'nba'}]  # But has NBA tag -> sports
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports' from tag, got '{result.category}'"
        assert result.source == 'tag_library', f"Expected 'tag_library', got '{result.source}'"
    
    def test_api_category_takes_priority_over_asset_class(self):
        """API category (LAYER 3) should take priority over asset_class (LAYER 3.5)"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'priority-002',
            'category': 'crypto',  # API says crypto
            'asset_class': 'sports',  # But asset_class says sports
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'crypto', f"Expected 'crypto' from API category, got '{result.category}'"
        assert result.source == 'api_category', f"Expected 'api_category', got '{result.source}'"
    
    def test_asset_class_used_when_api_category_is_other(self):
        """asset_class (LAYER 3.5) should be used when API category is 'other'"""
        tag_lib = TagLibraryService()
        
        market = {
            'id': 'priority-003',
            'category': 'other',  # API says 'other' (unhelpful)
            'asset_class': 'sports',  # asset_class provides real category
            'question': 'Will X happen?',
            'tags': []
        }
        
        result = tag_lib.classify_market(market)
        assert result.category == 'sports', f"Expected 'sports' from asset_class, got '{result.category}'"
        assert result.source == 'asset_class', f"Expected 'asset_class', got '{result.source}'"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
