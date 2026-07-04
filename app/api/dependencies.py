# app/api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from app.services.auth_service import decode_access_token
from app.db.models import UserModel
from app.db.database import get_session_factory  # <--- CHANGED IMPORT

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserModel:
    """Decodes JWT and fetches the live User object from the database."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = decode_access_token(token)
    if token_data is None or token_data.username is None:
        raise credentials_exception
        
    factory = get_session_factory()  # <--- CHANGED
    async with factory() as session: # <--- CHANGED
        result = await session.execute(select(UserModel).where(UserModel.username == token_data.username))
        user = result.scalar_one_or_none()
        
        if user is None:
            raise credentials_exception
        
        # Optional: Check if user account is disabled
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Inactive user account")
            
        return user

def require_admin(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """Ensures the current user has the 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation forbidden: Admins only.",
        )
    return current_user