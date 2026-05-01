import re
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("prepq.security")

# ─────────────────────────────────────────────
# Injection / Abuse Patterns
# ─────────────────────────────────────────────

PROMPT_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|context)", re.IGNORECASE),
    re.compile(r"(system\s*prompt|system\s*message)", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|prior|previous)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a\s+)", re.IGNORECASE),
    re.compile(r"(DAN|do anything now)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(your\s+)?(instructions?|rules?|guidelines?)", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+(are|have\s+no)", re.IGNORECASE),
]

XSS_PATTERNS: list[re.Pattern] = [
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=\s*[\"']", re.IGNORECASE),
    re.compile(r"<\s*iframe", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+onerror", re.IGNORECASE),
    re.compile(r"data\s*:\s*text/html", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
]

SQL_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE),
    re.compile(r"\bUNION\s+(ALL\s+)?SELECT\b", re.IGNORECASE),
    re.compile(r"\bSELECT\s+\*\s+FROM\b", re.IGNORECASE),
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER)\b", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
    re.compile(r"'\s*OR\s+'?\d", re.IGNORECASE),
    re.compile(r"\bEXEC\s*\(", re.IGNORECASE),
    re.compile(r"\bxp_cmdshell\b", re.IGNORECASE),
]

ALL_PATTERNS = [
    ("prompt_injection", PROMPT_INJECTION_PATTERNS),
    ("xss", XSS_PATTERNS),
    ("sql_injection", SQL_INJECTION_PATTERNS),
]

# Endpoints that accept raw body (to scan)
SCAN_METHODS = {"POST", "PUT", "PATCH"}


def _detect_violation(text: str) -> tuple[bool, str]:
    """
    Scans text for all malicious patterns.
    Returns (is_violation, violation_type).
    """
    for violation_type, patterns in ALL_PATTERNS:
        for pattern in patterns:
            if pattern.search(text):
                return True, violation_type
    return False, ""


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, skip_paths: list[str] | None = None):
        super().__init__(app)
        self.skip_paths = skip_paths or ["/health", "/docs", "/openapi.json", "/redoc"]

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.skip_paths:
            return await call_next(request)

        if request.method in SCAN_METHODS:
            try:
                body_bytes = await request.body()
                body_text = body_bytes.decode("utf-8", errors="replace")

                is_violation, violation_type = _detect_violation(body_text)

                if is_violation:
                    user_id = getattr(request.state, "user_id", "anonymous")
                    logger.warning(
                        "Security violation detected",
                        extra={
                            "violation_type": violation_type,
                            "user_id": user_id,
                            "path": request.url.path,
                            "ip": request.client.host if request.client else "unknown",
                        },
                    )
                    return JSONResponse(
                        status_code=400,
                        content={"error": "Invalid input detected.", "code": 400},
                    )

                # Re-inject body so downstream handlers can read it
                async def receive():
                    return {"type": "http.request", "body": body_bytes}

                request._receive = receive  # noqa: SLF001

            except Exception:
                # Don't crash on body read errors — let the route handle it
                pass

        # Scan query params
        for key, value in request.query_params.items():
            is_violation, violation_type = _detect_violation(f"{key}={value}")
            if is_violation:
                user_id = getattr(request.state, "user_id", "anonymous")
                logger.warning(
                    "Security violation in query params",
                    extra={
                        "violation_type": violation_type,
                        "user_id": user_id,
                        "path": request.url.path,
                    },
                )
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid input detected.", "code": 400},
                )

        return await call_next(request)
