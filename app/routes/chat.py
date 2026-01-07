from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from typing import List

from app.core.security import get_current_user
from app.schemas.chat import (
    ChatRequest, 
    EditMessageRequest, 
    ChatSessionResponse, 
    MessageResponse
)
from app.services.chat_service import ChatService

router = APIRouter()

# --- Streaming Endpoints ---

@router.post("/message/stream")
async def stream_message(
    request: ChatRequest, 
    current_user = Depends(get_current_user)
):
    """
    Primary Chat Endpoint.
    Streams the AI response using Server-Sent Events (SSE).
    """
    # Note: process_message_stream is an async generator.
    # StreamingResponse iterates over it asynchronously.
    return StreamingResponse(
        ChatService.process_message_stream(
            user_id=current_user.id,
            message=request.message,
            thread_id=request.thread_id
        ),
        media_type="text/event-stream"
    )

@router.post("/message/edit")
async def edit_message(
    request: EditMessageRequest, 
    current_user = Depends(get_current_user)
):
    """
    Edit & Regenerate.
    Rewinds history to the edited message and streams a new response.
    """
    return StreamingResponse(
        ChatService.edit_message_stream(
            user_id=current_user.id,
            message_id=request.message_id,
            new_content=request.new_content
        ),
        media_type="text/event-stream"
    )

# --- History Management Endpoints ---

@router.get("/history", response_model=List[ChatSessionResponse])
async def get_chats(current_user = Depends(get_current_user)):
    """
    Sidebar: Get list of all user chats.
    """
    # MUST use await now, as the service is async
    chats = await ChatService.get_user_chats(current_user.id)
    return chats

@router.get("/history/{thread_id}", response_model=List[MessageResponse])
async def get_chat_detail(
    thread_id: str, 
    current_user = Depends(get_current_user)
):
    """
    Chat Window: Get full message history for a specific chat.
    """
    history = await ChatService.get_chat_history(current_user.id, thread_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return history

@router.delete("/history/{thread_id}")
async def delete_chat(
    thread_id: str, 
    current_user = Depends(get_current_user)
):
    """
    Delete a chat session.
    """
    success = await ChatService.delete_chat(current_user.id, thread_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found or could not be deleted")
    return {"status": "deleted", "id": thread_id}

@router.patch("/history/{thread_id}")
async def rename_chat(
    thread_id: str, 
    title: str = Body(..., embed=True), # Expects JSON: { "title": "New Name" }
    current_user = Depends(get_current_user)
):
    """
    Rename a chat session.
    """
    chat = await ChatService.rename_chat(current_user.id, thread_id, title)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat