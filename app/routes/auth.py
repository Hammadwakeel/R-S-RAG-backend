from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas.user import UserSignUp, UserLogin, UserResponse
from app.schemas.auth import Token
from app.services.auth_service import AuthService

router = APIRouter()

@router.post("/signup", response_model=UserResponse)
async def sign_up(user_data: UserSignUp):
    """
    Register a new user. 
    """
    # Service returns the raw Supabase User object
    auth_response = await AuthService.sign_up(user_data)
    
    # We map it to our Pydantic Schema
    if not auth_response.user:
        raise HTTPException(status_code=400, detail="Signup failed")
        
    return auth_response.user

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """
    Standard JSON Login.
    """
    auth_response = await AuthService.login(user_data)
    
    return {
        "access_token": auth_response.session.access_token,
        "token_type": "bearer",
        "user": auth_response.user,
        "refresh_token": auth_response.session.refresh_token
    }

@router.post("/login/swagger", include_in_schema=False)
async def login_swagger(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    Hidden endpoint strictly for Swagger UI 'Authorize' button.
    It accepts Form Data (username/password) instead of JSON.
    """
    user_data = UserLogin(email=form_data.username, password=form_data.password)
    auth_response = await AuthService.login(user_data)
    
    return {
        "access_token": auth_response.session.access_token,
        "token_type": "bearer"
    }