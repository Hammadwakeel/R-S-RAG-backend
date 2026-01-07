from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "RAG AI Backend"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Vector DB
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # AI Keys
    GROQ_API_KEY: str
    VOYAGE_API_KEY: str
    GOOGLE_API_KEY: str = ""

    # Pydantic V2 Settings Config
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore" # Ignore extra env vars
    )

settings = Settings()