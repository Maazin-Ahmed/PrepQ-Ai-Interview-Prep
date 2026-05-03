import logging
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger("prepq.metrics")

# ─────────────────────────────────────────────
# Metrics Definitions
# ─────────────────────────────────────────────

http_requests_total = Counter(
    "prepq_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "prepq_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

active_streams = Gauge(
    "prepq_active_streams",
    "Number of currently active SSE streams",
)

chat_requests_total = Counter(
    "prepq_chat_requests_total",
    "Total chat requests",
    ["user_tier"],
)

mock_scores_total = Counter(
    "prepq_mock_scores_total",
    "Total mock answer evaluations",
)

rate_limit_hits_total = Counter(
    "prepq_rate_limit_hits_total",
    "Total rate limit rejections",
)

security_violations_total = Counter(
    "prepq_security_violations_total",
    "Total security violation rejections",
    ["violation_type"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records request count and latency for all endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        method = request.method
        path = request.url.path

        # Track active SSE streams
        is_stream = path.startswith("/chat") or path.startswith("/plan") or path.startswith("/mock/question")
        if is_stream:
            active_streams.inc()

        try:
            response = await call_next(request)
            duration = time.time() - start

            http_requests_total.labels(
                method=method,
                path=path,
                status_code=str(response.status_code),
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                path=path,
            ).observe(duration)

            return response

        except Exception as exc:
            http_requests_total.labels(
                method=method,
                path=path,
                status_code="500",
            ).inc()
            raise exc

        finally:
            if is_stream:
                active_streams.dec()
