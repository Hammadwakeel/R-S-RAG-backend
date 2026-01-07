import asyncio
import logging
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, status
from app.core.database import supabase
from app.schemas.user import UserUpdate as ProfileUpdate

logger = logging.getLogger(__name__)

class UserService:
    
    @staticmethod
    async def get_or_create_profile(user_id: UUID, email: str, full_name: Optional[str] = None) -> dict:
        """
        Fetches a profile or creates one if it doesn't exist.
        Wraps blocking I/O in a thread.
        """
        try:
            # 1. Try to Fetch Existing Profile
            response = await asyncio.to_thread(
                supabase.table("profiles").select("*").eq("id", str(user_id)).execute
            )
            
            # Supabase SDK v2 returns 'data' as a list of dicts
            if response.data and len(response.data) > 0:
                return response.data[0]

            # 2. Create Profile if missing
            logger.info(f"👤 Creating profile for User {user_id}")
            
            new_profile = {
                "id": str(user_id),
                "email": email,
                "full_name": full_name or email.split("@")[0]
            }
            
            create_res = await asyncio.to_thread(
                supabase.table("profiles").insert(new_profile).execute
            )
            
            if not create_res.data:
                raise HTTPException(status_code=500, detail="Failed to create profile")
                
            return create_res.data[0]

        except Exception as e:
            logger.error(f"❌ Profile Error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Profile operation failed")

    @staticmethod
    async def get_profile(user_id: UUID) -> dict:
        """Get profile by ID"""
        try:
            response = await asyncio.to_thread(
                supabase.table("profiles").select("*").eq("id", str(user_id)).single().execute
            )
            return response.data
        except Exception as e:
            logger.error(f"❌ Failed to fetch profile {user_id}: {e}")
            raise HTTPException(status_code=404, detail="Profile not found")

    @staticmethod
    async def update_profile(user_id: UUID, update_data: ProfileUpdate) -> dict:
        """Update profile fields"""
        try:
            # Filter out None values to avoid overwriting with null
            data_to_update = {k: v for k, v in update_data.model_dump().items() if v is not None}
            
            if not data_to_update:
                return await UserService.get_profile(user_id)

            response = await asyncio.to_thread(
                supabase.table("profiles").update(data_to_update).eq("id", str(user_id)).execute
            )
            
            if not response.data:
                raise HTTPException(status_code=400, detail="Update failed")
                
            return response.data[0]
            
        except Exception as e:
            logger.error(f"❌ Failed to update profile {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Server error updating profile")