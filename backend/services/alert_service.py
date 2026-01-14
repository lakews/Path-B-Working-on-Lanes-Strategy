"""
SendGrid Email Alerts System for APEX TRADER
Sends alerts for trading events: whale activity, sentiment shifts, drawdowns, trade executions
"""
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content
from database import get_db

logger = logging.getLogger(__name__)

class AlertType:
    WHALE_ACTIVITY = "whale_activity"
    SENTIMENT_SHIFT = "sentiment_shift"
    DRAWDOWN_ALERT = "drawdown_alert"
    TRADE_EXECUTED = "trade_executed"
    BACKTEST_COMPLETE = "backtest_complete"
    RISK_THRESHOLD = "risk_threshold"

class AlertService:
    """SendGrid-based alert system for trading notifications"""
    
    def __init__(self):
        self._db = None
        self.sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        self.sender_email = os.environ.get('ALERT_SENDER_EMAIL', 'alerts@apextrader.com')
        self.enabled = bool(self.sendgrid_api_key)
        
        # Alert thresholds (configurable)
        self.thresholds = {
            'whale_activity_min': 0.7,  # Whale score threshold
            'sentiment_shift_min': 0.3,  # Minimum sentiment change
            'drawdown_max': 0.05,  # 5% drawdown triggers alert
            'profit_notification_min': 50.0  # Notify on $50+ trades
        }
        
        # Cooldown tracking (prevent alert spam)
        self.last_alert_times: Dict[str, datetime] = {}
        self.cooldown_minutes = {
            AlertType.WHALE_ACTIVITY: 15,
            AlertType.SENTIMENT_SHIFT: 30,
            AlertType.DRAWDOWN_ALERT: 60,
            AlertType.TRADE_EXECUTED: 5,
            AlertType.BACKTEST_COMPLETE: 0,
            AlertType.RISK_THRESHOLD: 30
        }
        
        if self.enabled:
            logger.info("AlertService initialized with SendGrid")
        else:
            logger.warning("AlertService: SendGrid API key not configured - alerts disabled")
    
    @property
    def db(self):
        """Lazy database connection"""
        if self._db is None:
            self._db = get_db()
        return self._db
    
    def _can_send_alert(self, alert_type: str) -> bool:
        """Check if alert is allowed (cooldown period)"""
        if alert_type not in self.last_alert_times:
            return True
        
        last_time = self.last_alert_times[alert_type]
        cooldown = self.cooldown_minutes.get(alert_type, 10)
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
        
        return elapsed >= cooldown
    
    def _record_alert(self, alert_type: str):
        """Record alert timestamp for cooldown tracking"""
        self.last_alert_times[alert_type] = datetime.now(timezone.utc)
    
    async def send_email(self, recipient: str, subject: str, html_content: str) -> bool:
        """Send email via SendGrid"""
        if not self.enabled:
            logger.warning("Email alerts disabled - no SendGrid API key")
            return False
        
        try:
            message = Mail(
                from_email=self.sender_email,
                to_emails=recipient,
                subject=subject,
                html_content=html_content
            )
            
            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)
            
            success = response.status_code in [200, 202]
            if success:
                logger.info(f"Alert email sent to {recipient}: {subject}")
            else:
                logger.error(f"SendGrid error: {response.status_code}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False
    
    async def send_whale_alert(self, recipient: str, market_id: str, whale_data: Dict) -> bool:
        """Send whale activity alert"""
        if not self._can_send_alert(AlertType.WHALE_ACTIVITY):
            return False
        
        whale_score = whale_data.get('whale_activity_score', 0)
        if whale_score < self.thresholds['whale_activity_min']:
            return False
        
        direction = whale_data.get('whale_direction', 'unknown')
        direction_emoji = "🐂" if direction == 'bullish' else "🐻" if direction == 'bearish' else "⚖️"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 24px; border: 1px solid #0f3460;">
                <h1 style="color: #f59e0b; margin: 0 0 16px 0;">🐋 Whale Activity Detected</h1>
                
                <div style="background: rgba(245, 158, 11, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <p style="margin: 0; color: #fbbf24;"><strong>Whale Score:</strong> {whale_score:.0%}</p>
                    <p style="margin: 8px 0 0 0; color: #fbbf24;"><strong>Direction:</strong> {direction_emoji} {direction.capitalize()}</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Market ID</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{market_id[:20]}...</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Confidence</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{whale_data.get('confidence', 0):.0%}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><span style="color: #94a3b8;">Volume Spike</span></td>
                        <td style="padding: 8px 0; text-align: right;"><span style="color: {'#10b981' if whale_data.get('volume_spike') else '#ef4444'};">{'Yes' if whale_data.get('volume_spike') else 'No'}</span></td>
                    </tr>
                </table>
                
                <p style="color: #64748b; font-size: 12px; margin-top: 20px; text-align: center;">
                    APEX TRADER Alert System • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        success = await self.send_email(
            recipient,
            f"🐋 Whale Alert: {direction.capitalize()} Activity ({whale_score:.0%})",
            html
        )
        
        if success:
            self._record_alert(AlertType.WHALE_ACTIVITY)
            await self._store_alert_history(AlertType.WHALE_ACTIVITY, recipient, whale_data)
        
        return success
    
    async def send_sentiment_alert(self, recipient: str, market_id: str, sentiment_data: Dict, previous_sentiment: float) -> bool:
        """Send sentiment shift alert"""
        if not self._can_send_alert(AlertType.SENTIMENT_SHIFT):
            return False
        
        current = sentiment_data.get('overall_sentiment', 0.5)
        shift = abs(current - previous_sentiment)
        
        if shift < self.thresholds['sentiment_shift_min']:
            return False
        
        direction = "bullish" if current > previous_sentiment else "bearish"
        color = "#10b981" if direction == "bullish" else "#ef4444"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 24px; border: 1px solid #0f3460;">
                <h1 style="color: #8b5cf6; margin: 0 0 16px 0;">📊 Sentiment Shift Alert</h1>
                
                <div style="background: rgba(139, 92, 246, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <p style="margin: 0; font-size: 24px; text-align: center;">
                        <span style="color: #94a3b8;">{previous_sentiment:.0%}</span>
                        <span style="color: {color}; margin: 0 12px;">→</span>
                        <span style="color: {color};">{current:.0%}</span>
                    </p>
                    <p style="margin: 8px 0 0 0; text-align: center; color: {color};">
                        {'+' if current > previous_sentiment else ''}{(current - previous_sentiment) * 100:.1f}% ({direction})
                    </p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Confidence</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{sentiment_data.get('confidence', 0):.0%}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">News Sentiment</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{sentiment_data.get('news_sentiment', 0):.0%}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><span style="color: #94a3b8;">Social Sentiment</span></td>
                        <td style="padding: 8px 0; text-align: right;"><span style="color: #fff;">{sentiment_data.get('social_sentiment', 0):.0%}</span></td>
                    </tr>
                </table>
                
                <p style="color: #64748b; font-size: 12px; margin-top: 20px; text-align: center;">
                    APEX TRADER Alert System • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        success = await self.send_email(
            recipient,
            f"📊 Sentiment Alert: {direction.capitalize()} Shift ({shift:.0%})",
            html
        )
        
        if success:
            self._record_alert(AlertType.SENTIMENT_SHIFT)
            await self._store_alert_history(AlertType.SENTIMENT_SHIFT, recipient, {
                'market_id': market_id,
                'previous': previous_sentiment,
                'current': current,
                'shift': shift
            })
        
        return success
    
    async def send_drawdown_alert(self, recipient: str, current_drawdown: float, equity: float, peak_equity: float) -> bool:
        """Send drawdown threshold alert"""
        if not self._can_send_alert(AlertType.DRAWDOWN_ALERT):
            return False
        
        if current_drawdown < self.thresholds['drawdown_max']:
            return False
        
        severity = "critical" if current_drawdown > 0.1 else "warning"
        color = "#ef4444" if severity == "critical" else "#f59e0b"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 24px; border: 1px solid {color};">
                <h1 style="color: {color}; margin: 0 0 16px 0;">⚠️ Drawdown Alert ({severity.upper()})</h1>
                
                <div style="background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 16px; text-align: center;">
                    <p style="margin: 0; font-size: 36px; color: {color}; font-weight: bold;">-{current_drawdown:.1%}</p>
                    <p style="margin: 8px 0 0 0; color: #94a3b8;">Current Drawdown</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Current Equity</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">${equity:,.2f}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Peak Equity</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">${peak_equity:,.2f}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><span style="color: #94a3b8;">Loss Amount</span></td>
                        <td style="padding: 8px 0; text-align: right;"><span style="color: #ef4444;">-${peak_equity - equity:,.2f}</span></td>
                    </tr>
                </table>
                
                <div style="background: rgba(239, 68, 68, 0.2); border-radius: 8px; padding: 12px; margin-top: 16px;">
                    <p style="margin: 0; color: #fca5a5; font-size: 14px;">
                        ⚠️ Consider reviewing your positions and risk management settings.
                    </p>
                </div>
                
                <p style="color: #64748b; font-size: 12px; margin-top: 20px; text-align: center;">
                    APEX TRADER Alert System • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        success = await self.send_email(
            recipient,
            f"⚠️ Drawdown Alert: -{current_drawdown:.1%} ({severity.upper()})",
            html
        )
        
        if success:
            self._record_alert(AlertType.DRAWDOWN_ALERT)
            await self._store_alert_history(AlertType.DRAWDOWN_ALERT, recipient, {
                'drawdown': current_drawdown,
                'equity': equity,
                'peak_equity': peak_equity,
                'severity': severity
            })
        
        return success
    
    async def send_trade_alert(self, recipient: str, trade: Dict) -> bool:
        """Send trade execution alert for significant trades"""
        pnl = trade.get('pnl', 0)
        
        # Only alert for significant trades
        if abs(pnl) < self.thresholds['profit_notification_min']:
            return False
        
        is_profit = pnl > 0
        color = "#10b981" if is_profit else "#ef4444"
        emoji = "💰" if is_profit else "📉"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 24px; border: 1px solid #0f3460;">
                <h1 style="color: {color}; margin: 0 0 16px 0;">{emoji} Trade {'Profit' if is_profit else 'Loss'} Alert</h1>
                
                <div style="background: rgba({'16, 185, 129' if is_profit else '239, 68, 68'}, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 16px; text-align: center;">
                    <p style="margin: 0; font-size: 36px; color: {color}; font-weight: bold;">
                        {'+' if is_profit else '-'}${abs(pnl):.2f}
                    </p>
                    <p style="margin: 8px 0 0 0; color: #94a3b8;">P&L</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Strategy</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{trade.get('strategy', 'N/A')}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Entry Price</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">${trade.get('entry_price', 0):.4f}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Exit Price</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">${trade.get('exit_price', 0):.4f}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><span style="color: #94a3b8;">Return</span></td>
                        <td style="padding: 8px 0; text-align: right;"><span style="color: {color};">{trade.get('return_pct', 0):.2f}%</span></td>
                    </tr>
                </table>
                
                <p style="color: #64748b; font-size: 12px; margin-top: 20px; text-align: center;">
                    APEX TRADER Alert System • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        success = await self.send_email(
            recipient,
            f"{emoji} Trade Alert: {'+' if is_profit else '-'}${abs(pnl):.2f} ({trade.get('strategy', 'N/A')})",
            html
        )
        
        if success:
            await self._store_alert_history(AlertType.TRADE_EXECUTED, recipient, trade)
        
        return success
    
    async def send_backtest_complete_alert(self, recipient: str, results: Dict) -> bool:
        """Send backtest completion alert"""
        pnl = results.get('total_pnl', 0)
        is_profit = pnl > 0
        color = "#10b981" if is_profit else "#ef4444"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #1a1a2e; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 24px; border: 1px solid #0f3460;">
                <h1 style="color: #06b6d4; margin: 0 0 16px 0;">✅ Backtest Complete</h1>
                
                <div style="background: rgba({'16, 185, 129' if is_profit else '239, 68, 68'}, 0.1); border-radius: 8px; padding: 16px; margin-bottom: 16px; text-align: center;">
                    <p style="margin: 0; font-size: 36px; color: {color}; font-weight: bold;">
                        {'+' if is_profit else ''}{results.get('total_return_pct', 0):.2f}%
                    </p>
                    <p style="margin: 8px 0 0 0; color: #94a3b8;">Total Return (${pnl:,.2f})</p>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Total Trades</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{results.get('total_trades', 0)}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Win Rate</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{results.get('win_rate', 0) * 100:.1f}%</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333;"><span style="color: #94a3b8;">Sharpe Ratio</span></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #333; text-align: right;"><span style="color: #fff;">{results.get('sharpe_ratio', 0):.2f}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><span style="color: #94a3b8;">Max Drawdown</span></td>
                        <td style="padding: 8px 0; text-align: right;"><span style="color: #ef4444;">-{results.get('max_drawdown', 0) * 100:.2f}%</span></td>
                    </tr>
                </table>
                
                <p style="color: #64748b; font-size: 12px; margin-top: 20px; text-align: center;">
                    APEX TRADER Alert System • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        success = await self.send_email(
            recipient,
            f"✅ Backtest Complete: {'+' if is_profit else ''}{results.get('total_return_pct', 0):.2f}% Return",
            html
        )
        
        if success:
            await self._store_alert_history(AlertType.BACKTEST_COMPLETE, recipient, {
                'backtest_id': results.get('backtest_id'),
                'total_pnl': pnl,
                'total_return_pct': results.get('total_return_pct')
            })
        
        return success
    
    async def _store_alert_history(self, alert_type: str, recipient: str, data: Dict):
        """Store alert in database for history tracking"""
        try:
            await self.db.alert_history.insert_one({
                "alert_type": alert_type,
                "recipient": recipient,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to store alert history: {e}")
    
    async def get_alert_history(self, limit: int = 50) -> List[Dict]:
        """Get recent alert history"""
        try:
            cursor = self.db.alert_history.find(
                {},
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error fetching alert history: {e}")
            return []
    
    async def get_alert_config(self) -> Dict:
        """Get current alert configuration"""
        return {
            "enabled": self.enabled,
            "sender_email": self.sender_email,
            "thresholds": self.thresholds,
            "cooldowns_minutes": self.cooldown_minutes
        }
    
    async def update_thresholds(self, new_thresholds: Dict):
        """Update alert thresholds"""
        self.thresholds.update(new_thresholds)
        logger.info(f"Alert thresholds updated: {self.thresholds}")


# Singleton instance
alert_service = AlertService()
