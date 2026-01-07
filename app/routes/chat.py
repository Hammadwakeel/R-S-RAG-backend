from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List
from app.schemas.chat import ChatRequest, EditMessageRequest, ChatSessionResponse, MessageResponse, ChatRenameRequest
from app.services.chat_service import ChatService
from app.core.security import get_current_user
from fastapi.responses import StreamingResponse # Import this

router = APIRouter()

@router.post("/message/stream")
async def send_message_stream(
    request: ChatRequest, 
    current_user = Depends(get_current_user)
):
    """
    Streaming Endpoint.
    Returns Server-Sent Events (SSE).
    """
    return StreamingResponse(
        ChatService.process_message_stream(
            user_id=current_user.id,
            message=request.message,
            thread_id=request.thread_id
        ),
        media_type="text/event-stream"
    )

# 2. Get All Chats (Sidebar)
@router.get("/history", response_model=List[ChatSessionResponse])
async def get_chats(current_user = Depends(get_current_user)):
    return ChatService.get_user_chats(current_user.id)

# 3. Get Specific Chat Messages (Main Window)
@router.get("/history/{thread_id}", response_model=List[MessageResponse])
async def get_chat_messages(
    thread_id: str = Path(..., title="The ID of the chat session"),
    current_user = Depends(get_current_user)
):
    messages = ChatService.get_chat_history(current_user.id, thread_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Chat not found or access denied")
    return messages

# 4. Delete Chat
@router.delete("/history/{thread_id}")
async def delete_chat(
    thread_id: str,
    current_user = Depends(get_current_user)
):
    success = ChatService.delete_chat(current_user.id, thread_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Chat deleted successfully"}

# 5. Rename Chat
@router.patch("/history/{thread_id}")
async def rename_chat(
    thread_id: str,
    request: ChatRenameRequest,
    current_user = Depends(get_current_user)
):
    result = ChatService.rename_chat(current_user.id, thread_id, request.title)
    if not result:
        raise HTTPException(status_code=404, detail="Chat not found")
    return result

@router.post("/message/edit")
async def edit_message(
    request: EditMessageRequest, 
    current_user = Depends(get_current_user)
):
    """
    Edits a message, deletes subsequent history, and streams a new response.
    """
    return StreamingResponse(
        ChatService.edit_message_stream(
            user_id=current_user.id,
            message_id=request.message_id,
            new_content=request.new_content
        ),
        media_type="text/event-stream"
    )