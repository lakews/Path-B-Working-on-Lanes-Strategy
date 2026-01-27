"""
Markout Score Analyzer
======================

Analyzes HFT execution quality using "Markout" methodology.

What is Markout?
- For every filled trade, look at the mid-price T seconds later
- Markout_PnL = (Price_T - Execution_Price) * Trade_Direction
- Positive Markout: Price moved in your favor after trade (good signal)
- Negative Markout: Price moved against you after trade (adverse selection)

Interpretation:
- Markout > 0: You're trading with information edge (smart money)
- Markout < 0: You're providing liquidity to informed traders (dumb money)
- Markout ≈ 0: Fair/neutral execution quality

This is THE key metric for HFT quality - more important than simple P&L.

Usage:
    python analysis/markout_score.py /path/to/hft_telemetry.csv

Author: APEX TRADER Quantitative Research
Date: January 2026
"""

import os
import sys
import csv
import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass

# Add backend to path
sys.path.insert(0, '/app/backend')

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Markout time horizons (seconds)
MARKOUT_HORIZONS = [1, 5, 10, 30, 60]

# Minimum trades for statistical significance
MIN_TRADES_FOR_STATS = 10

# Output directory
ANALYSIS_DIR = "/app/backend/data/analysis"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TradeRecord:
    """A single trade for markout analysis."""
    timestamp_ns: int
    market_id: str
    execution_price: float
    trade_side: str  # "BUY" or "SELL"
    trade_size: float
    mid_price_at_trade: float
    fair_value: float
    bias: float
    vol_multiplier: float
    effective_spread_bps: int


@dataclass
class MarkoutResult:
    """Markout analysis result for a single trade."""
    trade: TradeRecord
    markout_1s: float
    markout_5s: float
    markout_10s: float
    markout_30s: float
    markout_60s: float
    price_1s: float
    price_5s: float
    direction_correct: bool  # Did price move in expected direction?


@dataclass
class AggregateStats:
    """Aggregate markout statistics."""
    total_trades: int
    total_volume: float
    avg_markout_1s: float
    avg_markout_5s: float
    avg_markout_10s: float
    avg_markout_30s: float
    avg_markout_60s: float
    pct_direction_correct: float
    avg_bias: float
    avg_vol_multiplier: float
    avg_spread_bps: float
    toxic_trade_pct: float  # % of trades with negative markout


# =============================================================================
# MARKOUT CALCULATOR
# =============================================================================

