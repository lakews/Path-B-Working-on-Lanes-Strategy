import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

class Config:
    # MongoDB
    MONGO_URL = os.environ['MONGO_URL']
    DB_NAME = os.environ['DB_NAME']
    
    # Polymarket
    API_KEY = os.environ['API_KEY']
    API_SECRET = os.environ['API_SECRET']
    API_PASSPHRASE = os.environ['API_PASSPHRASE']
    POLYMARKET_ADDRESS = os.environ['POLYMARKET_ADDRESS']
    
    # Wallet
    PRIVATE_KEY = os.environ['PRIVATE_KEY']
    WALLET_ADDRESS = os.environ['WALLET_ADDRESS']
    POLYGON_RPC_URL = os.environ['POLYGON_RPC_URL']
    
    # LLM
    EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
    
    # Trading Configuration - NOTE: Settings page (MongoDB) is the SOURCE OF TRUTH
    # These are fallback defaults only used if MongoDB has no saved config
    INITIAL_CAPITAL = float(os.environ.get('INITIAL_CAPITAL', 10000))  # Default $10,000
    CAPITAL_DEPLOYMENT_PCT = float(os.environ.get('CAPITAL_DEPLOYMENT_PCT', 80))
    MAX_POSITION_SIZE_PCT = float(os.environ.get('MAX_POSITION_SIZE_PCT', 3))
    TRADES_PER_10MIN = int(os.environ.get('TRADES_PER_10MIN', 500))
    MAX_DRAWDOWN_PCT = float(os.environ.get('MAX_DRAWDOWN_PCT', 5))  # 5% default - Settings overrides
    KELLY_FRACTION = float(os.environ.get('KELLY_FRACTION', 0.25))
    MIN_KELLY_FRACTION = float(os.environ.get('MIN_KELLY_FRACTION', 0.10))
    MAX_KELLY_FRACTION = float(os.environ.get('MAX_KELLY_FRACTION', 0.50))
    
    # Market Selection Configuration - Settings page overrides these
    MIN_LIQUIDITY = float(os.environ.get('MIN_LIQUIDITY', 100))  # Minimum liquidity in USD
    MIN_VOLUME_24H = float(os.environ.get('MIN_VOLUME_24H', 1000))  # Minimum 24h volume in USD
    MAX_SPREAD = float(os.environ.get('MAX_SPREAD', 0.05))  # Maximum bid-ask spread (5%)
    MAX_OPEN_POSITIONS = int(os.environ.get('MAX_OPEN_POSITIONS', 50))  # Max concurrent positions
    
    # System Performance
    EXECUTION_LATENCY_MS = int(os.environ.get('EXECUTION_LATENCY_MS', 100))
    ML_INFERENCE_LATENCY_MS = int(os.environ.get('ML_INFERENCE_LATENCY_MS', 50))
    
    # Calculated values
    @property
    def DEPLOYED_CAPITAL(self):
        return self.INITIAL_CAPITAL * (self.CAPITAL_DEPLOYMENT_PCT / 100)
    
    @property
    def MAX_POSITION_SIZE(self):
        # Max position is % of DEPLOYED capital, not initial capital
        return self.DEPLOYED_CAPITAL * (self.MAX_POSITION_SIZE_PCT / 100)
    
    @property
    def TRADE_INTERVAL_SECONDS(self):
        return 600 / self.TRADES_PER_10MIN

config = Config()