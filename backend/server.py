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
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone, timedelta

from database import connect_db, close_db, get_db
from config import config
from trading_bot import ApexTrader
from services.performance_analytics import PerformanceAnalytics
from backtest.backtest_engine import BacktestEngine
from data.historical_collector import HistoricalDataCollector
from ml.rl_engine import RLAdaptiveEngine
from ml.social_sentiment import social_sentiment_analyzer
from ml.whale_tracker import whale_tracker
from ml.strategy_tuner import strategy_tuner
from auth import (
    create_access_token, authenticate_user, get_current_user, get_current_user_optional,
    create_user, init_default_admin, Token, UserCreate, UserLogin, UserResponse,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

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
trading_mode: str = "stopped"  # "stopped", "live", "backtest", "paper"
paper_trading_enabled: bool = False  # Paper trading flag

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
    enabled_asset_classes: Optional[List[str]] = None
    enabled_strategies: Optional[List[str]] = None

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
                        # Prices are already normalized by the API
                        yes_price = float(m.get('yes_price', 0.5))
                        no_price = float(m.get('no_price', 0.5))
                        
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

@api_router.get("/analytics")
async def get_analytics():
    """Get comprehensive performance analytics"""
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
            # Strategies and asset classes
            "enabled_strategies": saved_config.get("enabled_strategies", user_config["enabled_strategies"]) if saved_config else user_config["enabled_strategies"],
            "enabled_asset_classes": saved_config.get("enabled_asset_classes", user_config["enabled_asset_classes"]) if saved_config else user_config["enabled_asset_classes"],
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
        
        # Update asset classes and strategies
        if config_update.enabled_asset_classes is not None:
            user_config["enabled_asset_classes"] = config_update.enabled_asset_classes
            db_update["enabled_asset_classes"] = config_update.enabled_asset_classes
        
        if config_update.enabled_strategies is not None:
            user_config["enabled_strategies"] = config_update.enabled_strategies
            db_update["enabled_strategies"] = config_update.enabled_strategies
        
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
    try:
        from ml.rl_engine import RLAdaptiveEngine
        rl = RLAdaptiveEngine()
        
        # Load existing model
        await rl.load_model()
        
        stats = await rl.get_training_stats()
        
        return {
            "rl_stats": stats,
            "model_status": "loaded" if rl.training_iterations > 0 else "fresh"
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
    global paper_trader, trading_mode
    
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
        await paper_trader.stop(graceful=graceful)
        trading_mode = "stopped"
        
        status = paper_trader.get_status()
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

@api_router.get("/paper/trades")
async def get_paper_trades(limit: int = 50):
    """Get paper trading trade history"""
    global paper_trader
    
    if not paper_trader:
        return {"trades": []}
    
    return {"trades": paper_trader.get_trade_history(limit)}

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
                "side": trade.get("side"),
                "entry_price": trade.get("entry_price", 0),
                "exit_price": trade.get("price", 0),
                "size": trade.get("size", 0),
                "pnl": trade.get("pnl", 0),
                "hold_time_seconds": trade.get("hold_time_seconds", 0),
                "exit_reason": trade.get("exit_reason", "unknown"),
                "timestamp": trade.get("timestamp")
            })
        
        return {"trades": formatted_trades, "count": len(formatted_trades)}
    except Exception as e:
        logger.error(f"Error getting session trades: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@api_router.post("/paper/reset-live-stats")
async def reset_live_stats(current_user: str = Depends(get_current_user)):
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
        paper_trader.strategy_equity = {s: 0.0 for s in paper_trader.strategy_equity}
        paper_trader.asset_class_equity = {}
        paper_trader.strategy_stats = {
            'delta_neutral': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'volatility_exploitation': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'alpha_directional': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0},
            'arbitrage': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0}
        }
        paper_trader.asset_class_stats = {}
        
        logger.info("Live session stats reset")
        return {"message": "Live stats reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting live stats: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@api_router.post("/paper/reset-cumulative-stats")
async def reset_cumulative_stats(current_user: str = Depends(get_current_user)):
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
        
        return {
            "overall": overall,
            "by_strategy": cumulative_strategy,
            "by_asset_class": cumulative_asset_class,
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
    """Cleanup on shutdown"""
    global trading_bot, historical_collector, ws_manager
    if trading_bot and trading_bot.running:
        await trading_bot.stop()
    if historical_collector and historical_collector.price_history_running:
        await historical_collector.stop_price_history_collection()
    if ws_manager:
        await ws_manager.stop_broadcast_loop()
    await close_db()
    logger.info("APEX TRADER API Shutdown")