class MarkoutAnalyzer:
    """
    Analyzes HFT execution quality via Markout methodology.
    
    Steps:
    1. Load telemetry data
    2. Extract filled trades
    3. For each trade, find price at T+1s, T+5s, etc.
    4. Calculate markout = (price_T - exec_price) * direction
    5. Aggregate statistics
    """
    
    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.price_timeline: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        self.results: List[MarkoutResult] = []
    
    def load_telemetry(self, filepath: str) -> int:
        """Load telemetry data from CSV file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Telemetry file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    timestamp_ns = int(row.get('timestamp_ns', 0))
                    market_id = row.get('market_id', '')
                    mid_price = float(row.get('market_mid_price', 0) or 0)
                    
                    # Build price timeline for markout lookup
                    if timestamp_ns and market_id and mid_price > 0:
                        self.price_timeline[market_id].append((timestamp_ns, mid_price))
                    
                    # Extract actual trades (not skips)
                    decision = row.get('decision', '')
                    trade_side = row.get('trade_side', '')
                    trade_size = float(row.get('trade_size', 0) or 0)
                    execution_price = float(row.get('execution_price', 0) or 0)
                    
                    if decision == 'TRADE' and trade_side in ['BUY', 'SELL'] and trade_size > 0:
                        trade = TradeRecord(
                            timestamp_ns=timestamp_ns,
                            market_id=market_id,
                            execution_price=execution_price,
                            trade_side=trade_side,
                            trade_size=trade_size,
                            mid_price_at_trade=mid_price,
                            fair_value=float(row.get('fair_value', 0) or 0),
                            bias=float(row.get('bias', 0) or 0),
                            vol_multiplier=float(row.get('vol_multiplier', 1) or 1),
                            effective_spread_bps=int(row.get('effective_spread_bps', 0) or 0),
                        )
                        self.trades.append(trade)
                        
                except (ValueError, KeyError) as e:
                    logger.debug(f"Skipping malformed row: {e}")
                    continue
        
        # Sort price timelines
        for market_id in self.price_timeline:
            self.price_timeline[market_id].sort(key=lambda x: x[0])
        
        return len(self.trades)
    
    def calculate_markouts(self) -> List[MarkoutResult]:
        """Calculate markout for each trade."""
        self.results = []
        
        for trade in self.trades:
            result = self._calculate_single_markout(trade)
            if result:
                self.results.append(result)
        
        return self.results
    
    def _calculate_single_markout(self, trade: TradeRecord) -> Optional[MarkoutResult]:
        """Calculate markout for a single trade."""
        timeline = self.price_timeline.get(trade.market_id, [])
        
        if not timeline:
            return None
        
        # Direction multiplier (BUY = +1, SELL = -1)
        direction = 1 if trade.trade_side == 'BUY' else -1
        
        # Find prices at each horizon
        price_1s = self._find_price_at_horizon(timeline, trade.timestamp_ns, 1)
        price_5s = self._find_price_at_horizon(timeline, trade.timestamp_ns, 5)
        price_10s = self._find_price_at_horizon(timeline, trade.timestamp_ns, 10)
        price_30s = self._find_price_at_horizon(timeline, trade.timestamp_ns, 30)
        price_60s = self._find_price_at_horizon(timeline, trade.timestamp_ns, 60)
        
        # Calculate markouts
        def calc_markout(price_t: float) -> float:
            if price_t <= 0 or trade.execution_price <= 0:
                return 0.0
            return (price_t - trade.execution_price) * direction
        
        markout_1s = calc_markout(price_1s)
        markout_5s = calc_markout(price_5s)
        markout_10s = calc_markout(price_10s)
        markout_30s = calc_markout(price_30s)
        markout_60s = calc_markout(price_60s)
        
        # Direction correctness check
        # If we bought (direction=1), price going up is correct
        direction_correct = (markout_5s > 0) if price_5s > 0 else False
        
        return MarkoutResult(
            trade=trade,
            markout_1s=markout_1s,
            markout_5s=markout_5s,
            markout_10s=markout_10s,
            markout_30s=markout_30s,
            markout_60s=markout_60s,
            price_1s=price_1s,
            price_5s=price_5s,
            direction_correct=direction_correct,
        )
    
    def _find_price_at_horizon(
        self,
        timeline: List[Tuple[int, float]],
        trade_ts: int,
        horizon_seconds: int
    ) -> float:
        """Find price at T+horizon seconds after trade."""
        target_ns = trade_ts + (horizon_seconds * 1_000_000_000)
        
        # Binary search for closest timestamp
        left, right = 0, len(timeline) - 1
        closest_price = 0.0
        closest_diff = float('inf')
        
        while left <= right:
            mid = (left + right) // 2
            ts, price = timeline[mid]
            diff = abs(ts - target_ns)
            
            if diff < closest_diff:
                closest_diff = diff
                closest_price = price
            
            if ts < target_ns:
                left = mid + 1
            else:
                right = mid - 1
        
        # Only return if we found something within 5 seconds of target
        if closest_diff < 5_000_000_000:
            return closest_price
        return 0.0
    
    def get_aggregate_stats(self) -> AggregateStats:
        """Calculate aggregate statistics from all results."""
        if not self.results:
            return AggregateStats(
                total_trades=0,
                total_volume=0.0,
                avg_markout_1s=0.0,
                avg_markout_5s=0.0,
                avg_markout_10s=0.0,
                avg_markout_30s=0.0,
                avg_markout_60s=0.0,
                pct_direction_correct=0.0,
                avg_bias=0.0,
                avg_vol_multiplier=0.0,
                avg_spread_bps=0.0,
                toxic_trade_pct=0.0,
            )
        
        n = len(self.results)
        total_volume = sum(r.trade.trade_size for r in self.results)
        
        # Volume-weighted markouts
        def weighted_avg(attr: str) -> float:
            total = sum(getattr(r, attr) * r.trade.trade_size for r in self.results)
            return total / total_volume if total_volume > 0 else 0
        
        avg_markout_1s = weighted_avg('markout_1s')
        avg_markout_5s = weighted_avg('markout_5s')
        avg_markout_10s = weighted_avg('markout_10s')
        avg_markout_30s = weighted_avg('markout_30s')
        avg_markout_60s = weighted_avg('markout_60s')
        
        # Direction accuracy
        correct_count = sum(1 for r in self.results if r.direction_correct)
        pct_direction_correct = (correct_count / n) * 100
        
        # Trade characteristics
        avg_bias = sum(r.trade.bias for r in self.results) / n
        avg_vol_multiplier = sum(r.trade.vol_multiplier for r in self.results) / n
        avg_spread_bps = sum(r.trade.effective_spread_bps for r in self.results) / n
        
        # Toxicity (negative markout trades)
        toxic_count = sum(1 for r in self.results if r.markout_5s < 0)
        toxic_trade_pct = (toxic_count / n) * 100
        
        return AggregateStats(
            total_trades=n,
            total_volume=total_volume,
            avg_markout_1s=avg_markout_1s,
            avg_markout_5s=avg_markout_5s,
            avg_markout_10s=avg_markout_10s,
            avg_markout_30s=avg_markout_30s,
            avg_markout_60s=avg_markout_60s,
            pct_direction_correct=pct_direction_correct,
            avg_bias=avg_bias,
            avg_vol_multiplier=avg_vol_multiplier,
            avg_spread_bps=avg_spread_bps,
            toxic_trade_pct=toxic_trade_pct,
        )
    
    def get_by_market_stats(self) -> Dict[str, AggregateStats]:
        """Get markout stats grouped by market."""
        by_market: Dict[str, List[MarkoutResult]] = defaultdict(list)
        
        for result in self.results:
            by_market[result.trade.market_id].append(result)
        
        stats = {}
        for market_id, results in by_market.items():
            # Temporarily swap results for calculation
            original_results = self.results
            self.results = results
            stats[market_id] = self.get_aggregate_stats()
            self.results = original_results
        
        return stats


# =============================================================================
# REPORT GENERATION
# =============================================================================

def print_markout_report(analyzer: MarkoutAnalyzer) -> None:
    """Print a formatted markout analysis report."""
    stats = analyzer.get_aggregate_stats()
    
    print("\n" + "=" * 80)
    print("              HFT MARKOUT ANALYSIS REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Total Trades Analyzed: {stats.total_trades}")
    print(f"Total Volume: ${stats.total_volume:,.2f}")
    print("=" * 80)
    
    # Markout Summary
    print("\n📊 MARKOUT SUMMARY (Volume-Weighted)")
    print("-" * 80)
    print(f"{'Horizon':<15} | {'Avg Markout':>15} | {'Interpretation':>30}")
    print("-" * 80)
    
    def interpret(markout: float) -> str:
        if markout > 0.005:
            return "✅ Strong Edge (Good)"
        elif markout > 0:
            return "✅ Slight Edge"
        elif markout > -0.005:
            return "⚠️ Slight Adverse Selection"
        else:
            return "❌ Toxic (Adverse Selection)"
    
    print(f"{'T+1s':<15} | ${stats.avg_markout_1s:>14.4f} | {interpret(stats.avg_markout_1s):>30}")
    print(f"{'T+5s':<15} | ${stats.avg_markout_5s:>14.4f} | {interpret(stats.avg_markout_5s):>30}")
    print(f"{'T+10s':<15} | ${stats.avg_markout_10s:>14.4f} | {interpret(stats.avg_markout_10s):>30}")
    print(f"{'T+30s':<15} | ${stats.avg_markout_30s:>14.4f} | {interpret(stats.avg_markout_30s):>30}")
    print(f"{'T+60s':<15} | ${stats.avg_markout_60s:>14.4f} | {interpret(stats.avg_markout_60s):>30}")
    print("-" * 80)
    
    # Quality Metrics
    print("\n📈 EXECUTION QUALITY METRICS")
    print("-" * 80)
    print(f"Direction Accuracy: {stats.pct_direction_correct:.1f}%")
    print(f"Toxic Trade Rate: {stats.toxic_trade_pct:.1f}%")
    print(f"Avg Bias Used: {stats.avg_bias:+.3f}")
    print(f"Avg Vol Multiplier: {stats.avg_vol_multiplier:.2f}x")
    print(f"Avg Effective Spread: {stats.avg_spread_bps:.0f} bps")
    print("-" * 80)
    
    # Verdict
    print("\n🔍 VERDICT")
    print("-" * 80)
    
    if stats.avg_markout_5s > 0.005:
        print("✅ EXCELLENT: Strong positive markout - trading with information edge")
    elif stats.avg_markout_5s > 0:
        print("✅ GOOD: Slightly positive markout - neutral to good execution")
    elif stats.avg_markout_5s > -0.005:
        print("⚠️ WARNING: Slightly negative markout - minor adverse selection")
    else:
        print("❌ FAIL: Significant negative markout - providing liquidity to informed traders")
        print("   Action: Review signal quality, increase staleness thresholds, widen spreads")
    
    print("=" * 80)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_markout_analysis(filepath: str) -> AggregateStats:
    """Run markout analysis on a telemetry file."""
    print(f"\n📂 Loading telemetry from: {filepath}")
    
    analyzer = MarkoutAnalyzer()
    trade_count = analyzer.load_telemetry(filepath)
    
    print(f"📊 Loaded {trade_count} trades, {len(analyzer.price_timeline)} markets")
    
    if trade_count < MIN_TRADES_FOR_STATS:
        print(f"⚠️ Not enough trades for statistical significance (min: {MIN_TRADES_FOR_STATS})")
        return analyzer.get_aggregate_stats()
    
    print("🔬 Calculating markouts...")
    analyzer.calculate_markouts()
    
    print_markout_report(analyzer)
    
    return analyzer.get_aggregate_stats()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Try to find latest telemetry file
        telemetry_dir = "/app/backend/data/telemetry"
        if os.path.exists(telemetry_dir):
            files = [f for f in os.listdir(telemetry_dir) if f.startswith('hft_telemetry')]
            if files:
                latest = sorted(files)[-1]
                filepath = os.path.join(telemetry_dir, latest)
                print(f"Using latest telemetry file: {filepath}")
            else:
                print("Usage: python markout_score.py <telemetry_file.csv>")
                print("No telemetry files found in default directory.")
                sys.exit(1)
        else:
            print("Usage: python markout_score.py <telemetry_file.csv>")
            sys.exit(1)
    else:
        filepath = sys.argv[1]
    
    run_markout_analysis(filepath)
