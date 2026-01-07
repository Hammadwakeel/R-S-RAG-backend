from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from typing import Any

from app.schemas.user import UserSignUp, UserLogin
from app.services.auth_service import AuthService

router = APIRouter()

# --- JSON Login (For your Frontend/Mobile App) ---
@router.post("/signup")
async def sign_up(user: UserSignUp):
    result = AuthService.sign_up(user)
    return {"message": "User created", "user": result.user}

@router.post("/login")
async def login(user: UserLogin):
    result = AuthService.login(user)
    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "user": result.user
    }

# --- Swagger UI Login (Form Data) ---
@router.post("/login/swagger", include_in_schema=False)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> Any:
    """
    Specific endpoint for Swagger UI Authorization.
    Swagger sends 'username' and 'password' as form fields.
    We map 'username' -> 'email' for Supabase.
    """
    try:
        # Create a UserLogin object from the form data
        user_data = UserLogin(email=form_data.username, password=form_data.password)
        result = AuthService.login(user_data)
        
        # Return exact format expected by OAuth2 spec
        return {
            "access_token": result.session.access_token,
            "token_type": "bearer"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Incorrect email or password")