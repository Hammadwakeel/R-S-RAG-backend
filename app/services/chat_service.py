import asyncio
import json
import logging
from typing import List, Optional, AsyncGenerator, Dict, Any, TypedDict
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Import Lazy-Loaded Clients
import app.core.database as db
from app.core.config import settings

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- State Definition ---
class GraphState(TypedDict):
    question: str
    thread_id: str
    chat_summary: str      
    chat_history_recent: str 
    retrieved_docs: List[Document]
    compressed_context: str

# --- Graph Nodes ---
# Note: These run synchronously within the LangGraph execution.
# We wrap the entire graph execution in a thread later to avoid blocking the API.

def simple_retrieval(state: GraphState) -> Dict[str, Any]:
    logger.info("🔍 [Node] Retrieval")
    if not db.retriever:
        logger.warning("⚠️ Retriever not initialized.")
        return {"retrieved_docs": []}
        
    try:
        unique_docs = db.retriever.invoke(state["question"])
        # Simple deduplication
        seen = set()
        deduped = []
        for d in unique_docs:
            sig = hash(d.page_content[:100])
            if sig not in seen:
                seen.add(sig)
                deduped.append(d)
        return {"retrieved_docs": deduped}
    except Exception as e:
        logger.error(f"❌ Retrieval failed: {e}")
        return {"retrieved_docs": []}

def batch_compress(state: GraphState) -> Dict[str, Any]:
    logger.info("⚖️ [Node] Compression")
    if not state["retrieved_docs"]:
        return {"compressed_context": "No relevant documents."}

    raw_context = "\n\n".join([d.page_content for d in state["retrieved_docs"][:3]])
    
    # If no LLM available, return raw text
    if not db.llm_flash:
        return {"compressed_context": raw_context[:1000]}

    try:
        # Using the Flash model for fast summarization
        msg = db.llm_flash.invoke(
            f"Extract relevant facts for the question: '{state['question']}'\n\nContext:\n{raw_context}"
        )
        return {"compressed_context": msg.content}
    except Exception as e:
        logger.warning(f"⚠️ Compression failed, using raw context: {e}")
        return {"compressed_context": raw_context[:1000]}

