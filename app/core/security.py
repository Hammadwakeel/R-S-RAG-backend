from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.database import supabase
from app.core.config import settings

# This tells Swagger UI to send the username/password to this URL to get a token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/swagger")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Validates the JWT token.
    OAuth2PasswordBearer automatically extracts the token from the request header.
    """
    try:
        # Verify the token with Supabase
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_response.user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )