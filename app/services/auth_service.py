import asyncio
import logging
from fastapi import HTTPException, status
from gotrue.errors import AuthApiError
# 1. CHANGE THIS IMPORT
import app.core.database as db 
from app.schemas.user import UserSignUp, UserLogin

logger = logging.getLogger(__name__)

class AuthService:
    
    @staticmethod
    async def sign_up(user_data: UserSignUp):
        """
        Registers a new user.
        Wraps blocking Supabase call in a thread.
        """
        # 2. Add Safety Check
        if not db.supabase:
            logger.error("❌ Database not initialized")
            raise HTTPException(status_code=500, detail="Database unavailable")

        try:
            # 3. Use 'db.supabase' instead of just 'supabase'
            auth_response = await asyncio.to_thread(
                db.supabase.auth.sign_up,
                {
                    "email": user_data.email, 
                    "password": user_data.password,
                    "options": {
                        "data": {"full_name": user_data.full_name}
                    }
                }
            )
            
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Registration failed. No user returned."
                )
            
            return auth_response

        except AuthApiError as e:
            logger.warning(f"⚠️ Auth API Error: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
        except Exception as e:
            logger.error(f"❌ Unexpected Sign-up Error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error during signup")

    @staticmethod
    async def login(user_data: UserLogin):
        """
        Authenticates a user.
        Wraps blocking Supabase call in a thread.
        """
        # 2. Add Safety Check
        if not db.supabase:
            logger.error("❌ Database not initialized")
            raise HTTPException(status_code=500, detail="Database unavailable")

        try:
            # 3. Use 'db.supabase' instead of just 'supabase'
            auth_response = await asyncio.to_thread(
                db.supabase.auth.sign_in_with_password,
                {"email": user_data.email, "password": user_data.password}
            )

            if not auth_response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Invalid credentials"
                )

            return auth_response

        except AuthApiError as e:
            logger.warning(f"⚠️ Login Failed: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        except Exception as e:
            logger.error(f"❌ Unexpected Login Error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed")