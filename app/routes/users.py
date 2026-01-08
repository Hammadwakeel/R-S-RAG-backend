from fastapi import APIRouter, Depends, HTTPException
from app.schemas.user import UserResponse, UserUpdate
from app.core.security import get_current_user
from app.services.user_service import UserService

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user = Depends(get_current_user)):
    """
    Get current user profile.
    """
    # ⚡ FIX: Changed from 'get_or_create_profile' to 'get_user_profile'
    # The logic inside the service handles the "create if missing" part.
    return await UserService.get_user_profile(current_user.id)

@router.patch("/me", response_model=UserResponse)
async def update_user_me(
    user_update: UserUpdate,
    current_user = Depends(get_current_user)
):
    """
    Update current user profile.
    """
    return await UserService.update_user_profile(current_user.id, user_update)