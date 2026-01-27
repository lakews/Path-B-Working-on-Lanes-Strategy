from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class MarketCategory(str, Enum):
    CRYPTO = "crypto"
    SPORTS = "sports"
    POLITICS = "politics"
    FINANCE = "finance"
    CULTURE = "culture"
    WEATHER = "weather"
    ENTERTAINMENT = "entertainment"

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class StrategyType(str, Enum):
    DELTA_NEUTRAL = "delta_neutral"
    ALPHA_DIRECTIONAL = "alpha_directional"
    VOLATILITY_EXPLOITATION = "volatility_exploitation"
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"

class Market(BaseModel):
    id: str
    condition_id: str
    question: str
    category: MarketCategory
    end_date: Optional[datetime] = None
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    order_book: Dict[str, Any] = {}
    last_update: datetime = Field(default_factory=datetime.utcnow)
    
class Position(BaseModel):
    id: str
    market_id: str
    side: OrderSide
    shares: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    strategy: StrategyType
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Trade(BaseModel):
    id: str
    market_id: str
    order_id: str
    side: OrderSide
    price: float
    shares: float
    total_cost: float
    fee: float
    strategy: StrategyType
    strategy_lane: str = "ALPHA"  # Three-Speed: HFT, ALPHA, or GAMMA (default ALPHA for safety)
    execution_latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Signal(BaseModel):
    id: str
    market_id: str
    signal_type: str
    confidence: float
    source: str
    value: float
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SharpTrader(BaseModel):
    id: str
    address: str
    win_rate: float
    roi: float
    avg_line_movement: float
    total_volume: float
    category_focus: MarketCategory
    identified_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)

class PerformanceMetrics(BaseModel):
    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_capital: float
    deployed_capital: float
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    num_trades: int
    num_positions: int
    avg_execution_latency_ms: float