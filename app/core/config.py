from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    VOYAGE_API_KEY: str
    GOOGLE_API_KEY: str
    GROQ_API_KEY: str
    
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "RAG AI Backend"

    class Config:
        env_file = ".env"

settings = Settings()