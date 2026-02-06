from fastapi import FastAPI, APIRouter, BackgroundTasks, Query, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import asyncio
import secrets
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set, Any
from datetime import datetime, timezone, timedelta

from database import connect_db, close_db, get_db
from config import config
from trading_bot import ApexTrader
from services.performance_analytics import PerformanceAnalytics
from schemas.analytics import ComprehensiveMetricsResponse, LaneMetric
from backtest.backtest_engine import BacktestEngine
from data.historical_collector import HistoricalDataCollector
from ml.rl_engine import RLAdaptiveEngine
from ml.social_sentiment import social_sentiment_analyzer
from ml.whale_tracker import whale_tracker
from ml.strategy_tuner import strategy_tuner
from ml.market_classifier import (
    get_ambiguity_matrix, get_default_ambiguity_matrix, update_ambiguity_matrix
)
from auth import (
    create_access_token, authenticate_user, get_current_user, get_current_user_optional,
    create_user, init_default_admin, Token, UserCreate, UserLogin, UserResponse,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from services.market_alerts import get_market_alerts_service, MarketAlertsService
from services.news_injector import get_news_injector, NewsInjector
from services.signal_cache import get_signal_cache, EmergentSignalCache
from services.webhook_sources import get_webhook_sources_manager, WebhookSourcesManager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the main app
app = FastAPI(title="APEX TRADER API", version="1.0.0")

# =============================================
# AUTHENTICATION (Dual-mode: Basic Auth + JWT)
# =============================================
security = HTTPBasic(auto_error=False)

# Get credentials from environment or use defaults
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'apex2026!')

async def verify_credentials_dual(
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
    current_user = Depends(get_current_user_optional)
):
    """
    Verify authentication via either:
    1. JWT Bearer token (preferred)
    2. HTTP Basic Auth (legacy fallback)
    """
    # First try JWT authentication
    if current_user:
        return current_user.get("username", "jwt_user")
    
    # Fall back to HTTP Basic Auth
    if credentials:
        correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
        correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
        if correct_username and correct_password:
            return credentials.username
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer, Basic"},
    )

# Keep old function for backward compatibility
def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials for sensitive endpoints (legacy)"""
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global trading bot instance
trading_bot: Optional[ApexTrader] = None
analytics_engine: Optional[PerformanceAnalytics] = None
backtest_engine: Optional[BacktestEngine] = None
historical_collector: Optional[HistoricalDataCollector] = None
rl_engine: Optional[RLAdaptiveEngine] = None
news_injector: Optional[NewsInjector] = None  # Lane 5: News/Emergent
trading_mode: str = "stopped"  # "stopped", "live", "backtest", "paper"
paper_trading_enabled: bool = False  # Paper trading flag


# =============================================
# MARKET FETCHER FOR NEWS INJECTOR (Lane 5)
# =============================================

async def get_active_markets_for_news() -> List[Dict]:
    """
    Fetch active markets for the NewsInjector to analyze news against.
    
    This function is passed to NewsInjector as market_fetcher.
    Returns markets with valid prices from Gamma API or DB fallback.
    """
    try:
        from data.polymarket_api import PolymarketAPI
        
        # Try Gamma API first for fresh data
        try:
            async with PolymarketAPI() as api:
                raw_markets = await api.get_markets(limit=100)
                
                if raw_markets:
                    markets = []
                    for m in raw_markets:
                        raw_yes = m.get('yes_price')
                        if raw_yes is None or raw_yes == 0:
                            continue
                        
                        yes_price = float(raw_yes)
                        raw_no = m.get('no_price')
                        no_price = float(raw_no) if raw_no and raw_no != 0 else (1 - yes_price)
                        
                        markets.append({
                            "id": m.get('condition_id') or m.get('id'),
                            "question": m.get('question', ''),
                            "description": m.get('description', ''),
                            "category": m.get('category', 'unknown'),
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "volume_24h": float(m.get('volume_24h', 0) or 0),
                            "liquidity": float(m.get('liquidity', 0) or 0),
                            "active": m.get('active', True)
                        })
                    
                    if markets:
                        logger.info(f"[MARKET FETCHER] Returning {len(markets)} markets from Gamma API")
                        return markets
        except Exception as api_error:
            logger.warning(f"[MARKET FETCHER] Gamma API failed: {api_error}")
        
        # Fallback: Get from database
        db = get_db()
        cursor = db.markets.find(
            {"active": True, "yes_price": {"$gt": 0}},
            {"_id": 0}
        ).limit(100)
        
        markets = await cursor.to_list(length=100)
        logger.info(f"[MARKET FETCHER] Returning {len(markets)} markets from DB fallback")
        return markets
        
    except Exception as e:
        logger.error(f"[MARKET FETCHER] Error fetching markets: {e}")
        return []


# =============================================
# WEBSOCKET CONNECTION MANAGER
# =============================================

class WebSocketConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Active connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Active connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        if not self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)
    
    async def start_broadcast_loop(self):
        """Start periodic broadcasting of updates"""
        self._running = True
        while self._running:
            try:
                if self.active_connections:
                    update = await self._gather_update_data()
                    await self.broadcast(update)
                await asyncio.sleep(2)  # Broadcast every 2 seconds
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(5)
    
    async def stop_broadcast_loop(self):
        """Stop the broadcast loop"""
        self._running = False
    
    async def _gather_update_data(self) -> dict:
        """Gather data for real-time updates"""
        global trading_mode, trading_bot, backtest_engine
        
        db = get_db()
        
        # Get recent trades
        recent_trades = []
        try:
            cursor = db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(5)
            recent_trades = await cursor.to_list(length=5)
        except Exception:
            pass
        
        # Get P&L
        total_pnl = 0.0
        try:
            pipeline = [{"$group": {"_id": None, "total_pnl": {"$sum": "$pnl"}}}]
            result = await db.trades.aggregate(pipeline).to_list(length=1)
            total_pnl = result[0]["total_pnl"] if result else 0.0
        except Exception:
            pass
        
        # Get open positions count
        open_positions = 0
        try:
            open_positions = await db.positions.count_documents({"status": "open"})
        except Exception:
            pass
        
        # Backtest status
        backtest_status = None
        if backtest_engine and backtest_engine.running:
            backtest_status = {
                "running": True,
                "backtest_id": backtest_engine.backtest_id,
                "progress": len(backtest_engine.trades) if backtest_engine else 0,
                "current_capital": backtest_engine.current_capital if backtest_engine else 0
            }
        
        return {
            "type": "update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trading_mode": trading_mode,
            "bot_running": trading_bot.running if trading_bot else False,
            "total_pnl": float(total_pnl),
            "open_positions": open_positions,
            "recent_trades": recent_trades,
            "backtest_status": backtest_status
        }

# Global WebSocket manager
ws_manager = WebSocketConnectionManager()

# Models
class SystemStatus(BaseModel):
    status: str
    bot_running: bool
    trading_mode: str
    configuration: Dict
    timestamp: str

class PerformanceResponse(BaseModel):
    total_capital: float
    total_pnl: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    num_trades: int
    num_positions: int

class StrategyExitParams(BaseModel):
    take_profit: Optional[float] = None  # e.g., 0.02 = 2%
    stop_loss: Optional[float] = None    # e.g., -0.02 = -2%
    max_hours: Optional[float] = None    # e.g., 4 = 4 hours

class AssetClassExitMultipliers(BaseModel):
    tp_mult: Optional[float] = None      # Take profit multiplier
    sl_mult: Optional[float] = None      # Stop loss multiplier  
    time_mult: Optional[float] = None    # Time limit multiplier

class TradingConfig(BaseModel):
    trades_per_10min: Optional[int] = None
    initial_capital: Optional[float] = None
    capital_deployment_pct: Optional[float] = None
    max_position_size_pct: Optional[float] = None
    kelly_fraction: Optional[float] = None
    kelly_enabled: Optional[bool] = None  # Toggle Kelly Criterion on/off
    max_drawdown_pct: Optional[float] = None
    # Market selection filters
    min_liquidity: Optional[float] = None
    max_liquidity: Optional[float] = None  # New: max liquidity filter
    min_volume_24h: Optional[float] = None
    max_spread: Optional[float] = None
    max_open_positions: Optional[int] = None
    # Stuck price filter
    stuck_price_multiplier: Optional[float] = None  # Volume multiplier for stuck prices (0.0, 0.5, 1.0)
    enabled_asset_classes: Optional[List[str]] = None
    enabled_strategies: Optional[List[str]] = None
    # Exit parameters per strategy
    exit_params: Optional[Dict[str, StrategyExitParams]] = None
    # Asset class exit multipliers
    asset_class_exit_multipliers: Optional[Dict[str, AssetClassExitMultipliers]] = None
    # Advanced position sizing parameters
    min_kelly_fraction: Optional[float] = None      # Min Kelly bound (default 0.10)
    max_kelly_fraction: Optional[float] = None      # Max Kelly bound (default 0.50)
    min_position_size: Optional[float] = None       # Minimum position in USD (default 5)
    min_liquidity_for_full_size: Optional[float] = None  # Volume needed for full position (default 10000)
    # Market alerts configuration
    alerts_enabled: Optional[bool] = None           # Enable real-time alerts
    alert_volume_threshold: Optional[float] = None  # Volume spike threshold (e.g., 2.0 = 2x avg)
    # Strategy selection thresholds (configurable)
    volatility_threshold: Optional[float] = None    # Threshold for volatility strategy (default 0.06)
    sentiment_strength_threshold: Optional[float] = None  # Threshold for alpha directional (default 0.25)
    sharp_alignment_threshold: Optional[float] = None     # Threshold for arbitrage (default 0.8)
    delta_neutral_price_min: Optional[float] = None       # Min price for delta neutral (default 0.40)
    delta_neutral_price_max: Optional[float] = None       # Max price for delta neutral (default 0.70)
    # Sentiment-based side selection thresholds
    bullish_sentiment_threshold: Optional[float] = None   # Above this → YES (default 0.55)
    bearish_sentiment_threshold: Optional[float] = None   # Below this → NO (default 0.45)
    # NEW: Polymarket Position Sizer Configuration
    use_polymarket_sizer: Optional[bool] = None           # Toggle new vs legacy sizer
    polymarket_fee_pct: Optional[float] = None            # Exit fee (default 0.02 = 2%)
    sector_caps: Optional[Dict[str, float]] = None        # Max portfolio allocation per category
    oracle_multipliers: Optional[Dict[str, float]] = None # Oracle risk multipliers by category
    # Event Caps Configuration
    event_caps: Optional[Dict[str, float]] = None         # Event concentration limits
    
    # ==============================================================
    # TWO-SPEED ARCHITECTURE CONFIGURATION (HFT/Alpha)
    # ==============================================================
    hft_allocation_pct: Optional[float] = None            # % of deployed capital to HFT
    alpha_allocation_pct: Optional[float] = None          # % of deployed capital to Alpha
    hft_max_position_pct: Optional[float] = None          # Max position as % of HFT capital
    alpha_max_position_pct: Optional[float] = None        # Max position as % of Alpha capital
    hft_positions_pct: Optional[float] = None             # % of global max positions for HFT
    alpha_positions_pct: Optional[float] = None           # % of global max positions for Alpha
    # Strategy Risk Multipliers
    strategy_risk_multipliers: Optional[Dict[str, float]] = None  # Per-strategy sizing multipliers
    # Expiry Thresholds
    expiry_thresholds: Optional[Dict[str, Any]] = None    # Time-to-expiry thresholds
    # Strategy Expiry Adjustments  
    expiry_strategy_adjustments: Optional[Dict[str, Any]] = None  # Per-strategy expiry behavior
    # HFT Execution Parameters
    hft_execution: Optional[Dict[str, Any]] = None        # Inventory skew, OFI settings
    # Spread Policy
    spread_policy: Optional[Dict[str, float]] = None      # Max spreads, fees, EV params
    # Variance Sizing (Tail Risk)
    variance_sizing: Optional[Dict[str, float]] = None    # Kill switch thresholds

# Default event caps (used for reset)
DEFAULT_EVENT_CAPS = {
    "max_event_exposure_pct": 0.15,  # 15% max per correlated event
    "similarity_threshold": 0.60,    # 60% question similarity = same event
}

# Store user config preferences
user_config = {
    "enabled_asset_classes": ["finance", "politics", "sports", "crypto", "entertainment", "science"],
    "enabled_strategies": ["delta_neutral", "volatility_exploitation", "alpha_directional", "arbitrage"]
}

# Routes
@api_router.get("/")
async def root():
    return {
        "message": "APEX TRADER - Advanced Polymarket Execution System",
        "version": "1.0.0",
        "status": "operational"
    }

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@api_router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get system status and configuration"""
    global trading_mode, backtest_engine, user_config, paper_trading_enabled
    
    # Auto-correct trading mode if backtest has completed
    if trading_mode == "backtest":
        if not backtest_engine or not backtest_engine.running:
            trading_mode = "stopped"
    
    return SystemStatus(
        status="running" if trading_bot and trading_bot.running else "stopped",
        bot_running=trading_bot.running if trading_bot else False,
        trading_mode=trading_mode,
        configuration={
            "initial_capital": config.INITIAL_CAPITAL,
            "deployed_capital": config.DEPLOYED_CAPITAL,
            "max_position_size": config.MAX_POSITION_SIZE,
            "trades_per_10min": config.TRADES_PER_10MIN,
            "max_drawdown_pct": config.MAX_DRAWDOWN_PCT,
            "kelly_fraction": config.KELLY_FRACTION,
            "min_kelly_fraction": config.MIN_KELLY_FRACTION,
            "max_kelly_fraction": config.MAX_KELLY_FRACTION,
            "enabled_asset_classes": user_config.get("enabled_asset_classes", []),
            "enabled_strategies": user_config.get("enabled_strategies", []),
            "paper_trading": paper_trading_enabled
        },
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@api_router.post("/mode/paper")
async def enable_paper_trading(username: str = Depends(verify_credentials_dual)):
    """Enable paper trading mode - simulates live trading without real money"""
    global trading_mode, paper_trading_enabled
    paper_trading_enabled = True
    trading_mode = "paper"
    logger.info(f"Paper trading enabled by {username}")
    return {
        "message": "Paper trading mode enabled",
        "mode": "paper",
        "description": "Trading signals will be generated and logged, but NO real trades will be executed"
    }

@api_router.post("/mode/live")
async def enable_live_trading(username: str = Depends(verify_credentials_dual)):
    """Enable live trading mode - CAUTION: Real money will be used"""
    global trading_mode, paper_trading_enabled
    paper_trading_enabled = False
    trading_mode = "live"
    logger.info(f"LIVE trading enabled by {username}")
    return {
        "message": "⚠️ LIVE trading mode enabled - Real money will be used!",
        "mode": "live",
        "warning": "All trades will be executed with real funds"
    }

@api_router.post("/mode/stop")
async def stop_trading():
    """Stop all trading"""
    global trading_mode, paper_trading_enabled
    paper_trading_enabled = False
    trading_mode = "stopped"
    
    # Stop the bot if running
    if trading_bot and trading_bot.running:
        await trading_bot.stop()
    
    return {"message": "Trading stopped", "mode": "stopped"}

# =============================================
# JWT AUTHENTICATION ENDPOINTS
# =============================================

@api_router.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login with username and password to get a JWT token
    
    Returns a Bearer token that can be used for subsequent API calls
    """
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login
    db = get_db()
    await db.users.update_one(
        {"username": user["username"]},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
    )
    
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "username": user["username"],
            "email": user.get("email"),
            "is_admin": user.get("is_admin", False)
        }
    )

@api_router.post("/auth/login/json")
async def login_json(credentials: UserLogin):
    """
    Login with username and password (JSON body) to get a JWT token
    Alternative to form-based login
    """
    user = await authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login
    db = get_db()
    await db.users.update_one(
        {"username": user["username"]},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
    )
    
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": user["username"],
            "email": user.get("email"),
            "is_admin": user.get("is_admin", False)
        }
    }

@api_router.post("/auth/register")
async def register_user(user_data: UserCreate, current_user = Depends(get_current_user)):
    """
    Register a new user (admin only)
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create new users"
        )
    
    new_user = await create_user(user_data)
    return {"message": "User created successfully", "user": new_user}

@api_router.get("/auth/me")
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current authenticated user's information"""
    return UserResponse(
        username=current_user["username"],
        email=current_user.get("email"),
        created_at=current_user.get("created_at", ""),
        is_admin=current_user.get("is_admin", False)
    )

@api_router.post("/auth/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user = Depends(get_current_user)
):
    """Change current user's password"""
    from auth import verify_password, get_password_hash
    
    db = get_db()
    user = await db.users.find_one({"username": current_user["username"]})
    
    if not verify_password(old_password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    await db.users.update_one(
        {"username": current_user["username"]},
        {"$set": {"hashed_password": get_password_hash(new_password)}}
    )
    
    return {"message": "Password changed successfully"}

@api_router.post("/bot/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the LIVE trading bot"""
    global trading_bot, trading_mode
    
    if trading_mode == "backtest" and backtest_engine and backtest_engine.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Backtest is running. Stop backtest first."}
        )
    
    if trading_bot and trading_bot.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Live trading bot is already running"}
        )
    
    try:
        trading_bot = ApexTrader()
        background_tasks.add_task(trading_bot.start)
        trading_mode = "live"
        
        return {"message": "Live trading bot started successfully", "mode": "live"}
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to start bot: {str(e)}"}
        )

@api_router.post("/bot/stop")
async def stop_bot():
    """Stop the LIVE trading bot"""
    global trading_bot, trading_mode
    
    if not trading_bot or not trading_bot.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Live trading bot is not running"}
        )
    
    try:
        await trading_bot.stop()
        trading_mode = "stopped"
        return {"message": "Live trading bot stopped successfully"}
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop bot: {str(e)}"}
        )

@api_router.post("/backtest/start")
async def start_backtest(
    background_tasks: BackgroundTasks,
    start_date: str,
    end_date: str,
    strategies: Optional[List[str]] = Query(default=None),
    asset_classes: Optional[List[str]] = Query(default=None),
    use_tuned_params: bool = True,
    data_source: str = Query(default="auto", description="Data source: auto, real, snapshots, live, hybrid")
):
    """Start backtesting with optional strategy, asset class, and data source filters
    
    Data source options:
    - auto: Automatically select best available data
    - real: Use only real price history data (most accurate)
    - snapshots: Use historical snapshots (faster, less accurate)
    - live: Fetch live data during backtest (slowest, most current)
    - hybrid: Combine real prices with snapshots for gaps
    """
    global backtest_engine, trading_mode, user_config
    
    logger.info(f"Backtest start request: strategies={strategies}, asset_classes={asset_classes}, use_tuned={use_tuned_params}, data_source={data_source}")
    
    if trading_bot and trading_bot.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Live trading is running. Stop live trading first."}
        )
    
    if backtest_engine and backtest_engine.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Backtest is already running"}
        )
    
    try:
        if not backtest_engine:
            backtest_engine = BacktestEngine()
        
        trading_mode = "backtest"
        
        # Use user config if not specified
        if strategies is None:
            strategies = user_config.get("enabled_strategies")
        if asset_classes is None:
            asset_classes = user_config.get("enabled_asset_classes")
        
        logger.info(f"Running backtest with strategies={strategies}, asset_classes={asset_classes}, use_tuned={use_tuned_params}, data_source={data_source}")
        
        # Run backtest in background
        async def run_backtest_task():
            await backtest_engine.run_backtest(start_date, end_date, strategies, asset_classes, use_tuned_params, data_source)
        
        background_tasks.add_task(run_backtest_task)
        
        return {
            "message": "Backtest started successfully",
            "mode": "backtest",
            "start_date": start_date,
            "end_date": end_date,
            "strategies": strategies,
            "asset_classes": asset_classes,
            "using_tuned_params": use_tuned_params,
            "data_source": data_source
        }
    except Exception as e:
        logger.error(f"Error starting backtest: {e}")
        trading_mode = "stopped"
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to start backtest: {str(e)}"}
        )

@api_router.post("/backtest/stop")
async def stop_backtest():
    """Stop running backtest"""
    global backtest_engine, trading_mode
    
    # Always reset the trading mode when stop is requested
    try:
        if backtest_engine and backtest_engine.running:
            await backtest_engine.stop_backtest()
        
        trading_mode = "stopped"
        return {"message": "Backtest stopped successfully", "mode": trading_mode}
    except Exception as e:
        logger.error(f"Error stopping backtest: {e}")
        trading_mode = "stopped"  # Reset mode even on error
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop backtest: {str(e)}"}
        )

@api_router.get("/backtest/results")
async def get_backtest_results(backtest_id: Optional[str] = None):
    """Get backtest results"""
    global backtest_engine
    
    try:
        if not backtest_engine:
            backtest_engine = BacktestEngine()
        
        results = await backtest_engine.get_backtest_results(backtest_id)
        
        if not results:
            return JSONResponse(
                status_code=404,
                content={"message": "No backtest results found"}
            )
        
        return results
    except Exception as e:
        logger.error(f"Error getting backtest results: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get results: {str(e)}"}
        )

@api_router.get("/backtest/history")
async def get_backtest_history(limit: int = 10):
    """Get list of past backtest results"""
    global backtest_engine
    
    try:
        if not backtest_engine:
            backtest_engine = BacktestEngine()
        
        history = await backtest_engine.get_backtest_history(limit)
        
        return {
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting backtest history: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get history: {str(e)}"}
        )

@api_router.post("/backtest/compare")
async def compare_backtests(backtest_ids: List[str]):
    """Compare multiple backtest results with comprehensive metrics"""
    global backtest_engine
    
    try:
        if not backtest_engine:
            backtest_engine = BacktestEngine()
        
        if len(backtest_ids) < 1:
            return JSONResponse(
                status_code=400,
                content={"message": "At least 1 backtest ID required for analysis"}
            )
        
        comparison = await backtest_engine.compare_backtests(backtest_ids)
        
        if "error" in comparison:
            return JSONResponse(
                status_code=404,
                content={"message": comparison["error"]}
            )
        
        return comparison
    except Exception as e:
        logger.error(f"Error comparing backtests: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to compare: {str(e)}"}
        )

@api_router.delete("/backtest/{backtest_id}")
async def delete_backtest(backtest_id: str):
    """Delete a backtest result"""
    global backtest_engine
    
    try:
        if not backtest_engine:
            backtest_engine = BacktestEngine()
        
        success = await backtest_engine.delete_backtest(backtest_id)
        
        if success:
            return {"message": f"Backtest {backtest_id} deleted successfully"}
        else:
            return JSONResponse(
                status_code=404,
                content={"message": "Backtest not found"}
            )
    except Exception as e:
        logger.error(f"Error deleting backtest: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to delete: {str(e)}"}
        )

@api_router.get("/performance", response_model=PerformanceResponse)
async def get_performance():
    """Get current performance metrics"""
    db = get_db()
    
    try:
        metrics = await db.performance_metrics.find_one(
            {},
            {"_id": 0},
            sort=[("timestamp", -1)]
        )
        
        if not metrics:
            return PerformanceResponse(
                total_capital=config.INITIAL_CAPITAL,
                total_pnl=0.0,
                win_rate=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                num_trades=0,
                num_positions=0
            )
        
        return PerformanceResponse(**metrics)
    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get performance: {str(e)}"}
        )

@api_router.get("/positions")
async def get_positions():
    """Get all open positions"""
    db = get_db()
    
    try:
        positions = await db.positions.find({}, {"_id": 0}).to_list(length=1000)
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get positions: {str(e)}"}
        )

@api_router.get("/trades")
async def get_trades(limit: int = 100):
    """Get recent trades"""
    db = get_db()
    
    try:
        trades = await db.trades.find(
            {},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        return {"trades": trades, "count": len(trades)}
    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get trades: {str(e)}"}
        )

@api_router.get("/markets")
async def get_markets(limit: int = 50, category: str = None):
    """Get active markets from Polymarket Gamma API (LIVE data) or historical fallback"""
    db = get_db()
    
    try:
        # First try to get fresh markets from Polymarket Gamma API
        from data.polymarket_api import PolymarketAPI
        
        try:
            async with PolymarketAPI() as api:
                # get_markets() returns normalized data with yes_price, no_price already set
                raw_markets = await api.get_markets(limit=limit)
                
                if raw_markets:
                    markets = []
                    for m in raw_markets:
                        # STRICT PRICE VALIDATION - Skip markets without valid prices
                        raw_yes = m.get('yes_price')
                        raw_no = m.get('no_price')
                        
                        if raw_yes is None or raw_yes == 0:
                            continue  # Skip markets without valid price data
                        
                        yes_price = float(raw_yes)
                        no_price = float(raw_no) if raw_no is not None and raw_no != 0 else (1 - yes_price)
                        
                        # Get category from normalized data or categorize
                        question = m.get('question', '')
                        cat = m.get('category') or categorize_market(question)
                        
                        if category and cat.lower() != category.lower():
                            continue
                        
                        markets.append({
                            "id": m.get('condition_id') or m.get('id'),
                            "question": question,
                            "category": cat,
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "volume": float(m.get('volume', 0) or 0),
                            "volume_24h": float(m.get('volume_24h', 0) or 0),
                            "liquidity": float(m.get('liquidity', 0) or 0),
                            "end_date": m.get('end_date'),
                            "active": m.get('active', True)
                        })
                    
                    if markets:
                        logger.info(f"Returning {len(markets)} LIVE markets from Gamma API")
                        return {"markets": markets[:limit], "count": len(markets[:limit]), "source": "gamma_api_live"}
        except Exception as api_error:
            logger.warning(f"Polymarket Gamma API failed, falling back to historical data: {api_error}")
        
        # Fallback: Get unique markets from historical data
        pipeline = [
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": "$market_id",
                "question": {"$first": "$question"},
                "category": {"$first": "$category"},
                "yes_price": {"$first": "$yes_price"},
                "no_price": {"$first": "$no_price"},
                "volume": {"$first": "$volume"},
                "liquidity": {"$first": "$liquidity"},
                "end_date": {"$first": "$end_date"},
                "timestamp": {"$first": "$timestamp"}
            }},
            {"$limit": limit}
        ]
        
        if category:
            pipeline.insert(0, {"$match": {"category": category}})
        
        cursor = db.historical_data.aggregate(pipeline)
        historical_markets = await cursor.to_list(length=limit)
        
        markets = [{
            "id": m["_id"],
            "question": m.get("question", ""),
            "category": m.get("category", "finance"),
            "yes_price": m.get("yes_price", 0.5),
            "no_price": m.get("no_price", 0.5),
            "volume": m.get("volume", 0),
            "liquidity": m.get("liquidity", 0),
            "end_date": m.get("end_date"),
            "active": True
        } for m in historical_markets]
        
        return {"markets": markets, "count": len(markets), "source": "historical_data"}
    except Exception as e:
        logger.error(f"Error getting markets: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get markets: {str(e)}"}
        )

def categorize_market(question: str) -> str:
    """Categorize market based on question text"""
    question_lower = question.lower()
    
    crypto_keywords = ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'coin', 'token', 'solana', 'sol']
    sports_keywords = ['nfl', 'nba', 'mlb', 'soccer', 'football', 'game', 'championship', 'super bowl', 'world series', 'playoffs', 'win', 'vs']
    politics_keywords = ['election', 'president', 'congress', 'senate', 'vote', 'political', 'trump', 'biden', 'governor', 'democrat', 'republican']
    entertainment_keywords = ['oscar', 'grammy', 'emmy', 'movie', 'film', 'album', 'box office', 'celebrity']
    
    if any(kw in question_lower for kw in crypto_keywords):
        return "crypto"
    elif any(kw in question_lower for kw in sports_keywords):
        return "sports"
    elif any(kw in question_lower for kw in politics_keywords):
        return "politics"
    elif any(kw in question_lower for kw in entertainment_keywords):
        return "entertainment"
    else:
        return "finance"

@api_router.get("/analytics", response_model=ComprehensiveMetricsResponse)
async def get_analytics():
    """
    Get comprehensive performance analytics.
    
    Returns detailed metrics including:
    - Overall performance (PnL, win rate, trades)
    - Strategy breakdown
    - Asset class breakdown
    - **Lane breakdown (HFT, ALPHA, GAMMA)** - Three-Speed Architecture
    - Advanced metrics (Sortino, profit factor, etc.)
    """
    global analytics_engine
    
    try:
        if not analytics_engine:
            analytics_engine = PerformanceAnalytics()
        
        analytics = await analytics_engine.calculate_comprehensive_metrics()
        return analytics
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get analytics: {str(e)}"}
        )

@api_router.get("/trades/stats")
async def get_trade_stats():
    """Get trade frequency statistics for different time windows"""
    db = get_db()
    
    try:
        now = datetime.now(timezone.utc)
        
        # Define time windows
        windows = {
            "10min": now - timedelta(minutes=10),
            "30min": now - timedelta(minutes=30),
            "1hr": now - timedelta(hours=1),
            "24hr": now - timedelta(hours=24)
        }
        
        # Count trades for each window
        stats = {}
        for window_name, window_start in windows.items():
            count = await db.trades.count_documents({
                "timestamp": {"$gte": window_start.isoformat()}
            })
            stats[window_name] = count
        
        # Get live (currently executing) trades count
        live_trades = await db.trades.count_documents({
            "status": {"$in": ["pending", "executing", "open"]}
        })
        
        # Get total P&L
        pnl_pipeline = [
            {"$group": {"_id": None, "total_pnl": {"$sum": "$pnl"}}}
        ]
        pnl_result = await db.trades.aggregate(pnl_pipeline).to_list(length=1)
        total_pnl = pnl_result[0]["total_pnl"] if pnl_result else 0.0
        
        # Get P&L percentage (relative to initial capital)
        pnl_pct = (total_pnl / config.INITIAL_CAPITAL) * 100 if config.INITIAL_CAPITAL > 0 else 0
        
        return {
            "live_trades": live_trades,
            "trades_10min": stats["10min"],
            "trades_30min": stats["30min"],
            "trades_1hr": stats["1hr"],
            "trades_24hr": stats["24hr"],
            "total_pnl": total_pnl,
            "pnl_pct": pnl_pct,
            "timestamp": now.isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting trade stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get trade stats: {str(e)}"}
        )

