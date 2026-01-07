import logging
from fastapi import APIRouter, Depends
from app.schemas.user import UserResponse, UserUpdate
from app.services.user_service import UserService
from app.core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def read_users_me(current_user = Depends(get_current_user)):
    logger.info(f"👤 Fetching profile for user_id: {current_user.id}")
    profile = UserService.get_or_create_profile(current_user)
    return profile

@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
async def update_user_me(user_update: UserUpdate, current_user = Depends(get_current_user)):
    logger.info(f"✏️ Update request for user_id: {current_user.id}")
    updated_profile = UserService.update_profile(current_user.id, user_update)
    return updated_profile