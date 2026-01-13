from fastapi import FastAPI, APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from database import connect_db, close_db, get_db
from config import config
from trading_bot import ApexTrader
from services.performance_analytics import PerformanceAnalytics
from backtest.backtest_engine import BacktestEngine

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

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global trading bot instance
trading_bot: Optional[ApexTrader] = None
analytics_engine: Optional[PerformanceAnalytics] = None
backtest_engine: Optional[BacktestEngine] = None
trading_mode: str = "stopped"  # "stopped", "live", "backtest"

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
    max_drawdown_pct: Optional[float] = None

# Routes
@api_router.get("/")
async def root():
    return {
        "message": "APEX TRADER - Advanced Polymarket Execution System",
        "version": "1.0.0",
        "status": "operational"
    }

@api_router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get system status and configuration"""
    global trading_mode
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
            "max_kelly_fraction": config.MAX_KELLY_FRACTION
        },
        timestamp=datetime.now(timezone.utc).isoformat()
    )

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
    strategies: Optional[List[str]] = None
):
    """Start backtesting"""
    global backtest_engine, trading_mode
    
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
        
        # Run backtest in background
        async def run_backtest_task():
            await backtest_engine.run_backtest(start_date, end_date, strategies)
        
        background_tasks.add_task(run_backtest_task)
        
        return {
            "message": "Backtest started successfully",
            "mode": "backtest",
            "start_date": start_date,
            "end_date": end_date
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
    
    if not backtest_engine or not backtest_engine.running:
        return JSONResponse(
            status_code=400,
            content={"message": "No backtest is running"}
        )
    
    try:
        await backtest_engine.stop_backtest()
        trading_mode = "stopped"
        return {"message": "Backtest stopped successfully"}
    except Exception as e:
        logger.error(f"Error stopping backtest: {e}")
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
async def get_markets(limit: int = 50):
    """Get active markets"""
    db = get_db()
    
    try:
        markets = await db.markets.find(
            {},
            {"_id": 0}
        ).sort("volume", -1).limit(limit).to_list(length=limit)
        
        return {"markets": markets, "count": len(markets)}
    except Exception as e:
        logger.error(f"Error getting markets: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to get markets: {str(e)}"}
        )

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
@api_router.post("/config/update")
async def update_config(config_update: TradingConfig):
    """Update trading configuration"""
    try:
        if config_update.trades_per_10min:
            os.environ['TRADES_PER_10MIN'] = str(config_update.trades_per_10min)
        
        if config_update.initial_capital:
            os.environ['INITIAL_CAPITAL'] = str(config_update.initial_capital)
        
        if config_update.capital_deployment_pct:
            os.environ['CAPITAL_DEPLOYMENT_PCT'] = str(config_update.capital_deployment_pct)
        
        if config_update.max_position_size_pct:
            os.environ['MAX_POSITION_SIZE_PCT'] = str(config_update.max_position_size_pct)
        
        if config_update.kelly_fraction is not None:
            # Validate Kelly fraction is within bounds
            kelly = max(config.MIN_KELLY_FRACTION, min(config.MAX_KELLY_FRACTION, config_update.kelly_fraction))
            os.environ['KELLY_FRACTION'] = str(kelly)
        
        if config_update.max_drawdown_pct:
            os.environ['MAX_DRAWDOWN_PCT'] = str(config_update.max_drawdown_pct)
        
        return {"message": "Configuration updated. Restart bot for changes to take effect."}
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to update config: {str(e)}"}
        )

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
    await connect_db()
    logger.info("APEX TRADER API Started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global trading_bot
    if trading_bot and trading_bot.running:
        await trading_bot.stop()
    await close_db()
    logger.info("APEX TRADER API Shutdown")