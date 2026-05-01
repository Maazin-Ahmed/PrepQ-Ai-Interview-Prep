import time
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from redis import asyncio as aioredis
import os

logger = logging.getLogger("prepq.rate_limit")

RATE_LIMIT_REQUESTS = 20      # max requests
RATE_LIMIT_WINDOW = 60        # per N seconds

# Endpoints subject to rate limiting (all protected routes)
RATE_LIMITED_PATHS = {"/chat", "/plan", "/mock"}
SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/metrics"}


def _get_redis_client() -> aioredis.Redis:
    url = os.environ.get("UPSTASH_REDIS_URL", "")
    token = os.environ.get("UPSTASH_REDIS_TOKEN", "")

    if not url:
        raise RuntimeError("UPSTASH_REDIS_URL is not set.")

    # Upstash Redis REST over TLS — use redis+ssl scheme with token as password
    # URL format: rediss://:TOKEN@HOST:PORT
    if "upstash.io" in url and not url.startswith("redis"):
        host = url.replace("https://", "").replace("http://", "")
        redis_url = f"rediss://:{token}@{host}:6379"
    else:
        redis_url = url

    return aioredis.from_url(redis_url, decode_responses=True)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._redis: aioredis.Redis | None = None

    def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = _get_redis_client()
        return self._redis

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip non-rate-limited paths
        if path in SKIP_PATHS or not any(path.startswith(p) for p in RATE_LIMITED_PATHS):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # No user_id means auth middleware rejected — let that handle it
            return await call_next(request)

        key = f"rate_limit:{user_id}"
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW

        try:
            redis = self._client()
            pipe = redis.pipeline()
            # Sliding window using sorted set
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, RATE_LIMIT_WINDOW)
            results = await pipe.execute()

            request_count = results[2]  # zcard result

            if request_count > RATE_LIMIT_REQUESTS:
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "user_id": user_id,
                        "path": path,
                        "count": request_count,
                    },
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded. Maximum 20 requests per minute.",
                        "code": 429,
                    },
                    headers={
                        "Retry-After": str(RATE_LIMIT_WINDOW),
                        "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(now + RATE_LIMIT_WINDOW)),
                    },
                )

            remaining = max(0, RATE_LIMIT_REQUESTS - request_count)
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(now + RATE_LIMIT_WINDOW))
            return response

        except Exception as exc:
            # Redis unavailable — fail open, don't block the user
            logger.warning(f"Rate limiter skipped (Redis unavailable): {exc}")
            return await call_next(request)
