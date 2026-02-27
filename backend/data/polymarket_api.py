import aiohttp
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

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
            # EXPIRATION CHECK - Block expired markets at the source
            end_date_str = m.get('endDate')
            if end_date_str:
                try:
                    from dateutil.parser import parse
                    end_date = parse(end_date_str)
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    if end_date < datetime.now(timezone.utc):
                        logger.debug(f"[API] Expired market {m.get('conditionId', 'unknown')[:16]} (ended {end_date_str}) - skipping")
                        return None
                except Exception as e:
                    logger.debug(f"[API] Could not parse end_date for {m.get('conditionId', 'unknown')[:16]}: {e}")
            
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
            
            # STRICT PRICE VALIDATION - Return None if no valid price data
            if not outcome_prices or len(outcome_prices) == 0:
                logger.debug(f"[API] No outcomePrices for market {m.get('conditionId', 'unknown')[:16]} - skipping")
                return None
            
            yes_price = float(outcome_prices[0])
            if yes_price == 0:
                logger.debug(f"[API] Zero yes_price for market {m.get('conditionId', 'unknown')[:16]} - skipping")
                return None
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
                # Use Polymarket's authoritative category field (lowercase for consistency)
                'category': (m.get('category') or 'Other').lower(),
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
        """
        Categorize market by question content using TagLibraryService.
        
        This method uses the centralized TagLibraryService for accurate
        market classification, replacing the basic keyword matching.
        """
        try:
            from services.tag_library_service import get_tag_library_service
            tag_library = get_tag_library_service()
            result = tag_library.classify_market({'question': question})
            return result.category
        except Exception as e:
            # Fallback to basic keyword matching if TagLibraryService unavailable
            logger.debug(f"TagLibraryService unavailable in API categorization: {e}")
            q = question.lower()
            if any(w in q for w in ['bitcoin', 'crypto', 'ethereum', 'btc', 'eth', 'solana', 'doge']):
                return 'crypto'
            elif any(w in q for w in ['trump', 'biden', 'election', 'congress', 'senate', 'vote', 'president', 'governor', 'republican', 'democrat']):
                return 'politics'
            elif any(w in q for w in ['fed', 'rate', 'inflation', 'gdp', 'stock', 'market', 's&p', 'recession', 'tariff', 'interest']):
                return 'economics'
            elif any(w in q for w in ['nba', 'nfl', 'mlb', 'ncaa', 'game', 'match', 'championship', 'super bowl', 'la liga', 'premier league', 'uefa', 'lebron', 'messi', 'ronaldo']):
                return 'sports'
            elif any(w in q for w in ['spacex', 'nasa', 'ai', 'openai', 'science', 'research', 'climate']):
                return 'science-tech'
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
        """
        Fetch order book for a token from CLOB.
        
        CRITICAL FIX (Task 20): Polymarket CLOB returns orderbook with:
        - BIDS sorted ASCENDING (lowest first) - needs reversal
        - ASKS sorted DESCENDING (highest first) - needs reversal
        
        We normalize to standard format:
        - BIDS: sorted DESCENDING (best/highest bid first)
        - ASKS: sorted ASCENDING (best/lowest ask first)
        """
        try:
            url = f"{self.clob_url}/book"
            params = {"token_id": token_id}
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    raw_book = await response.json()
                    
                    # CRITICAL: Normalize orderbook sorting
                    bids = raw_book.get('bids', [])
                    asks = raw_book.get('asks', [])
                    
                    # Sort bids DESCENDING by price (highest bid first = best bid)
                    if bids:
                        bids = sorted(bids, key=lambda x: float(x['price']), reverse=True)
                    
                    # Sort asks ASCENDING by price (lowest ask first = best ask)
                    if asks:
                        asks = sorted(asks, key=lambda x: float(x['price']), reverse=False)
                    
                    # Return normalized book
                    raw_book['bids'] = bids
                    raw_book['asks'] = asks
                    
                    # Log if we found good liquidity
                    if bids and asks:
                        best_bid = float(bids[0]['price'])
                        best_ask = float(asks[0]['price'])
                        spread = best_ask - best_bid
                        if spread < 0.05:  # Less than 5% spread
                            logger.debug(f"[CLOB] Good liquidity: bid={best_bid:.4f} ask={best_ask:.4f} spread={spread:.2%}")
                    
                    return raw_book
                return {"bids": [], "asks": []}
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return {"bids": [], "asks": []}
    
    async def get_trades(self, token_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent trades for a token"""
        try:
            url = f"{self.clob_url}/trades"
            # Polymarket CLOB API uses 'asset_id' for token trades
            params = {"asset_id": token_id, "limit": limit}
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

    async def get_market_price_history_batch(self, markets: List[Dict], interval: str = "1w", fidelity: int = 60) -> Dict[str, Dict]:
        """
        Fetch price history for multiple markets in batch.
        
        Args:
            markets: List of market dictionaries with clobTokenIds
            interval: Time interval ("1h", "6h", "1d", "1w", "max")
            fidelity: Resolution in minutes
            
        Returns:
            Dict mapping condition_id to {history, question, token_id, ...}
        """
        results = {}
        
        for market in markets:
            condition_id = market.get('condition_id') or market.get('id')
            token_ids = market.get('clobTokenIds', market.get('tokens', []))
            
            if not token_ids or not condition_id:
                continue
            
            # Use the first token ID (YES token) for price history
            token_id = token_ids[0] if isinstance(token_ids, list) else token_ids
            
            try:
                history = await self.get_price_history(token_id, interval, fidelity)
                if history:
                    results[condition_id] = {
                        "history": history,
                        "question": market.get('question', ''),
                        "token_id": token_id,
                        "volume24hr": market.get('volume_24h', 0),
                        "liquidity": market.get('liquidity', 0)
                    }
            except Exception as e:
                logger.debug(f"Error fetching price history for {condition_id}: {e}")
        
        logger.info(f"Fetched price history for {len(results)} markets")
        return results

