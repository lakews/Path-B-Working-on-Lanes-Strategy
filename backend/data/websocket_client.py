import json
import logging
from typing import Dict, Any, Optional, Callable
import aiohttp

logger = logging.getLogger(__name__)

class PolymarketWebSocket:
    """WebSocket client for Polymarket CLOB real-time data"""
    
    def __init__(self):
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.running = False
        self.callbacks: Dict[str, list] = {}
        
    async def connect(self):
        """Connect to Polymarket WebSocket"""
        try:
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(self.ws_url)
            self.running = True
            logger.info("Connected to Polymarket WebSocket")
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        logger.info("Disconnected from Polymarket WebSocket")
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to specific event types"""
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)
    
    async def subscribe_to_market(self, market_id: str):
        """Subscribe to specific market updates"""
        if self.ws:
            await self.ws.send_json({
                "type": "subscribe",
                "market": market_id
            })
            logger.info(f"Subscribed to market: {market_id}")
    
    async def listen(self):
        """Listen for WebSocket messages"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
        except Exception as e:
            logger.error(f"Error in WebSocket listener: {e}")
        finally:
            await self.disconnect()
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        event_type = data.get('type', 'unknown')
        
        if event_type in self.callbacks:
            for callback in self.callbacks[event_type]:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in callback for {event_type}: {e}")