from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID

# Shared properties
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

# Properties to receive via API on creation
class UserSignUp(UserBase):
    password: str = Field(min_length=6)

# Properties to receive via API on login
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Properties to receive via API on update
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

# Properties to return to client
class UserResponse(UserBase):
    id: UUID
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True