def history_management(state: GraphState) -> Dict[str, Any]:
    logger.info("🗄️ [Node] History: Managing rolling window...")
    
    # 1. Fetch Summary & Messages
    # Note: We access db.supabase directly here. Since this runs inside the 
    # thread-wrapped graph, it won't block the main event loop.
    try:
        if db.supabase:
            chat_res = db.supabase.table("chats").select("summary").eq("id", state["thread_id"]).single().execute()
            current_summary = chat_res.data.get("summary") or "No previous summary."
        else:
            current_summary = "DB Unavailable"
    except Exception:
        current_summary = "No previous summary."

    try:
        active_msgs = []
        if db.supabase:
            res = db.supabase.table("messages").select("*")\
                .eq("chat_id", state["thread_id"])\
                .eq("is_summarized", False)\
                .order("created_at", desc=False)\
                .execute()
            active_msgs = res.data or []
    except Exception as e:
        logger.error(f"❌ Failed to fetch messages: {e}")
        return {"chat_summary": current_summary, "chat_history_recent": ""}

    # 3. Check for Overflow
    THRESHOLD = 10
    
    if len(active_msgs) > THRESHOLD:
        logger.info("🧹 History overflow. Updating summary...")
        msgs_to_summarize = active_msgs[:5]
        msgs_to_keep = active_msgs[5:]
        
        text_chunk = "\n".join([f"{m['role']}: {m['content']}" for m in msgs_to_summarize])
        
        # Update Summary
        if db.llm_flash:
            try:
                new_sum_msg = db.llm_flash.invoke(
                    f"Update the summary with these new lines. Preserve key facts.\n\nCurrent Summary:\n{current_summary}\n\nNew Lines:\n{text_chunk}"
                )
                current_summary = new_sum_msg.content
                
                # Update DB
                if db.supabase:
                    db.supabase.table("chats").update({"summary": current_summary}).eq("id", state["thread_id"]).execute()
                    ids = [m['id'] for m in msgs_to_summarize]
                    db.supabase.table("messages").update({"is_summarized": True}).in_("id", ids).execute()
            except Exception as e:
                logger.error(f"❌ Summary update failed: {e}")

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
        logger.info(f"🚀 Streaming message for User {user_id}")
        
        if not db.supabase:
            yield f"data: {json.dumps({'error': 'Database unavailable'})}\n\n"
            return

        # 1. Create/Get Thread (Async Wrapper)
        try:
            if not thread_id:
                # Run blocking DB call in thread
                res = await asyncio.to_thread(
                    db.supabase.table("chats").insert({"user_id": user_id, "title": message[:30]}).execute
                )
                thread_id = res.data[0]["id"]
            
            # Log User Message
            await asyncio.to_thread(
                db.supabase.table("messages").insert({
                    "chat_id": thread_id, "role": "user", "content": message
                }).execute
            )
        except Exception as e:
            logger.error(f"❌ DB Init Error: {e}")
            yield f"data: {json.dumps({'error': 'Failed to save message'})}\n\n"
            return

        # 2. Run Context Pipeline (Async Wrapper)
        # We run the whole LangGraph in a thread so its blocking retrieval doesn't freeze FastAPI
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"question": message, "thread_id": thread_id}
        
        try:
            # Running the graph in a separate thread
            state = await asyncio.to_thread(app_graph.invoke, inputs, config)
        except Exception as e:
            logger.error(f"❌ Context Pipeline Failed: {e}")
            state = {
                "chat_summary": "", 
                "chat_history_recent": "", 
                "compressed_context": "Context unavailable due to error."
            }

        # 3. Stream Generation
        if not db.llm_pro:
            yield f"data: {json.dumps({'error': 'AI Model unavailable'})}\n\n"
            return

        system_instruction = (
            "You are a helpful AI assistant. Answer clearly and concisely.\n"
            "Use the provided Long-Term Summary for past context.\n"
            "Use the Recent History for immediate conversation flow.\n"
            "Use the Context for factual knowledge."
        )
        
        user_content = (
            f"Long-Term Summary:\n{state.get('chat_summary', '')}\n\n"
            f"Recent History:\n{state.get('chat_history_recent', '')}\n\n"
            f"Context:\n{state.get('compressed_context', '')}\n\n"
            f"Question: {message}\n"
            "Answer:"
        )

        full_response = ""
        try:
            # Use LangChain's astream for true async streaming (works for Groq, Gemini, OpenAI)
            async for chunk in db.llm_pro.astream([
                ("system", system_instruction),
                ("human", user_content)
            ]):
                content = chunk.content
                if content:
                    full_response += content
                    payload = json.dumps({"content": content, "thread_id": thread_id})
                    yield f"data: {payload}\n\n"
        except Exception as e:
            logger.error(f"🔥 Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        finally:
            # 4. Save Response (Async Wrapper)
            if full_response:
                try:
                    await asyncio.to_thread(
                        db.supabase.table("messages").insert({
                            "chat_id": thread_id, "role": "assistant", "content": full_response
                        }).execute
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to save response: {e}")
            
            yield "data: [DONE]\n\n"

    @staticmethod
    async def edit_message_stream(user_id: str, message_id: str, new_content: str) -> AsyncGenerator[str, None]:
        logger.info(f"✏️ User {user_id} editing message {message_id}")
        
        if not db.supabase:
            yield f"data: {json.dumps({'error': 'Database unavailable'})}\n\n"
            return

        # 1. Fetch Target Message
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
            
            # Check Ownership
            chat_check = await asyncio.to_thread(
                db.supabase.table("chats").select("id").eq("id", thread_id).eq("user_id", user_id).execute
            )
            if not chat_check.data:
                yield f"data: {json.dumps({'error': 'Access denied'})}\n\n"
                return

        except Exception as e:
            logger.error(f"❌ DB Fetch Error: {e}")
            yield f"data: {json.dumps({'error': 'Database error'})}\n\n"
            return

        # 2. Robust Rewind (Delete Future Messages)
        try:
            logger.info(f"🔍 Finding messages after {created_at}...")
            future_msgs = await asyncio.to_thread(
                db.supabase.table("messages").select("id").eq("chat_id", thread_id).gt("created_at", created_at).execute
            )
            
            ids_to_delete = [m['id'] for m in future_msgs.data]
            
            if ids_to_delete:
                logger.info(f"🗑️ Deleting {len(ids_to_delete)} future messages...")
                await asyncio.to_thread(
                    db.supabase.table("messages").delete().in_("id", ids_to_delete).execute
                )

            # 3. Update Content & Reset Summary
            await asyncio.to_thread(
                db.supabase.table("messages").update({
                    "content": new_content,
                    "is_summarized": False 
                }).eq("id", message_id).execute
            )
            
            # Clear summary
            await asyncio.to_thread(
                db.supabase.table("chats").update({"summary": ""}).eq("id", thread_id).execute
            )
            
        except Exception as e:
            logger.error(f"❌ DB Update Error: {e}")
            yield f"data: {json.dumps({'error': 'Failed to update history'})}\n\n"
            return

        # 4. Re-run Pipeline (Logic copied from process_message_stream for regeneration)
        # We can reuse the graph logic here.
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"question": new_content, "thread_id": thread_id}
        
        try:
            state = await asyncio.to_thread(app_graph.invoke, inputs, config)
            
            system_instruction = (
                "You are a helpful AI assistant. Answer clearly and concisely.\n"
                "Use the provided Long-Term Summary for past context.\n"
                "Use the Recent History for immediate conversation flow.\n"
                "Use the Context for factual knowledge."
            )
            
            user_content = (
                f"Long-Term Summary:\n{state.get('chat_summary', '')}\n\n"
                f"Recent History:\n{state.get('chat_history_recent', '')}\n\n"
                f"Context:\n{state.get('compressed_context', '')}\n\n"
                f"Question: {new_content}\n"
                "Answer:"
            )

            if db.llm_pro:
                full_response = ""
                async for chunk in db.llm_pro.astream([
                    ("system", system_instruction),
                    ("human", user_content)
                ]):
                    content = chunk.content
                    if content:
                        full_response += content
                        payload = json.dumps({"content": content, "thread_id": thread_id})
                        yield f"data: {payload}\n\n"

                # Save new response
                if full_response:
                    try:
                        await asyncio.to_thread(
                            db.supabase.table("messages").insert({
                                "chat_id": thread_id, "role": "assistant", "content": full_response
                            }).execute
                        )
                    except: pass

        except Exception as e:
            logger.critical(f"🔥 Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        yield "data: [DONE]\n\n"

    # --- Frontend APIs (Wrapped) ---

    @staticmethod
    async def get_user_chats(user_id: str) -> List[dict]:
        try:
            if not db.supabase: return []
            res = await asyncio.to_thread(
                db.supabase.table("chats").select("id, title, created_at")\
                    .eq("user_id", user_id)\
                    .order("created_at", desc=True)\
                    .execute
            )
            return res.data or []
        except: return []

    @staticmethod
    async def get_chat_history(user_id: str, thread_id: str) -> Optional[List[dict]]:
        try:
            if not db.supabase: return []
            chat_check = await asyncio.to_thread(
                db.supabase.table("chats").select("id").eq("id", thread_id).eq("user_id", user_id).execute
            )
            if not chat_check.data: return None

            res = await asyncio.to_thread(
                db.supabase.table("messages").select("*")\
                    .eq("chat_id", thread_id)\
                    .order("created_at", desc=False)\
                    .execute
            )
            return res.data or []
        except: return []

    @staticmethod
    async def delete_chat(user_id: str, thread_id: str) -> bool:
        try:
            if not db.supabase: return False
            res = await asyncio.to_thread(
                db.supabase.table("chats").delete().eq("id", thread_id).eq("user_id", user_id).execute
            )
            return len(res.data) > 0
        except: return False

    @staticmethod
    async def rename_chat(user_id: str, thread_id: str, new_title: str) -> Optional[dict]:
        try:
            if not db.supabase: return None
            res = await asyncio.to_thread(
                db.supabase.table("chats").update({"title": new_title})\
                    .eq("id", thread_id).eq("user_id", user_id)\
                    .execute
            )
            return res.data[0] if res.data else None
        except: return None