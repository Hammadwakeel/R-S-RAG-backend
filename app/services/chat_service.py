import logging
import json
from typing import List, TypedDict, Optional, AsyncGenerator
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from groq import Groq
from app.core.config import settings

# Import Database & Tools
from app.core.database import supabase, retriever


# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Groq Client ---
# Note: In production, move API Key to .env
GROQ_API_KEY = settings.GROQ_API_KEY
client = Groq(api_key=GROQ_API_KEY)

# --- State Definition ---
class GraphState(TypedDict):
    question: str
    thread_id: str
    chat_summary: str      
    chat_history_recent: str 
    retrieved_docs: List[Document]
    compressed_context: str
    generation: str

# --- Helper: Groq API Wrapper ---
def call_groq(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.5):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_completion_tokens=4096, 
            top_p=1,
            stream=False 
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Groq API Error ({model}): {e}")
        return None

# --- Graph Nodes ---

def simple_retrieval(state: GraphState):
    logger.info("🔍 [Node] Retrieval")
    try:
        unique_docs = retriever.invoke(state["question"])
        # Simple deduplication
        seen = set()
        deduped = []
        for d in unique_docs:
            sig = hash(d.page_content[:100])
            if sig not in seen:
                seen.add(sig)
                deduped.append(d)
        return {"retrieved_docs": deduped}
    except:
        return {"retrieved_docs": []}

def batch_compress(state: GraphState):
    logger.info("⚖️ [Node] Compression")
    if not state["retrieved_docs"]:
        return {"compressed_context": "No relevant documents."}

    raw_context = "\n\n".join([d.page_content for d in state["retrieved_docs"][:3]])
    
    # Use Fast Llama model for compression
    compressed = call_groq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        system_prompt="Extract relevant sentences only.",
        user_prompt=f"Question: {state['question']}\nContext:\n{raw_context}",
        temperature=0.1
    )
    
    return {"compressed_context": compressed if compressed else raw_context[:1000]}

def history_management(state: GraphState):
    """
    SMART HISTORY:
    1. Reads Current Summary.
    2. Reads ONLY 'Unsummarized' messages.
    3. If > 10 unsummarized messages:
       - Takes the oldest 5.
       - Compresses them into the Summary.
       - Marks them as 'is_summarized=True' (BUT KEEPS THEM IN DB).
    """
    logger.info("🗄️ [Node] History: Managing rolling window...")
    
    # 1. Fetch Current Summary
    try:
        chat_res = supabase.table("chats").select("summary").eq("id", state["thread_id"]).single().execute()
        current_summary = chat_res.data.get("summary") or "No previous summary."
    except:
        current_summary = "No previous summary."

    # 2. Fetch UNSUMMARIZED Messages
    try:
        res = supabase.table("messages").select("*")\
            .eq("chat_id", state["thread_id"])\
            .eq("is_summarized", False)\
            .order("created_at", desc=False)\
            .execute() # Get oldest first
            
        active_msgs = res.data
    except Exception as e:
        logger.error(f"❌ Failed to fetch messages: {e}")
        return {"chat_summary": current_summary, "chat_history_recent": ""}

    # 3. Check for Overflow
    THRESHOLD = 10
    
    if len(active_msgs) > THRESHOLD:
        logger.info("🧹 History overflow. Updating summary...")
        
        # We summarize the oldest chunk, keep the newest chunk raw
        msgs_to_summarize = active_msgs[:5]  # Oldest 5
        msgs_to_keep = active_msgs[5:]       # Newest ones
        
        text_chunk = "\n".join([f"{m['role']}: {m['content']}" for m in msgs_to_summarize])
        
        # Update Summary
        new_summary = call_groq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            system_prompt="Update the summary with these new lines. Preserve key facts (numbers, names).",
            user_prompt=f"Current Summary:\n{current_summary}\n\nNew Lines:\n{text_chunk}",
            temperature=0.3
        )
        
        if new_summary:
            current_summary = new_summary
            # A. Update Chat Summary
            supabase.table("chats").update({"summary": current_summary}).eq("id", state["thread_id"]).execute()
            
            # B. Mark messages as summarized (DO NOT DELETE)
            ids_to_flag = [m['id'] for m in msgs_to_summarize]
            supabase.table("messages").update({"is_summarized": True}).in_("id", ids_to_flag).execute()
            
        formatted_recent = [f"{'Human' if m['role']=='user' else 'AI'}: {m['content']}" for m in msgs_to_keep]
        
    else:
        formatted_recent = [f"{'Human' if m['role']=='user' else 'AI'}: {m['content']}" for m in active_msgs]

    recent_str = "\n".join(formatted_recent)
    
    return {
        "chat_summary": current_summary,
        "chat_history_recent": recent_str
    }

