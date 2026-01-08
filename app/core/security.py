from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
import app.core.database as db # Import the module, not the variable

# 1. Fix the Token URL to match your API prefix
# This tells Swagger UI where to send the username/password
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login/swagger"
)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Validates the JWT token with Supabase Auth.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 2. Check if DB is ready
    if not db.supabase:
        raise HTTPException(
            status_code=503, 
            detail="Database not initialized"
        )

    try:
        # 3. Verify Token with Supabase
        # 'get_user' verifies the JWT signature and expiration
        user_response = db.supabase.auth.get_user(token)
        
        if not user_response.user:
            raise credentials_exception
            
        return user_response.user

    except Exception as e:
        # Log the specific auth error for debugging
        print(f"Auth Error: {e}") 
        raise credentials_exception