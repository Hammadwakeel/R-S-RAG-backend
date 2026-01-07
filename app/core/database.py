import os
from supabase import create_client, Client
from qdrant_client import QdrantClient
from langchain_voyageai import VoyageAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

# 1. Supabase Client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# 2. AI Models (Initialized globally for reuse)
os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY
os.environ["VOYAGE_API_KEY"] = settings.VOYAGE_API_KEY

llm_flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
llm_pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0)

embeddings = VoyageAIEmbeddings(model="voyage-3-large")

# 3. Vector Store Client
q_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

vector_store = QdrantVectorStore(
    client=q_client, 
    collection_name="manual_pages", 
    embedding=embeddings
)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})