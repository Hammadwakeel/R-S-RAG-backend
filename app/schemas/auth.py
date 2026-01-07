from pydantic import BaseModel
from app.schemas.user import UserResponse

# NOTE: UserSignup and UserLogin have been removed to avoid duplication.
# Import them from app.schemas.user instead.

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse  # Added to return user info along with the token