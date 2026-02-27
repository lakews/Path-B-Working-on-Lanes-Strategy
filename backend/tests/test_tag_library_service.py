"""
Test TagLibraryService API Endpoints
====================================

Tests for the new TagLibraryService architecture that replaces brittle keyword-based
sports market filtering with a pre-curated tag library.

Features tested:
1. /api/tag-library/stats - Returns correct statistics
2. /api/tag-library/classify - Correctly classifies sports, crypto, politics markets
3. risk_config.json - Has valid 'categories' section with sub-categories
4. /api/paper/cumulative-stats - Includes 'by_sub_category' field
"""

import pytest
import requests
import os
import json

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")


class TestTagLibraryStats:
    """Test /api/tag-library/stats endpoint"""
    
    def test_stats_endpoint_returns_200(self):
        """Test that stats endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/tag-library/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_stats_has_required_fields(self):
        """Test that stats response has required fields"""
        response = requests.get(f"{BASE_URL}/api/tag-library/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check top-level fields
        assert "status" in data, "Missing 'status' field"
        assert "stats" in data, "Missing 'stats' field"
        assert "message" in data, "Missing 'message' field"
        
        # Check status is active
        assert data["status"] == "active", f"Expected status 'active', got '{data['status']}'"
    
    def test_stats_contains_tag_counts(self):
        """Test that stats contains tag counts by category"""
        response = requests.get(f"{BASE_URL}/api/tag-library/stats")
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        
        # Should have total_tags
        assert "total_tags" in stats, "Missing 'total_tags' in stats"
        total_tags = stats["total_tags"]
        
        # Per the spec, should have 398 tags across 7 categories
        # Allow some flexibility (350-450 range)
        assert 350 <= total_tags <= 450, f"Expected ~398 tags, got {total_tags}"
        
        # Should have tags_by_category
        assert "tags_by_category" in stats, "Missing 'tags_by_category' in stats"
        tags_by_category = stats["tags_by_category"]
        
        # Should have at least 7 categories
        assert len(tags_by_category) >= 7, f"Expected at least 7 categories, got {len(tags_by_category)}"
        
        # Check expected categories exist
        expected_categories = ["sports", "crypto", "politics", "economics", "science-tech", "entertainment", "geopolitics"]
        for cat in expected_categories:
            assert cat in tags_by_category, f"Missing category '{cat}' in tags_by_category"


class TestTagLibraryClassify:
    """Test /api/tag-library/classify endpoint"""
    
    def test_classify_sports_market_nfl(self):
        """Test classification of NFL sports market"""
        market_data = {
            "id": "test-nfl-market",
            "question": "Will the Chiefs win the Super Bowl?",
            "tags": [{"slug": "nfl"}, {"slug": "super-bowl"}],
            "category": "sports"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check classification structure
        assert "classification" in data, "Missing 'classification' field"
        assert "is_sports" in data, "Missing 'is_sports' field"
        
        classification = data["classification"]
        
        # Should be classified as sports
        assert classification["category"] == "sports", f"Expected category 'sports', got '{classification['category']}'"
        assert data["is_sports"] == True, "Expected is_sports to be True"
        
        # Should have sub_category
        assert "sub_category" in classification, "Missing 'sub_category' in classification"
        assert classification["sub_category"] == "american-football", f"Expected sub_category 'american-football', got '{classification['sub_category']}'"
    
    def test_classify_sports_market_nba(self):
        """Test classification of NBA basketball market"""
        market_data = {
            "id": "test-nba-market",
            "question": "Will the Lakers win the NBA Finals?",
            "tags": [{"slug": "nba"}, {"slug": "lakers"}],
            "category": "sports"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        assert classification["category"] == "sports"
        assert classification["sub_category"] == "basketball"
        assert data["is_sports"] == True
    
    def test_classify_sports_market_soccer(self):
        """Test classification of soccer market"""
        market_data = {
            "id": "test-soccer-market",
            "question": "Will Manchester United win the Premier League?",
            "tags": [{"slug": "premier-league"}, {"slug": "manchester-united"}],
            "category": "sports"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        assert classification["category"] == "sports"
        assert classification["sub_category"] == "soccer"
        assert data["is_sports"] == True
    
    def test_classify_crypto_market_bitcoin(self):
        """Test classification of Bitcoin crypto market"""
        market_data = {
            "id": "test-btc-market",
            "question": "Will Bitcoin reach $100k by end of year?",
            "tags": [{"slug": "bitcoin"}, {"slug": "btc"}],
            "category": "crypto"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        assert classification["category"] == "crypto", f"Expected category 'crypto', got '{classification['category']}'"
        assert classification["sub_category"] == "btc", f"Expected sub_category 'btc', got '{classification['sub_category']}'"
        assert data["is_sports"] == False, "Expected is_sports to be False for crypto"
    
    def test_classify_crypto_market_ethereum(self):
        """Test classification of Ethereum crypto market"""
        market_data = {
            "id": "test-eth-market",
            "question": "Will Ethereum flip Bitcoin?",
            "tags": [{"slug": "ethereum"}, {"slug": "eth"}],
            "category": "crypto"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        assert classification["category"] == "crypto"
        assert classification["sub_category"] == "eth"
        assert data["is_sports"] == False
    
    def test_classify_politics_market_us(self):
        """Test classification of US politics market"""
        market_data = {
            "id": "test-politics-market",
            "question": "Will Trump win the 2028 election?",
            "tags": [{"slug": "donald-trump"}, {"slug": "2028-election"}],
            "category": "politics"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        assert classification["category"] == "politics", f"Expected category 'politics', got '{classification['category']}'"
        assert classification["sub_category"] == "us-politics", f"Expected sub_category 'us-politics', got '{classification['sub_category']}'"
        assert data["is_sports"] == False
    
    def test_classify_market_with_confidence(self):
        """Test that classification includes confidence score"""
        market_data = {
            "id": "test-confidence-market",
            "question": "Will the UFC champion retain title?",
            "tags": [{"slug": "ufc"}],
            "category": "sports"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        # Should have confidence field
        assert "confidence" in classification, "Missing 'confidence' in classification"
        assert 0 <= classification["confidence"] <= 1, f"Confidence should be 0-1, got {classification['confidence']}"
        
        # Tag-based classification should have high confidence (1.0)
        assert classification["confidence"] == 1.0, f"Expected confidence 1.0 for tag-based, got {classification['confidence']}"
    
    def test_classify_market_with_source(self):
        """Test that classification includes source field"""
        market_data = {
            "id": "test-source-market",
            "question": "Will OpenAI release GPT-5?",
            "tags": [{"slug": "openai"}, {"slug": "ai"}],
            "category": "science"
        }
        
        response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market_data)
        assert response.status_code == 200
        
        data = response.json()
        classification = data["classification"]
        
        # Should have source field
        assert "source" in classification, "Missing 'source' in classification"
        assert classification["source"] in ["tag_library", "keyword", "api_category", "default"], \
            f"Unexpected source: {classification['source']}"


class TestRiskConfigCategories:
    """Test risk_config.json has valid 'categories' section"""
    
    def test_risk_config_has_categories_section(self):
        """Test that risk_config.json has 'categories' section"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert "categories" in config, "Missing 'categories' section in risk_config.json"
    
    def test_categories_has_metadata(self):
        """Test that categories section has metadata"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        categories = config["categories"]
        assert "_metadata" in categories, "Missing '_metadata' in categories"
        
        metadata = categories["_metadata"]
        assert "description" in metadata, "Missing 'description' in categories metadata"
        assert "version" in metadata, "Missing 'version' in categories metadata"
    
    def test_categories_has_required_categories(self):
        """Test that categories section has all required categories"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        categories = config["categories"]
        
        # Required categories (aligned with TagLibraryService)
        required_categories = ["sports", "crypto", "politics", "economics", "science-tech", "entertainment", "geopolitics", "default"]
        
        for cat in required_categories:
            assert cat in categories, f"Missing required category '{cat}' in risk_config.json"
    
    def test_categories_have_sub_categories(self):
        """Test that each category has sub_categories"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        categories = config["categories"]
        
        for cat_name, cat_data in categories.items():
            if cat_name == "_metadata":
                continue
            
            assert "sub_categories" in cat_data, f"Missing 'sub_categories' in category '{cat_name}'"
            sub_cats = cat_data["sub_categories"]
            
            # Should have at least _default sub-category
            assert "_default" in sub_cats, f"Missing '_default' sub-category in '{cat_name}'"
    
    def test_sports_category_has_expected_sub_categories(self):
        """Test that sports category has expected sub-categories"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        sports = config["categories"]["sports"]
        sub_cats = sports["sub_categories"]
        
        # Expected sports sub-categories
        expected_sub_cats = ["basketball", "american-football", "soccer", "mma", "tennis"]
        
        for sub_cat in expected_sub_cats:
            assert sub_cat in sub_cats, f"Missing sports sub-category '{sub_cat}'"
    
    def test_crypto_category_has_expected_sub_categories(self):
        """Test that crypto category has expected sub-categories"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        crypto = config["categories"]["crypto"]
        sub_cats = crypto["sub_categories"]
        
        # Expected crypto sub-categories
        expected_sub_cats = ["btc", "eth", "altcoin", "defi"]
        
        for sub_cat in expected_sub_cats:
            assert sub_cat in sub_cats, f"Missing crypto sub-category '{sub_cat}'"
    
    def test_sub_categories_have_allocation_and_multipliers(self):
        """Test that sub-categories have allocation_pct, tp_mult, sl_mult"""
        config_path = "/app/backend/config/risk_config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        categories = config["categories"]
        
        for cat_name, cat_data in categories.items():
            if cat_name == "_metadata":
                continue
            
            sub_cats = cat_data.get("sub_categories", {})
            
            for sub_cat_name, sub_cat_data in sub_cats.items():
                assert "allocation_pct" in sub_cat_data, \
                    f"Missing 'allocation_pct' in {cat_name}/{sub_cat_name}"
                assert "tp_mult" in sub_cat_data, \
                    f"Missing 'tp_mult' in {cat_name}/{sub_cat_name}"
                assert "sl_mult" in sub_cat_data, \
                    f"Missing 'sl_mult' in {cat_name}/{sub_cat_name}"


class TestCumulativeStatsSubCategory:
    """Test /api/paper/cumulative-stats includes by_sub_category field"""
    
    def test_cumulative_stats_returns_200(self):
        """Test that cumulative-stats endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_cumulative_stats_has_by_sub_category(self):
        """Test that cumulative-stats response has by_sub_category field"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required fields
        assert "overall" in data, "Missing 'overall' field"
        assert "by_strategy" in data, "Missing 'by_strategy' field"
        assert "by_asset_class" in data, "Missing 'by_asset_class' field"
        assert "by_sub_category" in data, "Missing 'by_sub_category' field"
    
    def test_cumulative_stats_by_sub_category_structure(self):
        """Test that by_sub_category has correct structure (can be empty dict)"""
        response = requests.get(f"{BASE_URL}/api/paper/cumulative-stats")
        assert response.status_code == 200
        
        data = response.json()
        by_sub_category = data.get("by_sub_category", {})
        
        # Should be a dict (can be empty if no trades)
        assert isinstance(by_sub_category, dict), f"Expected dict, got {type(by_sub_category)}"
        
        # If not empty, check structure
        if by_sub_category:
            for category, sub_cats in by_sub_category.items():
                assert isinstance(sub_cats, dict), f"Expected dict for category '{category}'"


class TestTagLibraryCategories:
    """Test /api/tag-library/categories endpoint"""
    
    def test_categories_endpoint_returns_200(self):
        """Test that categories endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/tag-library/categories")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_categories_has_required_fields(self):
        """Test that categories response has required fields"""
        response = requests.get(f"{BASE_URL}/api/tag-library/categories")
        assert response.status_code == 200
        
        data = response.json()
        
        assert "categories" in data, "Missing 'categories' field"
        assert "total_tags" in data, "Missing 'total_tags' field"
        assert "allocation_template" in data, "Missing 'allocation_template' field"
    
    def test_categories_contains_sports(self):
        """Test that categories contains sports with slugs"""
        response = requests.get(f"{BASE_URL}/api/tag-library/categories")
        assert response.status_code == 200
        
        data = response.json()
        categories = data["categories"]
        
        assert "sports" in categories, "Missing 'sports' category"
        sports = categories["sports"]
        
        assert "tag_count" in sports, "Missing 'tag_count' in sports"
        assert "slugs" in sports, "Missing 'slugs' in sports"
        assert "total_slugs" in sports, "Missing 'total_slugs' in sports"
        
        # Sports should have many tags
        assert sports["tag_count"] > 50, f"Expected >50 sports tags, got {sports['tag_count']}"


