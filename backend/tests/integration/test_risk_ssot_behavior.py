"""
Test Suite: Risk SSOT Behavioral Verification
==============================================
Verifies that the "Three-Speed" Risk Architecture makes correct decisions.

This is NOT a crash test - it tests DECISION LOGIC.

Scenario Matrix:
1. Gamma Moonshot - Low liquidity ($300) passes Gamma, fails HFT/Alpha
2. HFT Scalp - High liquidity ($15k) passes all strategies
3. Alpha Whale - Price-sensitive ($0.08) triggers whale tier
4. System Noise - Trash data ($50) rejected by all

Author: APEX TRADER QA
Date: January 2026
"""

import pytest
import sys

sys.path.insert(0, '/app/backend')

from risk_config import RISK


class MockStrategy:
    """Mock strategy object to inject .type attribute."""
    def __init__(self, type_name: str):
        self.type = type_name


# =============================================================================
# SCENARIO MATRIX - Parameterized Test Data
# =============================================================================

RISK_DECISION_SCENARIOS = [
    # -------------------------------------------------------------------------
    # Scenario 1: Gamma Moonshot (Low Liquidity - $300)
    # Price=$0.05, Liquidity=$300, Volume=$300
    # -------------------------------------------------------------------------
    # HFT: REJECT - needs $10,000 liquidity
    ("Gamma_Moonshot_HFT", 0.05, 300.0, 300.0, "HFT", False),
    # Alpha: REJECT - whale tier needs $500
    ("Gamma_Moonshot_Alpha", 0.05, 300.0, 300.0, "ALPHA", False),
    # Gamma: ACCEPT - floor is $250
    ("Gamma_Moonshot_Gamma", 0.05, 300.0, 300.0, "GAMMA", True),
    
    # -------------------------------------------------------------------------
    # Scenario 2: HFT Scalp (High Liquidity - $15,000)
    # Price=$1.50, Liquidity=$15,000, Volume=$10,000
    # -------------------------------------------------------------------------
    # HFT: ACCEPT - meets $10,000 requirement
    ("HFT_Scalp_HFT", 1.50, 15000.0, 10000.0, "HFT", True),
    # Alpha: ACCEPT - exceeds $1,000 core requirement
    ("HFT_Scalp_Alpha", 1.50, 15000.0, 10000.0, "ALPHA", True),
    # Gamma: ACCEPT - exceeds $250 floor
    ("HFT_Scalp_Gamma", 1.50, 15000.0, 10000.0, "GAMMA", True),
    
    # -------------------------------------------------------------------------
    # Scenario 3: Alpha Whale (Price Sensitivity - $0.08)
    # Tests that cheap assets (<$0.10) trigger whale tier ($500 vs $1000)
    # -------------------------------------------------------------------------
    # Alpha at $0.08 with $600 liquidity: ACCEPT (whale tier = $500)
    ("Alpha_Whale_Accept", 0.08, 600.0, 600.0, "ALPHA", True),
    # Alpha at $1.00 with $600 liquidity: REJECT (core tier = $1000)
    ("Alpha_Core_Reject", 1.00, 600.0, 600.0, "ALPHA", False),
    # HFT at $0.08 with $600 liquidity: REJECT (always needs $10,000)
    ("Alpha_Whale_HFT_Reject", 0.08, 600.0, 600.0, "HFT", False),
    
    # -------------------------------------------------------------------------
    # Scenario 4: System Noise (Trash Data - $50)
    # Must be rejected by ALL strategies
    # -------------------------------------------------------------------------
    ("Noise_HFT", 1.00, 50.0, 50.0, "HFT", False),
    ("Noise_Alpha", 1.00, 50.0, 50.0, "ALPHA", False),
    ("Noise_Gamma", 1.00, 50.0, 50.0, "GAMMA", False),
    
    # -------------------------------------------------------------------------
    # Scenario 5: Edge Cases - Boundary Testing
    # -------------------------------------------------------------------------
    # Exactly at HFT threshold
    ("HFT_Boundary_Exact", 0.50, 10000.0, 5000.0, "HFT", True),
    ("HFT_Boundary_Below", 0.50, 9999.0, 5000.0, "HFT", False),
    
    # Exactly at Gamma threshold
    ("Gamma_Boundary_Exact", 0.05, 250.0, 250.0, "GAMMA", True),
    ("Gamma_Boundary_Below", 0.05, 249.0, 250.0, "GAMMA", False),
    
    # Alpha price boundary ($0.10)
    ("Alpha_Price_Boundary_Core", 0.10, 1000.0, 1000.0, "ALPHA", True),  # >= 0.10 = core
    ("Alpha_Price_Boundary_Whale", 0.09, 500.0, 500.0, "ALPHA", True),   # < 0.10 = whale
]


