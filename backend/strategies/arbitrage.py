import logging
from typing import Dict, Optional, List
from database import get_db
from ml.signal_fusion import SignalFusionEngine
from ml.kelly_sharpe_optimizer import KellySharpeOptimizer
from trading.execution_engine import ExecutionEngine
from trading.position_manager import PositionManager
from trading.risk_controller import RiskController
from models import OrderSide, StrategyType

logger = logging.getLogger(__name__)

class MultiMarketArbitrageStrategy:
    """Multi-market arbitrage strategy
    Detects price discrepancies across similar markets
    Target: Risk-free profit from market inefficiencies
    
    Strategy Type: HFT (requires high liquidity for sub-second execution)
    """
    
    def __init__(self):
        self.db = get_db()
        self.type = 'HFT'  # Three-Speed Architecture: Requires strict liquidity ($10k+)
        self.signal_fusion = SignalFusionEngine()
        self.kelly_optimizer = KellySharpeOptimizer()
        self.execution = ExecutionEngine()
        self.position_mgr = PositionManager()
        self.risk_ctrl = RiskController()
        self.arbitrage_threshold = 0.05  # 5% price difference
        self.min_liquidity = 5000
        
    async def execute_strategy(self, market_data: Dict) -> Optional[Dict]:
        """Execute arbitrage strategy
        Find similar markets with price discrepancies
        """
        try:
            market_id = market_data.get('id')
            question = market_data.get('question', '')
            category = market_data.get('category')
            liquidity = market_data.get('liquidity', 0)
            
            # STRICT PRICE VALIDATION
            yes_price = market_data.get('yes_price')
            if yes_price is None or yes_price == 0:
                logger.warning(f"[ARBITRAGE-REJECT] Missing price for {market_id[:16] if market_id else 'unknown'}")
                return None
            yes_price = float(yes_price)
            
            # Only consider liquid markets
            if liquidity < self.min_liquidity:
                return None
            
            # Find similar markets
            similar_markets = await self._find_similar_markets(question, category, market_id)
            
            if not similar_markets:
                return None
            
            # Look for arbitrage opportunities
            for similar_market in similar_markets:
                arb_opportunity = self._detect_arbitrage(
                    market_data,
                    similar_market
                )
                
                if arb_opportunity:
                    # Execute arbitrage
                    result = await self._execute_arbitrage(
                        market_data,
                        similar_market,
                        arb_opportunity
                    )
                    
                    if result:
                        return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing arbitrage strategy: {e}")
            return None
    
    async def _find_similar_markets(
        self,
        question: str,
        category: str,
        exclude_id: str
    ) -> List[Dict]:
        """Find similar markets that might have arbitrage opportunities"""
        try:
            # Extract key terms from question
            key_terms = self._extract_key_terms(question)
            
            if not key_terms:
                return []
            
            # Search for markets with similar terms
            query = {
                "id": {"$ne": exclude_id},
                "category": category,
                "liquidity": {"$gte": self.min_liquidity},
                "$or": [
                    {"question": {"$regex": term, "$options": "i"}}
                    for term in key_terms[:3]  # Use top 3 key terms
                ]
            }
            
            cursor = self.db.markets.find(
                query,
                {"_id": 0}
            ).limit(10)
            
            markets = await cursor.to_list(length=10)
            return markets
            
        except Exception as e:
            logger.error(f"Error finding similar markets: {e}")
            return []
    
    def _extract_key_terms(self, question: str) -> List[str]:
        """Extract key terms from market question"""
        try:
            # Simple keyword extraction
            # Remove common words
            stop_words = {
                'will', 'the', 'be', 'to', 'a', 'an', 'of', 'in', 'on', 'at',
                'by', 'for', 'with', 'is', 'are', 'was', 'were', 'been',
                'being', 'have', 'has', 'had', 'do', 'does', 'did', 'before',
                'after', 'above', 'below', 'between', 'into', 'through',
                'during', 'than', 'or', 'and', 'but', 'if', 'then', 'so'
            }
            
            words = question.lower().split()
            key_terms = [
                word for word in words
                if word not in stop_words and len(word) > 3
            ]
            
            return key_terms[:5]  # Top 5 terms
            
        except Exception as e:
            logger.error(f"Error extracting key terms: {e}")
            return []
    
    def _detect_arbitrage(
        self,
        market1: Dict,
        market2: Dict
    ) -> Optional[Dict]:
        """Detect arbitrage opportunity between two markets"""
        try:
            # STRICT PRICE VALIDATION
            price1 = market1.get('yes_price')
            price2 = market2.get('yes_price')
            
            if price1 is None or price1 == 0 or price2 is None or price2 == 0:
                logger.debug("[ARBITRAGE] Missing price in one or both markets for comparison")
                return None
            
            price1 = float(price1)
            price2 = float(price2)
            
            # Calculate price difference
            price_diff = abs(price1 - price2)
            price_diff_pct = price_diff / min(price1, price2) if min(price1, price2) > 0 else 0
            
            # Check if difference exceeds threshold
            if price_diff_pct < self.arbitrage_threshold:
                return None
            
            # Determine which market to buy and which to sell
            if price1 < price2:
                buy_market = market1
                sell_market = market2
            else:
                buy_market = market2
                sell_market = market1
            
            # Calculate expected profit
            buy_price = buy_market.get('yes_price')
            sell_price = sell_market.get('yes_price')
            expected_profit_pct = (sell_price - buy_price) / buy_price if buy_price > 0 else 0
            
            return {
                "buy_market": buy_market,
                "sell_market": sell_market,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "price_diff_pct": price_diff_pct,
                "expected_profit_pct": expected_profit_pct
            }
            
        except Exception as e:
            logger.error(f"Error detecting arbitrage: {e}")
            return None
    
    async def _execute_arbitrage(
        self,
        market1: Dict,
        market2: Dict,
        opportunity: Dict
    ) -> Optional[Dict]:
        """Execute arbitrage trades"""
        try:
            buy_market = opportunity['buy_market']
            sell_market = opportunity['sell_market']
            expected_profit_pct = opportunity['expected_profit_pct']
            
            # Calculate position size
            position_size, kelly_pct = await self.kelly_optimizer.calculate_position_size(
                buy_market,
                0.9,  # High confidence for arbitrage
                0.95  # High win probability
            )
            
            if position_size < 10:
                return None
            
            buy_shares = position_size / opportunity['buy_price'] if opportunity['buy_price'] > 0 else 0
            sell_shares = buy_shares  # Equal shares for hedge
            
            # Check risk approval
            approved, reason = await self.risk_ctrl.check_trade_approval(
                buy_market.get('id'),
                position_size * 2,  # Both legs
                0.9
            )
            
            if not approved:
                logger.info(f"Arbitrage trade rejected: {reason}")
                return None
            
            # Execute buy leg
            buy_result = await self.execution.execute_order(
                market_id=buy_market.get('id'),
                side=OrderSide.BUY,
                price=opportunity['buy_price'],
                shares=buy_shares,
                strategy=StrategyType.ARBITRAGE
            )
            
            if buy_result['status'] != 'FILLED':
                return None
            
            # Execute sell leg
            sell_result = await self.execution.execute_order(
                market_id=sell_market.get('id'),
                side=OrderSide.SELL,
                price=opportunity['sell_price'],
                shares=sell_shares,
                strategy=StrategyType.ARBITRAGE
            )
            
            # Open positions
            if buy_result['status'] == 'FILLED':
                await self.position_mgr.open_position(
                    market_id=buy_market.get('id'),
                    side=OrderSide.BUY,
                    shares=buy_shares,
                    price=opportunity['buy_price'],
                    strategy=StrategyType.ARBITRAGE
                )
            
            if sell_result['status'] == 'FILLED':
                await self.position_mgr.open_position(
                    market_id=sell_market.get('id'),
                    side=OrderSide.SELL,
                    shares=sell_shares,
                    price=opportunity['sell_price'],
                    strategy=StrategyType.ARBITRAGE
                )
            
            logger.info(f"Arbitrage executed: {expected_profit_pct:.2%} expected profit")
            
            return {
                "strategy": "arbitrage",
                "buy_trade": buy_result,
                "sell_trade": sell_result,
                "expected_profit_pct": expected_profit_pct
            }
            
        except Exception as e:
            logger.error(f"Error executing arbitrage: {e}")
            return None
