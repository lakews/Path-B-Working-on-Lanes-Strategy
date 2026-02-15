"""
Sharp Detector - Comprehensive Implementation
==============================================
Detects and tracks sharp (professional) traders using:
- Phase 1: Proxy methods using existing market data
- Phase 2: Trade data collection from Polymarket API
- Phase 3: Scheduled sharp trader identification

Sharp traders are identified by:
- High win rate (>70%)
- Significant volume (>$10k)
- Consistent performance across multiple trades
- Category specialization
"""

import numpy as np
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from database import get_db
from models import MarketCategory
import uuid

logger = logging.getLogger(__name__)


class SharpDetector:
    """
    Comprehensive sharp trader detection system.
    
    Provides three detection methods:
    1. Proxy detection (using order flow, momentum, volume)
    2. Historical analysis (from collected trade data)
    3. Real-time position tracking
    """
    
    # Configuration
    SHARP_WIN_RATE_THRESHOLD = 0.70      # 70% win rate to qualify as sharp
    SHARP_MIN_TRADES = 10                 # Minimum trades to evaluate
    SHARP_MIN_VOLUME = 10000              # $10k minimum volume
    TRACKING_WINDOW_DAYS = 7              # Days of history to analyze
    
    # Proxy detection thresholds
    VOLUME_SPIKE_THRESHOLD = 50000        # $50k suggests institutional activity
    MOMENTUM_THRESHOLD = 0.05             # 5% price move
    ORDER_FLOW_IMBALANCE = 1.3            # 30% imbalance ratio
    SHARP_Z_SCORE_THRESHOLD = 2.0         # Z-score for sharp activity
    
    # Background task settings
    TRADE_FETCH_INTERVAL = 300            # Fetch trades every 5 minutes
    SHARP_ID_INTERVAL = 21600             # Identify sharps every 6 hours
    POSITION_TRACK_INTERVAL = 60          # Track positions every 1 minute
    
    def __init__(self):
        self.db = get_db()
        self.sharp_threshold = self.SHARP_WIN_RATE_THRESHOLD
        self.min_trades = self.SHARP_MIN_TRADES
        self.tracking_window = timedelta(days=self.TRACKING_WINDOW_DAYS)
        
        # Import RISK config for unified thresholds
        try:
            from risk_config import RISK
            self.risk_config = RISK
            self.sharp_min_volume = getattr(RISK, 'SHARP_DETECTION_MIN_VOLUME', self.SHARP_MIN_VOLUME)
        except ImportError:
            self.risk_config = None
            self.sharp_min_volume = self.SHARP_MIN_VOLUME
        
        # Background task handles
        self._running = False
        self._trade_fetch_task = None
        self._sharp_id_task = None
        self._position_track_task = None
        
        # Cache for performance
        self._sharp_cache = {}  # market_id -> {is_active, direction, timestamp}
        self._cache_ttl = 30    # Cache TTL in seconds
        
        logger.info("[SHARP] SharpDetector initialized with comprehensive detection")
    
    # =========================================================================
    # PHASE 1: PROXY METHODS (Using Existing Data)
    # =========================================================================
    
    async def is_sharp_active(self, market_id: str) -> bool:
        """
        Detect sharp-like activity using available signals.
        Uses proxy indicators when real sharp data is unavailable.
        
        Signals checked:
        1. Volume spike (>$50k suggests institutional activity)
        2. Price momentum (>5% recent move)
        3. News catalyst (PATH B opportunity exists)
        4. Order flow imbalance (>30% directional)
        
        Returns True if 2+ signals indicate sharp activity.
        """
        try:
            # Check cache first
            cached = self._get_cached_sharp_status(market_id)
            if cached is not None:
                return cached.get('is_active', False)
            
            # First, check if we have real sharp trader data
            real_sharp_active = await self._check_real_sharp_activity(market_id)
            if real_sharp_active:
                self._cache_sharp_status(market_id, True, None)
                return True
            
            # Fallback to proxy detection
            signals = []
            
            # Get market data from cache
            market = await self.db.polymarket_cache.find_one(
                {'condition_id': market_id},
                {'_id': 0, 'volume_24h': 1, 'yes_price': 1, 'price_history': 1, 'order_book': 1}
            )
            
            if not market:
                return False
            
            # Signal 1: Volume spike
            volume = market.get('volume_24h', 0)
            if volume > self.VOLUME_SPIKE_THRESHOLD:
                signals.append('volume_spike')
            
            # Signal 2: Price momentum
            price_history = market.get('price_history', [])
            if len(price_history) >= 2:
                recent_move = abs(price_history[-1] - price_history[0])
                if recent_move > self.MOMENTUM_THRESHOLD:
                    signals.append('momentum')
            
            # Signal 3: News catalyst (PATH B opportunity)
            recent_news = await self.db.hft_opportunities.find_one(
                {'market_id': market_id, 'type': 'path_b'},
                {'_id': 0}
            )
            if recent_news:
                signals.append('news_catalyst')
            
            # Signal 4: Order flow imbalance
            ob = market.get('order_book', {})
            bids = ob.get('bids', [])
            asks = ob.get('asks', [])
            if bids and asks:
                bid_volume = sum(float(b.get('size', 0)) for b in bids[:5])
                ask_volume = sum(float(a.get('size', 0)) for a in asks[:5])
                if bid_volume > 0 and ask_volume > 0:
                    imbalance = max(bid_volume / ask_volume, ask_volume / bid_volume)
                    if imbalance >= self.ORDER_FLOW_IMBALANCE:
                        signals.append('order_flow_imbalance')
            
            # Require 2+ signals
            is_active = len(signals) >= 2
            
            if is_active:
                logger.debug(f"[SHARP] Activity detected in {market_id[:16]}: {signals}")
            
            self._cache_sharp_status(market_id, is_active, None)
            return is_active
            
        except Exception as e:
            logger.debug(f"[SHARP] is_sharp_active error: {e}")
            return False
    
    async def get_sharp_direction(self, market_id: str) -> Optional[str]:
        """
        Get the consensus direction of sharp traders for a market.
        
        Methods (in priority order):
        1. Real sharp trader positions (if available)
        2. Order flow imbalance direction
        3. Price momentum direction
        
        Returns 'YES', 'NO', or None if no clear signal.
        """
        try:
            # Check cache first
            cached = self._get_cached_sharp_status(market_id)
            if cached is not None and cached.get('direction'):
                return cached.get('direction')
            
            # First, check real sharp trader consensus
            real_direction = await self._get_real_sharp_direction(market_id)
            if real_direction:
                self._cache_sharp_status(market_id, True, real_direction)
                return real_direction
            
            # Fallback to proxy detection
            market = await self.db.polymarket_cache.find_one(
                {'condition_id': market_id},
                {'_id': 0, 'order_book': 1, 'yes_price': 1, 'price_history': 1}
            )
            
            if not market:
                return None
            
            direction = None
            confidence_scores = {'YES': 0, 'NO': 0}
            
            # Method 1: Order flow imbalance
            ob = market.get('order_book', {})
            bids = ob.get('bids', [])
            asks = ob.get('asks', [])
            if bids and asks:
                bid_volume = sum(float(b.get('size', 0)) for b in bids[:5])
                ask_volume = sum(float(a.get('size', 0)) for a in asks[:5])
                if bid_volume > ask_volume * self.ORDER_FLOW_IMBALANCE:
                    confidence_scores['YES'] += 2
                elif ask_volume > bid_volume * self.ORDER_FLOW_IMBALANCE:
                    confidence_scores['NO'] += 2
            
            # Method 2: Price momentum direction
            history = market.get('price_history', [])
            if len(history) >= 2:
                price_change = history[-1] - history[0]
                if price_change > 0.03:
                    confidence_scores['YES'] += 1
                elif price_change < -0.03:
                    confidence_scores['NO'] += 1
            
            # Method 3: Check PATH A signal direction
            path_a_signal = await self.db.signals.find_one(
                {'market_id': market_id, 'type': 'path_a'},
                {'_id': 0, 'direction': 1, 'bayes_factor': 1}
            )
            if path_a_signal and path_a_signal.get('bayes_factor', 0) >= 3.0:
                signal_dir = path_a_signal.get('direction')
                if signal_dir:
                    confidence_scores[signal_dir] += 2
            
            # Determine direction from confidence scores
            if confidence_scores['YES'] > confidence_scores['NO'] and confidence_scores['YES'] >= 2:
                direction = 'YES'
            elif confidence_scores['NO'] > confidence_scores['YES'] and confidence_scores['NO'] >= 2:
                direction = 'NO'
            
            if direction:
                logger.debug(f"[SHARP] Direction for {market_id[:16]}: {direction} (scores: {confidence_scores})")
                self._cache_sharp_status(market_id, True, direction)
            
            return direction
            
        except Exception as e:
            logger.debug(f"[SHARP] get_sharp_direction error: {e}")
            return None
    
    async def detect_sharp_movement(self, market_id: str) -> Dict:
        """
        Detect sharp trader movement with z-score analysis.
        
        Returns:
            {
                'z_score': float,      # Statistical significance of activity
                'direction': str,      # 'YES' or 'NO'
                'confidence': float,   # 0-1 confidence score
                'signals': list        # List of detected signals
            }
        """
        try:
            result = {
                'z_score': 0.0,
                'direction': None,
                'confidence': 0.0,
                'signals': []
            }
            
            # Get market data
            market = await self.db.polymarket_cache.find_one(
                {'condition_id': market_id},
                {'_id': 0, 'volume_24h': 1, 'yes_price': 1, 'price_history': 1, 
                 'order_book': 1, 'avg_volume_7d': 1}
            )
            
            if not market:
                return result
            
            z_scores = []
            
            # Z-score 1: Volume vs 7-day average
            volume = market.get('volume_24h', 0)
            avg_volume = market.get('avg_volume_7d', volume)
            if avg_volume > 0:
                vol_z = (volume - avg_volume) / max(avg_volume * 0.3, 1)  # Assume 30% std dev
                z_scores.append(vol_z)
                if vol_z > 2.0:
                    result['signals'].append(f'volume_spike_z{vol_z:.1f}')
            
            # Z-score 2: Price movement
            history = market.get('price_history', [])
            if len(history) >= 5:
                recent_move = abs(history[-1] - history[-5])
                avg_move = np.mean([abs(history[i] - history[i-1]) for i in range(1, len(history))])
                if avg_move > 0:
                    price_z = recent_move / max(avg_move, 0.01)
                    z_scores.append(price_z)
                    if price_z > 2.0:
                        result['signals'].append(f'price_move_z{price_z:.1f}')
            
            # Z-score 3: Order flow imbalance
            ob = market.get('order_book', {})
            bids = ob.get('bids', [])
            asks = ob.get('asks', [])
            if bids and asks:
                bid_vol = sum(float(b.get('size', 0)) for b in bids[:10])
                ask_vol = sum(float(a.get('size', 0)) for a in asks[:10])
                total_vol = bid_vol + ask_vol
                if total_vol > 0:
                    imbalance = (bid_vol - ask_vol) / total_vol
                    flow_z = abs(imbalance) * 5  # Scale to z-score-like value
                    z_scores.append(flow_z)
                    if flow_z > 1.5:
                        result['signals'].append(f'flow_imbalance_z{flow_z:.1f}')
                    
                    # Determine direction from imbalance
                    if imbalance > 0.2:
                        result['direction'] = 'YES'
                    elif imbalance < -0.2:
                        result['direction'] = 'NO'
            
            # Calculate composite z-score
            if z_scores:
                result['z_score'] = np.mean(z_scores)
                result['confidence'] = min(1.0, result['z_score'] / 3.0)
            
            # If no direction from flow, try momentum
            if not result['direction'] and len(history) >= 2:
                if history[-1] > history[0] + 0.03:
                    result['direction'] = 'YES'
                elif history[-1] < history[0] - 0.03:
                    result['direction'] = 'NO'
            
            return result
            
        except Exception as e:
            logger.debug(f"[SHARP] detect_sharp_movement error: {e}")
            return {'z_score': 0.0, 'direction': None, 'confidence': 0.0, 'signals': []}
    
    # =========================================================================
    # PHASE 2: DATA COLLECTION PIPELINE
    # =========================================================================
    
    async def start_background_tasks(self):
        """Start all background data collection tasks"""
        if self._running:
            logger.warning("[SHARP] Background tasks already running")
            return
        
        self._running = True
        
        # Start trade fetching task
        self._trade_fetch_task = asyncio.create_task(self._trade_fetch_loop())
        
        # Start sharp identification task
        self._sharp_id_task = asyncio.create_task(self._sharp_identification_loop())
        
        # Start position tracking task
        self._position_track_task = asyncio.create_task(self._position_tracking_loop())
        
        logger.info("[SHARP] Background tasks started")
    
    async def stop_background_tasks(self):
        """Stop all background tasks"""
        self._running = False
        
        for task in [self._trade_fetch_task, self._sharp_id_task, self._position_track_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("[SHARP] Background tasks stopped")
    
    async def _trade_fetch_loop(self):
        """Background loop to fetch trades from Polymarket"""
        while self._running:
            try:
                await self._fetch_recent_trades()
                await asyncio.sleep(self.TRADE_FETCH_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SHARP] Trade fetch error: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def _fetch_recent_trades(self):
        """Fetch recent trades from Polymarket CLOB API"""
        try:
            # Get active markets to fetch trades for
            markets = await self.db.polymarket_cache.find(
                {'volume_24h': {'$gt': 10000}},  # Only active markets
                {'_id': 0, 'condition_id': 1, 'token_ids': 1}
            ).limit(50).to_list(50)
            
            if not markets:
                return
            
            trades_collected = 0
            
            async with aiohttp.ClientSession() as session:
                for market in markets:
                    token_ids = market.get('token_ids', market.get('clobTokenIds', []))
                    if not token_ids:
                        continue
                    
                    # Fetch trades for YES token
                    token_id = token_ids[0]
                    try:
                        url = f"https://clob.polymarket.com/trades?asset_id={token_id}&limit=100"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                trades = data if isinstance(data, list) else data.get('trades', [])
                                
                                for trade in trades:
                                    await self._store_trade(market['condition_id'], trade)
                                    trades_collected += 1
                    except Exception as e:
                        logger.debug(f"[SHARP] Failed to fetch trades for {token_id[:16]}: {e}")
                    
                    await asyncio.sleep(0.1)  # Rate limiting
            
            if trades_collected > 0:
                logger.info(f"[SHARP] Collected {trades_collected} trades from {len(markets)} markets")
                
        except Exception as e:
            logger.error(f"[SHARP] Trade fetch error: {e}")
    
    async def _store_trade(self, market_id: str, trade: Dict):
        """Store a trade in the database"""
        try:
            trade_id = trade.get('id', trade.get('trade_id', str(uuid.uuid4())))
            
            trade_doc = {
                'trade_id': trade_id,
                'market_id': market_id,
                'trader_address': trade.get('maker', trade.get('taker', 'unknown')),
                'side': 'YES' if trade.get('side', '').upper() == 'BUY' else 'NO',
                'price': float(trade.get('price', 0)),
                'size': float(trade.get('size', trade.get('amount', 0))),
                'volume': float(trade.get('price', 0)) * float(trade.get('size', 0)),
                'timestamp': trade.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'trade_type': trade.get('type', 'unknown'),
                'collected_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert to avoid duplicates
            await self.db.market_trades.update_one(
                {'trade_id': trade_id},
                {'$set': trade_doc},
                upsert=True
            )
            
        except Exception as e:
            logger.debug(f"[SHARP] Failed to store trade: {e}")
    
    # =========================================================================
    # PHASE 3: SHARP TRADER IDENTIFICATION
    # =========================================================================
    
    async def _sharp_identification_loop(self):
        """Background loop to identify sharp traders"""
        # Initial delay to allow data collection
        await asyncio.sleep(60)
        
        while self._running:
            try:
                await self.identify_sharp_traders()
                await self._cleanup_stale_data()
                await asyncio.sleep(self.SHARP_ID_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SHARP] Identification loop error: {e}")
                await asyncio.sleep(300)  # Wait before retry
    
    async def identify_sharp_traders(self):
        """
        Identify sharp traders from collected trade data.
        
        Criteria:
        - Win rate >= 70%
        - Total volume >= $10k
        - At least 10 trades
        - Category concentration <= 2 (specialist)
        """
        try:
            recent_trades = await self._get_recent_trades()
            
            if not recent_trades:
                logger.debug("[SHARP] No recent trades to analyze")
                return
            
            trader_stats = self._analyze_traders(recent_trades)
            
            sharp_count = 0
            for address, stats in trader_stats.items():
                if self._is_sharp_trader(stats):
                    await self._store_sharp_trader(address, stats)
                    sharp_count += 1
            
            # Get current price for each market to calculate final_price
            await self._update_trade_outcomes()
            
            logger.info(f"[SHARP] Identified {sharp_count} sharp traders from {len(trader_stats)} analyzed")
            
        except Exception as e:
            logger.error(f"[SHARP] Error identifying sharp traders: {e}")
    
    async def _update_trade_outcomes(self):
        """Update trade outcomes with current prices for P&L calculation"""
        try:
            # Get trades without final_price
            pending_trades = await self.db.market_trades.find(
                {'final_price': {'$exists': False}},
                {'_id': 0, 'trade_id': 1, 'market_id': 1}
            ).limit(500).to_list(500)
            
            for trade in pending_trades:
                market = await self.db.polymarket_cache.find_one(
                    {'condition_id': trade['market_id']},
                    {'_id': 0, 'yes_price': 1}
                )
                if market:
                    await self.db.market_trades.update_one(
                        {'trade_id': trade['trade_id']},
                        {'$set': {'final_price': market.get('yes_price', 0.5)}}
                    )
                    
        except Exception as e:
            logger.debug(f"[SHARP] Failed to update trade outcomes: {e}")
    
    async def _position_tracking_loop(self):
        """Background loop to track sharp trader positions"""
        while self._running:
            try:
                await self._track_sharp_positions()
                await asyncio.sleep(self.POSITION_TRACK_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[SHARP] Position tracking error: {e}")
                await asyncio.sleep(30)
    
    async def _track_sharp_positions(self):
        """Track current positions of identified sharp traders"""
        try:
            # Get list of sharp traders
            sharp_traders = await self.db.sharp_traders.find(
                {},
                {'_id': 0, 'address': 1}
            ).to_list(100)
            
            if not sharp_traders:
                return
            
            addresses = [t['address'] for t in sharp_traders]
            
            # Get recent trades by sharp traders
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            
            pipeline = [
                {
                    '$match': {
                        'trader_address': {'$in': addresses},
                        'timestamp': {'$gte': cutoff.isoformat()}
                    }
                },
                {
                    '$group': {
                        '_id': {
                            'market_id': '$market_id',
                            'trader_address': '$trader_address'
                        },
                        'net_position': {
                            '$sum': {
                                '$cond': [
                                    {'$eq': ['$side', 'YES']},
                                    '$size',
                                    {'$multiply': ['$size', -1]}
                                ]
                            }
                        },
                        'total_volume': {'$sum': '$volume'},
                        'last_trade': {'$max': '$timestamp'}
                    }
                }
            ]
            
            positions = await self.db.market_trades.aggregate(pipeline).to_list(500)
            
            # Store/update positions
            for pos in positions:
                if abs(pos['net_position']) > 0:  # Has open position
                    await self.db.sharp_positions.update_one(
                        {
                            'market_id': pos['_id']['market_id'],
                            'trader_address': pos['_id']['trader_address']
                        },
                        {'$set': {
                            'market_id': pos['_id']['market_id'],
                            'trader_address': pos['_id']['trader_address'],
                            'side': 'YES' if pos['net_position'] > 0 else 'NO',
                            'size': abs(pos['net_position']),
                            'volume': pos['total_volume'],
                            'last_trade': pos['last_trade'],
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }},
                        upsert=True
                    )
                    
        except Exception as e:
            logger.debug(f"[SHARP] Position tracking error: {e}")
    
    async def _cleanup_stale_data(self):
        """Clean up old data to prevent unbounded growth"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            
            # Remove old trades
            result = await self.db.market_trades.delete_many(
                {'timestamp': {'$lt': cutoff.isoformat()}}
            )
            if result.deleted_count > 0:
                logger.debug(f"[SHARP] Cleaned up {result.deleted_count} old trades")
            
            # Remove stale sharp trader entries (no recent activity)
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            await self.db.sharp_traders.delete_many(
                {'last_activity': {'$lt': stale_cutoff.isoformat()}}
            )
            
            # Remove old positions
            await self.db.sharp_positions.delete_many(
                {'updated_at': {'$lt': cutoff.isoformat()}}
            )
            
        except Exception as e:
            logger.debug(f"[SHARP] Cleanup error: {e}")
    
    # =========================================================================
    # REAL SHARP TRADER METHODS (Using Collected Data)
    # =========================================================================
    
    async def _check_real_sharp_activity(self, market_id: str) -> bool:
        """Check if there's real sharp trader activity in a market"""
        try:
            # Check for recent sharp positions in this market
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            
            sharp_position = await self.db.sharp_positions.find_one({
                'market_id': market_id,
                'updated_at': {'$gte': recent_cutoff.isoformat()}
            })
            
            return sharp_position is not None
            
        except Exception as e:
            logger.debug(f"[SHARP] Real activity check error: {e}")
            return False
    
    async def _get_real_sharp_direction(self, market_id: str) -> Optional[str]:
        """Get consensus direction from real sharp trader positions"""
        try:
            positions = await self.db.sharp_positions.find(
                {'market_id': market_id},
                {'_id': 0, 'side': 1, 'volume': 1}
            ).to_list(50)
            
            if not positions:
                return None
            
            yes_volume = sum(p.get('volume', 0) for p in positions if p.get('side') == 'YES')
            no_volume = sum(p.get('volume', 0) for p in positions if p.get('side') == 'NO')
            
            total = yes_volume + no_volume
            if total == 0:
                return None
            
            # Require 60% consensus
            if yes_volume / total >= 0.6:
                return 'YES'
            elif no_volume / total >= 0.6:
                return 'NO'
            
            return None
            
        except Exception as e:
            logger.debug(f"[SHARP] Real direction check error: {e}")
            return None
    
    # =========================================================================
    # EXISTING METHODS (Preserved)
    # =========================================================================
    
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
            
            if address == 'unknown':
                continue
            
            if address not in trader_data:
                trader_data[address] = {
                    'trades': [],
                    'total_volume': 0,
                    'positive_movements': 0,
                    'total_movements': 0,
                    'categories': set(),
                    'markets': set()
                }
            
            trader_data[address]['trades'].append(trade)
            trader_data[address]['total_volume'] += trade.get('volume', 0)
            trader_data[address]['categories'].add(trade.get('category', 'unknown'))
            trader_data[address]['markets'].add(trade.get('market_id', 'unknown'))
            
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
                    'num_markets': len(data['markets']),
                    'category_focus': max(data['categories'], key=lambda x: sum(1 for t in data['trades'] if t.get('category') == x)) if data['categories'] else 'unknown',
                    'category_concentration': len(data['categories'])
                }
        
        return stats
    
    def _calculate_line_movement(self, trade: Dict) -> float:
        """Calculate line movement PNL after trade"""
        entry_price = trade.get('price', 0.5)
        final_price = trade.get('final_price', entry_price)
        size = trade.get('size', 0)
        side = trade.get('side', 'YES')
        
        if side == 'YES':
            return (final_price - entry_price) * size
        else:
            return (entry_price - final_price) * size
    
    def _is_sharp_trader(self, stats: Dict) -> bool:
        """Determine if trader qualifies as sharp"""
        win_rate = stats.get('win_rate', 0)
        volume = stats.get('total_volume', 0)
        num_trades = stats.get('num_trades', 0)
        concentration = stats.get('category_concentration', 5)
        
        return (
            win_rate >= self.sharp_threshold and
            volume >= self.sharp_min_volume and
            num_trades >= self.min_trades and
            concentration <= 3  # Relaxed to allow some diversification
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
            # First try the new sharp_positions collection
            positions = await self.db.sharp_positions.find(
                {'market_id': market_id},
                {'_id': 0}
            ).to_list(100)
            
            if positions:
                return positions
            
            # Fallback to old method
            sharp_traders = await self.db.sharp_traders.find({}, {"address": 1, "_id": 0}).to_list(length=100)
            addresses = [t['address'] for t in sharp_traders]
            
            if not addresses:
                return []
            
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
                    "num_trades": stats['num_trades'],
                    "num_markets": stats.get('num_markets', 0),
                    "category_focus": stats['category_focus'],
                    "identified_at": datetime.now(timezone.utc).isoformat(),
                    "last_activity": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            logger.debug(f"[SHARP] Stored sharp trader: {address[:16]}... (WR: {stats['win_rate']:.1%})")
        except Exception as e:
            logger.error(f"Error storing sharp trader: {e}")
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def _get_cached_sharp_status(self, market_id: str) -> Optional[Dict]:
        """Get cached sharp status if still valid"""
        cached = self._sharp_cache.get(market_id)
        if cached:
            age = (datetime.now(timezone.utc) - cached['timestamp']).total_seconds()
            if age < self._cache_ttl:
                return cached
        return None
    
    def _cache_sharp_status(self, market_id: str, is_active: bool, direction: Optional[str]):
        """Cache sharp status for performance"""
        self._sharp_cache[market_id] = {
            'is_active': is_active,
            'direction': direction,
            'timestamp': datetime.now(timezone.utc)
        }
    
    # =========================================================================
    # STATS & MONITORING
    # =========================================================================
    
    async def get_stats(self) -> Dict:
        """Get sharp detector statistics"""
        try:
            sharp_count = await self.db.sharp_traders.count_documents({})
            trade_count = await self.db.market_trades.count_documents({})
            position_count = await self.db.sharp_positions.count_documents({})
            
            return {
                'sharp_traders_identified': sharp_count,
                'trades_collected': trade_count,
                'active_positions_tracked': position_count,
                'background_tasks_running': self._running,
                'cache_size': len(self._sharp_cache)
            }
        except Exception as e:
            logger.error(f"[SHARP] Stats error: {e}")
            return {}
