import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db_clients
from app.routes import auth, users, chat

# --- 1. Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- 2. Lifespan (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executes on Startup.
    This ensures DB clients are ready BEFORE requests come in.
    """
    # 1. Initialize DB & AI Clients
    init_db_clients()
    
    yield
    
    # 2. Shutdown logic
    logger.info("🛑 Shutting down...")

# --- 3. App Definition ---
# Create the app ONCE with the lifespan handler
app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan 
)

# --- 4. Secure CORS ---
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins= '*',#[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- 5. Include Routers ---
# We use a separate Router for API v1 to group everything
from fastapi import APIRouter
api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])

# Mount the API router under /api/v1
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)