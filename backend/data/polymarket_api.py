import aiohttp
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

class PolymarketAPI:
    """REST API client for Polymarket"""
    
    def __init__(self):
        self.base_url = "https://clob.polymarket.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "Content-Type": "application/json",
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_markets(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch active markets"""
        try:
            url = f"{self.base_url}/markets"
            params = {"limit": limit, "offset": offset, "active": "true"}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Handle both list and dict response formats
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return data.get('data', data.get('markets', []))
                    return []
                else:
                    logger.error(f"Failed to fetch markets: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    async def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """Fetch specific market details"""
        try:
            url = f"{self.base_url}/markets/{condition_id}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to fetch market {condition_id}: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching market: {e}")
            return None
    
    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """Fetch order book for a token"""
        try:
            url = f"{self.base_url}/book"
            params = {"token_id": token_id}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to fetch order book: {response.status}")
                    return {"bids": [], "asks": []}
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return {"bids": [], "asks": []}
    
    async def get_trades(self, market_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent trades for a market"""
        try:
            url = f"{self.base_url}/trades"
            params = {"market": market_id, "limit": limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data if isinstance(data, list) else []
                else:
                    logger.error(f"Failed to fetch trades: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []