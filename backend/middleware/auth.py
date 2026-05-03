import logging
import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from supabase import create_client

logger = logging.getLogger("prepq.auth")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

SKIP_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
}

supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

async def verify_supabase_token(token: str):
    try:
        client = create_client(supabase_url, supabase_key)
        user = client.auth.get_user(token)
        return user.user
    except Exception as e:
        logger.warning(f"Supabase JWT verification failed: {e}")
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Extracts and verifies the Bearer JWT from the Authorization header.
    Injects `user_id` and `user_email` into request.state for downstream use.
    Skips verification for public paths.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if request.method == "OPTIONS":
            return await call_next(request)

        if path in SKIP_PATHS:
            return await call_next(request)

        # ── Development bypass ──────────────────────────
        # Skip JWT when running locally so the app works
        # without Supabase auth configured.
        if ENVIRONMENT == "development":
            request.state.user_id = "dev-user-local"
            request.state.user_email = "dev@localhost"
            request.state.jwt_payload = {}
            return await call_next(request)
        # ────────────────────────────────────────────────

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header.", "code": 401},
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                }
            )

        token = auth_header.removeprefix("Bearer ").strip()

        user = await verify_supabase_token(token)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired token.", "code": 401},
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                }
            )

        request.state.user_id = user.id
        request.state.user_email = getattr(user, "email", "")
        request.state.jwt_payload = {}

        return await call_next(request)


# ─────────────────────────────────────────────
# FastAPI Dependency (for route-level auth)
# ─────────────────────────────────────────────

async def require_auth(request: Request) -> str:
    """
    FastAPI dependency that returns the authenticated user_id.
    Use as: user_id: str = Depends(require_auth)
    The middleware already validated the token; this just extracts state.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_id
