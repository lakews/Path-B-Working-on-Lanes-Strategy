#!/usr/bin/env python3
"""
Lane Data Seeding Script
========================
Injects mock trades into the database to validate Lane Analytics UI.

This script creates:
- 50 HFT trades (high volume, small wins/losses, 66% win rate)
- 15 ALPHA trades (medium trades, balanced wins/losses)
- 5 GAMMA trades (moonshots, including one big winner)

Run: python scripts/seed_lane_data.py
Then refresh the dashboard to see the Lane Performance cards light up!

Author: APEX TRADER QA
Date: January 2026
"""

import sys
import os
import uuid
import random
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient
from config import config


def get_sync_db():
    """Get synchronous database connection."""
    client = MongoClient(config.MONGO_URL)
    return client[config.DB_NAME]


def generate_trade(
    strategy: str,
    strategy_lane: str,
    side: str,
    size: float,
    entry_price: float,
    exit_price: float,
    pnl: float,
    entry_time: datetime,
    exit_time: datetime,
    market_id: str = None,
    asset_class: str = "finance"
):
    """Generate a trade document matching paper_trader schema."""
    return {
        "trade_id": str(uuid.uuid4()),
        "session_id": "seed_session_001",
        "type": "exit",
        "market_id": market_id or f"seed_market_{uuid.uuid4().hex[:8]}",
        "market_question": f"Seeded {strategy_lane} Trade",
        "side": side,
        "size": size,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "price": exit_price,
        "yes_entry_price": entry_price,
        "yes_exit_price": exit_price,
        "pnl": round(pnl, 2),
        "pnl_pct": round((pnl / (size * entry_price)) * 100, 2) if size * entry_price > 0 else 0,
        "hold_time_seconds": int((exit_time - entry_time).total_seconds()),
        "strategy": strategy,
        "strategy_lane": strategy_lane,
        "asset_class": asset_class,
        "exit_reason": "take_profit" if pnl > 0 else "stop_loss",
        "reward_signal": 1 if pnl > 0 else -1,
        "timestamp": exit_time.isoformat(),
        "entry_time": entry_time.isoformat(),
        "seeded": True  # Mark as seeded data
    }


def seed_hft_trades(count: int = 50) -> list:
    """Generate HFT trades - high volume, small PnL, fast execution."""
    print(f"   -> Generating {count} HFT trades (scalping)...")
    trades = []
    
    for i in range(count):
        # 66% win rate
        is_win = random.random() < 0.66
        
        # Small position sizes
        size = random.uniform(50, 200)
        entry_price = random.uniform(0.40, 0.60)
        
        # Small price movements
        if is_win:
            exit_price = entry_price + random.uniform(0.01, 0.03)
            pnl = size * (exit_price - entry_price)
        else:
            exit_price = entry_price - random.uniform(0.01, 0.02)
            pnl = size * (exit_price - entry_price)
        
        # Fast execution (seconds to minutes)
        entry_time = datetime.now(timezone.utc) - timedelta(minutes=count - i)
        exit_time = entry_time + timedelta(seconds=random.randint(10, 300))
        
        trades.append(generate_trade(
            strategy="arbitrage",
            strategy_lane="HFT",
            side="YES" if random.random() > 0.5 else "NO",
            size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            entry_time=entry_time,
            exit_time=exit_time,
            asset_class="crypto"
        ))
    
    return trades


def seed_alpha_trades(count: int = 15) -> list:
    """Generate ALPHA trades - directional bets, medium hold times."""
    print(f"   -> Generating {count} ALPHA trades (directional)...")
    trades = []
    
    for i in range(count):
        # 55% win rate (slight edge)
        is_win = random.random() < 0.55
        
        # Medium position sizes
        size = random.uniform(100, 500)
        entry_price = random.uniform(0.30, 0.70)
        
        # Medium price movements
        if is_win:
            exit_price = entry_price + random.uniform(0.05, 0.15)
            pnl = size * (exit_price - entry_price)
        else:
            exit_price = entry_price - random.uniform(0.03, 0.10)
            pnl = size * (exit_price - entry_price)
        
        # Hours to days hold time
        entry_time = datetime.now(timezone.utc) - timedelta(hours=count * 2 - i * 2)
        exit_time = entry_time + timedelta(hours=random.randint(1, 24))
        
        trades.append(generate_trade(
            strategy="alpha_directional",
            strategy_lane="ALPHA",
            side="YES",
            size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            entry_time=entry_time,
            exit_time=exit_time,
            asset_class=random.choice(["politics", "sports", "finance"])
        ))
    
    return trades


