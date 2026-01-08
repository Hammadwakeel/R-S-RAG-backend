import logging
import base64
from uuid import UUID
from fastapi import HTTPException
import app.core.database as db 
from app.schemas.user import UserUpdate

logger = logging.getLogger(__name__)

class UserService:
    
    @staticmethod
    def _upload_avatar_to_storage(user_id: str, base64_image: str) -> str:
        """
        Decodes Base64 image, uploads to Supabase Storage 'avatars' bucket,
        and returns a Signed URL.
        """
        try:
            if "," in base64_image:
                header, encoded = base64_image.split(",", 1)
                file_ext = header.split(";")[0].split("/")[1]
            else:
                encoded = base64_image
                file_ext = "png"

            file_data = base64.b64decode(encoded)
            file_path = f"{user_id}/avatar.{file_ext}"

            bucket = db.supabase.storage.from_("avatars")
            
            try:
                bucket.remove([file_path])
            except:
                pass

            bucket.upload(
                path=file_path,
                file=file_data,
                file_options={"content-type": f"image/{file_ext}", "upsert": "true"}
            )

            # Generate Signed URL (valid for 10 years approx)
            response = bucket.create_signed_url(file_path, 315360000)
            
            if isinstance(response, dict) and "signedURL" in response:
                return response["signedURL"]
            return response

        except Exception as e:
            logger.error(f"❌ Avatar Upload Error: {e}")
            return None

    @staticmethod
    async def get_user_profile(user_id: UUID):
        if not db.supabase:
            logger.error("Database client is not initialized")
            raise HTTPException(status_code=503, detail="Database unavailable")

        try:
            response = db.supabase.table("profiles").select("*").eq("id", str(user_id)).single().execute()
            
            if response.data:
                return response.data
            
            return {
                "id": str(user_id),
                "full_name": "",
                "avatar_url": "",
                "email": "" 
            }

        except Exception as e:
            logger.error(f"❌ Profile Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch profile")

    @staticmethod
    async def update_user_profile(user_id: UUID, user_data: UserUpdate):
        if not db.supabase:
            raise HTTPException(status_code=503, detail="Database unavailable")

        try:
            # Convert Pydantic model to dict, removing unset values
            updates = {
                k: v for k, v in user_data.model_dump(exclude_unset=True).items()
            }
            
            if not updates:
                return None

            # ---------------------------------------------------------
            # 🔐 FIX: Handle Password Update via Auth API
            # ---------------------------------------------------------
            if "password" in updates:
                new_password = updates.pop("password") # Remove from DB updates
                logger.info(f"🔐 Updating password for user {user_id}")
                
                try:
                    # Use the Admin API to update the user's password securely
                    db.supabase.auth.admin.update_user_by_id(
                        str(user_id), 
                        {"password": new_password}
                    )
                except Exception as auth_error:
                    logger.error(f"❌ Auth Update Failed: {auth_error}")
                    raise HTTPException(status_code=400, detail=f"Password update failed: {str(auth_error)}")

            # ---------------------------------------------------------
            # 🖼️ Handle Avatar Upload
            # ---------------------------------------------------------
            if "avatar_url" in updates and updates["avatar_url"].startswith("data:image"):
                new_url = UserService._upload_avatar_to_storage(str(user_id), updates["avatar_url"])
                if new_url:
                    updates["avatar_url"] = new_url
                else:
                    del updates["avatar_url"]
            
            # ---------------------------------------------------------
            # 💾 Update Profile Table (Name, Avatar, etc.)
            # ---------------------------------------------------------
            # Only proceed if there are still fields left to update (e.g. name or avatar)
            if updates:
                updates["updated_at"] = "now()"

                response = db.supabase.table("profiles").upsert({
                    "id": str(user_id),
                    **updates
                }).execute()
                
                if response.data and len(response.data) > 0:
                    return response.data[0]
                
                return updates
            
            # If only password was updated, return a basic success object
            return {"id": str(user_id), "status": "updated"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Update Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to update profile")