@pytest.mark.parametrize(
    "scenario, price, liquidity, volume, strat_type, expected_decision",
    RISK_DECISION_SCENARIOS
)
def test_risk_decision_matrix(scenario, price, liquidity, volume, strat_type, expected_decision):
    """
    Verifies that RiskConfig.get_thresholds() acts as the central brain
    for different strategy personalities.
    
    This is the CORE behavioral test for the Three-Speed architecture.
    """
    # Act - Get thresholds from SSOT
    min_liq, min_vol = RISK.get_thresholds(strat_type, price)
    
    # Calculate decision
    is_accepted = (liquidity >= min_liq) and (volume >= min_vol)
    
    # Assert with detailed message
    assert is_accepted == expected_decision, (
        f"\n{'='*60}\n"
        f"FAILED SCENARIO: {scenario}\n"
        f"{'='*60}\n"
        f"Strategy: {strat_type}\n"
        f"Price: ${price}\n"
        f"Liquidity: ${liquidity:,.0f} (required: ${min_liq:,.0f})\n"
        f"Volume: ${volume:,.0f} (required: ${min_vol:,.0f})\n"
        f"Expected: {'ACCEPT' if expected_decision else 'REJECT'}\n"
        f"Actual: {'ACCEPT' if is_accepted else 'REJECT'}\n"
        f"{'='*60}"
    )


class TestDataCleanerAlignment:
    """
    Verifies that the Data Cleaner (BayesianOutlierDetector) is aligned with
    the lowest possible system floor (Gamma).
    
    Critical: If the cleaner is too strict, we blind the AI to valid trades.
    
    Note: We test the SSOT values directly since the class requires DB.
    The class constructor uses RISK.DATA_CLEANING_MIN_LIQUIDITY.
    """
    
    def test_cleaner_accepts_gamma_trades(self):
        """Data cleaner MUST accept valid Gamma trades ($300)."""
        # The cleaner uses RISK.DATA_CLEANING_MIN_LIQUIDITY
        cleaner_threshold = RISK.DATA_CLEANING_MIN_LIQUIDITY
        
        # Gamma floor is $250, so $300 should be accepted
        assert cleaner_threshold <= 300.0, (
            f"Data Cleaner is rejecting valid Gamma trades!\n"
            f"Cleaner threshold: ${cleaner_threshold}\n"
            f"Gamma trade: $300\n"
            f"This blinds the AI to legitimate moonshot data."
        )
    
    def test_cleaner_rejects_noise(self):
        """Data cleaner MUST reject system noise ($50)."""
        # The cleaner uses RISK.DATA_CLEANING_MIN_LIQUIDITY
        cleaner_threshold = RISK.DATA_CLEANING_MIN_LIQUIDITY
        
        # $50 is trash data, must be rejected
        assert 50.0 < cleaner_threshold, (
            f"Data Cleaner is accepting noise!\n"
            f"Cleaner threshold: ${cleaner_threshold}\n"
            f"Noise data: $50\n"
            f"This pollutes AI training with garbage."
        )
    
    def test_cleaner_uses_gamma_floor(self):
        """Data cleaner threshold should equal Gamma floor (SSOT alignment)."""
        # Verify DATA_CLEANING matches GAMMA floor
        assert RISK.DATA_CLEANING_MIN_LIQUIDITY == RISK.GAMMA_MIN_LIQUIDITY, (
            f"Data Cleaner is NOT aligned with Gamma floor!\n"
            f"DATA_CLEANING: ${RISK.DATA_CLEANING_MIN_LIQUIDITY}\n"
            f"GAMMA: ${RISK.GAMMA_MIN_LIQUIDITY}\n"
            f"These must match so AI learns from all valid trades."
        )
    
    def test_bayesian_outlier_source_code_uses_risk(self):
        """Verify the actual source code imports and uses RISK."""
        import inspect
        from ml import bayesian_outlier
        
        source = inspect.getsource(bayesian_outlier)
        
        # Check that the module uses RISK for thresholds
        assert "RISK.DATA_CLEANING_MIN_LIQUIDITY" in source, (
            "BayesianOutlierDetector does not use RISK.DATA_CLEANING_MIN_LIQUIDITY!"
        )
        assert "from risk_config import RISK" in source, (
            "BayesianOutlierDetector does not import RISK from risk_config!"
        )