class TestHFTEngineTagLibraryIntegration:
    """Test that HFT Engine uses TagLibraryService for sports detection"""
    
    def test_classify_sports_market_for_hft_filtering(self):
        """Test that sports markets are correctly identified for HFT filtering"""
        # Test various sports markets that should be filtered by HFT
        sports_markets = [
            {"id": "nfl-1", "tags": [{"slug": "nfl"}], "question": "NFL game"},
            {"id": "nba-1", "tags": [{"slug": "nba"}], "question": "NBA game"},
            {"id": "soccer-1", "tags": [{"slug": "premier-league"}], "question": "Soccer match"},
            {"id": "ufc-1", "tags": [{"slug": "ufc"}], "question": "UFC fight"},
        ]
        
        for market in sports_markets:
            response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market)
            assert response.status_code == 200
            
            data = response.json()
            assert data["is_sports"] == True, f"Market {market['id']} should be classified as sports"
            assert data["classification"]["category"] == "sports"
    
    def test_classify_non_sports_market_for_hft(self):
        """Test that non-sports markets are not filtered by HFT"""
        non_sports_markets = [
            {"id": "btc-1", "tags": [{"slug": "bitcoin"}], "question": "Bitcoin price"},
            {"id": "politics-1", "tags": [{"slug": "us-politics"}], "question": "Election"},
            {"id": "ai-1", "tags": [{"slug": "openai"}], "question": "AI development"},
        ]
        
        for market in non_sports_markets:
            response = requests.post(f"{BASE_URL}/api/tag-library/classify", json=market)
            assert response.status_code == 200
            
            data = response.json()
            assert data["is_sports"] == False, f"Market {market['id']} should NOT be classified as sports"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
