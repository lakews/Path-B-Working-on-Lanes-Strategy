import aiohttp
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

class PolymarketAPI:
    """REST API client for Polymarket - Uses Gamma API for live data"""
    
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com"
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
        """Fetch LIVE active markets from Gamma API"""
        try:
            url = f"{self.gamma_url}/markets"
            params = {
                "limit": limit, 
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data if isinstance(data, list) else []
                    
                    # Normalize market data
                    normalized = []
                    for m in markets:
                        norm = self._normalize_gamma_market(m)
                        if norm:
                            normalized.append(norm)
                    
                    logger.info(f"Fetched {len(normalized)} LIVE markets from Gamma API")
                    return normalized
                else:
                    logger.error(f"Gamma API failed: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    def _normalize_gamma_market(self, m: Dict) -> Optional[Dict]:
        """Normalize Gamma API market to standard format"""
        try:
            # Parse clobTokenIds
            token_ids = m.get('clobTokenIds', [])
            if isinstance(token_ids, str):
                try:
                    token_ids = json.loads(token_ids)
                except:
                    token_ids = []
            
            # Parse outcomePrices for yes_price
            outcome_prices = m.get('outcomePrices', '[]')
            if isinstance(outcome_prices, str):
                try:
                    outcome_prices = json.loads(outcome_prices)
                except:
                    outcome_prices = []
            
            yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
            volume_24h = float(m.get('volume24hr', 0) or 0)
            liquidity = float(m.get('liquidityNum', 0) or 0)
            
            # Skip markets with no liquidity
            if liquidity < 100:
                return None
            
            return {
                'id': m.get('conditionId') or m.get('id'),
                'condition_id': m.get('conditionId'),
                'question': m.get('question', ''),
                'description': m.get('description', ''),
                'yes_price': yes_price,
                'no_price': 1 - yes_price,
                'volume': float(m.get('volume', 0) or 0),
                'volume_24h': volume_24h,
                'liquidity': liquidity,
                'end_date': m.get('endDate'),
                'active': not m.get('closed', False),
                'category': self._categorize_market(m.get('question', '')),
                'asset_class': self._categorize_market(m.get('question', '')),
                'tokens': token_ids,
                'clobTokenIds': token_ids,
                'outcomes': m.get('outcomes', ['Yes', 'No']),
                'spread': 0.02,
                'outstanding_contracts': liquidity,
            }
        except Exception as e:
            logger.debug(f"Error normalizing market: {e}")
            return None
    
    def _categorize_market(self, question: str) -> str:
        """Categorize market by question content"""
        q = question.lower()
        if any(w in q for w in ['bitcoin', 'crypto', 'ethereum', 'btc', 'eth', 'solana', 'doge']):
            return 'crypto'
        elif any(w in q for w in ['trump', 'biden', 'election', 'congress', 'senate', 'vote', 'president', 'governor', 'republican', 'democrat']):
            return 'politics'
        elif any(w in q for w in ['fed', 'rate', 'inflation', 'gdp', 'stock', 'market', 's&p', 'recession', 'tariff', 'interest']):
            return 'finance'
        elif any(w in q for w in ['nba', 'nfl', 'mlb', 'ncaa', 'game', 'match', 'championship', 'super bowl']):
            return 'sports'
        elif any(w in q for w in ['spacex', 'nasa', 'ai', 'openai', 'science', 'research', 'climate']):
            return 'science'
        else:
            return 'entertainment'
    
    async def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """Fetch specific market details from Gamma"""
        try:
            url = f"{self.gamma_url}/markets/{condition_id}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._normalize_gamma_market(data)
                return None
        except Exception as e:
            logger.error(f"Error fetching market: {e}")
            return None
    
    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """Fetch order book for a token from CLOB"""
        try:
            url = f"{self.clob_url}/book"
            params = {"token_id": token_id}
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return {"bids": [], "asks": []}
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return {"bids": [], "asks": []}
    
    async def get_trades(self, market_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent trades"""
        try:
            url = f"{self.clob_url}/trades"
            params = {"market": market_id, "limit": limit}
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data if isinstance(data, list) else []
                return []
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []
    
    async def get_markets_with_tokens(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch markets with token IDs - same as get_markets but explicit"""
        return await self.get_markets(limit=limit)
    
    async def get_price_history(self, token_id: str, interval: str = "1d", fidelity: int = 60) -> List[Dict[str, Any]]:
        """Fetch price history for a token"""
        try:
            min_fidelity = {"1h": 1, "6h": 1, "1d": 1, "1w": 5, "max": 60}
            fidelity = max(fidelity, min_fidelity.get(interval, 60))
            
            url = f"{self.clob_url}/prices-history"
            params = {"market": token_id, "interval": interval, "fidelity": fidelity}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('history', [])
                return []
        except Exception as e:
            logger.error(f"Error fetching price history: {e}")
            return []
