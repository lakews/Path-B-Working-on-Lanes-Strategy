"""
Polymarket-Native Sentiment Extraction

Extracts sentiment signals directly from Polymarket data:
1. Order Flow Imbalance - Buy vs Sell pressure from trades
2. Volume Momentum - Volume changes over 1h/6h/24h
3. Spread Analysis - Bid/ask spread tightening = confidence
4. Price Velocity - Rate of price change
5. Whale Detection - Large trade signals

No external API required - uses existing Polymarket Gamma/CLOB APIs
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)


class PolymarketSentimentExtractor:
    """
    Extract sentiment signals from Polymarket market data.
    
    All signals are normalized to 0-1 range where:
    - 0.5 = neutral
    - > 0.5 = bullish (favors YES)
    - < 0.5 = bearish (favors NO)
    """
    
    def __init__(self):
        # Historical data storage for momentum calculations
        self._price_history: Dict[str, List[Dict]] = defaultdict(list)
        self._volume_history: Dict[str, List[Dict]] = defaultdict(list)
        self._trade_history: Dict[str, List[Dict]] = defaultdict(list)
        self._sentiment_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # Configuration
        self.config = {
            'whale_threshold_usd': 1000,      # Trades above this = whale
            'large_trade_threshold': 500,      # Large trade threshold
            'momentum_windows': {
                '1h': 3600,
                '6h': 21600,
                '24h': 86400,
            },
            'max_history_items': 1000,         # Max items to keep per market
            'spread_neutral': 0.04,            # 4% spread = neutral confidence
            'volume_spike_threshold': 2.0,     # 2x avg volume = spike
        }
        
        logger.info("PolymarketSentimentExtractor initialized")
    
    async def analyze_market(
        self,
        market_id: str,
        market_data: Dict,
        trades: List[Dict] = None,
        order_book: Dict = None,
        price_history: List[Dict] = None
    ) -> Dict:
        """
        Comprehensive sentiment analysis for a market.
        
        Args:
            market_id: Unique market identifier
            market_data: Current market data (price, volume, etc.)
            trades: Recent trades from CLOB API
            order_book: Current order book from CLOB API
            price_history: Historical prices
            
        Returns:
            Dict with sentiment signals and combined score
        """
        try:
            current_price = float(market_data.get('yes_price', 0.5))
            current_volume = float(market_data.get('volume_24h', 0) or market_data.get('volume', 0) or 0)
            
            # Update histories
            self._update_price_history(market_id, current_price)
            self._update_volume_history(market_id, current_volume)
            if trades:
                self._update_trade_history(market_id, trades)
            
            # Calculate individual signals
            signals = {}
            
            # 1. Order Flow Imbalance (from order book depth or trades)
            signals['order_flow'] = self._calculate_order_flow(market_id, trades, order_book)
            
            # 2. Volume Momentum (1h, 6h, 24h)
            signals['volume_momentum'] = self._calculate_volume_momentum(market_id)
            
            # 3. Spread Analysis
            signals['spread_confidence'] = self._calculate_spread_confidence(order_book)
            
            # 4. Price Velocity
            signals['price_velocity'] = self._calculate_price_velocity(market_id)
            
            # 5. Whale Activity (from order book large orders if no trades)
            signals['whale_signal'] = self._calculate_whale_signal(market_id, trades, order_book)
            
            # 6. Price Momentum (trend direction)
            signals['price_momentum'] = self._calculate_price_momentum(market_id)
            
            # Combined sentiment score (weighted average)
            weights = {
                'order_flow': 0.25,
                'volume_momentum': 0.15,
                'spread_confidence': 0.10,
                'price_velocity': 0.15,
                'whale_signal': 0.20,
                'price_momentum': 0.15,
            }
            
            combined_score = 0.5  # Default neutral
            total_weight = 0
            signal_details = {}
            
            for signal_name, weight in weights.items():
                signal_data = signals.get(signal_name, {})
                if signal_data and signal_data.get('valid', False):
                    score = signal_data.get('score', 0.5)
                    combined_score += (score - 0.5) * weight
                    total_weight += weight
                    signal_details[signal_name] = {
                        'score': round(score, 4),
                        'weight': weight,
                        'contribution': round((score - 0.5) * weight, 4),
                        'details': signal_data.get('details', {})
                    }
            
            # Normalize combined score
            combined_score = max(0.01, min(0.99, combined_score))
            
            # Store sentiment history for momentum tracking
            sentiment_record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'score': combined_score,
                'signals': signal_details
            }
            self._sentiment_history[market_id].append(sentiment_record)
            self._trim_history(self._sentiment_history[market_id])
            
            # Calculate sentiment momentum
            sentiment_momentum = self._calculate_sentiment_momentum(market_id)
            
            result = {
                'market_id': market_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'combined_score': round(combined_score, 4),
                'sentiment_momentum': sentiment_momentum,
                'signals': signal_details,
                'interpretation': self._interpret_sentiment(combined_score, sentiment_momentum),
                'data_quality': {
                    'has_trades': bool(trades),
                    'has_order_book': bool(order_book),
                    'price_history_points': len(self._price_history.get(market_id, [])),
                    'trade_history_points': len(self._trade_history.get(market_id, [])),
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing market sentiment: {e}")
            return {
                'market_id': market_id,
                'combined_score': 0.5,
                'error': str(e)
            }
    
    def _calculate_order_flow(self, market_id: str, trades: List[Dict] = None, order_book: Dict = None) -> Dict:
        """
        Calculate order flow imbalance.
        
        Primary: From order book bid/ask depth imbalance (always available)
        Secondary: From recent trades if available
        
        Buy pressure vs sell pressure indicates market sentiment.
        """
        # Try order book depth imbalance first (more reliable, always available)
        if order_book:
            try:
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
                
                if bids and asks:
                    # Calculate depth at multiple price levels
                    bid_depth = sum(float(b.get('size', 0)) for b in bids[:10])
                    ask_depth = sum(float(a.get('size', 0)) for a in asks[:10])
                    total_depth = bid_depth + ask_depth
                    
                    if total_depth > 0:
                        # More bids = buying pressure = bullish
                        depth_imbalance = bid_depth / total_depth
                        
                        # Map to score (0.3-0.7 range)
                        score = 0.3 + (depth_imbalance * 0.4)
                        
                        return {
                            'valid': True,
                            'score': round(score, 4),
                            'source': 'order_book_depth',
                            'details': {
                                'bid_depth': round(bid_depth, 2),
                                'ask_depth': round(ask_depth, 2),
                                'depth_imbalance': round(depth_imbalance, 4),
                                'interpretation': 'bullish' if depth_imbalance > 0.55 else ('bearish' if depth_imbalance < 0.45 else 'neutral')
                            }
                        }
            except Exception as e:
                logger.debug(f"Order book depth calculation error: {e}")
        
        # Fallback to trades if available
        if not trades:
            trades = self._trade_history.get(market_id, [])[-100:]
        
        if not trades or len(trades) < 5:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_data'}}
        
        try:
            buy_volume = 0
            sell_volume = 0
            buy_count = 0
            sell_count = 0
            
            for trade in trades:
                # Determine trade direction
                # In Polymarket: buying YES = bullish, selling YES (buying NO) = bearish
                side = trade.get('side', '').lower()
                size = float(trade.get('size', 0) or trade.get('amount', 0) or 0)
                
                if side in ['buy', 'b', 'yes']:
                    buy_volume += size
                    buy_count += 1
                elif side in ['sell', 's', 'no']:
                    sell_volume += size
                    sell_count += 1
                else:
                    # Infer from price movement if side not specified
                    price = float(trade.get('price', 0.5))
                    if price > 0.5:
                        buy_volume += size * 0.5  # Partial credit
                    else:
                        sell_volume += size * 0.5
            
            total_volume = buy_volume + sell_volume
            if total_volume == 0:
                return {'valid': False, 'score': 0.5, 'details': {'reason': 'no_volume'}}
            
            # Calculate imbalance ratio (0 to 1, where 0.5 = balanced)
            imbalance = buy_volume / total_volume
            
            # Smooth extreme values
            score = 0.3 + (imbalance * 0.4)  # Map to 0.3-0.7 range
            
            return {
                'valid': True,
                'score': round(score, 4),
                'details': {
                    'buy_volume': round(buy_volume, 2),
                    'sell_volume': round(sell_volume, 2),
                    'buy_count': buy_count,
                    'sell_count': sell_count,
                    'imbalance_ratio': round(imbalance, 4),
                }
            }
        except Exception as e:
            logger.debug(f"Order flow calculation error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_volume_momentum(self, market_id: str) -> Dict:
        """
        Calculate volume momentum over multiple timeframes.
        
        Increasing volume = increasing interest = stronger signal
        """
        history = self._volume_history.get(market_id, [])
        
        if len(history) < 3:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_history'}}
        
        try:
            now = datetime.now(timezone.utc)
            
            # Calculate volume changes for each window
            momentum_scores = {}
            for window_name, window_seconds in self.config['momentum_windows'].items():
                cutoff = now - timedelta(seconds=window_seconds)
                
                recent_volumes = [
                    h['volume'] for h in history
                    if datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00')) > cutoff
                ]
                
                if len(recent_volumes) >= 2:
                    # Compare recent avg to older avg
                    mid = len(recent_volumes) // 2
                    recent_avg = np.mean(recent_volumes[mid:]) if recent_volumes[mid:] else 0
                    older_avg = np.mean(recent_volumes[:mid]) if recent_volumes[:mid] else recent_avg
                    
                    if older_avg > 0:
                        change_ratio = recent_avg / older_avg
                        # Convert to score: >1 = bullish (volume increasing)
                        # Map ratio to 0.3-0.7 range
                        score = 0.5 + (min(max(change_ratio - 1, -0.5), 0.5) * 0.4)
                        momentum_scores[window_name] = {
                            'score': round(score, 4),
                            'change_ratio': round(change_ratio, 4),
                            'recent_avg': round(recent_avg, 2),
                            'older_avg': round(older_avg, 2),
                        }
            
            if not momentum_scores:
                return {'valid': False, 'score': 0.5, 'details': {'reason': 'no_momentum_data'}}
            
            # Weighted average of momentum scores (shorter timeframes weighted more)
            weights = {'1h': 0.5, '6h': 0.3, '24h': 0.2}
            combined = 0.5
            for window, data in momentum_scores.items():
                combined += (data['score'] - 0.5) * weights.get(window, 0.2)
            
            return {
                'valid': True,
                'score': round(max(0.3, min(0.7, combined)), 4),
                'details': {
                    'windows': momentum_scores,
                    'data_points': len(history),
                }
            }
        except Exception as e:
            logger.debug(f"Volume momentum error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_spread_confidence(self, order_book: Dict = None) -> Dict:
        """
        Analyze bid/ask spread as confidence indicator.
        
        Tight spread = high confidence in current price
        Wide spread = uncertainty
        """
        if not order_book:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'no_order_book'}}
        
        try:
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            
            if not bids or not asks:
                return {'valid': False, 'score': 0.5, 'details': {'reason': 'empty_order_book'}}
            
            # Get best bid and ask
            best_bid = max(float(b.get('price', 0)) for b in bids) if bids else 0
            best_ask = min(float(a.get('price', 1)) for a in asks) if asks else 1
            
            spread = best_ask - best_bid
            spread_pct = spread / ((best_bid + best_ask) / 2) if (best_bid + best_ask) > 0 else 1
            
            # Tight spread = higher confidence (score closer to current price direction)
            # Wide spread = lower confidence (score closer to 0.5)
            neutral_spread = self.config['spread_neutral']
            
            if spread_pct <= neutral_spread / 2:
                confidence = 0.9  # Very tight spread
            elif spread_pct <= neutral_spread:
                confidence = 0.7
            elif spread_pct <= neutral_spread * 2:
                confidence = 0.5
            else:
                confidence = 0.3  # Wide spread = uncertainty
            
            # Calculate depth imbalance
            bid_depth = sum(float(b.get('size', 0)) for b in bids[:5])
            ask_depth = sum(float(a.get('size', 0)) for a in asks[:5])
            total_depth = bid_depth + ask_depth
            
            depth_imbalance = bid_depth / total_depth if total_depth > 0 else 0.5
            
            # Combine spread confidence with depth imbalance
            # More bids than asks = bullish pressure
            score = 0.5 + (depth_imbalance - 0.5) * confidence * 0.4
            
            return {
                'valid': True,
                'score': round(max(0.3, min(0.7, score)), 4),
                'details': {
                    'spread': round(spread, 4),
                    'spread_pct': round(spread_pct * 100, 2),
                    'confidence': round(confidence, 2),
                    'bid_depth': round(bid_depth, 2),
                    'ask_depth': round(ask_depth, 2),
                    'depth_imbalance': round(depth_imbalance, 4),
                }
            }
        except Exception as e:
            logger.debug(f"Spread confidence error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_price_velocity(self, market_id: str) -> Dict:
        """
        Calculate rate of price change.
        
        Fast price movement in a direction = strong momentum
        """
        history = self._price_history.get(market_id, [])
        
        if len(history) < 3:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_history'}}
        
        try:
            # Calculate velocity over last N points
            recent = history[-20:]  # Last 20 data points
            
            if len(recent) < 3:
                return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_recent'}}
            
            prices = [h['price'] for h in recent]
            
            # Calculate velocity (price change per time unit)
            first_price = prices[0]
            last_price = prices[-1]
            price_change = last_price - first_price
            
            # Calculate acceleration (is velocity increasing?)
            mid = len(prices) // 2
            first_half_change = prices[mid] - prices[0] if mid > 0 else 0
            second_half_change = prices[-1] - prices[mid]
            
            # Normalize to score
            # Positive change = bullish, negative = bearish
            # Map typical price changes (-0.1 to +0.1) to (0.3 to 0.7)
            velocity_score = 0.5 + (price_change * 2)  # Scale factor
            velocity_score = max(0.3, min(0.7, velocity_score))
            
            # Acceleration bonus/penalty
            if second_half_change > first_half_change > 0:
                velocity_score = min(0.75, velocity_score + 0.05)  # Accelerating up
            elif second_half_change < first_half_change < 0:
                velocity_score = max(0.25, velocity_score - 0.05)  # Accelerating down
            
            return {
                'valid': True,
                'score': round(velocity_score, 4),
                'details': {
                    'price_change': round(price_change, 4),
                    'first_half_change': round(first_half_change, 4),
                    'second_half_change': round(second_half_change, 4),
                    'is_accelerating': second_half_change > first_half_change,
                    'data_points': len(recent),
                }
            }
        except Exception as e:
            logger.debug(f"Price velocity error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_whale_signal(self, market_id: str, trades: List[Dict] = None, order_book: Dict = None) -> Dict:
        """
        Detect and analyze large orders (whale activity).
        
        Primary: From order book large orders (always available)
        Secondary: From trades if available
        
        Large buy orders = bullish signal
        Large sell orders = bearish signal
        """
        # Try order book first - look for large orders
        if order_book:
            try:
                bids = order_book.get('bids', [])
                asks = order_book.get('asks', [])
                
                if bids and asks:
                    whale_threshold = self.config['whale_threshold_usd']
                    large_threshold = self.config['large_trade_threshold']
                    
                    # Find large bid orders (whale buys)
                    large_bids = 0
                    whale_bids = 0
                    for bid in bids[:20]:
                        size = float(bid.get('size', 0))
                        price = float(bid.get('price', 0.5))
                        value = size * price
                        if value >= whale_threshold:
                            whale_bids += value
                        elif value >= large_threshold:
                            large_bids += value
                    
                    # Find large ask orders (whale sells)
                    large_asks = 0
                    whale_asks = 0
                    for ask in asks[:20]:
                        size = float(ask.get('size', 0))
                        price = float(ask.get('price', 0.5))
                        value = size * price
                        if value >= whale_threshold:
                            whale_asks += value
                        elif value >= large_threshold:
                            large_asks += value
                    
                    total_whale = whale_bids + whale_asks
                    total_large = large_bids + large_asks
                    
                    # Calculate signal
                    if total_whale > 0:
                        whale_ratio = whale_bids / total_whale
                        whale_signal = 0.5 + (whale_ratio - 0.5) * 0.4
                    else:
                        whale_signal = 0.5
                    
                    if total_large > 0:
                        large_ratio = large_bids / total_large
                        large_signal = 0.5 + (large_ratio - 0.5) * 0.2
                    else:
                        large_signal = 0.5
                    
                    combined = whale_signal * 0.7 + large_signal * 0.3
                    
                    return {
                        'valid': True,
                        'score': round(max(0.3, min(0.7, combined)), 4),
                        'source': 'order_book_whales',
                        'details': {
                            'whale_bids': round(whale_bids, 2),
                            'whale_asks': round(whale_asks, 2),
                            'large_bids': round(large_bids, 2),
                            'large_asks': round(large_asks, 2),
                            'whale_ratio': round(whale_bids / total_whale, 4) if total_whale > 0 else 0.5,
                            'interpretation': 'bullish' if whale_bids > whale_asks else ('bearish' if whale_asks > whale_bids else 'neutral')
                        }
                    }
            except Exception as e:
                logger.debug(f"Order book whale analysis error: {e}")
        
        # Fallback to trades
        if not trades:
            trades = self._trade_history.get(market_id, [])[-50:]
        
        if not trades:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'no_data'}}
        
        try:
            whale_threshold = self.config['whale_threshold_usd']
            large_threshold = self.config['large_trade_threshold']
            
            whale_buys = 0
            whale_sells = 0
            large_buys = 0
            large_sells = 0
            
            for trade in trades:
                size = float(trade.get('size', 0) or trade.get('amount', 0) or 0)
                price = float(trade.get('price', 0.5))
                value = size * price
                
                side = trade.get('side', '').lower()
                is_buy = side in ['buy', 'b', 'yes'] or (not side and price > 0.5)
                
                if value >= whale_threshold:
                    if is_buy:
                        whale_buys += value
                    else:
                        whale_sells += value
                elif value >= large_threshold:
                    if is_buy:
                        large_buys += value
                    else:
                        large_sells += value
            
            total_whale = whale_buys + whale_sells
            total_large = large_buys + large_sells
            
            # Calculate whale signal
            if total_whale > 0:
                whale_ratio = whale_buys / total_whale
                whale_signal = 0.5 + (whale_ratio - 0.5) * 0.4
            else:
                whale_signal = 0.5
            
            # Large trades as secondary signal
            if total_large > 0:
                large_ratio = large_buys / total_large
                large_signal = 0.5 + (large_ratio - 0.5) * 0.2
            else:
                large_signal = 0.5
            
            # Combine (whale activity weighted more)
            combined = whale_signal * 0.7 + large_signal * 0.3
            
            return {
                'valid': True,
                'score': round(max(0.3, min(0.7, combined)), 4),
                'details': {
                    'whale_buys': round(whale_buys, 2),
                    'whale_sells': round(whale_sells, 2),
                    'large_buys': round(large_buys, 2),
                    'large_sells': round(large_sells, 2),
                    'whale_ratio': round(whale_buys / total_whale, 4) if total_whale > 0 else 0.5,
                    'total_whale_volume': round(total_whale, 2),
                }
            }
        except Exception as e:
            logger.debug(f"Whale signal error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_price_momentum(self, market_id: str) -> Dict:
        """
        Calculate price trend direction and strength.
        """
        history = self._price_history.get(market_id, [])
        
        if len(history) < 5:
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_history'}}
        
        try:
            prices = [h['price'] for h in history[-30:]]
            
            # Simple moving averages
            if len(prices) >= 10:
                sma_short = np.mean(prices[-5:])
                sma_long = np.mean(prices[-10:])
                
                # Trend direction
                trend = sma_short - sma_long
                
                # Normalize trend to score
                score = 0.5 + (trend * 5)  # Scale factor for typical price ranges
                score = max(0.3, min(0.7, score))
                
                return {
                    'valid': True,
                    'score': round(score, 4),
                    'details': {
                        'sma_short': round(sma_short, 4),
                        'sma_long': round(sma_long, 4),
                        'trend': round(trend, 4),
                        'direction': 'bullish' if trend > 0.01 else ('bearish' if trend < -0.01 else 'neutral'),
                    }
                }
            
            return {'valid': False, 'score': 0.5, 'details': {'reason': 'insufficient_for_sma'}}
        except Exception as e:
            logger.debug(f"Price momentum error: {e}")
            return {'valid': False, 'score': 0.5, 'details': {'error': str(e)}}
    
    def _calculate_sentiment_momentum(self, market_id: str) -> Dict:
        """
        Calculate how sentiment is changing over time (1h, 6h, 24h windows).
        
        This is the KEY feature - tracking sentiment changes, not just absolute values.
        """
        history = self._sentiment_history.get(market_id, [])
        
        if len(history) < 2:
            return {
                'valid': False,
                '1h': {'change': 0, 'direction': 'neutral'},
                '6h': {'change': 0, 'direction': 'neutral'},
                '24h': {'change': 0, 'direction': 'neutral'},
            }
        
        try:
            now = datetime.now(timezone.utc)
            current_score = history[-1]['score'] if history else 0.5
            
            momentum = {'valid': True}
            
            for window_name, window_seconds in self.config['momentum_windows'].items():
                cutoff = now - timedelta(seconds=window_seconds)
                
                # Find earliest sentiment in window
                window_sentiments = [
                    h for h in history
                    if datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00')) > cutoff
                ]
                
                if window_sentiments:
                    earliest = window_sentiments[0]['score']
                    change = current_score - earliest
                    
                    # Determine direction and strength
                    if change > 0.05:
                        direction = 'strongly_bullish'
                    elif change > 0.02:
                        direction = 'bullish'
                    elif change < -0.05:
                        direction = 'strongly_bearish'
                    elif change < -0.02:
                        direction = 'bearish'
                    else:
                        direction = 'neutral'
                    
                    momentum[window_name] = {
                        'change': round(change, 4),
                        'direction': direction,
                        'start_score': round(earliest, 4),
                        'end_score': round(current_score, 4),
                        'data_points': len(window_sentiments),
                    }
                else:
                    momentum[window_name] = {
                        'change': 0,
                        'direction': 'neutral',
                        'reason': 'no_data_in_window'
                    }
            
            return momentum
            
        except Exception as e:
            logger.debug(f"Sentiment momentum error: {e}")
            return {
                'valid': False,
                '1h': {'change': 0, 'direction': 'neutral', 'error': str(e)},
                '6h': {'change': 0, 'direction': 'neutral'},
                '24h': {'change': 0, 'direction': 'neutral'},
            }
    
    def _interpret_sentiment(self, score: float, momentum: Dict) -> str:
        """Generate human-readable sentiment interpretation."""
        # Base interpretation
        if score >= 0.65:
            base = "Strongly Bullish"
        elif score >= 0.55:
            base = "Bullish"
        elif score <= 0.35:
            base = "Strongly Bearish"
        elif score <= 0.45:
            base = "Bearish"
        else:
            base = "Neutral"
        
        # Add momentum context
        momentum_1h = momentum.get('1h', {}).get('direction', 'neutral')
        if 'bullish' in momentum_1h:
            base += " (momentum rising)"
        elif 'bearish' in momentum_1h:
            base += " (momentum falling)"
        
        return base
    
    def _update_price_history(self, market_id: str, price: float):
        """Update price history for a market."""
        self._price_history[market_id].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'price': price
        })
        self._trim_history(self._price_history[market_id])
    
    def _update_volume_history(self, market_id: str, volume: float):
        """Update volume history for a market."""
        self._volume_history[market_id].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'volume': volume
        })
        self._trim_history(self._volume_history[market_id])
    
    def _update_trade_history(self, market_id: str, trades: List[Dict]):
        """Update trade history for a market."""
        for trade in trades:
            self._trade_history[market_id].append({
                **trade,
                'recorded_at': datetime.now(timezone.utc).isoformat()
            })
        self._trim_history(self._trade_history[market_id])
    
    def _trim_history(self, history: List):
        """Trim history to max size."""
        max_items = self.config['max_history_items']
        if len(history) > max_items:
            del history[:-max_items]
    
    def get_market_sentiment_summary(self, market_id: str) -> Dict:
        """Get a summary of current sentiment state for a market."""
        history = self._sentiment_history.get(market_id, [])
        
        if not history:
            return {'has_data': False}
        
        recent = history[-1]
        momentum = self._calculate_sentiment_momentum(market_id)
        
        return {
            'has_data': True,
            'current_score': recent['score'],
            'timestamp': recent['timestamp'],
            'momentum': momentum,
            'history_length': len(history),
            'interpretation': self._interpret_sentiment(recent['score'], momentum)
        }


# Singleton instance
_sentiment_extractor: Optional[PolymarketSentimentExtractor] = None


def get_polymarket_sentiment_extractor() -> PolymarketSentimentExtractor:
    """Get singleton sentiment extractor instance."""
    global _sentiment_extractor
    if _sentiment_extractor is None:
        _sentiment_extractor = PolymarketSentimentExtractor()
    return _sentiment_extractor
