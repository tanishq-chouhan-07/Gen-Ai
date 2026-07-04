# app/services/auth_service.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config.settings import get_settings
from app.api.schemas.auth import TokenData
from app.db.models import UserModel
from app.db.database import get_session_factory  # <--- CHANGED IMPORT

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_user(username: str, password: str, role: str = "user") -> UserModel:
    """Hashes password and saves a new user to PostgreSQL."""
    hashed_password = pwd_context.hash(password)
    new_user = UserModel(
        username=username,
        hashed_password=hashed_password,
        role=role
    )
    
    factory = get_session_factory()  # <--- CHANGED
    async with factory() as session: # <--- CHANGED
        try:
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user
        except IntegrityError:
            await session.rollback()
            raise ValueError("Username already registered")


async def authenticate_user(username: str, password: str) -> Optional[UserModel]:
    """Verifies username/password against the database."""
    factory = get_session_factory()  # <--- CHANGED
    async with factory() as session: # <--- CHANGED
        result = await session.execute(select(UserModel).where(UserModel.username == username))
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        if not pwd_context.verify(password, user.hashed_password):
            return None
        return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """Decodes JWT and returns token data if valid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            return None
        return TokenData(username=username, role=role)
    except JWTError:
        return None