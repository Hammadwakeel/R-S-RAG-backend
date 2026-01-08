import logging
from supabase import create_client, Client
from qdrant_client import QdrantClient
from langchain_voyageai import VoyageAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from groq import Groq  # <--- Native Client
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Global Placeholders ---
supabase: Client = None
groq_client: Groq = None  # <--- Single Native Client
retriever = None

def init_db_clients():
    """
    Initializes Supabase, Qdrant, and the native Groq Client.
    """
    global supabase, groq_client, retriever

    logger.info("🔌 Initializing Database & AI Clients...")

    # 1. Supabase
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        logger.info("✅ Supabase connected.")
    except Exception as e:
        logger.critical(f"❌ Failed to init Supabase: {e}")

    # 2. Qdrant
    try:
        q_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        logger.info("✅ Qdrant connected.")
    except Exception as e:
        logger.error(f"❌ Failed to init Qdrant: {e}")
        q_client = None

    # 3. Embeddings (Voyage AI)
    try:
        embeddings = VoyageAIEmbeddings(
            voyage_api_key=settings.VOYAGE_API_KEY, 
            model=settings.EMBEDDING_MODEL
        )
        logger.info("✅ Embeddings initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to init Embeddings: {e}")
        embeddings = None

    # 4. Retriever (Vector Store)
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

    # 5. Groq Native Client
    try:
        groq_client = Groq(api_key=settings.GROQ_API_KEY)
        logger.info("✅ Native Groq Client initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to init Groq: {e}")
        groq_client = None