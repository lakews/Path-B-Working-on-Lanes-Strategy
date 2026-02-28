""" Integration test for Architecture C Ultimate """
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.path_a_engine import (
    detect_category,
    calculate_bayes_factor_enhanced,
    calculate_adaptive_ttl,
    calculate_news_priority,
    MarketRegime
)

def test_category_detection():
    """Test category detection with 1,445+ keywords"""
    print("\n[TEST] Category Detection")
    # Test CRYPTO
    category, conf, matches = detect_category("Bitcoin surges past $100K on ETF approval")
    assert category == "CRYPTO", f"Expected CRYPTO, got {category}"
    print(f"  ✓ CRYPTO detected (confidence: {conf:.2f})")
    # Test GEOPOLITICS
    category, conf, matches = detect_category("Ukraine reports drone strikes on Russian targets")
    assert category == "GEOPOLITICS", f"Expected GEOPOLITICS, got {category}"
    print(f"  ✓ GEOPOLITICS detected (confidence: {conf:.2f})")
    # Test SPORTS
    category, conf, matches = detect_category("Lakers win NBA championship against Celtics")
    assert category == "SPORTS", f"Expected SPORTS, got {category}"
    print(f"  ✓ SPORTS detected (confidence: {conf:.2f})")
    # Test POLITICS
    category, conf, matches = detect_category("Trump and Biden debate in upcoming election")
    assert category == "POLITICS", f"Expected POLITICS, got {category}"
    print(f"  ✓ POLITICS detected (confidence: {conf:.2f})")
    print("   ✅ Category detection working!")

def test_bayes_multipliers():
    """Test category-specific Bayes multipliers"""
    print("\n[TEST] Bayes Multipliers")
    # Geopolitics gets 1.2× boost
    bf, mult, adjusted = calculate_bayes_factor_enhanced(0.85, 'strong', 'GEOPOLITICS')
    assert mult == 1.2
    print(f"  ✓ GEOPOLITICS: {mult}× boost ({bf:.2f} → {adjusted:.2f})")
    # Entertainment gets 0.7× penalty
    bf, mult, adjusted = calculate_bayes_factor_enhanced(0.85, 'strong', 'ENTERTAINMENT')
    assert mult == 0.7
    print(f"  ✓ ENTERTAINMENT: {mult}× penalty ({bf:.2f} → {adjusted:.2f})")
    # Finance gets 1.1× boost
    bf, mult, adjusted = calculate_bayes_factor_enhanced(0.85, 'strong', 'FINANCE')
    assert mult == 1.1
    print(f"  ✓ FINANCE: {mult}× boost ({bf:.2f} → {adjusted:.2f})")
    print("   ✅ Bayes multipliers working!")

def test_adaptive_ttl():
    """Test adaptive TTL"""
    print("\n[TEST] Adaptive TTL")
    # Crisis = short TTL (high volume)
    ttl, regime = calculate_adaptive_ttl('strong', {'volume': 1500000, 'volume_24h': 100000, 'liquidity': 50000}, None)
    assert regime == MarketRegime.CRISIS
    print(f"  ✓ CRISIS: {ttl}s TTL (regime: {regime.value})")
    # Volatile = medium TTL (high volume but not crisis level)
    ttl, regime = calculate_adaptive_ttl('strong', {'volume': 200000, 'volume_24h': 100000, 'liquidity': 50000}, None)
    # Volume / (volume_24h/24) = 200000 / 4167 = 48 which is > 3.0, so it's CRISIS
    # Let's use lower volume to get VOLATILE
    ttl, regime = calculate_adaptive_ttl('strong', {'volume': 8000, 'volume_24h': 100000, 'liquidity': 50000}, None)
    # 8000 / 4167 = 1.92 which is > 1.5, so VOLATILE
    assert regime == MarketRegime.VOLATILE
    print(f"  ✓ VOLATILE: {ttl}s TTL (regime: {regime.value})")
    # Quiet = long TTL (low volume, low liquidity)
    ttl, regime = calculate_adaptive_ttl('strong', {'volume': 500, 'volume_24h': 100000, 'liquidity': 30000}, None)
    assert regime == MarketRegime.QUIET
    print(f"  ✓ QUIET: {ttl}s TTL (regime: {regime.value})")
    # Normal
    ttl, regime = calculate_adaptive_ttl('strong', {'volume': 5000, 'volume_24h': 100000, 'liquidity': 100000}, None)
    # 5000 / 4167 = 1.2, which is < 1.5, and volume > 10000 or liquidity > 50000, so NORMAL
    assert regime == MarketRegime.NORMAL
    print(f"  ✓ NORMAL: {ttl}s TTL (regime: {regime.value})")
    print("   ✅ Adaptive TTL working!")

def test_news_priority():
    """Test news priority calculation"""
    print("\n[TEST] News Priority")
    # Breaking news = highest priority (lowest score)
    breaking_news = {'headline': 'BREAKING: Major earthquake', 'source': 'Reuters', 'urgency': 'breaking'}
    priority, urgency, mult = calculate_news_priority(breaking_news)
    print(f"  ✓ Breaking news: priority={priority}, urgency={urgency}")
    assert priority < 20, f"Breaking news should have low priority score, got {priority}"
    
    # Normal news = standard priority
    normal_news = {'headline': 'Tech company reports earnings', 'source': 'Blog', 'urgency': 'normal'}
    priority, urgency, mult = calculate_news_priority(normal_news)
    print(f"  ✓ Normal news: priority={priority}, urgency={urgency}")
    assert priority > 30, f"Normal news should have higher priority score, got {priority}"
    print("   ✅ News priority working!")

if __name__ == "__main__":
    print("=" * 60)
    print("PATH A ENGINE - INTEGRATION TEST")
    print("=" * 60)
    test_category_detection()
    test_bayes_multipliers()
    test_adaptive_ttl()
    test_news_priority()
    print("\n" + "=" * 60)
    print(" ✅ ALL INTEGRATION TESTS PASSED!")
    print("=" * 60)
