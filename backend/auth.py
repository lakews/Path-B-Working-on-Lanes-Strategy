"""
JWT Authentication Module for APEX TRADER
Replaces weak API key with secure JWT-based authentication
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from database import get_db

logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "apex-trader-super-secret-key-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "1440"))  # 24 hours default

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    email: Optional[str] = None
    created_at: str
    is_admin: bool = False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_user(username: str):
    """Get user from database"""
    db = get_db()
    user = await db.users.find_one({"username": username}, {"_id": 0})
    return user


async def authenticate_user(username: str, password: str):
    """Authenticate a user with username and password"""
    user = await get_user(username)
    if not user:
        return False
    if not verify_password(password, user.get("hashed_password", "")):
        return False
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise credentials_exception
    
    user = await get_user(token_data.username)
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_user_optional(token: str = Depends(oauth2_scheme)):
    """Get current user if token provided, otherwise return None"""
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


async def create_user(user_data: UserCreate, is_admin: bool = False):
    """Create a new user in the database"""
    db = get_db()
    
    # Check if user already exists
    existing_user = await db.users.find_one({"username": user_data.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if user_data.email:
        existing_email = await db.users.find_one({"email": user_data.email})
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Create user document
    user_doc = {
        "username": user_data.username,
        "hashed_password": get_password_hash(user_data.password),
        "email": user_data.email,
        "is_admin": is_admin,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": None
    }
    
    await db.users.insert_one(user_doc)
    logger.info(f"Created new user: {user_data.username}")
    
    return {
        "username": user_data.username,
        "email": user_data.email,
        "is_admin": is_admin,
        "created_at": user_doc["created_at"]
    }


async def init_default_admin():
    """Initialize default admin user if no users exist"""
    db = get_db()
    
    # Check if any users exist
    user_count = await db.users.count_documents({})
    if user_count == 0:
        # Create default admin user
        default_admin = UserCreate(
            username=os.environ.get("ADMIN_USERNAME", "admin"),
            password=os.environ.get("ADMIN_PASSWORD", "apex2026!"),
            email=os.environ.get("ADMIN_EMAIL", "admin@apex-trader.local")
        )
        await create_user(default_admin, is_admin=True)
        logger.info("Created default admin user")
