import asyncio
import logging
from fastapi import HTTPException, status
from gotrue.errors import AuthApiError
from app.core.database import supabase
from app.schemas.user import UserSignUp, UserLogin, UserResponse

logger = logging.getLogger(__name__)

class AuthService:
    
    @staticmethod
    async def sign_up(user_data: UserSignUp):
        """
        Registers a new user.
        Wraps blocking Supabase call in a thread.
        """
        try:
            # 1. Run blocking I/O in a thread
            auth_response = await asyncio.to_thread(
                supabase.auth.sign_up,
                {
                    "email": user_data.email, 
                    "password": user_data.password,
                    "options": {
                        "data": {"full_name": user_data.full_name}
                    }
                }
            )
            
            # 2. Validate Response
            if not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Registration failed. No user returned."
                )
            
            # 3. Create Profile (Optional - trigger often handles this, but good to be safe)
            # You might want to call UserService here if you don't use SQL Triggers
            
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
        try:
            # 1. Run blocking I/O in a thread
            auth_response = await asyncio.to_thread(
                supabase.auth.sign_in_with_password,
                {"email": user_data.email, "password": user_data.password}
            )

            # 2. Validate Response
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