@api_router.get("/config")
async def get_config():
    """Get current trading configuration from database - DB is the single source of truth"""
    try:
        db = get_db()
        saved_config = await db.user_config.find_one(
            {"type": "trading_preferences"},
            {"_id": 0}
        )
        
        # Return saved config or defaults - DB is the source of truth
        return {
            "initial_capital": saved_config.get("initial_capital", config.INITIAL_CAPITAL) if saved_config else config.INITIAL_CAPITAL,
            "capital_deployment_pct": saved_config.get("capital_deployment_pct", config.CAPITAL_DEPLOYMENT_PCT) if saved_config else config.CAPITAL_DEPLOYMENT_PCT,
            "max_position_size_pct": saved_config.get("max_position_size_pct", config.MAX_POSITION_SIZE_PCT) if saved_config else config.MAX_POSITION_SIZE_PCT,
            "kelly_fraction": saved_config.get("kelly_fraction", config.KELLY_FRACTION) if saved_config else config.KELLY_FRACTION,
            "kelly_enabled": saved_config.get("kelly_enabled", True) if saved_config else True,  # Default: Kelly enabled
            "max_drawdown_pct": saved_config.get("max_drawdown_pct", config.MAX_DRAWDOWN_PCT) if saved_config else config.MAX_DRAWDOWN_PCT,
            "trades_per_10min": saved_config.get("trades_per_10min", config.TRADES_PER_10MIN) if saved_config else config.TRADES_PER_10MIN,
            # Market selection filters
            "min_liquidity": saved_config.get("min_liquidity", config.MIN_LIQUIDITY) if saved_config else config.MIN_LIQUIDITY,
            "max_liquidity": saved_config.get("max_liquidity", 1000000) if saved_config else 1000000,  # Default $1M max
            "min_volume_24h": saved_config.get("min_volume_24h", config.MIN_VOLUME_24H) if saved_config else config.MIN_VOLUME_24H,
            "max_spread": saved_config.get("max_spread", config.MAX_SPREAD) if saved_config else config.MAX_SPREAD,
            "max_open_positions": saved_config.get("max_open_positions", config.MAX_OPEN_POSITIONS) if saved_config else config.MAX_OPEN_POSITIONS,
            # Stuck price filter
            "stuck_price_multiplier": saved_config.get("stuck_price_multiplier", 2.0) if saved_config else 2.0,  # Default 2x
            # Strategies and asset classes
            "enabled_strategies": saved_config.get("enabled_strategies", user_config["enabled_strategies"]) if saved_config else user_config["enabled_strategies"],
            "enabled_asset_classes": saved_config.get("enabled_asset_classes", user_config["enabled_asset_classes"]) if saved_config else user_config["enabled_asset_classes"],
            # Exit parameters per strategy (merge saved with defaults)
            "exit_params": {
                "delta_neutral": {
                    **{"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4},
                    **saved_config.get("exit_params", {}).get("delta_neutral", {})
                } if saved_config else {"take_profit": 0.02, "stop_loss": -0.02, "max_hours": 4},
                "volatility_exploitation": {
                    **{"take_profit": 0.05, "stop_loss": -0.05, "max_hours": 8},
                    **saved_config.get("exit_params", {}).get("volatility_exploitation", {})
                } if saved_config else {"take_profit": 0.05, "stop_loss": -0.05, "max_hours": 8},
                "alpha_directional": {
                    **{"take_profit": 0.08, "stop_loss": -0.05, "max_hours": 12},
                    **saved_config.get("exit_params", {}).get("alpha_directional", {})
                } if saved_config else {"take_profit": 0.08, "stop_loss": -0.05, "max_hours": 12},
                "arbitrage": {
                    **{"take_profit": 0.03, "stop_loss": -0.03, "max_hours": 6},
                    **saved_config.get("exit_params", {}).get("arbitrage", {})
                } if saved_config else {"take_profit": 0.03, "stop_loss": -0.03, "max_hours": 6},
            },
            # Asset class exit multipliers (merge saved with defaults)
            "asset_class_exit_multipliers": {
                "crypto": {
                    **{"tp_mult": 1.5, "sl_mult": 1.3, "time_mult": 0.5},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("crypto", {})
                } if saved_config else {"tp_mult": 1.5, "sl_mult": 1.3, "time_mult": 0.5},
                "politics": {
                    **{"tp_mult": 1.2, "sl_mult": 1.0, "time_mult": 1.5},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("politics", {})
                } if saved_config else {"tp_mult": 1.2, "sl_mult": 1.0, "time_mult": 1.5},
                "sports": {
                    **{"tp_mult": 1.0, "sl_mult": 0.8, "time_mult": 0.25},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("sports", {})
                } if saved_config else {"tp_mult": 1.0, "sl_mult": 0.8, "time_mult": 0.25},
                "finance": {
                    **{"tp_mult": 0.8, "sl_mult": 0.8, "time_mult": 1.0},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("finance", {})
                } if saved_config else {"tp_mult": 0.8, "sl_mult": 0.8, "time_mult": 1.0},
                "entertainment": {
                    **{"tp_mult": 1.0, "sl_mult": 1.0, "time_mult": 1.0},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("entertainment", {})
                } if saved_config else {"tp_mult": 1.0, "sl_mult": 1.0, "time_mult": 1.0},
                "science": {
                    **{"tp_mult": 1.0, "sl_mult": 1.0, "time_mult": 2.0},
                    **saved_config.get("asset_class_exit_multipliers", {}).get("science", {})
                } if saved_config else {"tp_mult": 1.0, "sl_mult": 1.0, "time_mult": 2.0},
            },
            # Advanced position sizing parameters
            "min_kelly_fraction": saved_config.get("min_kelly_fraction", 0.10) if saved_config else 0.10,
            "max_kelly_fraction": saved_config.get("max_kelly_fraction", 0.50) if saved_config else 0.50,
            "min_position_size": saved_config.get("min_position_size", 5.0) if saved_config else 5.0,
            "min_liquidity_for_full_size": saved_config.get("min_liquidity_for_full_size", 10000.0) if saved_config else 10000.0,
            # Market alerts configuration
            "alerts_enabled": saved_config.get("alerts_enabled", False) if saved_config else False,
            "alert_volume_threshold": saved_config.get("alert_volume_threshold", 2.0) if saved_config else 2.0,
            # Strategy selection thresholds
            "volatility_threshold": saved_config.get("volatility_threshold", 0.06) if saved_config else 0.06,
            "sentiment_strength_threshold": saved_config.get("sentiment_strength_threshold", 0.25) if saved_config else 0.25,
            "sharp_alignment_threshold": saved_config.get("sharp_alignment_threshold", 0.8) if saved_config else 0.8,
            "delta_neutral_price_min": saved_config.get("delta_neutral_price_min", 0.40) if saved_config else 0.40,
            "delta_neutral_price_max": saved_config.get("delta_neutral_price_max", 0.70) if saved_config else 0.70,
            # Sentiment-based side selection thresholds
            "bullish_sentiment_threshold": saved_config.get("bullish_sentiment_threshold", 0.55) if saved_config else 0.55,
            "bearish_sentiment_threshold": saved_config.get("bearish_sentiment_threshold", 0.45) if saved_config else 0.45,
            # NEW: Polymarket Position Sizer Configuration
            "use_polymarket_sizer": saved_config.get("use_polymarket_sizer", True) if saved_config else True,
            "polymarket_fee_pct": saved_config.get("polymarket_fee_pct", 0.02) if saved_config else 0.02,
            "sector_caps": saved_config.get("sector_caps", {
                "crypto": 0.20,
                "politics": 0.25,
                "sports": 0.30,
                "finance": 0.20,
                "entertainment": 0.15,
                "science": 0.15,
                "conflict": 0.10,
                "social": 0.10,
                "unknown": 0.15,
            }) if saved_config else {
                "crypto": 0.20,
                "politics": 0.25,
                "sports": 0.30,
                "finance": 0.20,
                "entertainment": 0.15,
                "science": 0.15,
                "conflict": 0.10,
                "social": 0.10,
                "unknown": 0.15,
            },
            # Oracle Risk Multipliers (configurable)
            "oracle_multipliers": saved_config.get("oracle_multipliers", None) if saved_config else None,
            "oracle_multipliers_default": get_default_ambiguity_matrix(),
            # Event Caps (configurable)
            "event_caps": saved_config.get("event_caps", DEFAULT_EVENT_CAPS) if saved_config else DEFAULT_EVENT_CAPS,
            "event_caps_default": DEFAULT_EVENT_CAPS,
            
            # ==============================================================
            # TWO-SPEED ARCHITECTURE CONFIGURATION (HFT/Alpha)
            # ==============================================================
            "hft_allocation_pct": saved_config.get("hft_allocation_pct", 40) if saved_config else 40,
            "alpha_allocation_pct": saved_config.get("alpha_allocation_pct", 60) if saved_config else 60,
            "hft_max_position_pct": saved_config.get("hft_max_position_pct", 10) if saved_config else 10,
            "alpha_max_position_pct": saved_config.get("alpha_max_position_pct", 25) if saved_config else 25,
            "hft_positions_pct": saved_config.get("hft_positions_pct", 5) if saved_config else 5,
            "alpha_positions_pct": saved_config.get("alpha_positions_pct", 2) if saved_config else 2,
            # Strategy Risk Multipliers
            "strategy_risk_multipliers": saved_config.get("strategy_risk_multipliers", {
                "delta_neutral": 1.2,
                "volatility_exploitation": 0.5,
                "alpha_directional": 0.8,
                "arbitrage": 1.1
            }) if saved_config else {
                "delta_neutral": 1.2,
                "volatility_exploitation": 0.5,
                "alpha_directional": 0.8,
                "arbitrage": 1.1
            },
            # Expiry Thresholds
            "expiry_thresholds": saved_config.get("expiry_thresholds", {
                "no_entry_hours": 6,
                "high_urgency_hours": 24,
                "medium_urgency_days": 7,
                "normal_days": 30
            }) if saved_config else {
                "no_entry_hours": 6,
                "high_urgency_hours": 24,
                "medium_urgency_days": 7,
                "normal_days": 30
            },
            # Strategy Expiry Adjustments
            "expiry_strategy_adjustments": saved_config.get("expiry_strategy_adjustments", {
                "delta_neutral": {"disable_within_hours": 48, "size_mult_near_expiry": 0.5},
                "volatility_exploitation": {"boost_within_days": 7, "boost_multiplier": 1.5, "disable_within_hours": 6},
                "alpha_directional": {"min_confidence_near_expiry": 0.7, "disable_within_hours": 6},
                "arbitrage": {"disable_within_hours": 6}
            }) if saved_config else {
                "delta_neutral": {"disable_within_hours": 48, "size_mult_near_expiry": 0.5},
                "volatility_exploitation": {"boost_within_days": 7, "boost_multiplier": 1.5, "disable_within_hours": 6},
                "alpha_directional": {"min_confidence_near_expiry": 0.7, "disable_within_hours": 6},
                "arbitrage": {"disable_within_hours": 6}
            },
            # HFT Execution Parameters
            "hft_execution": saved_config.get("hft_execution", {
                "max_inventory_usd": 1000,
                "skew_factor": 0.05,
                "ofi_threshold": 0.6,
                "ofi_adjustment": 0.01,
                "ofi_levels": 3
            }) if saved_config else {
                "max_inventory_usd": 1000,
                "skew_factor": 0.05,
                "ofi_threshold": 0.6,
                "ofi_adjustment": 0.01,
                "ofi_levels": 3
            },
            # Spread Policy
            "spread_policy": saved_config.get("spread_policy", {
                "max_spread_hft": 0.25,
                "max_spread_alpha": 0.15,
                "max_spread_aggressive": 0.06,
                "min_spread_maker": 0.005,
                "maker_spread_capture": 0.50,
                "adverse_selection_cost": 0.005,
                "taker_fee": 0.02
            }) if saved_config else {
                "max_spread_hft": 0.25,
                "max_spread_alpha": 0.15,
                "max_spread_aggressive": 0.06,
                "min_spread_maker": 0.005,
                "maker_spread_capture": 0.50,
                "adverse_selection_cost": 0.005,
                "taker_fee": 0.02
            },
            # Variance Sizing (Tail Risk)
            "variance_sizing": saved_config.get("variance_sizing", {
                "kill_switch_low": 0.03,
                "kill_switch_high": 0.97
            }) if saved_config else {
                "kill_switch_low": 0.03,
                "kill_switch_high": 0.97
            },
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get config: {str(e)}"}
        )

@api_router.post("/config/update")
async def update_config(config_update: TradingConfig):
    """Update trading configuration"""
    global user_config
    
    try:
        # Build update document for database persistence
        db_update = {
            "type": "trading_preferences",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if config_update.trades_per_10min:
            os.environ['TRADES_PER_10MIN'] = str(config_update.trades_per_10min)
            db_update["trades_per_10min"] = config_update.trades_per_10min
        
        if config_update.initial_capital:
            os.environ['INITIAL_CAPITAL'] = str(config_update.initial_capital)
            db_update["initial_capital"] = config_update.initial_capital
        
        if config_update.capital_deployment_pct:
            os.environ['CAPITAL_DEPLOYMENT_PCT'] = str(config_update.capital_deployment_pct)
            db_update["capital_deployment_pct"] = config_update.capital_deployment_pct
        
        if config_update.max_position_size_pct:
            os.environ['MAX_POSITION_SIZE_PCT'] = str(config_update.max_position_size_pct)
            db_update["max_position_size_pct"] = config_update.max_position_size_pct
        
        if config_update.kelly_fraction is not None:
            # Validate Kelly fraction is within bounds
            kelly = max(config.MIN_KELLY_FRACTION, min(config.MAX_KELLY_FRACTION, config_update.kelly_fraction))
            os.environ['KELLY_FRACTION'] = str(kelly)
            db_update["kelly_fraction"] = kelly
        
        if config_update.max_drawdown_pct:
            os.environ['MAX_DRAWDOWN_PCT'] = str(config_update.max_drawdown_pct)
            db_update["max_drawdown_pct"] = config_update.max_drawdown_pct
        
        # Kelly enabled toggle
        if config_update.kelly_enabled is not None:
            db_update["kelly_enabled"] = config_update.kelly_enabled
        
        # Market selection filters
        if config_update.min_liquidity is not None:
            os.environ['MIN_LIQUIDITY'] = str(config_update.min_liquidity)
            db_update["min_liquidity"] = config_update.min_liquidity
        
        if config_update.max_liquidity is not None:
            db_update["max_liquidity"] = config_update.max_liquidity
        
        if config_update.min_volume_24h is not None:
            os.environ['MIN_VOLUME_24H'] = str(config_update.min_volume_24h)
            db_update["min_volume_24h"] = config_update.min_volume_24h
        
        if config_update.max_spread is not None:
            os.environ['MAX_SPREAD'] = str(config_update.max_spread)
            db_update["max_spread"] = config_update.max_spread
        
        if config_update.max_open_positions is not None:
            os.environ['MAX_OPEN_POSITIONS'] = str(config_update.max_open_positions)
            db_update["max_open_positions"] = config_update.max_open_positions
        
        # Stuck price multiplier
        if config_update.stuck_price_multiplier is not None:
            db_update["stuck_price_multiplier"] = config_update.stuck_price_multiplier
        
        # Update asset classes and strategies
        if config_update.enabled_asset_classes is not None:
            user_config["enabled_asset_classes"] = config_update.enabled_asset_classes
            db_update["enabled_asset_classes"] = config_update.enabled_asset_classes
        
        if config_update.enabled_strategies is not None:
            user_config["enabled_strategies"] = config_update.enabled_strategies
            db_update["enabled_strategies"] = config_update.enabled_strategies
        
        # Update exit parameters per strategy
        if config_update.exit_params is not None:
            # Convert Pydantic models to dicts for MongoDB storage
            exit_params_dict = {}
            for strategy, params in config_update.exit_params.items():
                if params:
                    exit_params_dict[strategy] = {
                        "take_profit": params.take_profit,
                        "stop_loss": params.stop_loss,
                        "max_hours": params.max_hours
                    }
            db_update["exit_params"] = exit_params_dict
            logger.info(f"Exit params updated: {list(exit_params_dict.keys())}")
        
        # Update asset class exit multipliers
        if config_update.asset_class_exit_multipliers is not None:
            asset_mult_dict = {}
            for asset_class, multipliers in config_update.asset_class_exit_multipliers.items():
                if multipliers:
                    asset_mult_dict[asset_class] = {
                        "tp_mult": multipliers.tp_mult,
                        "sl_mult": multipliers.sl_mult,
                        "time_mult": multipliers.time_mult
                    }
            db_update["asset_class_exit_multipliers"] = asset_mult_dict
            logger.info(f"Asset class exit multipliers updated: {list(asset_mult_dict.keys())}")
        
        # Advanced position sizing parameters
        if config_update.min_kelly_fraction is not None:
            db_update["min_kelly_fraction"] = config_update.min_kelly_fraction
        if config_update.max_kelly_fraction is not None:
            db_update["max_kelly_fraction"] = config_update.max_kelly_fraction
        if config_update.min_position_size is not None:
            db_update["min_position_size"] = config_update.min_position_size
        if config_update.min_liquidity_for_full_size is not None:
            db_update["min_liquidity_for_full_size"] = config_update.min_liquidity_for_full_size
        
        # Market alerts configuration
        if config_update.alerts_enabled is not None:
            db_update["alerts_enabled"] = config_update.alerts_enabled
        if config_update.alert_volume_threshold is not None:
            db_update["alert_volume_threshold"] = config_update.alert_volume_threshold
        
        # Strategy selection thresholds
        if config_update.volatility_threshold is not None:
            db_update["volatility_threshold"] = config_update.volatility_threshold
        if config_update.sentiment_strength_threshold is not None:
            db_update["sentiment_strength_threshold"] = config_update.sentiment_strength_threshold
        if config_update.sharp_alignment_threshold is not None:
            db_update["sharp_alignment_threshold"] = config_update.sharp_alignment_threshold
        if config_update.delta_neutral_price_min is not None:
            db_update["delta_neutral_price_min"] = config_update.delta_neutral_price_min
        if config_update.delta_neutral_price_max is not None:
            db_update["delta_neutral_price_max"] = config_update.delta_neutral_price_max
        
        # Sentiment-based side selection thresholds
        if config_update.bullish_sentiment_threshold is not None:
            db_update["bullish_sentiment_threshold"] = config_update.bullish_sentiment_threshold
        if config_update.bearish_sentiment_threshold is not None:
            db_update["bearish_sentiment_threshold"] = config_update.bearish_sentiment_threshold
        
        # NEW: Polymarket Position Sizer Configuration
        if config_update.use_polymarket_sizer is not None:
            db_update["use_polymarket_sizer"] = config_update.use_polymarket_sizer
        if config_update.polymarket_fee_pct is not None:
            db_update["polymarket_fee_pct"] = config_update.polymarket_fee_pct
        if config_update.sector_caps is not None:
            db_update["sector_caps"] = config_update.sector_caps
        if config_update.oracle_multipliers is not None:
            db_update["oracle_multipliers"] = config_update.oracle_multipliers
            # Also update the runtime matrix
            update_ambiguity_matrix(config_update.oracle_multipliers)
        if config_update.event_caps is not None:
            db_update["event_caps"] = config_update.event_caps
        
        # ==============================================================
        # TWO-SPEED ARCHITECTURE CONFIGURATION (HFT/Alpha)
        # ==============================================================
        if config_update.hft_allocation_pct is not None:
            db_update["hft_allocation_pct"] = config_update.hft_allocation_pct
        if config_update.alpha_allocation_pct is not None:
            db_update["alpha_allocation_pct"] = config_update.alpha_allocation_pct
        if config_update.hft_max_position_pct is not None:
            db_update["hft_max_position_pct"] = config_update.hft_max_position_pct
        if config_update.alpha_max_position_pct is not None:
            db_update["alpha_max_position_pct"] = config_update.alpha_max_position_pct
        if config_update.hft_positions_pct is not None:
            db_update["hft_positions_pct"] = config_update.hft_positions_pct
        if config_update.alpha_positions_pct is not None:
            db_update["alpha_positions_pct"] = config_update.alpha_positions_pct
        
        # Strategy Risk Multipliers
        if config_update.strategy_risk_multipliers is not None:
            db_update["strategy_risk_multipliers"] = config_update.strategy_risk_multipliers
        
        # Expiry Thresholds
        if config_update.expiry_thresholds is not None:
            db_update["expiry_thresholds"] = config_update.expiry_thresholds
        
        # Strategy Expiry Adjustments
        if config_update.expiry_strategy_adjustments is not None:
            db_update["expiry_strategy_adjustments"] = config_update.expiry_strategy_adjustments
        
        # HFT Execution Parameters
        if config_update.hft_execution is not None:
            db_update["hft_execution"] = config_update.hft_execution
        
        # Spread Policy
        if config_update.spread_policy is not None:
            db_update["spread_policy"] = config_update.spread_policy
        
        # Variance Sizing (Tail Risk)
        if config_update.variance_sizing is not None:
            db_update["variance_sizing"] = config_update.variance_sizing
        
        # Store ALL config in database for persistence (not just strategies/asset classes)
        db = get_db()
        await db.user_config.update_one(
            {"type": "trading_preferences"},
            {"$set": db_update},
            upsert=True
        )
        
        logger.info(f"Config updated and saved to DB: {list(db_update.keys())}")
        
        return {"message": "Configuration updated and saved. New paper trading sessions will use these settings."}
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to update config: {str(e)}"}
        )

@api_router.post("/config/reload-live")
async def reload_config_live(username: str = Depends(verify_credentials_dual)):
    """Reload configuration for running paper trading session - hot reload"""
    global paper_trader
    
    if not paper_trader or not paper_trader.running:
        return JSONResponse(
            status_code=400,
            content={"message": "No paper trading session is running"}
        )
    
    try:
        result = await paper_trader.reload_config_live()
        return {
            "message": "Configuration reloaded for live session",
            **result
        }
    except Exception as e:
        logger.error(f"Error reloading config: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to reload config: {str(e)}"}
        )

# =============================================
# MARKET ALERTS ENDPOINTS
# =============================================
@api_router.get("/alerts")
async def get_market_alerts(limit: int = Query(default=20, le=50)):
    """Get recent market alerts"""
    try:
        alerts_service = get_market_alerts_service(ws_manager)
        alerts = alerts_service.get_recent_alerts(limit)
        return {
            "alerts": alerts,
            "count": len(alerts),
            "enabled": alerts_service.alerts_enabled,
            "volume_threshold": alerts_service.volume_threshold
        }
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get alerts: {str(e)}"}
        )

@api_router.post("/alerts/clear")
async def clear_market_alerts(username: str = Depends(verify_credentials_dual)):
    """Clear all market alerts"""
    try:
        alerts_service = get_market_alerts_service(ws_manager)
        alerts_service.clear_alerts()
        return {"message": "Alerts cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing alerts: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to clear alerts: {str(e)}"}
        )

@api_router.post("/alerts/toggle")
async def toggle_market_alerts(enabled: bool, username: str = Depends(verify_credentials_dual)):
    """Toggle market alerts on/off"""
    try:
        alerts_service = get_market_alerts_service(ws_manager)
        alerts_service.alerts_enabled = enabled
        
        # Save to database
        db = get_db()
        await db.user_config.update_one(
            {"type": "trading_preferences"},
            {"$set": {"alerts_enabled": enabled}},
            upsert=True
        )
        
        return {
            "message": f"Alerts {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        }
    except Exception as e:
        logger.error(f"Error toggling alerts: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to toggle alerts: {str(e)}"}
        )

# Historical Data Collection Endpoints
@api_router.get("/historical/stats")
async def get_historical_stats():
    """Get statistics about collected historical data"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        stats = await historical_collector.get_collection_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting historical stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get stats: {str(e)}"}
        )

@api_router.post("/historical/collect")
async def trigger_collection(background_tasks: BackgroundTasks):
    """Trigger a one-time data collection"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        # Run collection in background
        count = await historical_collector.collect_market_snapshot()
        
        return {
            "message": f"Collected {count} market snapshots",
            "count": count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error triggering collection: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to collect data: {str(e)}"}
        )

@api_router.post("/historical/start-continuous")
async def start_continuous_collection(background_tasks: BackgroundTasks):
    """Start continuous background data collection"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        if historical_collector.running:
            return JSONResponse(
                status_code=400,
                content={"message": "Continuous collection already running"}
            )
        
        background_tasks.add_task(historical_collector.start_collection)
        
        return {
            "message": "Started continuous data collection",
            "interval_seconds": historical_collector.collection_interval
        }
    except Exception as e:
        logger.error(f"Error starting continuous collection: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to start collection: {str(e)}"}
        )

@api_router.post("/historical/stop-continuous")
async def stop_continuous_collection():
    """Stop continuous background data collection"""
    global historical_collector
    
    try:
        if not historical_collector or not historical_collector.running:
            return JSONResponse(
                status_code=400,
                content={"message": "Continuous collection not running"}
            )
        
        await historical_collector.stop_collection()
        
        return {"message": "Stopped continuous data collection"}
    except Exception as e:
        logger.error(f"Error stopping continuous collection: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop collection: {str(e)}"}
        )

# Price History Collection Endpoints (High-Fidelity Data)
@api_router.post("/historical/collect-prices")
async def collect_price_history(
    market_limit: int = 50,
    interval: str = "1w",
    fidelity: int = 60
):
    """
    Collect high-fidelity price history for active markets.
    This provides REAL price movements instead of static snapshots.
    
    - market_limit: Number of markets to collect (ordered by volume)
    - interval: Time interval ("1h", "6h", "1d", "1w", "max")
    - fidelity: Resolution in minutes (minimum 5 for 1w interval)
    """
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        stats = await historical_collector.collect_price_history(
            market_limit=market_limit,
            interval=interval,
            fidelity=fidelity
        )
        
        return {
            "message": "Price history collection completed",
            "stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error collecting price history: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to collect price history: {str(e)}"}
        )

@api_router.get("/historical/price-stats")
async def get_price_history_stats():
    """Get statistics about collected price history data"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        stats = await historical_collector.get_price_history_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting price history stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get stats: {str(e)}"}
        )

@api_router.post("/historical/start-price-collection")
async def start_price_history_collection(
    background_tasks: BackgroundTasks,
    interval_minutes: int = 30,
    market_limit: int = 50
):
    """Start continuous high-fidelity price history collection"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        if historical_collector.price_history_running:
            return JSONResponse(
                status_code=400,
                content={"message": "Price history collection already running"}
            )
        
        background_tasks.add_task(
            historical_collector.start_price_history_collection,
            interval_minutes,
            market_limit
        )
        
        return {
            "message": "Started continuous price history collection",
            "interval_minutes": interval_minutes,
            "market_limit": market_limit
        }
    except Exception as e:
        logger.error(f"Error starting price history collection: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to start collection: {str(e)}"}
        )

@api_router.post("/historical/stop-price-collection")
async def stop_price_history_collection():
    """Stop continuous price history collection"""
    global historical_collector
    
    try:
        if not historical_collector or not historical_collector.price_history_running:
            return JSONResponse(
                status_code=400,
                content={"message": "Price history collection not running"}
            )
        
        await historical_collector.stop_price_history_collection()
        
        return {"message": "Stopped price history collection"}
    except Exception as e:
        logger.error(f"Error stopping price history collection: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop collection: {str(e)}"}
        )

@api_router.get("/historical/data")
async def get_historical_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100
):
    """Get historical market data"""
    global historical_collector
    
    try:
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        if start_date and end_date:
            data = await historical_collector.get_historical_data_by_date_range(
                start_date, end_date, category
            )
            return {"data": data[:limit], "total": len(data)}
        else:
            # Return recent data
            db = get_db()
            cursor = db.historical_data.find(
                {},
                {"_id": 0, "raw_data": 0}
            ).sort("timestamp", -1).limit(limit)
            data = await cursor.to_list(length=limit)
            return {"data": data, "count": len(data)}
    except Exception as e:
        logger.error(f"Error getting historical data: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get data: {str(e)}"}
        )

# ML Model Training Endpoints
@api_router.get("/ml/stats")
async def get_ml_stats():
    """Get all ML model training statistics"""
    try:
        from ml.volatility_predictor import VolatilityPredictor
        from ml.bayesian_outlier import BayesianOutlierDetector
        
        vol_predictor = VolatilityPredictor()
        outlier_detector = BayesianOutlierDetector()
        
        vol_stats = await vol_predictor.get_model_stats()
        outlier_stats = await outlier_detector.get_model_stats()
        
        return {
            "volatility_predictor": vol_stats,
            "bayesian_outlier": outlier_stats
        }
    except Exception as e:
        logger.error(f"Error getting ML stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get ML stats: {str(e)}"}
        )

@api_router.post("/ml/train/all")
async def train_all_ml_models(background_tasks: BackgroundTasks):
    """Train all ML models on historical data"""
    try:
        from ml.volatility_predictor import VolatilityPredictor
        from ml.bayesian_outlier import BayesianOutlierDetector
        
        results = {}
        
        # Train volatility predictor
        vol_predictor = VolatilityPredictor()
        vol_result = await vol_predictor.train_model()
        results["volatility_predictor"] = vol_result
        
        # Train mispricing detector
        outlier_detector = BayesianOutlierDetector()
        outlier_result = await outlier_detector.train_model()
        results["bayesian_outlier"] = outlier_result
        
        return {
            "message": "ML models training completed",
            "results": results
        }
    except Exception as e:
        logger.error(f"Error training ML models: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to train ML models: {str(e)}"}
        )

@api_router.post("/rl/learn-from-backtest/{backtest_id}")
async def rl_learn_from_backtest(backtest_id: str):
    """Trigger RL engine to learn from a specific backtest's results"""
    try:
        db = get_db()
        
        # Get the backtest results
        backtest_result = await db.backtest_results.find_one(
            {"backtest_id": backtest_id},
            {"_id": 0}
        )
        
        if not backtest_result:
            return JSONResponse(
                status_code=404,
                content={"message": "Backtest not found"}
            )
        
        # Create RL engine and learn from results
        from ml.rl_engine import RLAdaptiveEngine
        rl = RLAdaptiveEngine()
        
        # Try to load existing model first
        await rl.load_model()
        
        # Learn from this backtest
        await rl.learn_from_backtest_results(backtest_result)
        
        # Get updated stats
        stats = await rl.get_training_stats()
        
        return {
            "message": f"RL engine learned from backtest {backtest_id}",
            "backtest_return": backtest_result.get('total_return_pct', 0),
            "strategies_learned": list(backtest_result.get('strategy_results', {}).keys()),
            "rl_stats": stats
        }
    except Exception as e:
        logger.error(f"Error in RL learning from backtest: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to learn from backtest: {str(e)}"}
        )

@api_router.get("/rl/detailed-stats")
async def get_detailed_rl_stats():
    """Get detailed RL training statistics including Q-table analysis"""
    global rl_engine
    
    try:
        # Use global rl_engine to get accurate buffer stats
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
            await rl_engine.load_model()
        
        stats = await rl_engine.get_training_stats()
        
        return {
            "rl_stats": stats,
            "model_status": "loaded" if rl_engine.training_iterations > 0 else "fresh"
        }
    except Exception as e:
        logger.error(f"Error getting detailed RL stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get RL stats: {str(e)}"}
        )

@api_router.post("/ml/train/volatility")
async def train_volatility_model():
    """Train volatility prediction model"""
    try:
        from ml.volatility_predictor import VolatilityPredictor
        
        vol_predictor = VolatilityPredictor()
        result = await vol_predictor.train_model()
        
        return {
            "message": "Volatility model training completed",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error training volatility model: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to train: {str(e)}"}
        )

@api_router.post("/ml/train/mispricing")
async def train_mispricing_model():
    """Train mispricing detection model"""
    try:
        from ml.bayesian_outlier import BayesianOutlierDetector
        
        detector = BayesianOutlierDetector()
        result = await detector.train_model()
        
        return {
            "message": "Mispricing model training completed",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error training mispricing model: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to train: {str(e)}"}
        )

# Reinforcement Learning Engine Endpoints
@api_router.get("/rl/stats")
async def get_rl_stats():
    """Get RL engine training statistics"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
        
        stats = await rl_engine.get_training_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting RL stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get RL stats: {str(e)}"}
        )

@api_router.post("/rl/train")
async def trigger_rl_training():
    """Trigger RL batch training from replay buffer"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
        
        await rl_engine.train_from_replay()
        stats = await rl_engine.get_training_stats()
        
        return {
            "message": "RL batch training completed",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error in RL training: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to train RL: {str(e)}"}
        )

@api_router.post("/rl/save")
async def save_rl_model():
    """Save RL model to disk"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
        
        await rl_engine.save_model()
        return {"message": "RL model saved successfully"}
    except Exception as e:
        logger.error(f"Error saving RL model: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to save RL model: {str(e)}"}
        )

@api_router.post("/rl/load")
async def load_rl_model():
    """Load RL model from disk"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
        
        await rl_engine.load_model()
        stats = await rl_engine.get_training_stats()
        
        return {
            "message": "RL model loaded successfully",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error loading RL model: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to load RL model: {str(e)}"}
        )

@api_router.post("/rl/load-historical")
async def load_historical_experiences():
    """Load historical trading experiences into RL replay buffer"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine()
        
        loaded_count = await rl_engine.load_historical_experiences()
        stats = await rl_engine.get_training_stats()
        
        return {
            "message": f"Loaded {loaded_count} historical experiences",
            "loaded_count": loaded_count,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error loading historical experiences: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to load historical experiences: {str(e)}"}
        )

@api_router.post("/rl/switch-mode")
async def switch_rl_mode(use_dqn: bool = True):
    """Switch between DQN and Q-table modes"""
    global rl_engine
    
    try:
        if not rl_engine:
            rl_engine = RLAdaptiveEngine(use_dqn=use_dqn)
        else:
            rl_engine.switch_mode(use_dqn)
        
        stats = await rl_engine.get_training_stats()
        
        return {
            "message": f"Switched to {'DQN' if use_dqn else 'Q-table'} mode",
            "mode": "DQN" if use_dqn else "Q-table",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error switching RL mode: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to switch RL mode: {str(e)}"}
        )

# =============================================
# SOCIAL SENTIMENT ANALYSIS ENDPOINTS
# =============================================

@api_router.get("/sentiment/analyze")
async def analyze_sentiment(market_id: str = None, question: str = None, category: str = "unknown"):
    """Analyze social sentiment for a market"""
    try:
        market_data = {
            'id': market_id or 'manual',
            'question': question or '',
            'category': category
        }
        
        result = await social_sentiment_analyzer.analyze_market_sentiment(market_data)
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to analyze sentiment: {str(e)}"}
        )

@api_router.get("/sentiment/trending")
async def get_trending_topics(limit: int = 10):
    """Get currently trending topics from news"""
    try:
        topics = await social_sentiment_analyzer.get_trending_topics(limit)
        return {"trending_topics": topics}
    except Exception as e:
        logger.error(f"Error getting trending topics: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get trending topics: {str(e)}"}
        )


@api_router.get("/sentiment/enhanced/{market_id}")
async def get_enhanced_sentiment(market_id: str):
    """
    Get enhanced sentiment analysis for a market including:
    - Polymarket-native signals (order flow, volume momentum, whale activity)
    - LLM sentiment
    - Cross-market correlation
    - Sentiment momentum (1h/6h/24h changes)
    """
    try:
        from ml.enhanced_sentiment import get_enhanced_sentiment_analyzer
        from data.polymarket_api import PolymarketAPI
        
        analyzer = get_enhanced_sentiment_analyzer()
        if not analyzer:
            return JSONResponse(status_code=503, content={"error": "Sentiment analyzer not available"})
        
        # Fetch market data - try multiple methods
        async with PolymarketAPI() as api:
            # First try direct lookup
            market_data = await api.get_market(market_id)
            
            # If not found, search in active markets
            if not market_data:
                markets = await api.get_markets(limit=200)
                for m in markets:
                    if m.get('id') == market_id or m.get('condition_id') == market_id:
                        market_data = m
                        break
            
            if not market_data:
                return JSONResponse(status_code=404, content={"error": f"Market {market_id[:20]}... not found"})
            
            # Get trades and order book for full analysis
            token_ids = market_data.get('clobTokenIds', market_data.get('tokens', []))
            trades = []
            order_book = {}
            
            if token_ids and len(token_ids) > 0:
                try:
                    trades = await api.get_trades(token_ids[0], limit=50)
                except:
                    pass
                try:
                    order_book = await api.get_order_book(token_ids[0])
                except:
                    pass
        
        # Run enhanced analysis
        result = await analyzer.analyze(market_data, trades=trades, order_book=order_book)
        
        return {
            "market_id": market_id,
            "question": market_data.get('question', ''),
            "current_price": market_data.get('yes_price'),  # Let frontend handle None
            "sentiment": result
        }
        
    except Exception as e:
        logger.error(f"Error in enhanced sentiment: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/sentiment/momentum/{market_id}")
async def get_sentiment_momentum(market_id: str):
    """
    Get sentiment momentum for a market (how sentiment is changing over time).
    
    Returns changes over 1h, 6h, and 24h windows.
    """
    try:
        from ml.polymarket_sentiment import get_polymarket_sentiment_extractor
        
        extractor = get_polymarket_sentiment_extractor()
        summary = extractor.get_market_sentiment_summary(market_id)
        
        return {
            "market_id": market_id,
            **summary
        }
        
    except Exception as e:
        logger.error(f"Error getting sentiment momentum: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/sentiment/llm/stats")
async def get_llm_stats():
    """
    Get Smart LLM cache statistics.
    
    Returns cache hit/miss rates, call counts, cost savings, and configuration.
    
    The Smart LLM module uses Hybrid Smart-Cache:
    - Hot markets (high volume): shorter cache TTL (catch breaking news)
    - Cold markets (low volume): longer cache TTL (save money)
    """
    try:
        from ml.sentiment_llm import get_smart_llm_analyzer
        
        analyzer = get_smart_llm_analyzer()
        stats = analyzer.get_stats()
        config = stats.get('config', {})
        
        return {
            "status": "ok",
            "cache_strategy": "Hybrid Smart-Cache",
            "description": f"Hot markets (>${config.get('hot_market_volume_threshold', 50000):,}): {config.get('hot_market_ttl_seconds', 600)//60} min TTL, Cold markets: {config.get('cold_market_ttl_seconds', 3600)//60} min TTL",
            "stats": stats,
            "cache_entries": analyzer.get_cache_entries()
        }
        
    except Exception as e:
        logger.error(f"Error getting LLM stats: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/sentiment/llm/config")
async def get_llm_config():
    """
    Get Smart LLM cache configuration.
    
    Returns current cache configuration including:
    - hot_market_ttl_seconds: Cache TTL for high-volume markets
    - cold_market_ttl_seconds: Cache TTL for low-volume markets
    - hot_market_volume_threshold: Volume threshold to classify markets
    - llm_timeout_seconds: LLM API call timeout
    - estimated_cost_per_call: Estimated cost per LLM API call
    """
    try:
        from ml.sentiment_llm import get_smart_llm_analyzer
        
        analyzer = get_smart_llm_analyzer()
        config = analyzer.get_config()
        
        return {
            "status": "ok",
            "config": config,
            "config_info": {
                "hot_market_ttl_seconds": {
                    "value": config.get('hot_market_ttl_seconds', 600),
                    "unit": "seconds",
                    "description": "Cache TTL for hot (high-volume) markets. Shorter = fresher data, higher cost.",
                    "min": 60,
                    "max": 3600,
                    "default": 600
                },
                "cold_market_ttl_seconds": {
                    "value": config.get('cold_market_ttl_seconds', 3600),
                    "unit": "seconds", 
                    "description": "Cache TTL for cold (low-volume) markets. Longer = lower cost, less fresh.",
                    "min": 300,
                    "max": 7200,
                    "default": 3600
                },
                "hot_market_volume_threshold": {
                    "value": config.get('hot_market_volume_threshold', 50000),
                    "unit": "USD",
                    "description": "24h volume threshold to classify a market as 'hot'. Markets above this get shorter cache TTL.",
                    "min": 10000,
                    "max": 500000,
                    "default": 50000
                },
                "llm_timeout_seconds": {
                    "value": config.get('llm_timeout_seconds', 10.0),
                    "unit": "seconds",
                    "description": "Maximum time to wait for LLM response before timeout.",
                    "min": 5,
                    "max": 30,
                    "default": 10
                },
                "estimated_cost_per_call": {
                    "value": config.get('estimated_cost_per_call', 0.002),
                    "unit": "USD",
                    "description": "Estimated cost per LLM API call (for cost tracking).",
                    "min": 0.0001,
                    "max": 0.1,
                    "default": 0.002
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting LLM config: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.post("/sentiment/llm/config")
async def update_llm_config(config_update: Dict):
    """
    Update Smart LLM cache configuration.
    
    Accepts any of:
    - hot_market_ttl_seconds: 60-3600
    - cold_market_ttl_seconds: 300-7200
    - hot_market_volume_threshold: 10000-500000
    - llm_timeout_seconds: 5-30
    - estimated_cost_per_call: 0.0001-0.1
    """
    try:
        from ml.sentiment_llm import get_smart_llm_analyzer
        
        analyzer = get_smart_llm_analyzer()
        
        # Validate inputs
        validated = {}
        
        if 'hot_market_ttl_seconds' in config_update:
            val = int(config_update['hot_market_ttl_seconds'])
            validated['hot_market_ttl_seconds'] = max(60, min(3600, val))
            
        if 'cold_market_ttl_seconds' in config_update:
            val = int(config_update['cold_market_ttl_seconds'])
            validated['cold_market_ttl_seconds'] = max(300, min(7200, val))
            
        if 'hot_market_volume_threshold' in config_update:
            val = float(config_update['hot_market_volume_threshold'])
            validated['hot_market_volume_threshold'] = max(10000, min(500000, val))
            
        if 'llm_timeout_seconds' in config_update:
            val = float(config_update['llm_timeout_seconds'])
            validated['llm_timeout_seconds'] = max(5, min(30, val))
            
        if 'estimated_cost_per_call' in config_update:
            val = float(config_update['estimated_cost_per_call'])
            validated['estimated_cost_per_call'] = max(0.0001, min(0.1, val))
        
        if not validated:
            return JSONResponse(
                status_code=400, 
                content={"error": "No valid configuration parameters provided"}
            )
        
        new_config = analyzer.update_config(validated)
        
        return {
            "status": "ok",
            "message": f"Updated {len(validated)} configuration parameter(s)",
            "updated": validated,
            "config": new_config
        }
        
    except Exception as e:
        logger.error(f"Error updating LLM config: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/sentiment/polymarket/history-stats")
async def get_polymarket_history_stats():
    """
    Get Polymarket sentiment history statistics.
    
    Shows how much historical data has been collected for momentum signals.
    Time-based signals (volume_momentum, price_velocity, price_momentum) require
    sufficient historical data points to be calculated.
    
    Returns:
    - Total markets tracked
    - Data points per market
    - Momentum signal readiness status
    """
    try:
        from ml.polymarket_sentiment import get_polymarket_sentiment_extractor
        
        extractor = get_polymarket_sentiment_extractor()
        stats = extractor.get_history_stats()
        
        # Count ready vs building
        ready_count = sum(1 for m in stats.get('momentum_signal_readiness', {}).values() if m.get('status') == 'ready')
        building_count = sum(1 for m in stats.get('momentum_signal_readiness', {}).values() if m.get('status') == 'building')
        
        return {
            "status": "ok",
            "description": "Time-series cache for Polymarket momentum signals",
            "summary": {
                "total_markets_tracked": stats.get('total_markets_tracked', 0),
                "momentum_ready": ready_count,
                "momentum_building": building_count,
            },
            "requirements": {
                "price_momentum": "5+ price data points",
                "price_velocity": "3+ price data points", 
                "volume_momentum": "3+ volume data points",
            },
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting Polymarket history stats: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/realtime/status")
async def get_realtime_status():
    """
    Get real-time data feed status including WebSocket connection stats.
    Used by the WebSocket Health Monitor widget on the dashboard.
    """
    try:
        from data.polymarket_websocket import get_websocket_manager
        from services.realtime_market_service import get_realtime_market_service
        
        ws_manager = get_websocket_manager()
        ws_stats = ws_manager.get_stats()
        
        # Get realtime market service stats if available
        rtm_service = get_realtime_market_service()
        rtm_stats = rtm_service.get_stats() if rtm_service else {}
        
        return {
            "status": "connected" if ws_stats.get('connected') else "disconnected",
            "websocket": {
                "connected": ws_stats.get('connected', False),
                "running": ws_stats.get('running', False),
                "messages_received": ws_stats.get('messages_received', 0),
                "subscribed_tokens": ws_stats.get('subscribed_tokens', 0),
                "cached_prices": ws_stats.get('cached_prices', 0),
                "cached_order_books": ws_stats.get('cached_order_books', 0),
                "last_message": ws_stats.get('last_message'),
            },
            "market_service": {
                "running": rtm_stats.get('running', False),
                "token_mapping_ready": rtm_stats.get('token_mapping_ready', False),
                "markets_cached": rtm_stats.get('markets_cached', 0),
                "tokens_mapped": rtm_stats.get('tokens_mapped', 0),
                "yes_prices_cached": rtm_stats.get('yes_prices_cached', 0),
                "ws_updates_processed": rtm_stats.get('ws_updates', 0),
                "dropped_updates": rtm_stats.get('dropped_updates', 0),
                "rest_fetches": rtm_stats.get('rest_fetches', 0),
                "last_discovery": rtm_stats.get('last_discovery'),
            },
            "health": {
                "is_healthy": ws_stats.get('connected', False) and rtm_stats.get('token_mapping_ready', False),
                "update_rate": rtm_stats.get('ws_updates', 0),  # Total updates since start
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting realtime status: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@api_router.get("/sentiment/github/{market_id}")
async def get_github_sentiment(market_id: str):
    """
    Get GitHub activity sentiment for a crypto/tech market.
    
    Analyzes commit velocity, releases, issues, and community metrics.
    """
    try:
        from ml.github_sentiment import get_github_sentiment_analyzer
        from data.polymarket_api import PolymarketAPI
        
        analyzer = get_github_sentiment_analyzer()
        if not analyzer:
            return JSONResponse(status_code=503, content={"error": "GitHub analyzer not available"})
        
        # Fetch market data
        async with PolymarketAPI() as api:
            market_data = await api.get_market(market_id)
            
            if not market_data:
                markets = await api.get_markets(limit=200)
                for m in markets:
                    if m.get('id') == market_id:
                        market_data = m
                        break
            
            if not market_data:
                return JSONResponse(status_code=404, content={"error": "Market not found"})
        
        # Analyze GitHub sentiment
        result = await analyzer.analyze_market(market_data)
        
        return {
            "market_id": market_id,
            "question": market_data.get('question', ''),
            "category": market_data.get('category', ''),
            "github": result
        }
        
    except Exception as e:
        logger.error(f"Error in GitHub sentiment: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

# =============================================
# WHALE/SHARP TRACKER ENDPOINTS
# =============================================

@api_router.get("/whale/detect")
async def detect_whale_activity(market_id: str, volume24hr: float = 0, liquidity: float = 0):
    """Detect whale activity for a specific market"""
    try:
        market_data = {
            'id': market_id,
            'volume24hr': volume24hr,
            'liquidity': liquidity
        }
        
        result = await whale_tracker.detect_whale_activity(market_data)
        return result
        
    except Exception as e:
        logger.error(f"Error detecting whale activity: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to detect whale activity: {str(e)}"}
        )

@api_router.get("/whale/statistics")
async def get_whale_statistics():
    """Get overall whale tracking statistics"""
    try:
        stats = await whale_tracker.get_whale_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error getting whale statistics: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get statistics: {str(e)}"}
        )

@api_router.post("/whale/track-sharp")
async def track_sharp_traders():
    """Analyze and track sharp (smart money) traders"""
    try:
        result = await whale_tracker.track_sharp_traders()
        return result
    except Exception as e:
        logger.error(f"Error tracking sharp traders: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to track sharp traders: {str(e)}"}
        )

# =============================================
# STRATEGY TUNING ENDPOINTS
# =============================================

@api_router.post("/tuning/strategy")
async def tune_strategy(
    background_tasks: BackgroundTasks,
    strategy_name: str,
    start_date: str = "2026-01-01T00:00:00Z",
    end_date: str = "2026-01-14T23:59:59Z",
    max_combinations: int = 30
):
    """
    Tune a single strategy's parameters using grid search.
    Runs in background for large parameter spaces.
    """
    try:
        if strategy_tuner.running:
            return JSONResponse(
                status_code=400,
                content={"message": "Tuning already in progress"}
            )
        
        # Run tuning (this can take a while)
        result = await strategy_tuner.tune_strategy(
            strategy_name, start_date, end_date, max_combinations
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error tuning strategy: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to tune strategy: {str(e)}"}
        )

@api_router.post("/tuning/all")
async def tune_all_strategies(
    start_date: str = "2026-01-01T00:00:00Z",
    end_date: str = "2026-01-14T23:59:59Z",
    max_combinations_per_strategy: int = 20
):
    """Tune all strategies' parameters"""
    try:
        if strategy_tuner.running:
            return JSONResponse(
                status_code=400,
                content={"message": "Tuning already in progress"}
            )
        
        result = await strategy_tuner.tune_all_strategies(
            start_date, end_date, max_combinations_per_strategy
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error tuning all strategies: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to tune strategies: {str(e)}"}
        )

@api_router.get("/tuning/best/{strategy_name}")
async def get_best_parameters(strategy_name: str):
    """Get the best parameters from previous tuning for a strategy"""
    try:
        result = await strategy_tuner.get_best_parameters(strategy_name)
        if result:
            return result
        return {"message": "No tuning results found for this strategy"}
    except Exception as e:
        logger.error(f"Error getting best parameters: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get best parameters: {str(e)}"}
        )

@api_router.get("/tuning/history")
async def get_tuning_history(limit: int = 10):
    """Get recent tuning history"""
    try:
        history = await strategy_tuner.get_tuning_history(limit)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting tuning history: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get history: {str(e)}"}
        )

@api_router.post("/tuning/stop")
async def stop_tuning():
    """Stop current tuning process"""
    try:
        strategy_tuner.stop_tuning()
        return {"message": "Tuning stopped"}
    except Exception as e:
        logger.error(f"Error stopping tuning: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop tuning: {str(e)}"}
        )

# =============================================
# ALERTS SYSTEM ENDPOINTS
# =============================================

from services.alert_service import alert_service, AlertType