# --- Graph Construction (Prep Phase) ---
# We use the graph to prepare context, but generation happens in the stream.
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
        
        # 1. Create Thread
        if not thread_id:
            res = supabase.table("chats").insert({"user_id": user_id, "title": message[:30]}).execute()
            thread_id = res.data[0]["id"]

        # 2. Log User Message
        try:
            supabase.table("messages").insert({
                "chat_id": thread_id, 
                "role": "user", 
                "content": message
            }).execute()
        except: pass

        # 3. Run Pipeline (Context Preparation)
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"question": message, "thread_id": thread_id}
        
        try:
            state = app_graph.invoke(inputs, config=config)
            
            # 4. Construct Prompt (Text Only)
            system_instruction = (
                "You are a helpful AI assistant. Answer clearly and concisely.\n"
                "Use the provided Long-Term Summary for past context.\n"
                "Use the Recent History for immediate conversation flow.\n"
                "Use the Context for factual knowledge."
            )
            
            user_content = (
                f"Long-Term Summary:\n{state['chat_summary']}\n\n"
                f"Recent History:\n{state['chat_history_recent']}\n\n"
                f"Context:\n{state['compressed_context']}\n\n"
                f"Question: {message}\n"
                "Answer:"
            )

            # 5. Start Streaming
            stream = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                max_completion_tokens=4096,
                top_p=1,
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    payload = json.dumps({"content": content, "thread_id": thread_id})
                    yield f"data: {payload}\n\n"
                    
        except Exception as e:
            logger.critical(f"🔥 Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        finally:
            # 6. Stop Logic / Save Partial Response
            if full_response:
                try:
                    supabase.table("messages").insert({
                        "chat_id": thread_id, 
                        "role": "assistant", 
                        "content": full_response
                    }).execute()
                except: pass
            
            yield "data: [DONE]\n\n"

    @staticmethod
    async def edit_message_stream(user_id: str, message_id: str, new_content: str) -> AsyncGenerator[str, None]:
        logger.info(f"✏️ User {user_id} editing message {message_id}")
        
        # 1. Fetch Target Message
        try:
            msg_res = supabase.table("messages").select("*").eq("id", message_id).single().execute()
            if not msg_res.data:
                yield f"data: {json.dumps({'error': 'Message not found'})}\n\n"
                return
            
            original_msg = msg_res.data
            thread_id = original_msg['chat_id']
            created_at = original_msg['created_at']
            
            # Check Ownership
            chat_check = supabase.table("chats").select("id").eq("id", thread_id).eq("user_id", user_id).execute()
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
            future_msgs = supabase.table("messages")\
                .select("id")\
                .eq("chat_id", thread_id)\
                .gt("created_at", created_at)\
                .execute()
            
            ids_to_delete = [m['id'] for m in future_msgs.data]
            
            if ids_to_delete:
                logger.info(f"🗑️ Deleting {len(ids_to_delete)} future messages...")
                supabase.table("messages").delete().in_("id", ids_to_delete).execute()

            # 3. Update Content & Reset Summary
            supabase.table("messages").update({
                "content": new_content,
                "is_summarized": False 
            }).eq("id", message_id).execute()
            
            # Clear summary to rebuild context from fresh reality
            supabase.table("chats").update({"summary": ""}).eq("id", thread_id).execute()
            
        except Exception as e:
            logger.error(f"❌ DB Update Error: {e}")
            yield f"data: {json.dumps({'error': 'Failed to update history'})}\n\n"
            return

        # 4. Re-run Pipeline
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"question": new_content, "thread_id": thread_id}
        
        try:
            state = app_graph.invoke(inputs, config=config)
            
            system_instruction = (
                "You are a helpful AI assistant. Answer clearly and concisely.\n"
                "Use the provided Long-Term Summary for past context.\n"
                "Use the Recent History for immediate conversation flow.\n"
                "Use the Context for factual knowledge."
            )
            
            user_content = (
                f"Long-Term Summary:\n{state['chat_summary']}\n\n"
                f"Recent History:\n{state['chat_history_recent']}\n\n"
                f"Context:\n{state['compressed_context']}\n\n"
                f"Question: {new_content}\n"
                "Answer:"
            )

            stream = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                max_completion_tokens=4096,
                top_p=1,
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    payload = json.dumps({"content": content, "thread_id": thread_id})
                    yield f"data: {payload}\n\n"
                    
        except Exception as e:
            logger.critical(f"🔥 Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        finally:
            if full_response:
                try:
                    supabase.table("messages").insert({
                        "chat_id": thread_id, 
                        "role": "assistant", 
                        "content": full_response
                    }).execute()
                except: pass
            
            yield "data: [DONE]\n\n"

    # --- Frontend APIs ---

    @staticmethod
    def get_user_chats(user_id: str) -> List[dict]:
        """Sidebar: List all chats"""
        try:
            res = supabase.table("chats").select("id, title, created_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            return res.data
        except: return []

    @staticmethod
    def get_chat_history(user_id: str, thread_id: str) -> Optional[List[dict]]:
        """Chat Window: Get ALL messages."""
        try:
            chat_check = supabase.table("chats").select("id").eq("id", thread_id).eq("user_id", user_id).execute()
            if not chat_check.data: return None

            res = supabase.table("messages").select("*")\
                .eq("chat_id", thread_id)\
                .order("created_at", desc=False)\
                .execute()
            return res.data
        except: return []

    @staticmethod
    def delete_chat(user_id: str, thread_id: str) -> bool:
        try:
            res = supabase.table("chats").delete().eq("id", thread_id).eq("user_id", user_id).execute()
            return len(res.data) > 0
        except: return False

    @staticmethod
    def rename_chat(user_id: str, thread_id: str, new_title: str) -> Optional[dict]:
        try:
            res = supabase.table("chats").update({"title": new_title})\
                .eq("id", thread_id).eq("user_id", user_id)\
                .execute()
            return res.data[0] if res.data else None
        except: return None