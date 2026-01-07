import logging
from typing import Any
from app.core.database import supabase
from app.schemas.user import UserUpdate
from fastapi import HTTPException

# 1. Setup Logger
logger = logging.getLogger(__name__)

class UserService:
    @staticmethod
    def get_or_create_profile(user: Any):
        """
        Tries to fetch the profile. If not found (404), creates it using Auth data.
        'user' type is Any to avoid 'gotrue' import errors across versions.
        """
        try:
            # 1. Try to fetch existing profile
            response = supabase.table("profiles").select("*").eq("id", user.id).single().execute()
            logger.info(f"✅ Profile found for user {user.id}")
            return response.data
            
        except Exception:
            # 2. If fetch fails, create the profile manually
            logger.warning(f"⚠️ Profile missing for {user.id}. Attempting to create now...")
            try:
                new_profile = {
                    "id": user.id,
                    "email": user.email,
                    # Safe access to metadata
                    "full_name": user.user_metadata.get("full_name", "") if user.user_metadata else ""
                }
                data, count = supabase.table("profiles").insert(new_profile).execute()
                
                logger.info(f"✅ Successfully created profile for user {user.id}")
                return data[1][0] 
                
            except Exception as insert_error:
                logger.error(f"❌ Failed to create profile: {str(insert_error)}")
                raise HTTPException(status_code=400, detail=f"Could not create profile: {str(insert_error)}")

    @staticmethod
    def update_profile(user_id: str, user_data: UserUpdate):
        try:
            update_data = {k: v for k, v in user_data.dict().items() if v is not None}
            
            if not update_data:
                 logger.info(f"ℹ️ No changes requested for user {user_id}")
                 # Fetch existing to return valid response
                 response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
                 return response.data

            logger.info(f"📝 Updating profile for user {user_id}: {update_data}")
            response = supabase.table("profiles").update(update_data).eq("id", user_id).execute()
            
            if len(response.data) == 0:
                 logger.error(f"❌ User {user_id} not found during update")
                 raise HTTPException(status_code=404, detail="User not found")
                 
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Update failed: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))