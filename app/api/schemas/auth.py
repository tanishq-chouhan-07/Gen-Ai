from pydantic import BaseModel, Field, field_validator
from typing import Optional
import enum
import re

class RoleEnum(str, enum.Enum):
    user = "user"
    admin = "admin"

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    
    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v):
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must be alphanumeric (letters, numbers, underscores)")
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    role: RoleEnum = RoleEnum.user

class User(UserBase):
    id: str
    role: RoleEnum

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None