from app.core.database import supabase
from app.schemas.user import UserSignUp, UserLogin
from fastapi import HTTPException

class AuthService:
    @staticmethod
    def sign_up(user_data: UserSignUp):
        try:
            # Sign up creates the user in auth.users
            # The Trigger we wrote in SQL will automatically copy this to public.profiles
            response = supabase.auth.sign_up({
                "email": user_data.email,
                "password": user_data.password,
                "options": {
                    "data": {
                        "full_name": user_data.full_name
                    }
                }
            })
            return response
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def login(user_data: UserLogin):
        try:
            response = supabase.auth.sign_in_with_password({
                "email": user_data.email,
                "password": user_data.password,
            })
            return response
        except Exception as e:
            raise HTTPException(status_code=400, detail="Incorrect email or password")