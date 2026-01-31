"""
Test suite for Backtest History and Comparison features
Tests: /api/backtest/history, /api/backtest/compare endpoints
Features: History storage, comparison metrics, quality score, improvement insights
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://sentiment-deep-dive.preview.emergentagent.com').rstrip('/')

class TestBacktestHistory:
    """Tests for /api/backtest/history endpoint"""
    
    def test_get_backtest_history_returns_list(self):
        """Test that history endpoint returns a list of backtests"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "history" in data
        assert "count" in data
        assert isinstance(data["history"], list)
        assert data["count"] == len(data["history"])
    
    def test_backtest_history_has_required_fields(self):
        """Test that each backtest in history has required fields"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        if data["count"] > 0:
            backtest = data["history"][0]
            required_fields = [
                "backtest_id", "status", "initial_capital", "final_capital",
                "total_pnl", "total_return_pct", "total_trades", "win_rate",
                "max_drawdown", "sharpe_ratio", "profit_factor"
            ]
            for field in required_fields:
                assert field in backtest, f"Missing field: {field}"
    
    def test_backtest_history_limit_parameter(self):
        """Test that limit parameter works correctly"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=1")
        assert response.status_code == 200
        
        data = response.json()
        assert data["count"] <= 1


class TestBacktestCompare:
    """Tests for /api/backtest/compare endpoint"""
    
    @pytest.fixture
    def backtest_ids(self):
        """Get available backtest IDs for comparison"""
        response = requests.get(f"{BASE_URL}/api/backtest/history?limit=10")
        if response.status_code == 200:
            data = response.json()
            return [bt["backtest_id"] for bt in data.get("history", [])]
        return []
    
    def test_compare_backtests_returns_comparison_data(self, backtest_ids):
        """Test that compare endpoint returns comparison data"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "backtest_count" in data
        assert "backtests" in data
        assert "comparison_metrics" in data
    
    def test_compare_returns_quality_score(self, backtest_ids):
        """Test that compare returns strategy quality score with grade"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "educational_analysis" in data
        
        edu = data["educational_analysis"]
        assert "strategy_quality_score" in edu
        
        quality_score = edu["strategy_quality_score"]
        assert "grade" in quality_score
        assert "total_score" in quality_score
        assert "max_score" in quality_score
        assert "breakdown" in quality_score
        
        # Grade should be A-F
        assert quality_score["grade"] in ["A", "B", "C", "D", "F"]
        # Score should be 0-100
        assert 0 <= quality_score["total_score"] <= 100
        assert quality_score["max_score"] == 100
    
    def test_compare_returns_improvement_insights(self, backtest_ids):
        """Test that compare returns improvement insights with severity"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "improvement_insights" in data
        
        insights = data["improvement_insights"]
        assert isinstance(insights, list)
        
        if len(insights) > 0:
            insight = insights[0]
            assert "severity" in insight
            assert "area" in insight
            assert "issue" in insight
            assert "recommendation" in insight
            assert "action" in insight
            
            # Severity should be critical/high/medium/low
            assert insight["severity"] in ["critical", "high", "medium", "low"]
    
    def test_compare_returns_comparison_metrics(self, backtest_ids):
        """Test that compare returns detailed comparison metrics"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        metrics = data.get("comparison_metrics", {})
        
        expected_metrics = ["return", "sharpe_ratio", "max_drawdown", "win_rate", "profit_factor"]
        for metric in expected_metrics:
            assert metric in metrics, f"Missing metric: {metric}"
            
            metric_data = metrics[metric]
            assert "best" in metric_data
            assert "worst" in metric_data
            assert "avg" in metric_data
    
    def test_compare_returns_strategy_comparison(self, backtest_ids):
        """Test that compare returns strategy-level comparison"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "strategy_comparison" in data
        assert isinstance(data["strategy_comparison"], dict)
    
    def test_compare_returns_asset_class_comparison(self, backtest_ids):
        """Test that compare returns asset class comparison"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=backtest_ids[:2]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "asset_class_comparison" in data
        assert isinstance(data["asset_class_comparison"], dict)
    
    def test_compare_with_single_backtest(self, backtest_ids):
        """Test that compare works with single backtest for analysis"""
        if len(backtest_ids) < 1:
            pytest.skip("No backtests available for comparison")
        
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=[backtest_ids[0]]
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["backtest_count"] == 1
    
    def test_compare_with_empty_list_returns_error(self):
        """Test that compare with empty list returns error"""
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=[]
        )
        assert response.status_code == 400
    
    def test_compare_with_invalid_ids_returns_error(self):
        """Test that compare with invalid IDs returns error"""
        response = requests.post(
            f"{BASE_URL}/api/backtest/compare",
            json=["invalid-id-1", "invalid-id-2"]
        )
        assert response.status_code == 404


class TestBacktestStopEndpoint:
    """Tests for /api/backtest/stop endpoint"""
    
    def test_stop_backtest_when_not_running(self):
        """Test stop backtest when no backtest is running"""
        response = requests.post(f"{BASE_URL}/api/backtest/stop")
        # Should succeed and reset mode to stopped
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert data.get("mode") == "stopped"


class TestBacktestResults:
    """Tests for /api/backtest/results endpoint"""
    
    def test_get_latest_results(self):
        """Test getting latest backtest results"""
        response = requests.get(f"{BASE_URL}/api/backtest/results")
        # May return 404 if no results, or 200 with data
        assert response.status_code in [200, 404]
    
    def test_get_results_by_id(self):
        """Test getting results by specific backtest ID"""
        # First get a valid ID
        history_response = requests.get(f"{BASE_URL}/api/backtest/history?limit=1")
        if history_response.status_code == 200:
            data = history_response.json()
            if data.get("count", 0) > 0:
                backtest_id = data["history"][0]["backtest_id"]
                
                response = requests.get(f"{BASE_URL}/api/backtest/results?backtest_id={backtest_id}")
                assert response.status_code == 200
                
                result = response.json()
                assert result.get("backtest_id") == backtest_id


class TestEducationalAnalysis:
    """Tests for educational analysis features"""
    
    @pytest.fixture
    def comparison_data(self):
        """Get comparison data for testing"""
        history_response = requests.get(f"{BASE_URL}/api/backtest/history?limit=10")
        if history_response.status_code == 200:
            data = history_response.json()
            ids = [bt["backtest_id"] for bt in data.get("history", [])]
            if ids:
                compare_response = requests.post(
                    f"{BASE_URL}/api/backtest/compare",
                    json=ids[:2]
                )
                if compare_response.status_code == 200:
                    return compare_response.json()
        return None
    
    def test_educational_analysis_has_key_concepts(self, comparison_data):
        """Test that educational analysis includes key concepts"""
        if not comparison_data:
            pytest.skip("No comparison data available")
        
        edu = comparison_data.get("educational_analysis", {})
        assert "key_concepts" in edu
        
        concepts = edu["key_concepts"]
        expected_concepts = ["sharpe_ratio", "max_drawdown", "profit_factor", "win_rate"]
        for concept in expected_concepts:
            assert concept in concepts, f"Missing concept: {concept}"
    
    def test_educational_analysis_has_recommendations(self, comparison_data):
        """Test that educational analysis includes recommendations summary"""
        if not comparison_data:
            pytest.skip("No comparison data available")
        
        edu = comparison_data.get("educational_analysis", {})
        assert "recommendations_summary" in edu
        assert isinstance(edu["recommendations_summary"], list)
    
    def test_quality_score_breakdown_has_components(self, comparison_data):
        """Test that quality score breakdown has all components"""
        if not comparison_data:
            pytest.skip("No comparison data available")
        
        quality_score = comparison_data.get("educational_analysis", {}).get("strategy_quality_score", {})
        breakdown = quality_score.get("breakdown", [])
        
        expected_components = ["Return", "Sharpe Ratio", "Max Drawdown", "Profit Factor"]
        component_names = [b["component"] for b in breakdown]
        
        for comp in expected_components:
            assert comp in component_names, f"Missing component: {comp}"