class TestStrategyPathMapping:
    """
    Verifies that strategy names correctly map to their allocation paths.
    """
    
    @pytest.mark.parametrize("strategy_name, expected_path", [
        # HFT Path (35% allocation)
        ("HFT", "HFT"),
        ("ARBITRAGE", "HFT"),
        ("DELTA_NEUTRAL", "HFT"),
        ("MARKET_MAKING", "HFT"),
        
        # Gamma Path (10% allocation)
        ("GAMMA", "GAMMA"),
        ("GAMMA_SCALP", "GAMMA"),
        ("WHALE", "GAMMA"),
        ("MOONSHOT", "GAMMA"),
        ("VOLATILITY", "GAMMA"),  # Volatility exploitation = GAMMA moonshots
        ("VOLATILITY_EXPLOITATION", "GAMMA"),
        
        # Alpha Path (55% allocation) - default
        ("ALPHA", "ALPHA"),
        ("ALPHA_DIRECTIONAL", "ALPHA"),
        ("unknown_strategy", "ALPHA"),  # Unknown defaults to Alpha
        (None, "ALPHA"),  # None defaults to Alpha
    ])
    def test_strategy_path_mapping(self, strategy_name, expected_path):
        """Verify strategy names map to correct capital allocation paths."""
        actual_path = RISK.get_strategy_path(strategy_name)
        
        assert actual_path == expected_path, (
            f"Strategy '{strategy_name}' mapped to '{actual_path}', "
            f"expected '{expected_path}'"
        )


class TestThresholdValues:
    """
    Verify the actual threshold values match the architecture spec.
    """
    
    def test_hft_thresholds(self):
        """HFT requires strict high-liquidity filters."""
        min_liq, min_vol = RISK.get_thresholds("HFT", 0.50)
        assert min_liq == 10000.0, f"HFT min_liquidity should be $10,000, got ${min_liq}"
        assert min_vol == 5000.0, f"HFT min_volume should be $5,000, got ${min_vol}"
    
    def test_gamma_thresholds(self):
        """Gamma has the lowest floors for moonshots."""
        min_liq, min_vol = RISK.get_thresholds("GAMMA", 0.05)
        assert min_liq == 250.0, f"Gamma min_liquidity should be $250, got ${min_liq}"
        assert min_vol == 250.0, f"Gamma min_volume should be $250, got ${min_vol}"
    
    def test_alpha_core_thresholds(self):
        """Alpha Core (price >= $0.10) has moderate requirements."""
        min_liq, min_vol = RISK.get_thresholds("ALPHA", 0.50)
        assert min_liq == 1000.0, f"Alpha Core min_liquidity should be $1,000, got ${min_liq}"
        assert min_vol == 1000.0, f"Alpha Core min_volume should be $1,000, got ${min_vol}"
    
    def test_alpha_whale_thresholds(self):
        """Alpha Whale (price < $0.10) has relaxed requirements."""
        min_liq, min_vol = RISK.get_thresholds("ALPHA", 0.05)
        assert min_liq == 500.0, f"Alpha Whale min_liquidity should be $500, got ${min_liq}"
        assert min_vol == 500.0, f"Alpha Whale min_volume should be $500, got ${min_vol}"
    
    def test_threshold_hierarchy(self):
        """Verify HFT > Alpha Core > Alpha Whale > Gamma."""
        hft_liq, _ = RISK.get_thresholds("HFT", 0.50)
        alpha_core_liq, _ = RISK.get_thresholds("ALPHA", 0.50)
        alpha_whale_liq, _ = RISK.get_thresholds("ALPHA", 0.05)
        gamma_liq, _ = RISK.get_thresholds("GAMMA", 0.05)
        
        assert hft_liq > alpha_core_liq > alpha_whale_liq > gamma_liq, (
            f"Threshold hierarchy violated!\n"
            f"HFT: ${hft_liq} > Alpha Core: ${alpha_core_liq} > "
            f"Alpha Whale: ${alpha_whale_liq} > Gamma: ${gamma_liq}"
        )


class TestCapitalAllocationDefaults:
    """
    Verify the Three-Speed capital allocation percentages.
    """
    
    def test_allocations_sum_to_100(self):
        """HFT + Alpha + Gamma must equal 100%."""
        total = RISK.HFT_ALLOCATION_PCT + RISK.ALPHA_ALLOCATION_PCT + RISK.GAMMA_ALLOCATION_PCT
        assert total == 100.0, f"Allocations sum to {total}%, expected 100%"
    
    def test_default_allocation_values(self):
        """Verify default 35/55/10 split."""
        assert RISK.HFT_ALLOCATION_PCT == 35.0, f"HFT should be 35%, got {RISK.HFT_ALLOCATION_PCT}%"
        assert RISK.ALPHA_ALLOCATION_PCT == 55.0, f"Alpha should be 55%, got {RISK.ALPHA_ALLOCATION_PCT}%"
        assert RISK.GAMMA_ALLOCATION_PCT == 10.0, f"Gamma should be 10%, got {RISK.GAMMA_ALLOCATION_PCT}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
