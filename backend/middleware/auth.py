import logging
import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from jose import JWTError, jwt

logger = logging.getLogger("prepq.auth")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

SKIP_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
}

ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set.")
    return secret


def verify_jwt(token: str) -> dict:
    """
    Verifies a Supabase-issued JWT.
    Returns the decoded payload dict on success.
    Raises HTTPException 401 on any failure.
    """
    secret = _get_jwt_secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"verify_aud": False},  # Supabase sets audience to 'authenticated'
        )
        return payload
    except JWTError as exc:
        logger.warning(f"JWT verification failed: {exc}")
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


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
            )

        token = auth_header.removeprefix("Bearer ").strip()

        try:
            payload = verify_jwt(token)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail, "code": exc.status_code},
            )

        # Supabase JWT payload structure: {"sub": "<user_uuid>", "email": "...", ...}
        user_id = payload.get("sub")
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={"error": "Token missing user identifier.", "code": 401},
            )

        request.state.user_id = user_id
        request.state.user_email = payload.get("email", "")
        request.state.jwt_payload = payload

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