def seed_gamma_trades(count: int = 5) -> list:
    """Generate GAMMA trades - moonshots, extreme prices, big wins/losses."""
    print(f"   -> Generating {count} GAMMA trades (moonshots)...")
    trades = []
    
    # One guaranteed big winner
    trades.append(generate_trade(
        strategy="gamma_scalp",
        strategy_lane="GAMMA",
        side="YES",
        size=500,
        entry_price=0.03,  # Bought at $0.03
        exit_price=0.25,   # Sold at $0.25 - 8x!
        pnl=500 * (0.25 - 0.03),  # $110 profit
        entry_time=datetime.now(timezone.utc) - timedelta(days=2),
        exit_time=datetime.now(timezone.utc) - timedelta(hours=12),
        asset_class="politics"
    ))
    
    # Mix of smaller gamma plays
    for i in range(count - 1):
        is_win = random.random() < 0.40  # 40% win rate (high risk)
        
        # Small entries at extreme prices
        size = random.uniform(50, 200)
        entry_price = random.uniform(0.02, 0.08)  # Whale zone
        
        if is_win:
            # Big multiplier on wins
            exit_price = entry_price * random.uniform(2, 5)
            pnl = size * (exit_price - entry_price)
        else:
            # Lose most of position
            exit_price = entry_price * random.uniform(0.3, 0.7)
            pnl = size * (exit_price - entry_price)
        
        entry_time = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 7))
        exit_time = entry_time + timedelta(hours=random.randint(12, 72))
        
        trades.append(generate_trade(
            strategy="volatility_exploitation",
            strategy_lane="GAMMA",
            side="YES",
            size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            entry_time=entry_time,
            exit_time=exit_time,
            asset_class="sports"
        ))
    
    return trades


def seed_database():
    """Main seeding function."""
    print("\n🌱 APEX TRADER - Lane Data Seeder")
    print("=" * 50)
    
    db = get_sync_db()
    
    # Generate trades for each lane
    hft_trades = seed_hft_trades(50)
    alpha_trades = seed_alpha_trades(15)
    gamma_trades = seed_gamma_trades(5)
    
    all_trades = hft_trades + alpha_trades + gamma_trades
    
    # Calculate summary before insert
    print("\n📊 Trade Summary:")
    for lane in ["HFT", "ALPHA", "GAMMA"]:
        lane_trades = [t for t in all_trades if t["strategy_lane"] == lane]
        total_pnl = sum(t["pnl"] for t in lane_trades)
        wins = len([t for t in lane_trades if t["pnl"] > 0])
        print(f"   {lane}: {len(lane_trades)} trades, ${total_pnl:.2f} PnL, {wins}/{len(lane_trades)} wins")
    
    # Clear previous seeded data
    print("\n🗑️  Clearing previous seeded data...")
    result = db.paper_trades.delete_many({"seeded": True})
    print(f"   Deleted {result.deleted_count} old seeded trades")
    
    # Insert new trades
    print("\n💾 Inserting new trades...")
    result = db.paper_trades.insert_many(all_trades)
    print(f"   Inserted {len(result.inserted_ids)} trades")
    
    # Verify insertion
    hft_count = db.paper_trades.count_documents({"strategy_lane": "HFT", "seeded": True})
    alpha_count = db.paper_trades.count_documents({"strategy_lane": "ALPHA", "seeded": True})
    gamma_count = db.paper_trades.count_documents({"strategy_lane": "GAMMA", "seeded": True})
    
    print("\n✅ Database Seeding Complete!")
    print("=" * 50)
    print(f"   HFT:   {hft_count} trades (Cyan)")
    print(f"   ALPHA: {alpha_count} trades (Amber)")
    print(f"   GAMMA: {gamma_count} trades (Purple)")
    print("\n🚀 REFRESH YOUR DASHBOARD NOW!")
    print("   URL: http://localhost:3000/paper")
    print("=" * 50)
    
    return {
        "hft": hft_count,
        "alpha": alpha_count,
        "gamma": gamma_count,
        "total": hft_count + alpha_count + gamma_count
    }


if __name__ == "__main__":
    seed_database()