class AlertConfigUpdate(BaseModel):
    whale_activity_min: Optional[float] = None
    sentiment_shift_min: Optional[float] = None
    drawdown_max: Optional[float] = None
    profit_notification_min: Optional[float] = None

class TestAlertRequest(BaseModel):
    recipient_email: str
    alert_type: str = "test"

@api_router.get("/alerts/config")
async def get_alert_config():
    """Get current alert configuration"""
    return await alert_service.get_alert_config()

@api_router.post("/alerts/config")
async def update_alert_config(config_update: AlertConfigUpdate):
    """Update alert thresholds"""
    updates = {k: v for k, v in config_update.dict().items() if v is not None}
    await alert_service.update_thresholds(updates)
    return {"message": "Alert config updated", "new_config": await alert_service.get_alert_config()}

@api_router.get("/alerts/history")
async def get_alert_history(limit: int = Query(50, ge=1, le=200)):
    """Get alert history"""
    return {"history": await alert_service.get_alert_history(limit)}

@api_router.post("/alerts/test")
async def send_test_alert(request: TestAlertRequest):
    """Send a test alert email"""
    if not alert_service.enabled:
        return JSONResponse(
            status_code=400,
            content={"message": "Alerts disabled - SENDGRID_API_KEY not configured"}
        )
    
    # Send test backtest complete alert
    test_results = {
        "backtest_id": "test-alert",
        "total_pnl": 125.50,
        "total_return_pct": 12.55,
        "total_trades": 150,
        "win_rate": 0.65,
        "sharpe_ratio": 1.25,
        "max_drawdown": 0.03
    }
    
    success = await alert_service.send_backtest_complete_alert(
        request.recipient_email,
        test_results
    )
    
    if success:
        return {"message": f"Test alert sent to {request.recipient_email}"}
    else:
        return JSONResponse(
            status_code=500,
            content={"message": "Failed to send test alert"}
        )

# =============================================
# PAPER TRADING ENDPOINTS
# =============================================

from paper_trading.paper_trader import PaperTrader
from paper_trading.strategy_optimizer import StrategyOptimizer

paper_trader: Optional[PaperTrader] = None
strategy_optimizer: Optional[StrategyOptimizer] = None

# =============================================
# NEWS/EMERGENT LANE (Lane 5) - Webhook Endpoints
# =============================================

class NewsWebhookPayload(BaseModel):
    """Payload for news webhook"""
    headline: str = Field(..., description="News headline")
    content: str = Field("", description="Full news content")
    source: str = Field("webhook", description="News source URL or name")
    url: str = Field("", description="Original article URL")
    priority: str = Field("normal", description="Priority: 'high' or 'normal'")


@api_router.post("/hooks/news-alert")
async def news_webhook(
    payload: NewsWebhookPayload,
    background_tasks: BackgroundTasks
):
    """
    Webhook endpoint for news alerts.
    
    Lane 5: NEWS/EMERGENT
    
    This endpoint receives breaking news and processes it through:
    1. LLM analysis to determine market relevance
    2. Event Bayesian update to calculate Bayes Factor
    3. Cache injection if BF > threshold (default 3.0)
    
    The HFT loop then reads from cache and executes at speed.
    
    Expected payload:
    {
        "headline": "Breaking: ...",
        "content": "Full article text...",
        "source": "reuters.com",
        "url": "https://...",
        "priority": "high"  // or "normal"
    }
    """
    global news_injector
    
    try:
        # Initialize news injector if not already
        if news_injector is None:
            signal_cache = get_signal_cache()
            news_injector = get_news_injector(
                signal_cache=signal_cache,
                market_fetcher=get_active_markets_for_news
            )
        
        # Process webhook (runs in background for high priority, inline for normal)
        result = await news_injector.handle_webhook(payload.dict())
        
        return {
            "status": "accepted",
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[NEWS WEBHOOK] Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


class NewsTestPayload(BaseModel):
    """Payload for testing the full news pipeline"""
    headline: str = Field(..., description="News headline")
    content: str = Field("", description="Full news content")
    source: str = Field("test", description="News source")
    market_question: str = Field(..., description="Market question to test against")
    current_price: float = Field(0.5, description="Current YES price")


@api_router.post("/hooks/news-test")
async def test_news_pipeline(payload: NewsTestPayload):
    """
    TEST ENDPOINT: Verify the full Lane 5 pipeline.
    
    This endpoint simulates the complete flow:
    1. LLM Analysis (Event Resolution Adjudicator)
    2. Bayesian Update
    3. Signal Generation
    
    Use this to verify the pipeline without needing live markets.
    """
    from services.llm_service import get_llm_service
    from bayesian_math.event_bayes import get_event_bayes
    
    try:
        # Step 1: LLM Analysis
        llm_service = get_llm_service()
        llm_result = await llm_service.analyze_news_for_market(
            news_headline=payload.headline,
            news_content=payload.content,
            market_question=payload.market_question
        )
        
        # Step 2: Bayesian Update
        event_bayes = get_event_bayes()
        bayes_result = event_bayes.update(
            market_id="test_market",
            market_question=payload.market_question,
            current_price=payload.current_price,
            news_headline=payload.headline,
            news_content=payload.content,
            news_source=payload.source,
            llm_analysis={
                'direction': llm_result.direction,
                'impact': llm_result.impact,
                'confidence': llm_result.confidence,
                'reasoning': llm_result.rationale
            }
        )
        
        # Step 3: Calculate Kelly Size (simulate)
        posterior = bayes_result.posterior
        confidence = bayes_result.confidence
        edge = abs(posterior - payload.current_price)
        kelly_fraction = 0.25
        base_size_pct = posterior * kelly_fraction * confidence
        simulated_capital = 10000
        position_size = simulated_capital * base_size_pct if edge >= 0.02 else 0
        
        return {
            "status": "success",
            "pipeline_results": {
                "step_1_llm": {
                    "is_relevant": llm_result.is_relevant,
                    "is_bullish_for_yes": llm_result.is_bullish_for_yes,
                    "confidence": llm_result.confidence,
                    "direction": llm_result.direction,
                    "impact": llm_result.impact,
                    "rationale": llm_result.rationale
                },
                "step_2_bayes": {
                    "prior": round(bayes_result.prior, 4),
                    "posterior": round(bayes_result.posterior, 4),
                    "bayes_factor": round(bayes_result.bayes_factor, 4),
                    "is_actionable": bayes_result.is_actionable(),
                    "news_impact": bayes_result.news_impact.value
                },
                "step_3_kelly": {
                    "edge": round(edge, 4),
                    "kelly_fraction": kelly_fraction,
                    "position_size_usd": round(position_size, 2),
                    "would_trade": position_size > 5.0
                }
            },
            "verdict": "TRADE" if bayes_result.is_actionable() and position_size > 5.0 else "NO_TRADE",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[NEWS TEST] Error: {e}")
        import traceback
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e), "trace": traceback.format_exc()}
        )


@api_router.get("/hooks/news-status")
async def news_injector_status():
    """Get status of the News Injector service"""
    global news_injector
    
    if news_injector is None:
        return {
            "status": "not_initialized",
            "is_running": False,
            "config": {}
        }
    
    return {
        "status": "active" if news_injector.is_running else "stopped",
        "is_running": news_injector.is_running,
        "config": {
            "min_bayes_factor": news_injector.config.get('min_bayes_factor', 3.0),
            "poll_interval_seconds": news_injector.config.get('exa_poll_interval_seconds', 60),
            "exa_enabled": bool(news_injector._exa_api_key)
        },
        "stats": {
            "injections_this_minute": news_injector._injection_count
        }
    }


@api_router.post("/hooks/news-start")
async def start_news_injector(
    background_tasks: BackgroundTasks,
    username: str = Depends(verify_credentials_dual)
):
    """Start the News Injector background polling"""
    global news_injector
    
    try:
        if news_injector is None:
            signal_cache = get_signal_cache()
            news_injector = get_news_injector(
                signal_cache=signal_cache,
                market_fetcher=get_active_markets_for_news
            )
        
        if news_injector.is_running:
            return {"status": "already_running"}
        
        await news_injector.start()
        
        return {
            "status": "started",
            "message": "News Injector polling started",
            "exa_enabled": bool(news_injector._exa_api_key)
        }
        
    except Exception as e:
        logger.error(f"[NEWS INJECTOR] Start error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@api_router.post("/hooks/news-stop")
async def stop_news_injector(
    username: str = Depends(verify_credentials_dual)
):
    """Stop the News Injector background polling"""
    global news_injector
    
    if news_injector is None:
        return {"status": "not_initialized"}
    
    if not news_injector.is_running:
        return {"status": "already_stopped"}
    
    await news_injector.stop()
    
    return {
        "status": "stopped",
        "message": "News Injector polling stopped"
    }


@api_router.post("/hooks/news-config")
async def update_news_config(
    min_bayes_factor: float = 3.0,
    poll_interval_seconds: int = 60,
    username: str = Depends(verify_credentials_dual)
):
    """Update News Injector configuration"""
    global news_injector
    
    if news_injector is None:
        signal_cache = get_signal_cache()
        news_injector = get_news_injector(
            signal_cache=signal_cache,
            market_fetcher=get_active_markets_for_news
        )
    
    # Update config
    news_injector.config['min_bayes_factor'] = min_bayes_factor
    news_injector.config['exa_poll_interval_seconds'] = poll_interval_seconds
    news_injector.event_bayes.config['min_bayes_factor'] = min_bayes_factor
    
    return {
        "status": "updated",
        "config": {
            "min_bayes_factor": min_bayes_factor,
            "poll_interval_seconds": poll_interval_seconds
        }
    }


@api_router.post("/hooks/news-poll")
async def trigger_news_poll(
    query: str = "prediction market breaking news",
    num_results: int = 10,
    hours_back: int = 24
):
    """
    Manually trigger a news poll from Exa.ai.
    
    This endpoint allows testing the Exa.ai integration by
    performing an immediate search without waiting for the
    background polling interval.
    
    Args:
        query: Search query for Exa.ai
        num_results: Number of results to return (max 100)
        hours_back: How far back to search
        
    Returns:
        List of news events found
    """
    from services.news_service import get_news_poller
    
    try:
        poller = get_news_poller()
        
        if not poller.is_enabled():
            return JSONResponse(
                status_code=503,
                content={
                    "status": "disabled",
                    "message": "EXA_API_KEY not configured in backend/.env",
                    "hint": "Add EXA_API_KEY=your-key to /app/backend/.env"
                }
            )
        
        # Perform the poll
        events = await poller.poll_news(
            query=query,
            num_results=min(num_results, 100),
            hours_back=hours_back
        )
        
        # Get stats
        stats = poller.get_stats()
        
        return {
            "status": "success",
            "query": query,
            "events_found": len(events),
            "events": [event.to_dict() for event in events[:20]],  # Limit response size
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"[NEWS POLL] Manual poll error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@api_router.get("/hooks/exa-status")
async def get_exa_status():
    """
    Get the status of the Exa.ai news polling service.
    
    Returns configuration and statistics about news polling.
    """
    from services.news_service import get_news_poller
    
    poller = get_news_poller()
    stats = poller.get_stats()
    
    return {
        "exa_enabled": poller.is_enabled(),
        "exa_sdk_initialized": poller._exa_client is not None,
        "default_queries": poller.DEFAULT_QUERIES,
        "priority_sources": poller.PRIORITY_SOURCES,
        "stats": stats,
        "source_reliability_scores": poller.source_reliability
    }


# =============================================
# WEBHOOK SOURCES ENDPOINTS (Lane 5 Enhancement)
# =============================================

@api_router.get("/hooks/webhook-sources/status")
async def get_webhook_sources_status():
    """
    Get status of all webhook sources.
    
    Sources:
    - Apify Twitter: @AP, @WojESPN, @ShamsCharania, @Polymarket
    - Whale Alerts: Polymarket trades > $5,000
    - CryptoPanic: Macro crypto news
    """
    manager = get_webhook_sources_manager()
    return {
        "status": "running" if manager.is_running else "stopped",
        "stats": manager.get_stats()
    }


@api_router.get("/hooks/signal-cache/status")
async def get_signal_cache_status():
    """
    Get status of the signal cache (for debugging).
    
    Shows all cached signals with their TTL and metadata.
    """
    cache = get_signal_cache()
    
    # Get all non-expired signals
    signals = {}
    for key, entry in list(cache._cache.items()):
        if not entry.is_expired():
            signals[key] = {
                'value': entry.value,
                'expires_at': entry.expires_at.isoformat(),
                'ttl_remaining': (entry.expires_at - datetime.now(timezone.utc)).total_seconds()
            }
    
    return {
        "status": "active",
        "signal_count": len(signals),
        "signals": signals,
        "stats": cache._stats
    }


@api_router.post("/hooks/webhook-sources/start")
async def start_webhook_sources(background_tasks: BackgroundTasks):
    """
    Start all webhook source polling loops.
    
    Polling intervals:
    - Apify Twitter: Every 5 minutes
    - CryptoPanic: Every 1 minute
    - Whale Alerts: Real-time (WebSocket) with DIRECT INJECTION (skip LLM)
    """
    global news_injector
    
    # Get signal cache for whale direct injection
    signal_cache = get_signal_cache()
    
    # Ensure news injector is initialized
    if news_injector is None:
        news_injector = get_news_injector(
            signal_cache=signal_cache,
            market_fetcher=get_active_markets_for_news
        )
    
    # Create callback to process news through injector (for Apify, CryptoPanic)
    async def process_webhook_news(payload: Dict):
        from services.news_injector import NewsItem
        news = NewsItem(
            headline=payload.get('headline', ''),
            content=payload.get('content', ''),
            source=payload.get('source', 'webhook'),
            url=payload.get('url', ''),
            published_at=datetime.now(timezone.utc)
        )
        await news_injector.process_news(news)
    
    # Pass signal_cache for whale direct injection
    manager = get_webhook_sources_manager(
        news_callback=process_webhook_news,
        signal_cache=signal_cache
    )
    
    if manager.is_running:
        return {"status": "already_running", "message": "Webhook sources already running"}
    
    # Start in background
    background_tasks.add_task(manager.start)
    
    return {
        "status": "starting",
        "message": "Webhook sources starting...",
        "sources": {
            "apify_twitter": manager.apify.is_enabled(),
            "whale_alerts": manager.whale.is_enabled(),
            "cryptopanic": manager.cryptopanic.is_enabled(),
        }
    }


@api_router.post("/hooks/webhook-sources/stop")
async def stop_webhook_sources():
    """Stop all webhook source polling loops"""
    manager = get_webhook_sources_manager()
    
    if not manager.is_running:
        return {"status": "already_stopped", "message": "Webhook sources not running"}
    
    await manager.stop()
    
    return {"status": "stopped", "message": "Webhook sources stopped"}


@api_router.post("/hooks/test-whale-alert")
async def test_whale_alert(
    size_usd: float = 10000,
    side: str = "YES",
    price: float = 0.65,
    market_id: str = "test_market_123"
):
    """
    Test the whale alert system by simulating a large trade.
    
    This will process the fake trade through the news pipeline.
    """
    manager = get_webhook_sources_manager()
    
    # Simulate a trade
    trade_data = {
        'market': market_id,
        'side': side,
        'price': price,
        'size': size_usd / price,  # Shares = USD / price
    }
    
    news = await manager.whale.process_trade(trade_data)
    
    if news:
        return {
            "status": "alert_triggered",
            "headline": news.headline,
            "priority": news.priority,
            "size_usd": size_usd,
            "threshold": manager.whale.threshold_usd
        }
    else:
        return {
            "status": "below_threshold",
            "size_usd": size_usd,
            "threshold": manager.whale.threshold_usd,
            "message": f"Trade ${size_usd:,.0f} below threshold ${manager.whale.threshold_usd:,.0f}"
        }


@api_router.post("/hooks/test-cryptopanic")
async def test_cryptopanic_api():
    """
    Test CryptoPanic API status.
    
    Currently PAUSED - waiting for Premium subscription.
    """
    manager = get_webhook_sources_manager()
    
    if not manager.cryptopanic_api.is_enabled():
        return {
            "status": "paused",
            "message": "CryptoPanic is PAUSED (CRYPTOPANIC_ENABLED=false)",
            "reason": "Waiting for Premium subscription - free tier has 24h delay",
            "rss_status": "DEPRECATED - endpoint returns HTML",
            "how_to_reactivate": [
                "1. Upgrade to CryptoPanic GROWTH plan ($199/mo)",
                "2. Set CRYPTOPANIC_ENABLED=true in backend/.env",
                "3. Restart backend"
            ],
            "alternative": "Using Apify Twitter with crypto alpha accounts instead"
        }
    
    news_items = await manager.cryptopanic_api.fetch_news(limit=5)
    stats = manager.cryptopanic_api.get_stats()
    
    return {
        "status": "success",
        "source": "API (⚠️ 24h delay on free tier)",
        "items_found": len(news_items),
        "stats": stats,
        "news": [
            {
                "headline": n.headline[:100],
                "source": n.source,
                "priority": n.priority,
                "currencies": n.metadata.get('currencies', []),
                "url": n.url
            }
            for n in news_items[:10]
        ]
    }


@api_router.post("/hooks/test-apify")
async def test_apify_twitter(account: str = "Tier10k", hours_back: int = 720):
    """
    Smoke test for Apify Twitter scraper.
    
    Fetches tweets from a single account and returns raw structure + parsed results.
    Use this to verify the parser handles apidojo/tweet-scraper output correctly.
    
    Args:
        account: Twitter handle to fetch (default: Tier10k)
        hours_back: How far back to look for tweets (default: 720 = 30 days)
    """
    import aiohttp
    
    manager = get_webhook_sources_manager()
    
    if not manager.apify.is_enabled():
        return {
            "status": "disabled",
            "message": "Apify API key not configured",
            "hint": "Add APIFY_API_KEY to backend/.env"
        }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch tweets for the test account
            news_items = await manager.apify._fetch_account_tweets(
                session=session,
                account=account,
                hours_back=hours_back  # Use longer window for testing
            )
            
            return {
                "status": "success",
                "account": f"@{account}",
                "actor_id": manager.apify.actor_id,
                "hours_back": hours_back,
                "tweets_parsed": len(news_items),
                "target_accounts": manager.apify.TARGET_ACCOUNTS,
                "results": [
                    {
                        "headline": n.headline[:80],
                        "priority": n.priority,
                        "schema_detected": n.metadata.get('schema', 'unknown'),
                        "tweet_id": n.metadata.get('tweet_id', ''),
                        "likes": n.metadata.get('likes', 0),
                        "retweets": n.metadata.get('retweets', 0),
                    }
                    for n in news_items[:5]
                ]
            }
            
    except Exception as e:
        logger.error(f"[APIFY TEST] Error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "account": f"@{account}"
        }


@api_router.post("/hooks/apify-live-fire")
async def apify_live_fire_test(
    hours_back: int = 48,
    max_accounts: int = 15,
    background_tasks: BackgroundTasks = None
):
    """
    🔥 LIVE FIRE TEST: Full Apify scrape of ALL configured Twitter handles.
    
    This triggers the Apify scraping service for the complete target list
    and returns aggregated results. Use to verify end-to-end functionality.
    
    Args:
        hours_back: How far back to look for tweets (default: 48 hours)
        max_accounts: Max accounts to scrape (default: 15 = all)
        
    Warning: This is expensive! Each account triggers an Apify actor run.
    """
    import aiohttp
    from datetime import datetime, timezone
    
    manager = get_webhook_sources_manager()
    
    if not manager.apify.is_enabled():
        return {
            "status": "disabled",
            "message": "Apify API key not configured",
            "hint": "Add APIFY_API_KEY to backend/.env"
        }
    
    start_time = datetime.now(timezone.utc)
    logger.info(f"[APIFY LIVE FIRE] 🔥 Starting full scrape of {len(manager.apify.TARGET_ACCOUNTS)} accounts")
    
    results = {
        "status": "running",
        "start_time": start_time.isoformat(),
        "hours_back": hours_back,
        "accounts_total": len(manager.apify.TARGET_ACCOUNTS),
        "accounts_scraped": 0,
        "accounts_failed": 0,
        "total_tweets": 0,
        "tweets_by_account": {},
        "sample_headlines": [],
        "errors": [],
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            accounts_to_scrape = manager.apify.TARGET_ACCOUNTS[:max_accounts]
            
            for i, account in enumerate(accounts_to_scrape, 1):
                logger.info(f"[APIFY LIVE FIRE] 📡 Scraping {i}/{len(accounts_to_scrape)}: @{account}")
                
                try:
                    news_items = await manager.apify._fetch_account_tweets(
                        session=session,
                        account=account,
                        hours_back=hours_back
                    )
                    
                    results["accounts_scraped"] += 1
                    results["total_tweets"] += len(news_items)
                    results["tweets_by_account"][account] = len(news_items)
                    
                    # Collect sample headlines
                    for item in news_items[:2]:
                        results["sample_headlines"].append({
                            "account": f"@{account}",
                            "headline": item.headline[:80],
                            "priority": item.priority,
                            "likes": item.metadata.get('likes', 0),
                        })
                    
                    if news_items:
                        logger.info(f"[APIFY LIVE FIRE] ✅ @{account}: {len(news_items)} tweets")
                    else:
                        logger.info(f"[APIFY LIVE FIRE] ⚪ @{account}: 0 tweets (none in time window)")
                    
                    # Small delay between accounts to avoid rate limits
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    results["accounts_failed"] += 1
                    results["errors"].append(f"@{account}: {str(e)[:50]}")
                    logger.error(f"[APIFY LIVE FIRE] ❌ @{account}: {e}")
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        results["status"] = "completed"
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = round(duration, 1)
        
        logger.info(f"[APIFY LIVE FIRE] 🏁 Completed in {duration:.1f}s")
        logger.info(f"[APIFY LIVE FIRE] 📊 Total: {results['total_tweets']} tweets from {results['accounts_scraped']} accounts")
        
        return results
        
    except Exception as e:
        logger.error(f"[APIFY LIVE FIRE] 💥 Fatal error: {e}")
        results["status"] = "error"
        results["error"] = str(e)
        return results


# =============================================
# PAPER TRADING ENDPOINTS
# =============================================

@api_router.post("/paper/start")
async def start_paper_trading(
    background_tasks: BackgroundTasks,
    continuous_mode: bool = False,
    username: str = Depends(verify_credentials_dual)
):
    """Start paper trading session with RL learning
    
    Uses capital settings from Configuration tab (initial_capital, capital_deployment_pct, etc.)
    
    Args:
        continuous_mode: If True, runs indefinitely until manually stopped
    """
    global paper_trader, trading_mode, news_injector
    
    if trading_bot and trading_bot.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Live trading is running. Stop live trading first."}
        )
    
    if paper_trader and paper_trader.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Paper trading is already running"}
        )
    
    try:
        # Initialize adaptive position sizer
        from ml.adaptive_position_sizer import init_position_sizer
        await init_position_sizer()
        
        # PaperTrader now uses Config tab values for capital
        paper_trader = PaperTrader(continuous_mode=continuous_mode)
        
        # =================================================================
        # LANE 5: Connect Signal Cache for News/Emergent signals
        # =================================================================
        signal_cache = get_signal_cache()
        paper_trader.set_signal_cache(signal_cache)
        
        # Initialize News Injector with the same cache
        if news_injector is None:
            news_injector = get_news_injector(
                signal_cache=signal_cache,
                market_fetcher=get_active_markets_for_news
            )
        else:
            news_injector.signal_cache = signal_cache
            # Ensure market_fetcher is set even on existing instance
            if news_injector.market_fetcher is None:
                news_injector.market_fetcher = get_active_markets_for_news
        
        logger.info("[PAPER TRADING] Lane 5 signal cache connected")
        # =================================================================
        
        # Set up WebSocket broadcast callback for real-time updates
        from paper_trading.paper_trader import set_broadcast_callback
        set_broadcast_callback(ws_manager.broadcast)
        
        background_tasks.add_task(paper_trader.start)
        trading_mode = "paper"
        
        return {
            "message": "Paper trading started",
            "session_id": paper_trader.session_id,
            "initial_capital": paper_trader.initial_capital,
            "deployed_capital": paper_trader.deployed_capital,
            "continuous_mode": continuous_mode,
            "mode": "paper",
            "lane5_enabled": True,
            "config": {
                "capital_deployment_pct": paper_trader.capital_deployment_pct,
                "max_position_size_pct": paper_trader.max_position_size_pct,
                "kelly_fraction": paper_trader.kelly_fraction,
                "max_drawdown_pct": paper_trader.max_drawdown_pct,
            }
        }
    except Exception as e:
        logger.error(f"Error starting paper trading: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to start paper trading: {str(e)}"}
        )

@api_router.post("/paper/stop")
async def stop_paper_trading(
    graceful: bool = False,
    username: str = Depends(verify_credentials_dual)
):
    """Stop paper trading and save results
    
    Args:
        graceful: If True, stop accepting new trades but let existing positions
                 close naturally according to strategy rules (take profit/stop loss)
    """
    global paper_trader, trading_mode
    
    if not paper_trader or not paper_trader.running:
        return JSONResponse(
            status_code=400,
            content={"message": "Paper trading is not running"}
        )
    
    try:
        # Capture positions BEFORE stopping (they get cleared on stop)
        positions_before_stop = paper_trader.get_positions()
        
        await paper_trader.stop(graceful=graceful)
        trading_mode = "stopped"
        
        status = paper_trader.get_status()
        
        # Save session analytics for historical tracking
        try:
            logger.info(f"Saving session analytics for session {status.get('session_id')}")
            await save_session_analytics(positions_before_stop, status)
            logger.info(f"Successfully saved session analytics")
        except Exception as analytics_err:
            logger.error(f"Error saving session analytics: {analytics_err}", exc_info=True)
        
        return {
            "message": "Paper trading stopped",
            "final_status": status
        }
    except Exception as e:
        logger.error(f"Error stopping paper trading: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to stop paper trading: {str(e)}"}
        )

@api_router.post("/paper/recover-positions")
async def recover_positions(
    session_id: str = None,
    username: str = Depends(verify_credentials_dual)
):
    """Recover/reconstruct positions from trade history
    
    Useful for:
    - Recovering positions after unexpected restart
    - Reconstructing positions for an old session
    - Debugging position state
    """
    global paper_trader
    
    try:
        db = get_db()
        
        target_session = session_id
        if not target_session and paper_trader:
            target_session = paper_trader.session_id
        
        if not target_session:
            return JSONResponse(
                status_code=400,
                content={"message": "No session_id provided and no active paper trader"}
            )
        
        # Get all entry trades for this session
        entries = await db.paper_trades.find({
            "session_id": target_session,
            "type": "entry"
        }).to_list(None)
        
        # Get all exit trades for this session
        exits = await db.paper_trades.find({
            "session_id": target_session,
            "type": "exit"
        }).to_list(None)
        
        # Find closed market IDs
        closed_markets = set(e.get("market_id") for e in exits)
        
        # Find open positions
        open_positions = []
        for entry in entries:
            market_id = entry.get("market_id")
            if market_id and market_id not in closed_markets:
                open_positions.append({
                    "market_id": market_id,
                    "market_question": entry.get("market_question", "Unknown")[:50] + "...",
                    "entry_price": entry.get("entry_price", 0),
                    "side": entry.get("side", "NO"),
                    "size": entry.get("size", 0),
                    "entry_time": entry.get("timestamp"),
                    "strategy": entry.get("strategy", "unknown")
                })
        
        # If paper_trader is running and it's the same session, load into memory
        loaded_count = 0
        if paper_trader and paper_trader.running and paper_trader.session_id == target_session:
            for pos in open_positions:
                market_id = pos["market_id"]
                if market_id not in paper_trader.paper_positions:
                    paper_trader.paper_positions[market_id] = pos
                    await paper_trader._save_position_to_db(market_id, pos)
                    loaded_count += 1
        
        return {
            "message": f"Found {len(open_positions)} open positions for session {target_session}",
            "session_id": target_session,
            "total_entries": len(entries),
            "total_exits": len(exits),
            "open_positions": open_positions,
            "loaded_to_memory": loaded_count
        }
        
    except Exception as e:
        logger.error(f"Error recovering positions: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to recover positions: {str(e)}"}
        )


async def save_session_analytics(positions, status):
    """Save session-level analytics for historical comparison.
    
    Uses unrealized P&L from open positions as simulated realized P&L
    since positions are closed at session stop.
    """
    trades = status.get('trades', [])
    
    # Calculate simulated closure P&L for positions
    total_simulated_pnl = 0.0
    total_wins = 0
    total_positions = 0
    
    # Combine positions and trades for analysis
    all_items = []
    for p in positions:
        if p.get('sizing_breakdown'):
            # Use unrealized P&L directly (no spread in prediction markets)
            simulated_pnl = p.get('unrealized_pnl', 0)
            simulated_pnl_pct = p.get('unrealized_pnl_pct', 0)
            
            total_simulated_pnl += simulated_pnl
            total_positions += 1
            if simulated_pnl > 0:
                total_wins += 1
            
            all_items.append({
                'type': 'position',
                'sizing_breakdown': p.get('sizing_breakdown', {}),
                'category': p.get('sizing_breakdown', {}).get('category', 'unknown'),
                'pnl': simulated_pnl,
                'pnl_pct': simulated_pnl_pct,
                'entry_price': p.get('entry_price', 0),
                'current_price': p.get('current_price', 0),
                'size': p.get('size', 0),
                'side': p.get('side', 'YES')
            })
    
    # Also include any closed trades from the session
    for t in trades:
        if t.get('sizing_breakdown'):
            trade_pnl = t.get('pnl', 0)
            total_simulated_pnl += trade_pnl
            total_positions += 1
            if trade_pnl > 0:
                total_wins += 1
                
            all_items.append({
                'type': 'trade',
                'sizing_breakdown': t.get('sizing_breakdown', {}),
                'category': t.get('sizing_breakdown', {}).get('category', 'unknown'),
                'pnl': trade_pnl,
                'pnl_pct': t.get('return_pct', 0)
            })
    
    if not all_items:
        return
    
    # Calculate simulated win rate
    simulated_win_rate = (total_wins / total_positions * 100) if total_positions > 0 else 0
    
    # Calculate analytics
    analytics = {
        'by_category': {},
        'by_oracle_range': {'high': [], 'medium': [], 'low': []},
        'sizing_efficiency': []
    }
    
    for item in all_items:
        breakdown = item.get('sizing_breakdown', {})
        category = breakdown.get('category', item.get('category', 'unknown'))
        edge = breakdown.get('edge', 0)
        oracle_mult = breakdown.get('oracle_mult', 1)
        kelly_base = breakdown.get('kelly_base', 0)
        final_size = breakdown.get('final_size', 0)
        pnl = item.get('pnl', 0)
        
        # By Category
        if category not in analytics['by_category']:
            analytics['by_category'][category] = {'count': 0, 'total_edge': 0, 'total_pnl': 0, 'wins': 0}
        analytics['by_category'][category]['count'] += 1
        analytics['by_category'][category]['total_edge'] += edge
        analytics['by_category'][category]['total_pnl'] += pnl
        if pnl > 0:
            analytics['by_category'][category]['wins'] += 1
        
        # By Oracle Range
        range_key = 'high' if oracle_mult >= 0.9 else 'medium' if oracle_mult >= 0.6 else 'low'
        analytics['by_oracle_range'][range_key].append({'pnl': pnl})
        
        # Sizing Efficiency
        if kelly_base > 0:
            analytics['sizing_efficiency'].append(final_size / kelly_base)
    
    # Calculate summary metrics
    category_stats = {}
    for cat, data in analytics['by_category'].items():
        category_stats[cat] = {
            'count': data['count'],
            'avg_edge': (data['total_edge'] / data['count'] * 100) if data['count'] > 0 else 0,
            'total_pnl': data['total_pnl'],
            'win_rate': (data['wins'] / data['count'] * 100) if data['count'] > 0 else 0
        }
    
    oracle_stats = {}
    for tier in ['high', 'medium', 'low']:
        items = analytics['by_oracle_range'][tier]
        oracle_stats[tier] = {
            'count': len(items),
            'total_pnl': sum(x['pnl'] for x in items),
            'win_rate': (len([x for x in items if x['pnl'] > 0]) / len(items) * 100) if items else 0
        }
    
    avg_efficiency = (sum(analytics['sizing_efficiency']) / len(analytics['sizing_efficiency'])) if analytics['sizing_efficiency'] else 1.0
    
    # Save to database
    db = get_db()
    session_record = {
        'session_id': status.get('session_id', 'unknown'),
        'timestamp': datetime.now(timezone.utc),
        'duration_seconds': status.get('duration_seconds', 0),
        'total_trades': total_positions,  # Use actual position count
        'total_pnl': total_simulated_pnl,  # Use simulated P&L
        'win_rate': simulated_win_rate,    # Use simulated win rate
        'initial_capital': status.get('initial_capital', 0),
        'final_capital': status.get('current_capital', 0) + total_simulated_pnl,  # Adjusted final
        'category_stats': category_stats,
        'oracle_stats': oracle_stats,
        'sizing_efficiency': avg_efficiency,
        'sizer_mode': status.get('sizer_mode', 'polymarket'),
        'simulated_closure': True  # Flag indicating P&L is simulated
    }
    
    await db.paper_trading_analytics.insert_one(session_record)
    logger.info(f"Saved session analytics for {status.get('session_id')} - Simulated P&L: ${total_simulated_pnl:.2f}, Win Rate: {simulated_win_rate:.1f}%")


@api_router.get("/paper/analytics/history")
async def get_analytics_history(limit: int = 20):
    """Get historical session analytics for comparison charts."""
    try:
        db = get_db()
        cursor = db.paper_trading_analytics.find(
            {},
            {'_id': 0}
        ).sort('timestamp', -1).limit(limit)
        
        sessions = await cursor.to_list(length=limit)
        
        # Reverse to get chronological order for charts
        sessions.reverse()
        
        # Process for chart-friendly format
        chart_data = {
            'sessions': [],
            'efficiency_trend': [],
            'oracle_win_rates': {'high': [], 'medium': [], 'low': []},
            'category_trends': {}
        }
        
        for i, session in enumerate(sessions):
            timestamp = session.get('timestamp', datetime.now(timezone.utc))
            if isinstance(timestamp, datetime):
                label = timestamp.strftime('%m/%d %H:%M')
            else:
                label = f"Session {i+1}"
            
            chart_data['sessions'].append({
                'session_id': session.get('session_id', ''),
                'label': label,
                'total_trades': session.get('total_trades', 0),
                'total_pnl': session.get('total_pnl', 0),
                'win_rate': session.get('win_rate', 0),
                'sizer_mode': session.get('sizer_mode', 'unknown')
            })
            
            # Efficiency trend
            chart_data['efficiency_trend'].append({
                'label': label,
                'efficiency': session.get('sizing_efficiency', 1) * 100
            })
            
            # Oracle win rates
            oracle_stats = session.get('oracle_stats', {})
            for tier in ['high', 'medium', 'low']:
                tier_data = oracle_stats.get(tier, {})
                chart_data['oracle_win_rates'][tier].append({
                    'label': label,
                    'win_rate': tier_data.get('win_rate', 0),
                    'count': tier_data.get('count', 0)
                })
            
            # Category trends
            category_stats = session.get('category_stats', {})
            for cat, stats in category_stats.items():
                if cat not in chart_data['category_trends']:
                    chart_data['category_trends'][cat] = []
                chart_data['category_trends'][cat].append({
                    'label': label,
                    'avg_edge': stats.get('avg_edge', 0),
                    'win_rate': stats.get('win_rate', 0),
                    'pnl': stats.get('total_pnl', 0)
                })
        
        return {
            'sessions_count': len(sessions),
            'chart_data': chart_data
        }
    except Exception as e:
        logger.error(f"Error getting analytics history: {e}")
        return {'sessions_count': 0, 'chart_data': {}, 'error': str(e)}

@api_router.get("/paper/status")
async def get_paper_trading_status():
    """Get current paper trading status and performance"""
    global paper_trader
    
    if not paper_trader:
        return {
            "running": False, 
            "message": "No paper trading session",
            "open_positions": 0,
            "total_trades": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "current_capital": 0.0,
            "initial_capital": 0.0
        }
    
    return paper_trader.get_status()

@api_router.get("/paper/ai-stats")
async def get_paper_ai_stats():
    """Get AI/ML statistics for paper trading session"""
    global paper_trader
    
    if not paper_trader:
        return {"message": "No paper trading session", "ai_stats": {}}
    
    try:
        ai_stats = await paper_trader.get_ai_stats()
        return {"ai_stats": ai_stats}
    except Exception as e:
        logger.error(f"Error getting AI stats: {e}")
        return {"message": str(e), "ai_stats": {}}

@api_router.get("/paper/positions")
async def get_paper_positions():
    """Get current open paper positions"""
    global paper_trader
    
    if not paper_trader:
        return {"positions": []}
    
    return {"positions": paper_trader.get_positions()}

@api_router.get("/paper/gamma-stats")
async def get_gamma_stats():
    """Get Gamma Strategy (Whale Zone) statistics"""
    global paper_trader
    
    if not paper_trader:
        return {
            "gamma_stats": {
                "orders_generated": 0,
                "gap_opportunities": 0,
                "wall_snipes": 0,
                "wall_joins": 0,
                "free_rolls": 0,
                "moonbags": 0,
                "stop_losses": 0,
                "skipped_expensive": 0,
                "skipped_max_position": 0,
            },
            "config": {
                "whale_price_ceiling": 0.10,
                "whale_max_position": 15.0,
                "whale_max_spread_cents": 0.03,
            },
            "message": "No active session - showing defaults"
        }
    
    try:
        gamma_stats = paper_trader.gamma_trader.get_stats()
        
        # Calculate additional metrics
        total_entries = gamma_stats.get('gap_opportunities', 0) + gamma_stats.get('wall_snipes', 0) + gamma_stats.get('wall_joins', 0)
        total_exits = gamma_stats.get('free_rolls', 0) + gamma_stats.get('moonbags', 0) + gamma_stats.get('stop_losses', 0)
        
        # Calculate whale zone positions
        whale_positions = []
        whale_pnl = 0.0
        for pos_id, pos in paper_trader.paper_positions.items():
            strategy = pos.get('strategy', '')
            if strategy in ['gamma_scalp', 'hft_gamma_scalp', 'whale', 'gamma']:
                whale_positions.append({
                    'market_id': pos.get('market_id', '')[:16],
                    'side': pos.get('side'),
                    'entry_price': pos.get('entry_price'),
                    'current_price': pos.get('current_price'),
                    'size': pos.get('size'),
                    'unrealized_pnl': pos.get('unrealized_pnl', 0),
                    'free_roll_done': pos.get('free_roll_done', False),
                })
                whale_pnl += pos.get('unrealized_pnl', 0)
        
        return {
            "gamma_stats": gamma_stats,
            "summary": {
                "total_entries": total_entries,
                "total_exits": total_exits,
                "whale_positions_count": len(whale_positions),
                "whale_unrealized_pnl": round(whale_pnl, 2),
            },
            "whale_positions": whale_positions,
            "config": gamma_stats.get('config', {}),
        }
    except Exception as e:
        logger.error(f"Error getting gamma stats: {e}")
        return {"error": str(e), "gamma_stats": {}}

@api_router.get("/paper/exit-mode")
async def get_paper_exit_mode():
    """Get current exit mode (dynamic or simple)"""
    global paper_trader
    
    if not paper_trader:
        return {
            "use_dynamic_exit": True,
            "message": "No active session - showing default"
        }
    
    return {
        "use_dynamic_exit": paper_trader.use_dynamic_exit,
        "dynamic_exit_config": paper_trader.dynamic_exit_config,
        "time_entry_config": paper_trader.time_entry_config,
        "simple_exit_params": paper_trader.exit_params_by_strategy
    }

@api_router.post("/paper/exit-mode")
async def set_paper_exit_mode(use_dynamic: bool = True):
    """Toggle between dynamic and simple exit mode"""
    global paper_trader
    
    if not paper_trader:
        return {"error": "No active paper trading session"}
    
    paper_trader.use_dynamic_exit = use_dynamic
    mode_name = "Dynamic (Time-Aware)" if use_dynamic else "Simple (Configurable)"
    logger.info(f"Exit mode changed to: {mode_name}")
    
    return {
        "success": True,
        "use_dynamic_exit": paper_trader.use_dynamic_exit,
        "message": f"Exit mode set to: {mode_name}"
    }

