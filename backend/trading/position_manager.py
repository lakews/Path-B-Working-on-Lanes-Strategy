import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from database import get_db
from config import config
from models import OrderSide, StrategyType
import uuid

logger = logging.getLogger(__name__)

class PositionManager:
    """Manages trading positions with Kelly Criterion sizing"""
    
    def __init__(self):
        self.db = get_db()
        self.max_position_size = config.MAX_POSITION_SIZE
        
    async def open_position(
        self,
        market_id: str,
        side: OrderSide,
        shares: float,
        price: float,
        strategy: StrategyType
    ) -> Optional[str]:
        """Open new position"""
        try:
            existing = await self.get_position(market_id)
            
            if existing:
                return await self._update_position(existing, shares, price, side)
            
            position = {
                "id": str(uuid.uuid4()),
                "market_id": market_id,
                "side": side,
                "shares": shares,
                "avg_price": price,
                "current_price": price,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "strategy": strategy,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.positions.insert_one(position)
            logger.info(f"Opened position: {position['id']}")
            
            return position['id']
            
        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None
    
    async def close_position(self, position_id: str, exit_price: float) -> float:
        """Close position and calculate PnL"""
        try:
            position = await self.db.positions.find_one({"id": position_id})
            
            if not position:
                return 0.0
            
            pnl = self._calculate_pnl(position, exit_price)
            
            await self.db.positions.delete_one({"id": position_id})
            
            await self.db.closed_positions.insert_one({
                **position,
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "exit_price": exit_price,
                "realized_pnl": pnl
            })
            
            logger.info(f"Closed position {position_id} with PnL: ${pnl:.2f}")
            
            return pnl
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return 0.0
    
    async def update_positions(self, market_prices: Dict[str, float]):
        """Update all positions with current prices"""
        try:
            positions = await self.get_all_positions()
            
            for position in positions:
                market_id = position['market_id']
                if market_id in market_prices:
                    current_price = market_prices[market_id]
                    unrealized_pnl = self._calculate_pnl(position, current_price)
                    
                    await self.db.positions.update_one(
                        {"id": position['id']},
                        {"$set": {
                            "current_price": current_price,
                            "unrealized_pnl": unrealized_pnl,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
            
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
    
    def _calculate_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate position PnL"""
        try:
            shares = position['shares']
            avg_price = position['avg_price']
            side = position['side']
            
            if side == OrderSide.BUY:
                pnl = (current_price - avg_price) * shares
            else:
                pnl = (avg_price - current_price) * shares
            
            return pnl
            
        except Exception as e:
            logger.error(f"Error calculating PnL: {e}")
            return 0.0
    
    async def get_position(self, market_id: str) -> Optional[Dict]:
        """Get position for market"""
        try:
            return await self.db.positions.find_one({"market_id": market_id})
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None
    
    async def get_all_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            cursor = self.db.positions.find({})
            return await cursor.to_list(length=1000)
        except Exception as e:
            logger.error(f"Error getting all positions: {e}")
            return []
    
    async def _update_position(
        self, 
        existing: Dict, 
        new_shares: float, 
        new_price: float,
        side: OrderSide
    ) -> str:
        """Update existing position"""
        try:
            if side == existing['side']:
                total_shares = existing['shares'] + new_shares
                avg_price = (
                    (existing['avg_price'] * existing['shares']) + 
                    (new_price * new_shares)
                ) / total_shares
                
                await self.db.positions.update_one(
                    {"id": existing['id']},
                    {"$set": {
                        "shares": total_shares,
                        "avg_price": avg_price,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            else:
                net_shares = existing['shares'] - new_shares
                if net_shares <= 0:
                    await self.close_position(existing['id'], new_price)
                else:
                    await self.db.positions.update_one(
                        {"id": existing['id']},
                        {"$set": {
                            "shares": net_shares,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
            
            return existing['id']
            
        except Exception as e:
            logger.error(f"Error updating position: {e}")
            return existing['id']