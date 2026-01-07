from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.schemas.user import UserResponse, UserUpdate as ProfileUpdate
from app.services.user_service import UserService

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user = Depends(get_current_user)):
    """
    Get current user profile. 
    Automatically creates a profile entry if it's missing.
    """
    # Using 'await' because we made the service async
    profile = await UserService.get_or_create_profile(
        user_id=current_user.id,
        email=current_user.email,
        full_name=current_user.user_metadata.get("full_name")
    )
    return profile

@router.patch("/me", response_model=UserResponse)
async def update_user_me(
    update_data: ProfileUpdate,
    current_user = Depends(get_current_user)
):
    """
    Update user profile fields.
    """
    updated_profile = await UserService.update_profile(
        user_id=current_user.id,
        update_data=update_data
    )
    return updated_profile