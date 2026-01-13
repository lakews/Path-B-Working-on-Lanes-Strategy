from motor.motor_asyncio import AsyncIOMotorClient
from config import config
import logging

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    
db_instance = Database()

async def connect_db():
    """Connect to MongoDB"""
    try:
        db_instance.client = AsyncIOMotorClient(config.MONGO_URL)
        await db_instance.client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_db():
    """Close MongoDB connection"""
    if db_instance.client:
        db_instance.client.close()
        logger.info("MongoDB connection closed")

def get_db():
    """Get database instance"""
    return db_instance.client[config.DB_NAME]