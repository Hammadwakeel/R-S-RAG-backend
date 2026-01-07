import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db_clients
from app.routes import auth, users, chat

# --- 1. Setup Logging ---
# It's better to rely on Uvicorn's loggers in production, 
# but this ensures we see our app logs during dev.
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
    Execute logic on startup and shutdown.
    Ref: https://fastapi.tiangolo.com/advanced/events/
    """
    # STARTUP: Initialize Database & AI Clients safely
    init_db_clients()
    
    yield
    
    # SHUTDOWN: (Optional) Close connections here if needed
    logger.info("🛑 Shutting down application...")

# --- 3. App Definition ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    # Disable auto-docs in production if needed
    # docs_url=None if settings.ENV_MODE == "production" else "/docs"
)

# --- 4. Secure CORS ---
# Only allow origins defined in .env (e.g., http://localhost:3000)
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- 5. Include Routers ---
# Group all endpoints under /api/v1
api_router = FastAPI()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])

app.mount(settings.API_V1_STR, api_router)

@app.get("/health")
def health_check():
    """Simple health check for load balancers"""
    return {"status": "ok", "app": settings.PROJECT_NAME}

if __name__ == "__main__":
    import uvicorn
    # Use config settings for host/port if available, else default
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)