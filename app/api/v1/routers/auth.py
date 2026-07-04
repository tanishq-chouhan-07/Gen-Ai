from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.api.schemas.auth import Token, UserCreate, User
from app.services.auth_service import authenticate_user, create_access_token, create_user
from app.config.settings import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

@router.post("/register", response_model=User)
async def register(user: UserCreate):
    try:
        new_user = await create_user(user.username, user.password, user.role)
        return User(id=new_user.id, username=new_user.username, role=new_user.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}