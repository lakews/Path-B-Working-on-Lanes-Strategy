#!/usr/bin/env python3
"""
Strategy Forensics Engine
=========================
Deep-dive "Health Report" for each trading lane (HFT, ALPHA, GAMMA).

Calculates advanced risk/reward metrics to diagnose:
- Why HFT is bleeding money (fee drag vs bad signals?)
- If ALPHA's success is sustainable
- Gamma moonshot effectiveness

Metrics Calculated:
- Profit Factor (Gross Profit / |Gross Loss|)
- Avg Win vs Avg Loss
- Reward-to-Risk Ratio
- Expectancy (theoretical value of next trade)
- Holding Time (avg duration)
- Fee Simulation (0.05% per trade volume)

Run: python scripts/dev_tools/strategy_forensics.py

Author: APEX TRADER Quantitative Team
Date: January 2026
"""

import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Add backend to path
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient
from config import config


# =============================================================================
# CONFIGURATION
# =============================================================================

FEE_RATE = 0.0005  # 0.05% per trade (typical maker fee)
LANE_ORDER = ['HFT', 'ALPHA', 'GAMMA']

# Verdict thresholds
PROFIT_FACTOR_PASS = 1.2
PROFIT_FACTOR_WARNING = 1.0


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_db():
    """Get synchronous database connection."""
    client = MongoClient(config.MONGO_URL)
    return client[config.DB_NAME]


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_all_trades(db) -> List[Dict]:
    """Fetch all exit trades from paper_trades collection."""
    trades = list(db.paper_trades.find(
        {"type": "exit"},
        {"_id": 0}
    ))
    return trades


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object."""
    if not dt_str:
        return None
    try:
        # Handle various ISO formats
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return datetime.fromisoformat(dt_str)
    except:
        return None


# =============================================================================
# METRICS CALCULATION
# =============================================================================

def calculate_lane_metrics(trades: List[Dict]) -> Dict[str, Dict]:
    """Calculate comprehensive metrics for each lane."""
    
    # Group trades by lane
    lanes = defaultdict(list)
    for trade in trades:
        lane = trade.get('strategy_lane') or 'ALPHA'  # Default to ALPHA
        lanes[lane].append(trade)
    
    results = {}
    
    for lane, lane_trades in lanes.items():
        # Basic counts
        total = len(lane_trades)
        wins = [t for t in lane_trades if (t.get('pnl') or 0) > 0]
        losses = [t for t in lane_trades if (t.get('pnl') or 0) < 0]
        breakeven = [t for t in lane_trades if (t.get('pnl') or 0) == 0]
        
        # Win/Loss counts
        win_count = len(wins)
        loss_count = len(losses)
        
        # Win rate
        win_rate = (win_count / total * 100) if total > 0 else 0
        
        # Gross profit/loss
        gross_profit = sum(t.get('pnl', 0) for t in wins)
        gross_loss = abs(sum(t.get('pnl', 0) for t in losses))
        
        # Net PnL
        net_pnl = gross_profit - gross_loss
        
        # Profit Factor (key health indicator)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        # Average win/loss
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        
        # Reward-to-Risk Ratio
        rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else float('inf') if avg_win > 0 else 0
        
        # Expectancy: (Win% * Avg Win) - (Loss% * Avg Loss)
        loss_rate = (loss_count / total * 100) if total > 0 else 0
        expectancy = ((win_rate / 100) * avg_win) - ((loss_rate / 100) * avg_loss)
        
        # Holding time calculation
        holding_times = []
        for t in lane_trades:
            entry_time = parse_datetime(t.get('entry_time') or t.get('timestamp'))
            exit_time = parse_datetime(t.get('timestamp'))
            if entry_time and exit_time and exit_time > entry_time:
                delta = (exit_time - entry_time).total_seconds()
                holding_times.append(delta)
        
        avg_holding_seconds = (sum(holding_times) / len(holding_times)) if holding_times else 0
        
        # Volume calculation for fee simulation
        total_volume = sum(
            (t.get('size') or t.get('amount') or 0) * (t.get('price') or t.get('entry_price') or 0)
            for t in lane_trades
        )
        
        # Fee simulation (0.05% per trade on volume)
        estimated_fees = total_volume * FEE_RATE * 2  # Entry + Exit
        net_pnl_after_fees = net_pnl - estimated_fees
        
        # Fee drag percentage
        fee_drag_pct = (estimated_fees / gross_profit * 100) if gross_profit > 0 else 0
        
        # Largest win/loss
        largest_win = max((t.get('pnl', 0) for t in wins), default=0)
        largest_loss = min((t.get('pnl', 0) for t in losses), default=0)
        
        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = calculate_streaks(lane_trades)
        
        results[lane] = {
            'total_trades': total,
            'wins': win_count,
            'losses': loss_count,
            'breakeven': len(breakeven),
            'win_rate': win_rate,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'net_pnl': net_pnl,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'rr_ratio': rr_ratio,
            'expectancy': expectancy,
            'avg_holding_seconds': avg_holding_seconds,
            'total_volume': total_volume,
            'estimated_fees': estimated_fees,
            'net_pnl_after_fees': net_pnl_after_fees,
            'fee_drag_pct': fee_drag_pct,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'max_consec_wins': max_consec_wins,
            'max_consec_losses': max_consec_losses,
        }
    
    return results


def calculate_streaks(trades: List[Dict]) -> Tuple[int, int]:
    """Calculate max consecutive wins and losses."""
    if not trades:
        return 0, 0
    
    # Sort by timestamp
    sorted_trades = sorted(trades, key=lambda t: t.get('timestamp', ''))
    
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    
    for t in sorted_trades:
        pnl = t.get('pnl', 0)
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
        else:
            # Breakeven resets both
            current_wins = 0
            current_losses = 0
    
    return max_wins, max_losses


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


def format_currency(value: float, show_sign: bool = False) -> str:
    """Format currency with optional sign."""
    if show_sign:
        sign = '+' if value >= 0 else ''
        return f"{sign}${value:,.2f}"
    return f"${abs(value):,.2f}"


def get_verdict(profit_factor: float) -> Tuple[str, str]:
    """Get verdict based on profit factor."""
    if profit_factor == float('inf'):
        return "✅ PASS", "No losses recorded"
    elif profit_factor >= PROFIT_FACTOR_PASS:
        return "✅ PASS", "Healthy profit factor"
    elif profit_factor >= PROFIT_FACTOR_WARNING:
        return "⚠️ WARNING", "Marginal - needs improvement"
    else:
        return "❌ FAIL", "Losing strategy - investigate immediately"


# =============================================================================
# REPORT GENERATION
# =============================================================================

def print_header():
    """Print report header."""
    print("\n" + "=" * 100)
    print("                    APEX TRADER - STRATEGY FORENSICS REPORT")
    print("=" * 100)
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Fee Rate Assumption: {FEE_RATE * 100:.2f}% per trade (maker fee)")
    print("=" * 100)


def print_summary_table(metrics: Dict[str, Dict]):
    """Print the main summary table."""
    print("\n📊 LANE PERFORMANCE SUMMARY")
    print("-" * 100)
    
    # Header
    header = f"{'LANE':<8} | {'TRADES':>7} | {'WIN%':>6} | {'P/F':>6} | {'AVG WIN':>10} | {'AVG LOSS':>10} | {'R:R':>6} | {'EXP ($)':>10} | {'DURATION':>10}"
    print(header)
    print("-" * 100)
    
    # Data rows
    for lane in LANE_ORDER:
        if lane not in metrics:
            continue
        m = metrics[lane]
        
        # Format profit factor
        pf = m['profit_factor']
        pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
        
        # Format R:R
        rr = m['rr_ratio']
        rr_str = f"{rr:.1f}" if rr != float('inf') else "∞"
        
        row = (
            f"{lane:<8} | "
            f"{m['total_trades']:>7} | "
            f"{m['win_rate']:>5.1f}% | "
            f"{pf_str:>6} | "
            f"${m['avg_win']:>8.2f} | "
            f"${m['avg_loss']:>8.2f} | "
            f"{rr_str:>6} | "
            f"{format_currency(m['expectancy'], show_sign=True):>10} | "
            f"{format_duration(m['avg_holding_seconds']):>10}"
        )
        print(row)
    
    print("-" * 100)


def print_pnl_breakdown(metrics: Dict[str, Dict]):
    """Print PnL breakdown with fee analysis."""
    print("\n💰 P&L BREAKDOWN (Fee Analysis)")
    print("-" * 100)
    
    header = f"{'LANE':<8} | {'GROSS PROFIT':>14} | {'GROSS LOSS':>14} | {'NET PnL':>14} | {'EST. FEES':>12} | {'NET AFTER FEES':>14} | {'FEE DRAG':>10}"
    print(header)
    print("-" * 100)
    
    for lane in LANE_ORDER:
        if lane not in metrics:
            continue
        m = metrics[lane]
        
        row = (
            f"{lane:<8} | "
            f"${m['gross_profit']:>13,.2f} | "
            f"${m['gross_loss']:>13,.2f} | "
            f"{format_currency(m['net_pnl'], show_sign=True):>14} | "
            f"${m['estimated_fees']:>11,.2f} | "
            f"{format_currency(m['net_pnl_after_fees'], show_sign=True):>14} | "
            f"{m['fee_drag_pct']:>8.1f}%"
        )
        print(row)
    
    print("-" * 100)


def print_risk_metrics(metrics: Dict[str, Dict]):
    """Print detailed risk metrics."""
    print("\n📈 RISK METRICS")
    print("-" * 100)
    
    header = f"{'LANE':<8} | {'LARGEST WIN':>12} | {'LARGEST LOSS':>12} | {'MAX WIN STREAK':>14} | {'MAX LOSS STREAK':>15} | {'VOLUME':>14}"
    print(header)
    print("-" * 100)
    
    for lane in LANE_ORDER:
        if lane not in metrics:
            continue
        m = metrics[lane]
        
        row = (
            f"{lane:<8} | "
            f"${m['largest_win']:>11,.2f} | "
            f"${abs(m['largest_loss']):>11,.2f} | "
            f"{m['max_consec_wins']:>14} | "
            f"{m['max_consec_losses']:>15} | "
            f"${m['total_volume']:>13,.0f}"
        )
        print(row)
    
    print("-" * 100)


def print_verdicts(metrics: Dict[str, Dict]):
    """Print verdicts for each lane."""
    print("\n🔍 DIAGNOSTIC VERDICTS")
    print("-" * 100)
    
    for lane in LANE_ORDER:
        if lane not in metrics:
            continue
        m = metrics[lane]
        
        verdict, reason = get_verdict(m['profit_factor'])
        
        print(f"\n  {lane} LANE:")
        print(f"    Status: {verdict}")
        print(f"    Reason: {reason}")
        print(f"    Profit Factor: {m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "    Profit Factor: ∞ (no losses)")
        
        # Additional diagnostics
        if m['profit_factor'] < 1.0:
            # Failing - diagnose why
            if m['fee_drag_pct'] > 50:
                print(f"    ⚠️  Fee drag is {m['fee_drag_pct']:.1f}% of gross profit - FEES ARE THE KILLER")
            if m['win_rate'] < 30:
                print(f"    ⚠️  Win rate only {m['win_rate']:.1f}% - SIGNAL QUALITY ISSUE")
            if m['rr_ratio'] < 1.0:
                print(f"    ⚠️  R:R ratio {m['rr_ratio']:.2f} - CUTTING WINNERS, HOLDING LOSERS")
            if m['avg_holding_seconds'] < 60:
                print(f"    ⚠️  Avg hold time {format_duration(m['avg_holding_seconds'])} - POSSIBLY OVERTRADING")
        elif m['profit_factor'] >= PROFIT_FACTOR_PASS:
            # Passing - highlight strengths
            if m['expectancy'] > 0:
                print(f"    ✓  Positive expectancy: {format_currency(m['expectancy'], show_sign=True)} per trade")
            if m['rr_ratio'] > 2.0:
                print(f"    ✓  Strong R:R ratio: {m['rr_ratio']:.1f}")


def print_recommendations(metrics: Dict[str, Dict]):
    """Print actionable recommendations."""
    print("\n")
    print("=" * 100)
    print("                           RECOMMENDATIONS")
    print("=" * 100)
    
    recommendations = []
    
    # Analyze each lane
    for lane in LANE_ORDER:
        if lane not in metrics:
            continue
        m = metrics[lane]
        
        if lane == 'HFT' and m['profit_factor'] < 1.0:
            if m['fee_drag_pct'] > 30:
                recommendations.append(f"🔧 HFT: Consider maker-only orders or negotiating lower fees (current drag: {m['fee_drag_pct']:.1f}%)")
            if m['win_rate'] < 40:
                recommendations.append(f"🔧 HFT: Signal quality needs work - current win rate {m['win_rate']:.1f}% is too low for scalping")
            if m['avg_holding_seconds'] < 30:
                recommendations.append(f"🔧 HFT: Extremely short holds ({format_duration(m['avg_holding_seconds'])}) - consider minimum hold time filter")
        
        if lane == 'ALPHA':
            if m['win_rate'] < 20 and m['profit_factor'] > 1.0:
                recommendations.append(f"💡 ALPHA: Low win rate ({m['win_rate']:.1f}%) but profitable - this is valid if R:R is high ({m['rr_ratio']:.1f})")
            if m['max_consec_losses'] > 10:
                recommendations.append(f"⚠️ ALPHA: Max losing streak of {m['max_consec_losses']} - ensure position sizing can handle drawdowns")
        
        if lane == 'GAMMA':
            if m['total_trades'] < 20:
                recommendations.append(f"📊 GAMMA: Small sample size ({m['total_trades']} trades) - metrics may not be statistically significant")
            if m['win_rate'] < 20 and m['largest_win'] < m['gross_loss']:
                recommendations.append(f"🔧 GAMMA: Moonshots not paying off - largest win (${m['largest_win']:.2f}) doesn't cover losses")
    
    if not recommendations:
        recommendations.append("✅ All lanes appear healthy. Continue monitoring.")
    
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
    
    print("\n" + "=" * 100)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_forensics():
    """Main function to run the forensics report."""
    print_header()
    
    print("\n📂 Connecting to database...")
    db = get_db()
    
    print("📥 Fetching trades...")
    trades = fetch_all_trades(db)
    print(f"   Found {len(trades)} exit trades")
    
    if not trades:
        print("\n❌ No trades found in database. Run some trades first!")
        return
    
    print("🔬 Calculating metrics...")
    metrics = calculate_lane_metrics(trades)
    
    # Print reports
    print_summary_table(metrics)
    print_pnl_breakdown(metrics)
    print_risk_metrics(metrics)
    print_verdicts(metrics)
    print_recommendations(metrics)
    
    # Final summary
    total_pnl = sum(m['net_pnl'] for m in metrics.values())
    total_trades = sum(m['total_trades'] for m in metrics.values())
    
    print(f"\n📌 TOTAL: {total_trades} trades, Net P&L: {format_currency(total_pnl, show_sign=True)}")
    print("=" * 100)


if __name__ == "__main__":
    run_forensics()
