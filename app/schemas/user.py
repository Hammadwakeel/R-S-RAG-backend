from pydantic import BaseModel, EmailStr, Field, ConfigDict
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

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None  # <--- Make sure this exists!

# Properties to return to client
class UserResponse(UserBase):
    id: UUID
    avatar_url: Optional[str] = None
    role: str = "user" # ✅ Added role field

    # Pydantic V2 Configuration
    model_config = ConfigDict(from_attributes=True)