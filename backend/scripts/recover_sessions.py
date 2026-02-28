"""
Recovery Script: Fix Orphaned Paper Trading Sessions
This script finds all sessions with status='running' and:
1. Updates their status to 'interrupted'
2. Calculates their trade statistics from paper_trades collection
3. Populates the RL replay buffer from historical closed trades
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import sys
sys.path.insert(0, '/app/backend')
from config import config


async def recover_sessions():
    client = AsyncIOMotorClient(config.MONGO_URL)
    db = client[config.DB_NAME]
    
    print("=" * 60)
    print("Paper Trading Session Recovery Script")
    print("=" * 60)
    
    # 1. Find all orphaned sessions (status=running without recent activity)
    orphaned_sessions = await db.paper_trading_sessions.find({
        "status": "running"
    }).to_list(None)
    
    print(f"\nFound {len(orphaned_sessions)} orphaned sessions with status='running'")
    
    recovered_count = 0
    total_trades_recovered = 0
    
    for session in orphaned_sessions:
        session_id = session.get('session_id')
        
        # Get trades for this session
        trades = await db.paper_trades.find({
            "session_id": session_id,
            "type": "exit"  # Only closed trades
        }).to_list(None)
        
        if not trades:
            # Update status but no trades to recover
            await db.paper_trading_sessions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "status": "interrupted",
                    "end_time": datetime.now(timezone.utc).isoformat(),
                    "recovery_note": "Session interrupted - no trades found"
                }}
            )
            continue
        
        # Calculate statistics from trades
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.get('pnl', 0) > 0)
        win_rate = winning_trades / max(total_trades, 1)
        
        # Get strategy and asset class breakdowns
        strategy_stats = {}
        asset_class_stats = {}
        
        for trade in trades:
            strategy = trade.get('strategy', 'unknown')
            asset_class = trade.get('asset_class', 'unknown')
            pnl = trade.get('pnl', 0)
            
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'pnl': 0, 'trades': 0, 'wins': 0}
            strategy_stats[strategy]['pnl'] += pnl
            strategy_stats[strategy]['trades'] += 1
            if pnl > 0:
                strategy_stats[strategy]['wins'] += 1
            
            if asset_class not in asset_class_stats:
                asset_class_stats[asset_class] = {'pnl': 0, 'trades': 0, 'wins': 0}
            asset_class_stats[asset_class]['pnl'] += pnl
            asset_class_stats[asset_class]['trades'] += 1
            if pnl > 0:
                asset_class_stats[asset_class]['wins'] += 1
        
        # Build closed_trades list (last 100)
        closed_trades = [{
            "market_id": t.get('market_id'),
            "entry_price": t.get('entry_price'),
            "exit_price": t.get('exit_price'),
            "pnl": t.get('pnl'),
            "pnl_pct": t.get('pnl_pct'),
            "exit_reason": t.get('exit_reason'),
            "reward_signal": t.get('reward_signal', 0),
            "strategy": t.get('strategy'),
            "asset_class": t.get('asset_class')
        } for t in trades[-100:]]
        
        # Calculate duration from first to last trade timestamp
        if trades:
            trade_timestamps = [t.get('timestamp') for t in trades if t.get('timestamp')]
            if trade_timestamps:
                first_trade = min(trade_timestamps)
                last_trade = max(trade_timestamps)
                try:
                    if isinstance(first_trade, str):
                        first_dt = datetime.fromisoformat(first_trade.replace('Z', '+00:00'))
                        last_dt = datetime.fromisoformat(last_trade.replace('Z', '+00:00'))
                    else:
                        first_dt = first_trade
                        last_dt = last_trade
                    duration_seconds = int((last_dt - first_dt).total_seconds())
                except:
                    duration_seconds = 0
            else:
                duration_seconds = 0
        else:
            duration_seconds = 0
        
        # Update session with recovered data
        initial_capital = session.get('initial_capital', 10000)
        deployed_capital = initial_capital * 0.8  # Default 80%
        
        await db.paper_trading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "status": "recovered",
                "end_time": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration_seconds,
                "total_pnl": total_pnl,
                "total_pnl_pct": (total_pnl / deployed_capital) * 100 if deployed_capital > 0 else 0,
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "win_rate": win_rate,
                "strategy_stats": strategy_stats,
                "asset_class_stats": asset_class_stats,
                "closed_trades": closed_trades,
                "recovery_note": f"Session recovered - {total_trades} trades found"
            }}
        )
        
        recovered_count += 1
        total_trades_recovered += total_trades
        
        print(f"  ✓ Session {session_id[:8]}...: {total_trades} trades, ${total_pnl:.2f} P&L, {win_rate:.1%} WR")
    
    print(f"\n{'=' * 60}")
    print("Recovery Complete!")
    print(f"  Sessions recovered: {recovered_count}")
    print(f"  Total trades recovered: {total_trades_recovered}")
    print(f"{'=' * 60}")
    
    # 2. Pre-populate RL replay buffer from recent trades
    print("\n" + "=" * 60)
    print("Pre-populating RL Replay Buffer from Historical Trades")
    print("=" * 60)
    
    # Get recent trades with reward signals
    recent_trades = await db.paper_trades.find({
        "type": "exit",
        "reward_signal": {"$exists": True}
    }).sort("timestamp", -1).limit(1000).to_list(1000)
    
    print(f"\nFound {len(recent_trades)} trades with reward signals")
    
    # Store experiences in rl_experiences collection for batch loading
    if recent_trades:
        experiences = []
        for trade in recent_trades:
            # Build synthetic state from trade data
            experience = {
                "market_id": trade.get('market_id'),
                "state": [
                    trade.get('entry_price', 0.5),  # price
                    0.1,  # volatility estimate
                    0.5,  # sentiment
                    0.5,  # sharp_alignment
                    0.5,  # liquidity normalized
                    0.5,  # volume normalized
                    0.7,  # time_to_expiry
                    0.3   # portfolio_exposure
                ],
                "action_idx": 2 if trade.get('pnl', 0) > 0 else 0,  # BUY_MEDIUM or WAIT
                "reward": trade.get('reward_signal', 0),
                "timestamp": trade.get('timestamp'),
                "pnl": trade.get('pnl', 0),
                "pnl_pct": trade.get('pnl_pct', 0)
            }
            experiences.append(experience)
        
        # Store in DB for RL engine to load
        await db.rl_historical_experiences.delete_many({})  # Clear old
        await db.rl_historical_experiences.insert_many(experiences)
        
        print(f"  ✓ Stored {len(experiences)} experiences for RL pre-population")
        
        # Calculate stats
        positive_rewards = sum(1 for e in experiences if e['reward'] > 0)
        avg_reward = sum(e['reward'] for e in experiences) / max(len(experiences), 1)
        print(f"  Positive rewards: {positive_rewards}/{len(experiences)} ({positive_rewards/max(len(experiences),1):.1%})")
        print(f"  Average reward: {avg_reward:.4f}")
    
    client.close()
    print("\n✅ Recovery script complete!")


if __name__ == "__main__":
    asyncio.run(recover_sessions())
