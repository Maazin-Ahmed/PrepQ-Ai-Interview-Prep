# ruff: noqa: E402
# ─────────────────────────────────────────────
# Load environment — MUST happen before any other
# imports that read os.environ at module level.
# ─────────────────────────────────────────────
import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve to absolute path so it works regardless of CWD
# or how the script is invoked (uvicorn, python3 main.py, etc.)
_THIS_DIR = Path(__file__).resolve().parent          # backend/
_ROOT_DIR = _THIS_DIR.parent                         # repo root/

# Try both locations, but backend/.env takes precedence
load_dotenv(dotenv_path=_ROOT_DIR / ".env", override=False)
load_dotenv(dotenv_path=_THIS_DIR / ".env", override=True)

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from middleware.auth import AuthMiddleware
from middleware.rate_limit import RateLimitMiddleware
from routers import chat, plan, mock

# ─────────────────────────────────────────────
# Logging configuration
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("prepq.main")


# ─────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PrepQ backend starting up...")
    environment = os.environ.get("ENVIRONMENT", "development")
    logger.info(f"Environment: {environment}")
    yield
    logger.info("PrepQ backend shutting down.")


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(
    title="PrepQ API",
    description="AI-powered interview preparation agent for Indian students and freshers.",
    version="1.0.0",
    docs_url="/docs" if os.environ.get("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.environ.get("ENVIRONMENT") != "production" else None,
    lifespan=lifespan,
)

# ─────────────────────────────────────────────
# CORS — locked to frontend domain + localhost
# ─────────────────────────────────────────────
_frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
_allowed_origins = list({
    _frontend_url,
    "http://localhost:3000",
    "http://localhost:3001",   # Next.js fallback port
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# ─────────────────────────────────────────────
# Middleware stack (order matters — innermost first)
# Auth → RateLimit → Route
# Note: SecurityMiddleware removed to prevent Starlette 
# streaming response conflicts with body reading.
# ─────────────────────────────────────────────
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)

# ─────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(plan.router, prefix="/plan", tags=["plan"])
app.include_router(mock.router, prefix="/mock", tags=["mock"])


# ─────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return JSONResponse(
        content={
            "status": "ok",
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "version": "1.0.0",
        }
    )


@app.get("/metrics", tags=["system"])
async def metrics():
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────
# Global exception handler
# ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error.", "code": 500},
    )


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("ENVIRONMENT") != "production",
        log_level="info",
    )
