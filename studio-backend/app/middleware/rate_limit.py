import time
import collections
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Endpoints that bypass rate limiting
_BYPASS_PATHS = frozenset({"/health", "/ready", "/build-info", "/docs", "/openapi.json"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter per client IP."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._buckets: dict[str, collections.deque] = {}
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _BYPASS_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if client_ip == "testclient" and getattr(request.app.state, "disable_rate_limit_for_testclient", False):
            return await call_next(request)

        now = time.time()

        if now - self._last_cleanup > 60:
            self._cleanup_stale_buckets(now)
            self._last_cleanup = now

        if client_ip not in self._buckets:
            self._buckets[client_ip] = collections.deque()

        bucket = self._buckets[client_ip]

        while bucket and bucket[0] < now - 60:
            bucket.popleft()

        if len(bucket) >= self.rpm:
            retry_after = int(bucket[0] + 60 - now) + 1
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        response = await call_next(request)
        remaining = self.rpm - len(bucket)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return response

    def _cleanup_stale_buckets(self, now: float):
        stale_keys = [k for k, v in self._buckets.items() if not v or v[-1] < now - 120]
        for k in stale_keys:
            del self._buckets[k]
