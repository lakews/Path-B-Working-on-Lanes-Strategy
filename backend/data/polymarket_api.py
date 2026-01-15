import aiohttp
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

class PolymarketAPI:
    """REST API client for Polymarket"""
    
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.base_url = self.clob_url  # Backwards compatibility
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
        """Fetch active markets from Gamma API (live data)"""
        try:
            # Use Gamma API for live market data
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
                    
                    # Normalize market data for consistency
                    normalized = []
                    for m in markets:
                        # Parse clobTokenIds
                        token_ids = m.get('clobTokenIds', [])
                        if isinstance(token_ids, str):
                            try:
                                token_ids = json.loads(token_ids)
                            except:
                                token_ids = []
                        
                        # Calculate yes_price from outcomePrices
                        outcome_prices = m.get('outcomePrices', '[]')
                        if isinstance(outcome_prices, str):
                            try:
                                outcome_prices = json.loads(outcome_prices)
                            except:
                                outcome_prices = []
                        
                        yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
                        
                        normalized.append({
                            'id': m.get('conditionId') or m.get('id'),
                            'condition_id': m.get('conditionId'),
                            'question': m.get('question', ''),
                            'description': m.get('description', ''),
                            'yes_price': yes_price,
                            'no_price': 1 - yes_price,
                            'volume': float(m.get('volume', 0) or 0),
                            'volume_24h': float(m.get('volume24hr', 0) or 0),
                            'liquidity': float(m.get('liquidityNum', 0) or 0),
                            'end_date': m.get('endDate'),
                            'active': not m.get('closed', False),
                            'category': self._categorize_market(m.get('question', '')),
                            'asset_class': self._categorize_market(m.get('question', '')),
                            'tokens': token_ids,
                            'clobTokenIds': token_ids,
                            'outcomes': m.get('outcomes', ['Yes', 'No']),
                            'spread': m.get('spread', 0.02),
                            'outstanding_contracts': float(m.get('liquidityNum', 0) or 0),
                        })
                    
                    logger.info(f"Fetched {len(normalized)} live markets from Gamma API")
                    return normalized
                else:
                    logger.error(f"Failed to fetch markets from Gamma: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    def _categorize_market(self, question: str) -> str:
        """Categorize market by question content"""
        question_lower = question.lower()
        if any(w in question_lower for w in ['bitcoin', 'crypto', 'ethereum', 'btc', 'eth', 'solana']):
            return 'crypto'
        elif any(w in question_lower for w in ['trump', 'biden', 'election', 'congress', 'senate', 'vote', 'president']):
            return 'politics'
        elif any(w in question_lower for w in ['fed', 'rate', 'inflation', 'gdp', 'stock', 'market', 's&p']):
            return 'finance'
        elif any(w in question_lower for w in ['nba', 'nfl', 'mlb', 'ncaa', 'game', 'match', 'win']):
            return 'sports'
        elif any(w in question_lower for w in ['spacex', 'nasa', 'ai', 'openai', 'science', 'research']):
            return 'science'
        else:
            return 'entertainment'
    
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
    
    async def get_markets_with_tokens(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch markets from Gamma API with CLOB token IDs for price history"""
        try:
            url = f"{self.gamma_url}/markets"
            params = {"limit": limit, "closed": "false", "order": "volume24hr", "ascending": "false"}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data if isinstance(data, list) else []
                    
                    # Parse clobTokenIds if it's a JSON string
                    for market in markets:
                        token_ids = market.get('clobTokenIds', [])
                        if isinstance(token_ids, str):
                            try:
                                market['clobTokenIds'] = json.loads(token_ids)
                            except json.JSONDecodeError:
                                market['clobTokenIds'] = []
                    
                    return markets
                else:
                    logger.error(f"Failed to fetch markets from Gamma: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching markets from Gamma: {e}")
            return []
    
    async def get_price_history(self, token_id: str, interval: str = "1w", fidelity: int = 60) -> List[Dict[str, Any]]:
        """
        Fetch price history for a specific token.
        
        Args:
            token_id: The CLOB token ID
            interval: Time interval - "1h", "6h", "1d", "1w", "max"
            fidelity: Resolution in minutes (minimum depends on interval, e.g., 5 for 1w)
        
        Returns:
            List of {t: timestamp, p: price} dicts
        """
        try:
            # Adjust fidelity based on interval to meet API requirements
            min_fidelity = {"1h": 1, "6h": 1, "1d": 1, "1w": 5, "max": 60}
            fidelity = max(fidelity, min_fidelity.get(interval, 60))
            
            url = f"{self.clob_url}/prices-history"
            params = {"market": token_id, "interval": interval, "fidelity": fidelity}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    history = data.get('history', [])
                    return history
                else:
                    error_text = await response.text()
                    logger.debug(f"Price history request failed for {token_id[:20]}...: {response.status} - {error_text[:100]}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching price history: {e}")
            return []
    
    async def get_market_price_history_batch(self, markets: List[Dict], interval: str = "1w", fidelity: int = 60) -> Dict[str, List[Dict]]:
        """
        Fetch price history for multiple markets' tokens.
        
        Returns:
            Dict mapping market condition_id to list of price history points
        """
        result = {}
        
        for market in markets:
            condition_id = market.get('conditionId') or market.get('condition_id')
            token_ids = market.get('clobTokenIds', [])
            
            if not condition_id or not token_ids:
                continue
            
            # Get price history for YES token (first token)
            if len(token_ids) > 0:
                yes_token_id = token_ids[0]
                history = await self.get_price_history(yes_token_id, interval, fidelity)
                
                if history:
                    result[condition_id] = {
                        "question": market.get('question', ''),
                        "history": history,
                        "token_id": yes_token_id,
                        "outcomes": market.get('outcomes', ['Yes', 'No']),
                        "volume24hr": market.get('volume24hr', 0),
                        "liquidity": market.get('liquidityNum', 0)
                    }
        
        return result