# ============================================================================
# PORTFOLIO RISK CONFIG API (Task 23b: Configurable Risk Parameters)
# ============================================================================

@api_router.get("/config/portfolio-risk")
async def get_portfolio_risk_config():
    """
    Get current Portfolio Risk configuration.
    This is the Single Source of Truth for all sizing parameters.
    """
    from risk_config import RISK, get_defaults
    
    try:
        db = get_db()
        saved_config = await db.portfolio_risk_config.find_one(
            {"type": "portfolio_risk"},
            {"_id": 0}
        )
        
        # Load from DB if exists
        if saved_config:
            RISK.load_from_dict(saved_config)
        
        return {
            "config": RISK.to_dict(),
            "defaults": get_defaults(),
            "source": "database" if saved_config else "defaults"
        }
    except Exception as e:
        logger.error(f"Error getting portfolio risk config: {e}")
        return {
            "config": RISK.to_dict(),
            "defaults": get_defaults(),
            "source": "memory",
            "error": str(e)
        }

@api_router.post("/config/portfolio-risk")
async def update_portfolio_risk_config(config_data: Dict[str, Any]):
    """
    Update Portfolio Risk configuration.
    Saves to database and updates in-memory RISK instance.
    """
    from risk_config import RISK
    
    try:
        db = get_db()
        
        # Update in-memory config
        RISK.load_from_dict(config_data)
        
        # Save to database
        await db.portfolio_risk_config.update_one(
            {"type": "portfolio_risk"},
            {
                "$set": {
                    **config_data,
                    "type": "portfolio_risk",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        
        logger.info(f"[CONFIG] Portfolio risk config updated: whale=${RISK.WHALE_MAX_USD}, core=${RISK.CORE_MAX_USD}")
        
        return {
            "success": True,
            "config": RISK.to_dict(),
            "message": "Portfolio risk configuration saved"
        }
    except Exception as e:
        logger.error(f"Error updating portfolio risk config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

@api_router.post("/config/portfolio-risk/reset")
async def reset_portfolio_risk_config():
    """
    Reset Portfolio Risk configuration to defaults.
    """
    from risk_config import RISK, get_defaults
    
    try:
        db = get_db()
        
        # Reset in-memory
        RISK.reset_to_defaults()
        
        # Delete from database (will use defaults next time)
        await db.portfolio_risk_config.delete_one({"type": "portfolio_risk"})
        
        logger.info("[CONFIG] Portfolio risk config reset to defaults")
        
        return {
            "success": True,
            "config": get_defaults(),
            "message": "Portfolio risk configuration reset to defaults"
        }
    except Exception as e:
        logger.error(f"Error resetting portfolio risk config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================================
# EXIT ENGINE CONFIGURATION API (Task 24: Alpha-State Exit Engine)
# ============================================================================

@api_router.get("/config/exit-engine")
async def get_exit_engine_config():
    """
    Get Exit Engine configuration - Global Settings, Strategy Config, Asset Modifiers, Whale Zone.
    """
    from risk_config import (
        EXIT_GLOBAL_SETTINGS,
        EXIT_STRATEGY_CONFIG,
        EXIT_ALPHA_ASSET_MODIFIERS,
        EXIT_WHALE_ZONE,
        get_exit_config,
    )
    
    try:
        db = get_db()
        
        # Load from database if exists
        saved_config = await db.exit_engine_config.find_one({"type": "exit_engine"})
        
        if saved_config:
            # Remove MongoDB _id
            saved_config.pop('_id', None)
            saved_config.pop('type', None)
            return {
                "success": True,
                "config": saved_config,
                "defaults": get_exit_config(),
                "source": "database"
            }
        
        # Return defaults
        return {
            "success": True,
            "config": get_exit_config(),
            "defaults": get_exit_config(),
            "source": "defaults"
        }
    except Exception as e:
        logger.error(f"Error getting exit engine config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@api_router.post("/config/exit-engine")
async def update_exit_engine_config(config: dict):
    """
    Update Exit Engine configuration.
    
    Expected structure:
    {
        "global": {...},
        "strategies": {...},
        "alpha_modifiers": {...},
        "whale_zone": {...}
    }
    """
    from risk_config import (
        EXIT_GLOBAL_SETTINGS,
        EXIT_STRATEGY_CONFIG,
        EXIT_ALPHA_ASSET_MODIFIERS,
        EXIT_WHALE_ZONE,
    )
    from trading.exit_engine import get_exit_engine
    
    try:
        db = get_db()
        
        # Update in-memory configurations
        if 'global' in config:
            EXIT_GLOBAL_SETTINGS.update(config['global'])
        if 'strategies' in config:
            for strat, params in config['strategies'].items():
                if strat in EXIT_STRATEGY_CONFIG:
                    EXIT_STRATEGY_CONFIG[strat].update(params)
        if 'alpha_modifiers' in config:
            for asset, mods in config['alpha_modifiers'].items():
                if asset in EXIT_ALPHA_ASSET_MODIFIERS:
                    EXIT_ALPHA_ASSET_MODIFIERS[asset].update(mods)
        if 'whale_zone' in config:
            EXIT_WHALE_ZONE.update(config['whale_zone'])
        
        # Update the singleton exit engine instance
        exit_engine = get_exit_engine()
        exit_engine.global_settings = dict(EXIT_GLOBAL_SETTINGS)
        exit_engine.strategy_config = dict(EXIT_STRATEGY_CONFIG)
        exit_engine.alpha_modifiers = dict(EXIT_ALPHA_ASSET_MODIFIERS)
        exit_engine.whale_zone = dict(EXIT_WHALE_ZONE)
        
        # Persist to database
        save_data = {
            "type": "exit_engine",
            "global": dict(EXIT_GLOBAL_SETTINGS),
            "strategies": {k: dict(v) for k, v in EXIT_STRATEGY_CONFIG.items()},
            "alpha_modifiers": {k: dict(v) for k, v in EXIT_ALPHA_ASSET_MODIFIERS.items()},
            "whale_zone": dict(EXIT_WHALE_ZONE),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.exit_engine_config.update_one(
            {"type": "exit_engine"},
            {"$set": save_data},
            upsert=True
        )
        
        logger.info(f"[EXIT-CONFIG] Updated exit engine configuration")
        
        return {
            "success": True,
            "message": "Exit engine configuration updated",
            "config": {
                "global": dict(EXIT_GLOBAL_SETTINGS),
                "strategies": {k: dict(v) for k, v in EXIT_STRATEGY_CONFIG.items()},
                "alpha_modifiers": {k: dict(v) for k, v in EXIT_ALPHA_ASSET_MODIFIERS.items()},
                "whale_zone": dict(EXIT_WHALE_ZONE),
            }
        }
    except Exception as e:
        logger.error(f"Error updating exit engine config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@api_router.post("/config/exit-engine/reset")
async def reset_exit_engine_config():
    """
    Reset Exit Engine configuration to defaults.
    """
    from risk_config import (
        EXIT_GLOBAL_SETTINGS,
        EXIT_STRATEGY_CONFIG,
        EXIT_ALPHA_ASSET_MODIFIERS,
        EXIT_WHALE_ZONE,
    )
    from trading.exit_engine import get_exit_engine
    import copy
    
    try:
        db = get_db()
        
        # Define hardcoded defaults (since module-level dicts may be mutated)
        DEFAULT_GLOBAL = {
            'whale_threshold_price': 0.10,
            'max_spread_pct': 0.10,
            'expiry_guard_hours': 2.0,
            'min_trade_size_usd': 2.00,
            'free_ride_floor': 0.02,
            'free_ride_ceiling': 0.98,
        }
        DEFAULT_STRATEGIES = {
            'arbitrage': {'type': 'mechanical', 'action': 'CLOSE_ALL', 'tp_pct': 0.02, 'sl_pct': 0.02, 'max_hours': 6},
            'delta_neutral': {'type': 'mechanical', 'action': 'CLOSE_ALL', 'tp_pct': 0.015, 'sl_pct': 0.015, 'max_hours': 4},
            'volatility_exploitation': {'type': 'mechanical', 'action': 'CLOSE_ALL', 'tp_pct': 0.05, 'sl_pct': 0.05, 'max_hours': 24},
            'alpha_directional': {'type': 'complex', 'action': 'FREE_ROLL', 'profit_trigger_pct': 0.30, 'base_sl_pct': 0.15, 'base_max_hours': 72},
            'gamma_scalp': {'type': 'whale', 'action': 'GAMMA_EXIT', 'stop_multiple': 0.50, 'free_roll_multiple': 2.0, 'moonbag_multiple': 5.0, 'max_hours': 168},
        }
        DEFAULT_ALPHA_MODIFIERS = {
            'politics': {'profit_mult': 1.2, 'sl_mult': 1.0, 'time_mult': 3.0, 'use_trailing': True, 'use_thesis_fail': True, 'allow_zombie': False},
            'finance': {'profit_mult': 1.0, 'sl_mult': 1.2, 'time_mult': 1.0, 'use_trailing': True, 'use_thesis_fail': True, 'allow_zombie': False},
            'crypto': {'profit_mult': 1.5, 'sl_mult': 1.5, 'time_mult': 0.5, 'use_trailing': True, 'use_thesis_fail': True, 'allow_zombie': False},
            'sports': {'profit_mult': 1.0, 'sl_mult': 1.5, 'time_mult': 0.25, 'use_trailing': False, 'use_thesis_fail': False, 'allow_zombie': True},
            'entertainment': {'profit_mult': 2.0, 'sl_mult': 0.8, 'time_mult': 2.0, 'use_trailing': False, 'use_thesis_fail': False, 'allow_zombie': True},
            'science': {'profit_mult': 2.0, 'sl_mult': 0.5, 'time_mult': 5.0, 'use_trailing': False, 'use_thesis_fail': False, 'allow_zombie': True},
            'default': {'profit_mult': 1.0, 'sl_mult': 1.0, 'time_mult': 1.0, 'use_trailing': True, 'use_thesis_fail': True, 'allow_zombie': False},
        }
        DEFAULT_WHALE_ZONE = {
            'stop_loss_multiple': 0.50,
            'free_roll_multiple': 2.0,
            'free_roll_sell_pct': 0.50,
            'moonbag_multiple': 5.0,
        }
        
        # Update in-memory (clear and reset from hardcoded defaults)
        EXIT_GLOBAL_SETTINGS.clear()
        EXIT_GLOBAL_SETTINGS.update(copy.deepcopy(DEFAULT_GLOBAL))
        
        EXIT_STRATEGY_CONFIG.clear()
        EXIT_STRATEGY_CONFIG.update(copy.deepcopy(DEFAULT_STRATEGIES))
        
        EXIT_ALPHA_ASSET_MODIFIERS.clear()
        EXIT_ALPHA_ASSET_MODIFIERS.update(copy.deepcopy(DEFAULT_ALPHA_MODIFIERS))
        
        EXIT_WHALE_ZONE.clear()
        EXIT_WHALE_ZONE.update(copy.deepcopy(DEFAULT_WHALE_ZONE))
        
        # Update singleton
        exit_engine = get_exit_engine()
        exit_engine.global_settings = copy.deepcopy(DEFAULT_GLOBAL)
        exit_engine.strategy_config = copy.deepcopy(DEFAULT_STRATEGIES)
        exit_engine.alpha_modifiers = copy.deepcopy(DEFAULT_ALPHA_MODIFIERS)
        exit_engine.whale_zone = copy.deepcopy(DEFAULT_WHALE_ZONE)
        
        # Delete from database
        await db.exit_engine_config.delete_one({"type": "exit_engine"})
        
        logger.info("[EXIT-CONFIG] Reset exit engine configuration to defaults")
        
        default_config = {
            'global': DEFAULT_GLOBAL,
            'strategies': DEFAULT_STRATEGIES,
            'alpha_modifiers': DEFAULT_ALPHA_MODIFIERS,
            'whale_zone': DEFAULT_WHALE_ZONE,
        }
        
        return {
            "success": True,
            "config": default_config,
            "message": "Exit engine configuration reset to defaults"
        }
    except Exception as e:
        logger.error(f"Error resetting exit engine config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@api_router.get("/exit-engine/stats")
async def get_exit_engine_stats():
    """
    Get Exit Engine runtime statistics.
    """
    from trading.exit_engine import get_exit_engine
    
    try:
        exit_engine = get_exit_engine()
        stats = exit_engine.get_stats()
        
        # Add integration status
        global paper_trader
        stats['integration'] = {
            'enabled': paper_trader.use_exit_engine if paper_trader else False,
            'legacy_mode': not (paper_trader.use_exit_engine if paper_trader else True),
        }
        
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting exit engine stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@api_router.post("/exit-engine/toggle")
async def toggle_exit_engine(enable: bool = None):
    """
    Toggle between new ExitEngine (Task 24) and legacy exit logic.
    
    If enable is not provided, toggles current state.
    """
    global paper_trader
    
    if not paper_trader:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "No paper trading session active"}
        )
    
    try:
        if enable is None:
            # Toggle
            paper_trader.use_exit_engine = not paper_trader.use_exit_engine
        else:
            paper_trader.use_exit_engine = enable
        
        mode = "ExitEngine (Task 24)" if paper_trader.use_exit_engine else "Legacy Dynamic Exit"
        logger.info(f"[EXIT-TOGGLE] Switched to {mode}")
        
        return {
            "success": True,
            "use_exit_engine": paper_trader.use_exit_engine,
            "mode": mode,
            "message": f"Exit logic switched to {mode}"
        }
    except Exception as e:
        logger.error(f"Error toggling exit engine: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================================
# SSOT RISK CONFIG API (5-Lane Architecture)
# ============================================================================
# Single Source of Truth for all risk parameters.
# JSON file at backend/config/risk_config.json drives everything.

@api_router.get("/risk-config")
async def get_risk_config():
    """
    Get the current risk configuration from the SSOT JSON file.
    This is the master config that drives all 5 lanes.
    """
    from services.risk_manager import get_risk_manager
    
    try:
        risk_manager = get_risk_manager()
        config = risk_manager.get_config()
        status = risk_manager.get_status()
        
        return {
            "success": True,
            "config": config,
            "status": status,
            "synced": True
        }
    except Exception as e:
        logger.error(f"Error getting risk config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "synced": False}
        )


@api_router.post("/risk-config")
async def update_risk_config(config_data: Dict[str, Any]):
    """
    Update the risk configuration and save to the SSOT JSON file.
    This triggers a hot-reload of the risk manager.
    """
    from services.risk_manager import get_risk_manager
    
    try:
        risk_manager = get_risk_manager()
        success, message = risk_manager.update_config(config_data)
        
        if success:
            logger.info(f"[RISK-CONFIG] Configuration updated via API")
            return {
                "success": True,
                "message": message,
                "config": risk_manager.get_config(),
                "synced": True
            }
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": message, "synced": False}
            )
    except Exception as e:
        logger.error(f"Error updating risk config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "synced": False}
        )


@api_router.post("/risk-config/reload")
async def reload_risk_config():
    """
    Hot-reload the risk configuration from the JSON file.
    Use this after manually editing the config file.
    """
    from services.risk_manager import get_risk_manager
    
    try:
        risk_manager = get_risk_manager()
        success, message = risk_manager.reload_config()
        
        if success:
            return {
                "success": True,
                "message": message,
                "config": risk_manager.get_config(),
                "synced": True
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": message, "synced": False}
            )
    except Exception as e:
        logger.error(f"Error reloading risk config: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "synced": False}
        )


@api_router.get("/risk-config/status")
async def get_risk_config_status():
    """
    Get the status of the risk manager (loaded, version, etc.)
    """
    from services.risk_manager import get_risk_manager
    
    try:
        risk_manager = get_risk_manager()
        return {
            "success": True,
            "status": risk_manager.get_status(),
            "synced": True
        }
    except Exception as e:
        logger.error(f"Error getting risk config status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "synced": False}
        )


@api_router.post("/risk-config/check-order")
async def check_order_risk(
    lane: str,
    amount: float,
    capital: float = 10000.0,
    utilization: float = 0.0,
    sector: Optional[str] = None,
    sector_exposure: float = 0.0,
    market_price: float = 0.5
):
    """
    Test the risk manager's check_order function.
    Useful for debugging and understanding why orders are blocked/trimmed.
    """
    from services.risk_manager import get_risk_manager
    
    try:
        risk_manager = get_risk_manager()
        result = risk_manager.check_order(
            lane=lane,
            amount=amount,
            capital=capital,
            current_utilization=utilization,
            sector=sector,
            sector_exposure=sector_exposure,
            market_price=market_price
        )
        
        return {
            "success": True,
            "result": result.to_dict()
        }
    except Exception as e:
        logger.error(f"Error checking order risk: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================================
# ALPHA MODEL WEIGHTS API (Task 19: Dynamic Alpha Tuning)
# ============================================================================

@api_router.get("/settings/alpha")
async def get_alpha_weights():
    """
    Get current Alpha model weights.
    
    Returns weights that control the Bayesian probability calculation:
    - sentiment_weight: Influence of LLM sentiment (0.0-2.0)
    - rl_weight: Influence of RL model (0.0-2.0)
    - Other tuning parameters
    """
    global paper_trader
    
    if not paper_trader:
        # Return default weights if no session
        return {
            "active_session": False,
            "weights": {
                'sentiment_weight': 0.50,
                'rl_weight': 0.60,
                'sharp_weight': 0.30,
                'sentiment_neutral_low': 0.45,
                'sentiment_neutral_high': 0.55,
                'max_sentiment_delta': 2.0,
                'min_rl_confidence': 0.15,
            },
            "message": "No active session - showing defaults"
        }
    
    return {
        "active_session": True,
        "weights": paper_trader.get_alpha_weights()
    }

@api_router.post("/settings/alpha")
async def update_alpha_weights(
    sentiment_weight: float = None,
    rl_weight: float = None,
    sharp_weight: float = None,
    sentiment_neutral_low: float = None,
    sentiment_neutral_high: float = None,
    max_sentiment_delta: float = None,
    min_rl_confidence: float = None
):
    """
    Update Alpha model weights at runtime.
    
    This allows real-time tuning of how much each signal source influences
    the Bayesian probability calculation. All parameters are optional.
    
    Weight Guidelines:
    - sentiment_weight: 0.3-0.7 typical (higher = trust news more)
    - rl_weight: 0.4-0.8 typical (higher = trust math model more)
    - Combined weights can exceed 1.0 for stronger signals
    
    Example:
    ```
    POST /api/settings/alpha
    {"sentiment_weight": 0.40, "rl_weight": 0.70}
    ```
    """
    global paper_trader
    
    if not paper_trader:
        return {"error": "No active paper trading session"}
    
    # Build update dict from provided values
    updates = {}
    if sentiment_weight is not None:
        updates['sentiment_weight'] = sentiment_weight
    if rl_weight is not None:
        updates['rl_weight'] = rl_weight
    if sharp_weight is not None:
        updates['sharp_weight'] = sharp_weight
    if sentiment_neutral_low is not None:
        updates['sentiment_neutral_low'] = sentiment_neutral_low
    if sentiment_neutral_high is not None:
        updates['sentiment_neutral_high'] = sentiment_neutral_high
    if max_sentiment_delta is not None:
        updates['max_sentiment_delta'] = max_sentiment_delta
    if min_rl_confidence is not None:
        updates['min_rl_confidence'] = min_rl_confidence
    
    if not updates:
        return {
            "error": "No weights provided to update",
            "current_weights": paper_trader.get_alpha_weights()
        }
    
    result = paper_trader.update_alpha_weights(updates)
    return result

@api_router.post("/paper/dynamic-config")
async def update_dynamic_exit_config(
    tp_capture_pct: float = None,
    tp_min: float = None,
    tp_max: float = None,
    sl_base: float = None,
    sl_extreme: float = None
):
    """Update dynamic exit configuration parameters"""
    global paper_trader
    
    if not paper_trader:
        return {"error": "No active paper trading session"}
    
    updates = {}
    if tp_capture_pct is not None:
        paper_trader.dynamic_exit_config['tp_capture_pct'] = tp_capture_pct
        updates['tp_capture_pct'] = tp_capture_pct
    if tp_min is not None:
        paper_trader.dynamic_exit_config['tp_min'] = tp_min
        updates['tp_min'] = tp_min
    if tp_max is not None:
        paper_trader.dynamic_exit_config['tp_max'] = tp_max
        updates['tp_max'] = tp_max
    if sl_base is not None:
        paper_trader.dynamic_exit_config['sl_base'] = sl_base
        updates['sl_base'] = sl_base
    if sl_extreme is not None:
        paper_trader.dynamic_exit_config['sl_extreme'] = sl_extreme
        updates['sl_extreme'] = sl_extreme
    
    return {
        "success": True,
        "updates": updates,
        "current_config": paper_trader.dynamic_exit_config
    }

@api_router.get("/paper/trades")
async def get_paper_trades(limit: int = 50):
    """Get paper trading trade history - from live session or database"""
    global paper_trader
    
    # If paper trader is running, get trades from current session
    if paper_trader and paper_trader.running:
        return {"trades": paper_trader.get_trade_history(limit)}
    
    # Otherwise, get recent trades from database
    try:
        db = get_db()
        cursor = db.paper_trades.find(
            {},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        trades = await cursor.to_list(length=limit)
        return {"trades": trades}
    except Exception as e:
        logger.error(f"Error getting trades from DB: {e}")
        return {"trades": []}

@api_router.get("/paper/sessions")
async def get_paper_sessions(limit: int = 10):
    """Get list of paper trading sessions"""
    try:
        db = get_db()
        cursor = db.paper_trading_sessions.find(
            {"type": "paper_trading"},
            {"_id": 0}
        ).sort("start_time", -1).limit(limit)
        
        sessions = await cursor.to_list(length=limit)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"Error getting paper sessions: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get sessions: {str(e)}"}
        )

@api_router.get("/paper/session/{session_id}")
async def get_paper_session_details(session_id: str):
    """Get detailed results for a specific paper trading session"""
    try:
        db = get_db()
        session = await db.paper_trading_sessions.find_one(
            {"session_id": session_id},
            {"_id": 0}
        )
        
        if not session:
            return JSONResponse(
                status_code=404,
                content={"message": "Session not found"}
            )
        
        # Get trades for this session
        cursor = db.paper_trades.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(500)
        trades = await cursor.to_list(length=500)
        
        return {
            "session": session,
            "trades": trades
        }
    except Exception as e:
        logger.error(f"Error getting session details: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get session: {str(e)}"}
        )

@api_router.get("/paper/session/{session_id}/trades")
async def get_session_trades(session_id: str):
    """Get all trades for a specific paper trading session with entry/exit details"""
    try:
        db = get_db()
        
        # Get all exit trades for this session (which contain entry/exit info)
        cursor = db.paper_trades.find(
            {"session_id": session_id, "type": "exit"},
            {"_id": 0}
        ).sort("timestamp", -1)
        trades = await cursor.to_list(length=1000)
        
        # Format trades with all required info
        formatted_trades = []
        for trade in trades:
            formatted_trades.append({
                "market_id": trade.get("market_id"),
                "market_question": trade.get("market_question", "Unknown"),
                "strategy": trade.get("strategy"),
                "asset_class": trade.get("asset_class"),
                "side": trade.get("side"),
                "entry_price": trade.get("entry_price", 0),
                "exit_price": trade.get("exit_price", 0),  # Fixed: was "price"
                "size": trade.get("size", 0),
                "pnl": trade.get("pnl", 0),
                "pnl_pct": trade.get("pnl_pct", 0),  # Added: was missing
                "hold_time_seconds": trade.get("hold_time_seconds", 0),
                "exit_reason": trade.get("exit_reason", "unknown"),
                "timestamp": trade.get("timestamp")
            })
        
        return {"trades": formatted_trades, "count": len(formatted_trades)}
    except Exception as e:
        logger.error(f"Error getting session trades: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@api_router.post("/paper/reset-live-stats")
async def reset_live_stats(current_user: str = Depends(verify_credentials_dual)):
    """Reset live session statistics without stopping the trading session"""
    global paper_trader
    try:
        if not paper_trader:
            return JSONResponse(status_code=400, content={"message": "No paper trader running"})
        
        # Reset stats
        paper_trader.total_trades = 0
        paper_trader.winning_trades = 0
        paper_trader.total_pnl = 0.0
        paper_trader.unrealized_pnl = 0.0
        paper_trader.max_drawdown = 0.0
        paper_trader.peak_capital = paper_trader.initial_capital
        paper_trader.current_capital = paper_trader.initial_capital
        paper_trader.closed_trades = []
        paper_trader.trade_history = []
        paper_trader.trade_returns = []
        paper_trader.equity_curve = []
        
        # Clear all open positions
        paper_trader.paper_positions = {}
        
        # Reset circuit breaker
        paper_trader.circuit_breaker_triggered = False
        
        paper_trader.strategy_equity = {s: 0.0 for s in paper_trader.strategy_equity}
        paper_trader.asset_class_equity = {}
        paper_trader.strategy_stats = {
            'delta_neutral': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'volatility_exploitation': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'alpha_directional': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
        }
        paper_trader.asset_class_stats = {}
        
        logger.info("Live session stats reset (including open positions)")
        return {"message": "Live stats reset successfully", "positions_cleared": True}
    except Exception as e:
        logger.error(f"Error resetting live stats: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@api_router.post("/paper/reset-cumulative-stats")
async def reset_cumulative_stats(current_user: str = Depends(verify_credentials_dual)):
    """Reset ALL cumulative trading statistics across all sessions"""
    try:
        db = get_db()
        
        # Delete all paper trading sessions
        result1 = await db.paper_trading_sessions.delete_many({"type": "paper_trading"})
        
        # Delete all paper trades
        result2 = await db.paper_trades.delete_many({})
        
        logger.info(f"Cumulative stats reset: {result1.deleted_count} sessions, {result2.deleted_count} trades deleted")
        return {
            "message": "Cumulative stats reset successfully",
            "sessions_deleted": result1.deleted_count,
            "trades_deleted": result2.deleted_count
        }
    except Exception as e:
        logger.error(f"Error resetting cumulative stats: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@api_router.get("/paper/analytics")
async def get_paper_analytics():
    """Get comprehensive paper trading analytics with live market data"""
    try:
        db = get_db()
        
        # Get current session status
        current_status = None
        if paper_trader and paper_trader.running:
            current_status = paper_trader.get_status()
        
        # Get all completed sessions
        cursor = db.paper_trading_sessions.find(
            {"type": "paper_trading", "status": "completed"},
            {"_id": 0}
        ).sort("end_time", -1).limit(20)
        completed_sessions = await cursor.to_list(length=20)
        
        # Calculate aggregate stats
        total_pnl = sum(s.get('total_pnl', 0) for s in completed_sessions)
        total_trades = sum(s.get('total_trades', 0) for s in completed_sessions)
        total_wins = sum(s.get('winning_trades', 0) for s in completed_sessions)
        
        # Aggregate strategy performance
        strategy_performance = {
            'delta_neutral': {'trades': 0, 'wins': 0, 'pnl': 0.0},
            'volatility_exploitation': {'trades': 0, 'wins': 0, 'pnl': 0.0},
            'alpha_directional': {'trades': 0, 'wins': 0, 'pnl': 0.0},
            'arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0}
        }
        
        for session in completed_sessions:
            stats = session.get('strategy_stats', {})
            for strategy, data in stats.items():
                if strategy in strategy_performance:
                    strategy_performance[strategy]['trades'] += data.get('trades', 0)
                    strategy_performance[strategy]['wins'] += data.get('wins', 0)
                    strategy_performance[strategy]['pnl'] += data.get('pnl', 0)
        
        # Get recent trades for equity curve
        recent_trades = []
        trades_cursor = db.paper_trades.find(
            {"type": "exit"},
            {"_id": 0}
        ).sort("timestamp", -1).limit(100)
        recent_trades = await trades_cursor.to_list(length=100)
        
        # Build equity curve
        equity_curve = []
        cumulative_pnl = 0
        for trade in reversed(recent_trades):
            cumulative_pnl += trade.get('pnl', 0)
            equity_curve.append({
                "timestamp": trade.get('timestamp'),
                "pnl": cumulative_pnl,
                "strategy": trade.get('strategy', 'unknown')
            })
        
        return {
            "current_session": current_status,
            "completed_sessions": len(completed_sessions),
            "aggregate_stats": {
                "total_pnl": total_pnl,
                "total_trades": total_trades,
                "total_wins": total_wins,
                "win_rate": total_wins / total_trades if total_trades > 0 else 0
            },
            "strategy_performance": strategy_performance,
            "equity_curve": equity_curve,
            "recent_sessions": completed_sessions[:5]
        }
        
    except Exception as e:
        logger.error(f"Error getting paper analytics: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get analytics: {str(e)}"}
        )

@api_router.get("/paper/cumulative-stats")
async def get_cumulative_stats():
    """Get cumulative trading stats across ALL paper trading sessions"""
    try:
        db = get_db()
        
        # Get all completed sessions for cumulative calculation
        cursor = db.paper_trading_sessions.find(
            {"type": "paper_trading"},
            {"_id": 0}
        )
        all_sessions = await cursor.to_list(length=1000)
        
        # Calculate cumulative strategy stats
        cumulative_strategy = {
            'delta_neutral': {'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0},
            'volatility_exploitation': {'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0},
            'alpha_directional': {'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0},
            'arbitrage': {'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0}
        }
        
        # Calculate cumulative asset class stats
        cumulative_asset_class = {}
        
        # Overall cumulative
        overall = {
            'total_sessions': len(all_sessions),
            'total_trades': 0,
            'total_wins': 0,
            'total_pnl': 0.0,
            'total_initial_capital': 0.0,
            'continuous_sessions': 0,
            'avg_session_trades': 0
        }
        
        for session in all_sessions:
            overall['total_trades'] += session.get('total_trades', 0)
            overall['total_wins'] += session.get('winning_trades', 0)
            overall['total_pnl'] += session.get('total_pnl', 0)
            overall['total_initial_capital'] += session.get('initial_capital', 0)
            if session.get('continuous_mode'):
                overall['continuous_sessions'] += 1
            
            # Strategy stats
            strategy_stats = session.get('strategy_stats', {})
            for strategy, data in strategy_stats.items():
                if strategy in cumulative_strategy:
                    if data.get('trades', 0) > 0:
                        cumulative_strategy[strategy]['total_trades'] += data.get('trades', 0)
                        cumulative_strategy[strategy]['total_wins'] += data.get('wins', 0)
                        cumulative_strategy[strategy]['total_pnl'] += data.get('pnl', 0)
                        cumulative_strategy[strategy]['sessions'] += 1
            
            # Asset class stats
            asset_stats = session.get('asset_class_stats', {})
            for asset_class, data in asset_stats.items():
                if asset_class not in cumulative_asset_class:
                    cumulative_asset_class[asset_class] = {
                        'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0
                    }
                if data.get('trades', 0) > 0:
                    cumulative_asset_class[asset_class]['total_trades'] += data.get('trades', 0)
                    cumulative_asset_class[asset_class]['total_wins'] += data.get('wins', 0)
                    cumulative_asset_class[asset_class]['total_pnl'] += data.get('pnl', 0)
                    cumulative_asset_class[asset_class]['sessions'] += 1
        
        # Add current session if running
        if paper_trader and paper_trader.running:
            overall['total_trades'] += paper_trader.total_trades
            overall['total_wins'] += paper_trader.winning_trades
            overall['total_pnl'] += paper_trader.total_pnl
            
            for strategy, data in paper_trader.strategy_stats.items():
                if strategy in cumulative_strategy and data.get('trades', 0) > 0:
                    cumulative_strategy[strategy]['total_trades'] += data.get('trades', 0)
                    cumulative_strategy[strategy]['total_wins'] += data.get('wins', 0)
                    cumulative_strategy[strategy]['total_pnl'] += data.get('pnl', 0)
            
            for asset_class, data in paper_trader.asset_class_stats.items():
                if asset_class not in cumulative_asset_class:
                    cumulative_asset_class[asset_class] = {
                        'total_trades': 0, 'total_wins': 0, 'total_pnl': 0.0, 'sessions': 0
                    }
                if data.get('trades', 0) > 0:
                    cumulative_asset_class[asset_class]['total_trades'] += data.get('trades', 0)
                    cumulative_asset_class[asset_class]['total_wins'] += data.get('wins', 0)
                    cumulative_asset_class[asset_class]['total_pnl'] += data.get('pnl', 0)
        
        # Calculate win rates and avg trades
        overall['win_rate'] = overall['total_wins'] / overall['total_trades'] if overall['total_trades'] > 0 else 0
        overall['avg_session_trades'] = overall['total_trades'] / overall['total_sessions'] if overall['total_sessions'] > 0 else 0
        
        # Add win rates to strategy stats
        for strategy, data in cumulative_strategy.items():
            data['win_rate'] = data['total_wins'] / data['total_trades'] if data['total_trades'] > 0 else 0
        
        # Add win rates to asset class stats
        for asset_class, data in cumulative_asset_class.items():
            data['win_rate'] = data['total_wins'] / data['total_trades'] if data['total_trades'] > 0 else 0
        
        # Build cumulative returns distribution from all trades
        trades_cursor = db.paper_trades.find(
            {"type": "exit"},
            {"_id": 0, "pnl": 1, "size": 1}
        )
        all_trades = await trades_cursor.to_list(length=10000)
        
        # Add current session trades if running
        if paper_trader and paper_trader.running:
            all_trades.extend([{"pnl": t.get("pnl", 0), "size": t.get("size", 1)} for t in paper_trader.closed_trades])
        
        # Calculate returns distribution
        returns_distribution = {"bins": [], "stats": None}
        if all_trades:
            returns = [t.get("pnl", 0) / max(t.get("size", 1), 0.01) * 100 for t in all_trades]
            
            # Create bins
            import numpy as np
            if len(returns) > 0:
                bin_edges = [-50, -30, -20, -10, -5, -2, 0, 2, 5, 10, 20, 30, 50, 100]
                bins = []
                for i in range(len(bin_edges) - 1):
                    count = sum(1 for r in returns if bin_edges[i] <= r < bin_edges[i+1])
                    bins.append({
                        "min": bin_edges[i],
                        "max": bin_edges[i+1],
                        "label": f"{bin_edges[i]}% to {bin_edges[i+1]}%",
                        "count": count
                    })
                
                returns_distribution["bins"] = bins
                returns_distribution["stats"] = {
                    "mean": float(np.mean(returns)) if returns else 0,
                    "median": float(np.median(returns)) if returns else 0,
                    "std": float(np.std(returns)) if returns else 0,
                    "positive_returns": sum(1 for r in returns if r > 0),
                    "negative_returns": sum(1 for r in returns if r < 0),
                    "skewness": 0,
                    "kurtosis": 0
                }
        
        return {
            "overall": overall,
            "by_strategy": cumulative_strategy,
            "by_asset_class": cumulative_asset_class,
            "returns_distribution": returns_distribution,
            "current_session_included": paper_trader.running if paper_trader else False
        }
        
    except Exception as e:
        logger.error(f"Error getting cumulative stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get cumulative stats: {str(e)}"}
        )

# =============================================
# STRATEGY OPTIMIZER ENDPOINTS
# =============================================

@api_router.post("/optimizer/run/{session_id}")
async def run_strategy_optimization(session_id: str, username: str = Depends(verify_credentials_dual)):
    """Run strategy optimization based on a paper trading session"""
    global strategy_optimizer
    
    try:
        if not strategy_optimizer:
            strategy_optimizer = StrategyOptimizer()
            await strategy_optimizer.load_params()
        
        result = await strategy_optimizer.optimize_from_paper_session(session_id)
        return result
        
    except Exception as e:
        logger.error(f"Error running optimization: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Optimization failed: {str(e)}"}
        )

@api_router.get("/optimizer/params")
async def get_optimizer_params():
    """Get current optimized strategy parameters"""
    global strategy_optimizer
    
    try:
        if not strategy_optimizer:
            strategy_optimizer = StrategyOptimizer()
            await strategy_optimizer.load_params()
        
        return {
            "params": strategy_optimizer.get_params()
        }
    except Exception as e:
        logger.error(f"Error getting params: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get params: {str(e)}"}
        )

@api_router.get("/optimizer/stats")
async def get_optimization_stats():
    """Get optimization history and statistics"""
    global strategy_optimizer
    
    try:
        if not strategy_optimizer:
            strategy_optimizer = StrategyOptimizer()
            await strategy_optimizer.load_params()
        
        return await strategy_optimizer.get_optimization_stats()
        
    except Exception as e:
        logger.error(f"Error getting optimization stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get stats: {str(e)}"}
        )

@api_router.post("/optimizer/apply")
async def apply_optimized_params(username: str = Depends(verify_credentials_dual)):
    """Apply optimized parameters to trading strategies"""
    global strategy_optimizer
    
    try:
        if not strategy_optimizer:
            return JSONResponse(
                status_code=400,
                content={"message": "No optimization has been run yet"}
            )
        
        params = strategy_optimizer.get_params()
        
        # Save params for use by paper trader and live trading
        db = get_db()
        await db.strategy_params.update_one(
            {"type": "active"},
            {"$set": {
                "type": "active",
                "params": params,
                "applied_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return {
            "message": "Optimized parameters applied",
            "params": params
        }
        
    except Exception as e:
        logger.error(f"Error applying params: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to apply params: {str(e)}"}
        )

# =============================================
# WEBSOCKET ENDPOINT FOR REAL-TIME UPDATES
# =============================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time trading updates.
    Clients connect to receive live trade feeds, P&L updates, and backtest progress.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial state on connection
        initial_data = await ws_manager._gather_update_data()
        initial_data["type"] = "connected"
        await websocket.send_json(initial_data)
        
        # Keep connection alive and listen for client messages
        while True:
            try:
                # Wait for messages from client (ping/pong or commands)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                
                if data == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                elif data == "get_update":
                    update = await ws_manager._gather_update_data()
                    await websocket.send_json(update)
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ws_manager.disconnect(websocket)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    global user_config, ws_manager
    await connect_db()
    
    # Initialize default admin user if no users exist
    try:
        await init_default_admin()
    except Exception as e:
        logger.warning(f"Could not initialize default admin: {e}")
    
    # Load saved user config from database
    try:
        db = get_db()
        saved_config = await db.user_config.find_one({"type": "trading_preferences"}, {"_id": 0})
        if saved_config:
            if "enabled_asset_classes" in saved_config:
                user_config["enabled_asset_classes"] = saved_config["enabled_asset_classes"]
            if "enabled_strategies" in saved_config:
                user_config["enabled_strategies"] = saved_config["enabled_strategies"]
            logger.info(f"Loaded user config: {len(user_config['enabled_strategies'])} strategies, {len(user_config['enabled_asset_classes'])} asset classes")
    except Exception as e:
        logger.warning(f"Could not load saved config: {e}")
    
    # Start continuous price history collection in background
    try:
        global historical_collector
        if not historical_collector:
            historical_collector = HistoricalDataCollector()
        
        # Start background task for continuous price collection (every 30 minutes)
        asyncio.create_task(historical_collector.start_price_history_collection(
            interval_minutes=30,
            market_limit=100
        ))
        logger.info("Started continuous price history collection (30 min interval, 100 markets)")
    except Exception as e:
        logger.warning(f"Could not start continuous price collection: {e}")
    
    # Start WebSocket broadcast loop
    try:
        asyncio.create_task(ws_manager.start_broadcast_loop())
        logger.info("Started WebSocket broadcast loop")
    except Exception as e:
        logger.warning(f"Could not start WebSocket broadcast: {e}")
    
    logger.info("APEX TRADER API Started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown - save all running sessions"""
    global trading_bot, historical_collector, ws_manager, paper_trader
    
    # CRITICAL: Save paper trading session on shutdown
    if paper_trader and paper_trader.running:
        logger.info("Shutdown: Saving paper trading session...")
        try:
            await paper_trader.stop(graceful=False)  # Force close positions and save
            logger.info("Shutdown: Paper trading session saved successfully")
        except Exception as e:
            logger.error(f"Shutdown: Error saving paper trading session: {e}")
    
    if trading_bot and trading_bot.running:
        await trading_bot.stop()
    if historical_collector and historical_collector.price_history_running:
        await historical_collector.stop_price_history_collection()
    if ws_manager:
        await ws_manager.stop_broadcast_loop()
    await close_db()
    logger.info("APEX TRADER API Shutdown")