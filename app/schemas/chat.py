from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

# --- Request Models ---
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None 

class ChatRenameRequest(BaseModel):
    title: str

# --- Response Models ---
class ChatSessionResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime

class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime

class ChatResponse(BaseModel):
    response: str
    thread_id: str

class EditMessageRequest(BaseModel):
    message_id: str
    new_content: str