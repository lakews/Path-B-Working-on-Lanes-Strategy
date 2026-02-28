"""
API KEY PERSISTENCE SERVICE
============================

Stores API keys in MongoDB for persistence across forks/restarts.
Keys are stored encrypted and loaded on startup to override .env placeholders.

Collections:
- api_keys: Stores encrypted API keys with metadata

Usage:
1. On startup: load_api_keys_from_db() - loads keys into environment
2. On key update: save_api_key(key_name, key_value) - persists to MongoDB
3. On key retrieval: get_api_key(key_name) - gets from env (loaded from DB)
"""

import os
import logging
import base64
from datetime import datetime, timezone
from typing import Dict, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Supported API keys that can be persisted
SUPPORTED_KEYS = [
    'EXA_API_KEY',
    'APIFY_API_KEY', 
    'CRYPTOPANIC_API_KEY',
    'ODDS_API_KEY',
    'FINNHUB_API_KEY',
    'SENDGRID_API_KEY',
    'EMERGENT_LLM_KEY',
]

# Simple encryption using a derived key from DB_NAME (not military-grade, but prevents casual exposure)
def _get_cipher():
    """Get Fernet cipher for encryption/decryption"""
    # Use DB_NAME as salt for key derivation (unique per deployment)
    salt = os.environ.get('DB_NAME', 'apex_trader').encode()
    # Use a fixed passphrase (can be made configurable)
    passphrase = b'apex_trader_api_key_store_v1'
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase))
    return Fernet(key)


def _encrypt_key(value: str) -> str:
    """Encrypt an API key value"""
    try:
        cipher = _get_cipher()
        return cipher.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"[API KEY STORE] Encryption error: {e}")
        return value  # Fallback to plaintext if encryption fails


def _decrypt_key(encrypted: str) -> str:
    """Decrypt an API key value"""
    try:
        cipher = _get_cipher()
        return cipher.decrypt(encrypted.encode()).decode()
    except Exception as e:
        logger.error(f"[API KEY STORE] Decryption error: {e}")
        return encrypted  # Return as-is if decryption fails


async def save_api_key(db, key_name: str, key_value: str) -> bool:
    """
    Save an API key to MongoDB.
    
    Args:
        db: MongoDB database instance
        key_name: Name of the key (e.g., 'EXA_API_KEY')
        key_value: The actual API key value
        
    Returns:
        True if saved successfully
    """
    if key_name not in SUPPORTED_KEYS:
        logger.warning(f"[API KEY STORE] Unsupported key: {key_name}")
        return False
    
    try:
        encrypted_value = _encrypt_key(key_value)
        
        await db.api_keys.update_one(
            {'key_name': key_name},
            {
                '$set': {
                    'key_name': key_name,
                    'encrypted_value': encrypted_value,
                    'updated_at': datetime.now(timezone.utc),
                    'is_placeholder': _is_placeholder(key_value),
                }
            },
            upsert=True
        )
        
        # Also update environment variable
        os.environ[key_name] = key_value
        
        logger.info(f"[API KEY STORE] ✓ Saved {key_name} to MongoDB")
        return True
        
    except Exception as e:
        logger.error(f"[API KEY STORE] Error saving {key_name}: {e}")
        return False


async def load_api_keys_from_db(db) -> Dict[str, bool]:
    """
    Load all API keys from MongoDB and set as environment variables.
    
    Called on startup to restore persisted keys.
    
    Returns:
        Dict of key_name -> loaded (True/False)
    """
    results = {}
    
    try:
        cursor = db.api_keys.find({})
        keys = await cursor.to_list(length=100)
        
        for key_doc in keys:
            key_name = key_doc.get('key_name')
            encrypted_value = key_doc.get('encrypted_value')
            is_placeholder = key_doc.get('is_placeholder', True)
            
            if not key_name or not encrypted_value:
                continue
                
            # Skip if it's a placeholder
            if is_placeholder:
                logger.debug(f"[API KEY STORE] Skipping placeholder: {key_name}")
                results[key_name] = False
                continue
            
            try:
                decrypted_value = _decrypt_key(encrypted_value)
                
                # Only override if current env is placeholder or empty
                current_value = os.environ.get(key_name, '')
                if not current_value or _is_placeholder(current_value):
                    os.environ[key_name] = decrypted_value
                    logger.info(f"[API KEY STORE] ✓ Loaded {key_name} from MongoDB")
                    results[key_name] = True
                else:
                    logger.debug(f"[API KEY STORE] {key_name} already set in env, skipping")
                    results[key_name] = True
                    
            except Exception as e:
                logger.error(f"[API KEY STORE] Error loading {key_name}: {e}")
                results[key_name] = False
        
        loaded_count = sum(1 for v in results.values() if v)
        logger.info(f"[API KEY STORE] Loaded {loaded_count}/{len(results)} API keys from MongoDB")
        
    except Exception as e:
        logger.error(f"[API KEY STORE] Error loading keys: {e}")
    
    return results


async def get_api_key_status(db) -> List[Dict]:
    """
    Get status of all supported API keys.
    
    Returns list of dicts with key status info.
    """
    status = []
    
    for key_name in SUPPORTED_KEYS:
        env_value = os.environ.get(key_name, '')
        
        # Check if stored in DB
        db_doc = await db.api_keys.find_one({'key_name': key_name})
        
        status.append({
            'key_name': key_name,
            'is_set': bool(env_value) and not _is_placeholder(env_value),
            'is_placeholder': _is_placeholder(env_value),
            'in_database': db_doc is not None and not db_doc.get('is_placeholder', True),
            'last_updated': db_doc.get('updated_at').isoformat() if db_doc and db_doc.get('updated_at') else None,
            'preview': f"{env_value[:8]}..." if env_value and len(env_value) > 8 else '(not set)',
        })
    
    return status


def _is_placeholder(value: str) -> bool:
    """Check if a value is a placeholder (not a real API key)"""
    if not value:
        return True
    
    placeholders = [
        'your-api-key',
        'placeholder',
        'xxx',
        'test',
        'demo',
        'quanthub',  # The old EXA placeholder
        'strategybot',  # Polymarket placeholder
        'markets-first',  # Another old EXA placeholder
        'apify_api_xxx',  # Apify placeholder
    ]
    
    value_lower = value.lower()
    for p in placeholders:
        if p in value_lower:
            return True
    
    # Also check if it's too short to be a real key
    if len(value) < 10:
        return True
    
    # Check if it looks like a UUID or typical API key pattern
    # Real keys are usually longer and alphanumeric
    if len(value) < 20 and '-' in value and not any(c.isdigit() for c in value.replace('-', '')):
        return True
    
    return False


# Singleton for quick access
_api_key_store_initialized = False

async def init_api_key_store(db):
    """Initialize API key store on startup"""
    global _api_key_store_initialized
    
    if _api_key_store_initialized:
        return
    
    logger.info("[API KEY STORE] Initializing...")
    
    # Create index
    await db.api_keys.create_index('key_name', unique=True)
    
    # Load keys from DB
    await load_api_keys_from_db(db)
    
    _api_key_store_initialized = True
    logger.info("[API KEY STORE] ✓ Initialized")
