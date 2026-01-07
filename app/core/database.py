from supabase import create_client, Client
from qdrant_client import QdrantClient
from langchain_voyageai import VoyageAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
import logging

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Global Placeholders ---
# These start as None and are populated by init_db_clients()
supabase: Client = None
llm_flash = None
llm_pro = None
retriever = None

def init_db_clients():
    """
    Initializes database and AI clients.
    Call this function on App Startup (in main.py), NOT at module level.
    """
    global supabase, llm_flash, llm_pro, retriever

    logger.info("🔌 Initializing Database & AI Clients...")

    # 1. Supabase Client
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        logger.info("✅ Supabase connected.")
    except Exception as e:
        logger.critical(f"❌ Failed to init Supabase: {e}")
        # Note: If Supabase is mandatory for auth, you might want to raise e here.

    # 2. Qdrant Client
    try:
        q_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        logger.info("✅ Qdrant connected.")
    except Exception as e:
        logger.error(f"❌ Failed to init Qdrant: {e}")
        q_client = None

    # 3. Embeddings (Voyage AI)
    try:
        # Pass API key explicitly instead of setting os.environ
        embeddings = VoyageAIEmbeddings(
            voyage_api_key=settings.VOYAGE_API_KEY, 
            model="voyage-3-large"
        )
        logger.info("✅ Embeddings initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to init Embeddings: {e}")
        embeddings = None

    # 4. Vector Store & Retriever
    if q_client and embeddings:
        try:
            vector_store = QdrantVectorStore(
                client=q_client, 
                collection_name="manual_pages", 
                embedding=embeddings
            )
            retriever = vector_store.as_retriever(search_kwargs={"k": 5})
            logger.info("✅ Retriever ready.")
        except Exception as e:
            logger.error(f"❌ Failed to init Vector Store: {e}")
            retriever = None
    else:
        logger.warning("⚠️ Skipping Retriever init (Missing Qdrant or Embeddings)")

    # 5. LLMs (Google Gemini)
    try:
        # Pass API key explicitly
        llm_flash = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            temperature=0, 
            google_api_key=settings.GOOGLE_API_KEY
        )
        llm_pro = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro", 
            temperature=0, 
            google_api_key=settings.GOOGLE_API_KEY
        )
        logger.info("✅ LLMs initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to init LLMs: {e}")
        llm_flash = None
        llm_pro = None