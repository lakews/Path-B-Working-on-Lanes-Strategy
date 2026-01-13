import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from database import get_db
from models import MarketCategory
import uuid

logger = logging.getLogger(__name__)

class SharpDetector:
    """Detects sharp traders using line movement analysis"""
    
    def __init__(self):
        self.db = get_db()
        self.sharp_threshold = 0.7
        self.min_trades = 10
        self.tracking_window = timedelta(days=7)
        
    async def identify_sharp_traders(self):
        """Identify sharp traders from recent activity"""
        try:
            recent_trades = await self._get_recent_trades()
            
            trader_stats = self._analyze_traders(recent_trades)
            
            for address, stats in trader_stats.items():
                if self._is_sharp_trader(stats):
                    await self._store_sharp_trader(address, stats)
            
            logger.info(f"Identified {len(trader_stats)} potential sharp traders")
            
        except Exception as e:
            logger.error(f"Error identifying sharp traders: {e}")
    
    async def get_sharp_alignment(self, market_id: str, proposed_side: str) -> float:
        """Get alignment score with sharp traders for a market
        Returns: score from 0 (against sharps) to 1 (with sharps)
        """
        try:
            sharp_positions = await self._get_sharp_positions(market_id)
            
            if not sharp_positions:
                return 0.5
            
            sharp_consensus = self._calculate_consensus(sharp_positions, proposed_side)
            
            return sharp_consensus
            
        except Exception as e:
            logger.error(f"Error getting sharp alignment: {e}")
            return 0.5
    
    def _analyze_traders(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Analyze trader performance metrics"""
        trader_data = {}
        
        for trade in trades:
            address = trade.get('trader_address', 'unknown')
            
            if address not in trader_data:
                trader_data[address] = {
                    'trades': [],
                    'total_volume': 0,
                    'positive_movements': 0,
                    'total_movements': 0,
                    'categories': set(),
                    'reaction_times': []
                }
            
            trader_data[address]['trades'].append(trade)
            trader_data[address]['total_volume'] += trade.get('volume', 0)
            trader_data[address]['categories'].add(trade.get('category', 'unknown'))
            
            line_movement = self._calculate_line_movement(trade)
            if line_movement > 0:
                trader_data[address]['positive_movements'] += 1
            trader_data[address]['total_movements'] += 1
        
        stats = {}
        for address, data in trader_data.items():
            if len(data['trades']) >= self.min_trades:
                stats[address] = {
                    'win_rate': data['positive_movements'] / data['total_movements'] if data['total_movements'] > 0 else 0,
                    'total_volume': data['total_volume'],
                    'num_trades': len(data['trades']),
                    'category_focus': max(data['categories'], key=lambda x: sum(1 for t in data['trades'] if t.get('category') == x)) if data['categories'] else 'unknown',
                    'category_concentration': len(data['categories'])
                }
        
        return stats
    
    def _calculate_line_movement(self, trade: Dict) -> float:
        """Calculate line movement PNL after trade"""
        entry_price = trade.get('price', 0.5)
        final_price = trade.get('final_price', entry_price)
        volume = trade.get('volume', 0)
        
        return (final_price - entry_price) * volume
    
    def _is_sharp_trader(self, stats: Dict) -> bool:
        """Determine if trader qualifies as sharp"""
        win_rate = stats.get('win_rate', 0)
        volume = stats.get('total_volume', 0)
        num_trades = stats.get('num_trades', 0)
        concentration = stats.get('category_concentration', 5)
        
        return (
            win_rate >= self.sharp_threshold and
            volume >= 100000 and
            num_trades >= self.min_trades and
            concentration <= 2
        )
    
    def _calculate_consensus(self, positions: List[Dict], proposed_side: str) -> float:
        """Calculate sharp trader consensus"""
        if not positions:
            return 0.5
        
        total_volume = sum(p.get('volume', 0) for p in positions)
        if total_volume == 0:
            return 0.5
        
        aligned_volume = sum(
            p.get('volume', 0) for p in positions 
            if p.get('side') == proposed_side
        )
        
        consensus = aligned_volume / total_volume
        return consensus
    
    async def _get_recent_trades(self) -> List[Dict]:
        """Get recent market trades"""
        try:
            cutoff = datetime.now(timezone.utc) - self.tracking_window
            
            cursor = self.db.market_trades.find(
                {"timestamp": {"$gte": cutoff.isoformat()}},
                {"_id": 0}
            ).limit(10000)
            
            return await cursor.to_list(length=10000)
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    async def _get_sharp_positions(self, market_id: str) -> List[Dict]:
        """Get sharp trader positions for a market"""
        try:
            sharp_traders = await self.db.sharp_traders.find({}, {"address": 1, "_id": 0}).to_list(length=100)
            addresses = [t['address'] for t in sharp_traders]
            
            cursor = self.db.positions.find(
                {
                    "market_id": market_id,
                    "trader_address": {"$in": addresses}
                },
                {"_id": 0}
            )
            
            return await cursor.to_list(length=100)
        except Exception as e:
            logger.error(f"Error getting sharp positions: {e}")
            return []
    
    async def _store_sharp_trader(self, address: str, stats: Dict):
        """Store sharp trader in database"""
        try:
            await self.db.sharp_traders.update_one(
                {"address": address},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "address": address,
                    "win_rate": stats['win_rate'],
                    "roi": stats['win_rate'] * 100,
                    "avg_line_movement": 0.05,
                    "total_volume": stats['total_volume'],
                    "category_focus": stats['category_focus'],
                    "identified_at": datetime.now(timezone.utc).isoformat(),
                    "last_activity": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error storing sharp trader: {e}")