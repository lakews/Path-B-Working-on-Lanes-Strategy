"""
Market Alerts Service
Real-time alerts for high-volume markets with significant price changes.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from database import get_db

logger = logging.getLogger(__name__)


class MarketAlertsService:
    """
    Monitors markets for significant events and triggers alerts.
    
    Alert Types:
    1. Volume Spike: Market volume increases significantly vs average
    2. Price Movement: Large price swing in short time
    3. High Opportunity: Strong signal from sentiment/ML models
    """
    
    # Default thresholds (can be overridden from config)
    DEFAULT_VOLUME_SPIKE_THRESHOLD = 2.0  # 2x average volume
    DEFAULT_PRICE_CHANGE_THRESHOLD = 0.05  # 5% price change
    DEFAULT_MIN_LIQUIDITY = 5000  # Min $5k for alerts
    
    def __init__(self, ws_manager=None):
        self.db = get_db()
        self.ws_manager = ws_manager
        self.running = False
        self.alerts_enabled = False
        self.volume_threshold = self.DEFAULT_VOLUME_SPIKE_THRESHOLD
        self.price_threshold = self.DEFAULT_PRICE_CHANGE_THRESHOLD
        self.min_liquidity = self.DEFAULT_MIN_LIQUIDITY
        
        # Track recent prices for change detection
        self.price_history: Dict[str, List[Dict]] = {}
        self.recent_alerts: List[Dict] = []  # Keep last 50 alerts
        self.alerted_markets: Set[str] = set()  # Debounce alerts
        
    async def load_config(self):
        """Load alert configuration from database"""
        try:
            config = await self.db.user_config.find_one(
                {"type": "trading_preferences"},
                {"_id": 0}
            )
            if config:
                self.alerts_enabled = config.get("alerts_enabled", False)
                self.volume_threshold = config.get("alert_volume_threshold", self.DEFAULT_VOLUME_SPIKE_THRESHOLD)
                logger.info(f"Alerts config loaded: enabled={self.alerts_enabled}, volume_threshold={self.volume_threshold}x")
        except Exception as e:
            logger.error(f"Failed to load alerts config: {e}")
    
    async def check_market(self, market_data: Dict) -> Optional[Dict]:
        """
        Check a single market for alert conditions.
        Returns alert dict if conditions met, None otherwise.
        """
        if not self.alerts_enabled:
            return None
            
        market_id = market_data.get('id', '')
        
        # Skip if recently alerted (debounce 5 min)
        if market_id in self.alerted_markets:
            return None
        
        # Extract market info
        liquidity = float(market_data.get('liquidity', 0) or 0)
        volume_24h = float(market_data.get('volume24hr', 0) or 0)
        yes_price = float(market_data.get('yes_price', 0.5) or 0.5)
        question = market_data.get('question', 'Unknown Market')[:100]
        asset_class = market_data.get('category', 'unknown')
        
        # Skip low liquidity markets
        if liquidity < self.min_liquidity:
            return None
        
        alert = None
        
        # Check for volume spike
        if volume_24h > 0:
            # Simple heuristic: high volume relative to liquidity suggests activity
            volume_to_liquidity = volume_24h / max(liquidity, 1)
            if volume_to_liquidity > self.volume_threshold:
                alert = {
                    "type": "volume_spike",
                    "severity": "high" if volume_to_liquidity > self.volume_threshold * 1.5 else "medium",
                    "market_id": market_id,
                    "question": question,
                    "asset_class": asset_class,
                    "volume_24h": volume_24h,
                    "liquidity": liquidity,
                    "volume_ratio": round(volume_to_liquidity, 2),
                    "current_price": yes_price,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"🔥 Volume spike detected: {volume_to_liquidity:.1f}x volume/liquidity ratio"
                }
        
        # Check for price movement
        if market_id in self.price_history:
            history = self.price_history[market_id]
            if len(history) >= 2:
                old_price = history[0]['price']
                price_change = abs(yes_price - old_price)
                if price_change >= self.price_threshold:
                    direction = "📈" if yes_price > old_price else "📉"
                    alert = {
                        "type": "price_movement",
                        "severity": "high" if price_change > self.price_threshold * 2 else "medium",
                        "market_id": market_id,
                        "question": question,
                        "asset_class": asset_class,
                        "old_price": old_price,
                        "current_price": yes_price,
                        "price_change_pct": round(price_change * 100, 2),
                        "liquidity": liquidity,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"{direction} Price moved {price_change*100:.1f}%: {old_price:.2f} → {yes_price:.2f}"
                    }
        
        # Update price history
        self._update_price_history(market_id, yes_price)
        
        # If we have an alert, record it
        if alert:
            self._record_alert(alert)
            self.alerted_markets.add(market_id)
            # Schedule debounce removal after 5 minutes
            asyncio.create_task(self._remove_debounce(market_id, 300))
            
        return alert
    
    def _update_price_history(self, market_id: str, price: float):
        """Keep last 10 price points per market"""
        if market_id not in self.price_history:
            self.price_history[market_id] = []
        
        self.price_history[market_id].append({
            "price": price,
            "timestamp": datetime.now(timezone.utc)
        })
        
        # Keep only last 10
        if len(self.price_history[market_id]) > 10:
            self.price_history[market_id] = self.price_history[market_id][-10:]
    
    def _record_alert(self, alert: Dict):
        """Keep last 50 alerts"""
        self.recent_alerts.insert(0, alert)
        if len(self.recent_alerts) > 50:
            self.recent_alerts = self.recent_alerts[:50]
    
    async def _remove_debounce(self, market_id: str, delay_seconds: int):
        """Remove market from debounce set after delay"""
        await asyncio.sleep(delay_seconds)
        self.alerted_markets.discard(market_id)
    
    async def broadcast_alert(self, alert: Dict):
        """Send alert to all connected WebSocket clients"""
        if self.ws_manager:
            await self.ws_manager.broadcast({
                "type": "market_alert",
                "data": alert
            })
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Get recent alerts"""
        return self.recent_alerts[:limit]
    
    def clear_alerts(self):
        """Clear all alerts"""
        self.recent_alerts = []
        self.alerted_markets.clear()
        self.price_history.clear()


# Global instance
market_alerts_service: Optional[MarketAlertsService] = None


def get_market_alerts_service(ws_manager=None) -> MarketAlertsService:
    """Get or create the market alerts service"""
    global market_alerts_service
    if market_alerts_service is None:
        market_alerts_service = MarketAlertsService(ws_manager)
    return market_alerts_service
