import asyncio
import json
import logging
from typing import List, Optional, AsyncGenerator, Dict, Any, TypedDict
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Import Database
import app.core.database as db
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- State Definition ---
class GraphState(TypedDict):
    question: str
    thread_id: str
    chat_summary: str      
    chat_history_recent: str 
    retrieved_docs: List[Document]
    compressed_context: str

# --- Helper: Sync Groq Call for Nodes ---
def run_groq_sync(model: str, system: str, user: str) -> str:
    """Helper for non-streaming Groq calls inside Graph Nodes"""
    if not db.groq_client:
        logger.warning("⚠️ Groq Client not initialized")
        return ""
    try:
        completion = db.groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.1
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Groq Sync Error: {e}")
        return ""

# --- Graph Nodes ---

def simple_retrieval(state: GraphState) -> Dict[str, Any]:
    logger.info("🔍 [Node] Retrieval")
    if not db.retriever:
        return {"retrieved_docs": []}
    try:
        unique_docs = db.retriever.invoke(state["question"])
        seen = set()
        deduped = []
        for d in unique_docs:
            sig = hash(d.page_content) 
            if sig not in seen:
                seen.add(sig)
                deduped.append(d)
        return {"retrieved_docs": deduped}
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return {"retrieved_docs": []}

def batch_compress(state: GraphState) -> Dict[str, Any]:
    logger.info("⚖️ [Node] Compression")
    if not state["retrieved_docs"]:
        return {"compressed_context": "No relevant documents."}

    raw_context = "\n\n".join([d.page_content for d in state["retrieved_docs"][:3]])
    
    # Use Native Groq Call
    compressed = run_groq_sync(
        model=settings.MODEL_FAST,
        system="Extract relevant facts for the question.",
        user=f"Question: {state['question']}\n\nContext:\n{raw_context}"
    )
    
    return {"compressed_context": compressed if compressed else raw_context[:1000]}

def history_management(state: GraphState) -> Dict[str, Any]:
    logger.info("🗄️ [Node] History")
    
    current_summary = "No previous summary."
    if db.supabase:
        try:
            res = db.supabase.table("chats").select("summary").eq("id", state["thread_id"]).single().execute()
            if res.data: current_summary = res.data.get("summary") or "No previous summary."
        except: pass

    active_msgs = []
    if db.supabase:
        try:
            res = db.supabase.table("messages").select("*")\
                .eq("chat_id", state["thread_id"]).eq("is_summarized", False)\
                .order("created_at", desc=False).execute()
            active_msgs = res.data or []
        except: pass

    if len(active_msgs) > 10:
        msgs_to_summarize = active_msgs[:5]
        msgs_to_keep = active_msgs[5:]
        text_chunk = "\n".join([f"{m['role']}: {m['content']}" for m in msgs_to_summarize])
        
        # Use Native Groq Call
        new_summary = run_groq_sync(
            model=settings.MODEL_FAST,
            system="Update the summary with these new lines. Preserve key facts.",
            user=f"Current Summary:\n{current_summary}\n\nNew Lines:\n{text_chunk}"
        )

        if new_summary and db.supabase:
            current_summary = new_summary
            ids = [m['id'] for m in msgs_to_summarize]
            try:
                db.supabase.rpc("update_chat_summary_atomic", {
                    "p_chat_id": state["thread_id"],
                    "p_new_summary": current_summary,
                    "p_msg_ids": ids
                }).execute()
            except Exception as e:
                logger.error(f"RPC Error: {e}")

        formatted_recent = [f"{'Human' if m['role']=='user' else 'AI'}: {m['content']}" for m in msgs_to_keep]
    else:
        formatted_recent = [f"{'Human' if m['role']=='user' else 'AI'}: {m['content']}" for m in active_msgs]

    return {
        "chat_summary": current_summary,
        "chat_history_recent": "\n".join(formatted_recent)
    }

# --- Graph Setup ---
workflow = StateGraph(GraphState)
workflow.add_node("retrieve", simple_retrieval)
workflow.add_node("compress", batch_compress)
workflow.add_node("history", history_management)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "compress")
workflow.add_edge("compress", "history")
workflow.add_edge("history", END)
app_graph = workflow.compile(checkpointer=MemorySaver())

# --- Service Class ---
class ChatService:
    
    @staticmethod
    async def process_message_stream(user_id: str, message: str, thread_id: str = None) -> AsyncGenerator[str, None]:
        # CHECK: Must have Groq Client
        if not db.supabase or not db.groq_client:
            yield f"data: {json.dumps({'error': 'System unavailable'})}\n\n"
            return

        # 1. DB Init (Async Wrapper)
        try:
            if not thread_id:
                res = await asyncio.to_thread(
                    db.supabase.table("chats").insert({"user_id": user_id, "title": message[:30]}).execute
                )
                thread_id = res.data[0]["id"]
            
            await asyncio.to_thread(
                db.supabase.table("messages").insert({"chat_id": thread_id, "role": "user", "content": message}).execute
            )
        except Exception:
            yield f"data: {json.dumps({'error': 'DB Error'})}\n\n"
            return

        # 2. Pipeline (Async Wrapper)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await asyncio.to_thread(app_graph.invoke, {"question": message, "thread_id": thread_id}, config)
        except Exception as e:
            logger.error(f"Graph Error: {e}")
            state = {"chat_summary": "", "chat_history_recent": "", "compressed_context": ""}

        # 3. Native Groq Streaming
        system_instruction = (
            "You are a helpful AI assistant.\n"
            "Use the provided Long-Term Summary, Recent History, and Context."
        )
        user_content = (
            f"Summary: {state.get('chat_summary')}\nHistory: {state.get('chat_history_recent')}\n"
            f"Context: {state.get('compressed_context')}\nQuestion: {message}"
        )

        full_response = ""
        try:
            # Native Stream Call (Wrapped in thread because .create() is blocking by default, 
            # but we can iterate the generator in the thread or use stream=True)
            
            # NOTE: Groq's python client stream=True returns a sync generator.
            # To make it truly async-friendly in FastAPI, we can iterate it.
            
            stream = await asyncio.to_thread(
                db.groq_client.chat.completions.create,
                model=settings.MODEL_PRO,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content, 'thread_id': thread_id})}\n\n"
                    # Small sleep to allow event loop to breathe if needed
                    await asyncio.sleep(0)

        except Exception as e:
            logger.critical(f"Streaming Error: {e}")
            yield f"data: {json.dumps({'error': 'AI Error'})}\n\n"
            
        finally:
            if full_response:
                try:
                    await asyncio.to_thread(
                        db.supabase.table("messages").insert({
                            "chat_id": thread_id, "role": "assistant", "content": full_response
                        }).execute
                    )
                except: pass
            yield "data: [DONE]\n\n"

    @staticmethod
    async def edit_message_stream(user_id: str, message_id: str, new_content: str) -> AsyncGenerator[str, None]:
        # Re-implemented to use native Groq
        if not db.supabase or not db.groq_client:
            yield f"data: {json.dumps({'error': 'System unavailable'})}\n\n"
            return
            
        # 1. Fetch & Verify
        try:
            msg_res = await asyncio.to_thread(
                db.supabase.table("messages").select("*").eq("id", message_id).single().execute
            )
            if not msg_res.data:
                yield f"data: {json.dumps({'error': 'Message not found'})}\n\n"
                return
            
            original_msg = msg_res.data
            thread_id = original_msg['chat_id']
            created_at = original_msg['created_at']
            
            # 2. Rewind
            future_msgs = await asyncio.to_thread(
                db.supabase.table("messages").select("id").eq("chat_id", thread_id).gt("created_at", created_at).execute
            )
            ids_to_delete = [m['id'] for m in future_msgs.data]
            if ids_to_delete:
                await asyncio.to_thread(db.supabase.table("messages").delete().in_("id", ids_to_delete).execute)

            # Update & Reset
            await asyncio.to_thread(
                db.supabase.table("messages").update({"content": new_content, "is_summarized": False}).eq("id", message_id).execute
            )
            await asyncio.to_thread(
                db.supabase.table("chats").update({"summary": ""}).eq("id", thread_id).execute
            )
            
        except Exception:
            yield f"data: {json.dumps({'error': 'Edit failed'})}\n\n"
            return

        # 3. Regenerate (Same logic as process_message_stream)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await asyncio.to_thread(app_graph.invoke, {"question": new_content, "thread_id": thread_id}, config)
        except:
             state = {"chat_summary": "", "chat_history_recent": "", "compressed_context": ""}

        system_instruction = "You are a helpful AI assistant."
        user_content = (
            f"Summary: {state.get('chat_summary')}\nHistory: {state.get('chat_history_recent')}\n"
            f"Context: {state.get('compressed_context')}\nQuestion: {new_content}"
        )

        full_response = ""
        try:
            stream = await asyncio.to_thread(
                db.groq_client.chat.completions.create,
                model=settings.MODEL_PRO,
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": user_content}],
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content, 'thread_id': thread_id})}\n\n"
                    await asyncio.sleep(0)
        except Exception:
             yield f"data: {json.dumps({'error': 'AI Error'})}\n\n"

        if full_response:
             try:
                await asyncio.to_thread(
                    db.supabase.table("messages").insert({
                        "chat_id": thread_id, "role": "assistant", "content": full_response
                    }).execute
                )
             except: pass
        yield "data: [DONE]\n\n"

    # --- Frontend APIs ---

    @staticmethod
    async def get_user_chats(user_id: str) -> List[dict]:
        try:
            if not db.supabase: return []
            res = await asyncio.to_thread(
                db.supabase.table("chats").select("id, title, created_at")\
                    .eq("user_id", user_id).order("created_at", desc=True).execute
            )
            return res.data or []
        except: return []

    @staticmethod
    async def get_chat_history(user_id: str, thread_id: str) -> Optional[List[dict]]:
        try:
            if not db.supabase: return []
            res = await asyncio.to_thread(
                db.supabase.table("messages").select("*")\
                    .eq("chat_id", thread_id).order("created_at", desc=False).execute
            )
            return res.data or []
        except: return []

    @staticmethod
    async def delete_chat(user_id: str, thread_id: str) -> bool:
        """
        Deletes a chat and returns True if successful.
        Uses count='exact' to verify deletion even if no data is returned.
        """
        try:
            if not db.supabase: return False
            
            # ✅ UPDATED: Added count='exact'
            res = await asyncio.to_thread(
                db.supabase.table("chats")
                .delete(count="exact")
                .eq("id", thread_id)
                .eq("user_id", user_id)
                .execute
            )
            
            # ✅ UPDATED: Check count instead of data
            if res.count is not None and res.count > 0:
                return True
            
            return False
        except Exception as e: 
            logger.error(f"Delete Chat Error: {e}")
            return False

    @staticmethod
    async def rename_chat(user_id: str, thread_id: str, new_title: str) -> Optional[dict]:
        """
        Renames a chat and returns the updated chat object.
        """
        try:
            if not db.supabase: return None
            
            # 1. Update (✅ Removed .select() to fix AttributeError)
            res = await asyncio.to_thread(
                db.supabase.table("chats")
                .update({"title": new_title})
                .eq("id", thread_id)
                .eq("user_id", user_id)
                .execute
            )
            
            # 2. If data is returned immediately (Best Case)
            if res.data and len(res.data) > 0:
                return res.data[0]
            
            # 3. Fallback: If update succeeded but returned no data (Fixes 404 error)
            # We explicitly fetch the row to ensure we return a valid object
            refresh = await asyncio.to_thread(
                 db.supabase.table("chats")
                 .select("id, title, created_at")
                 .eq("id", thread_id)
                 .eq("user_id", user_id)
                 .execute
            )
            
            return refresh.data[0] if refresh.data else None

        except Exception as e: 
            logger.error(f"Rename Chat Error: {e}")
            return None