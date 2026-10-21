"""Redis-backed rate-limiting middleware with fail-closed behavior."""

import redis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces per-IP rate limits using Redis.

    Fail-closed: if Redis is unavailable, returns 503 rather than
    allowing unlimited requests.
    The /health path is exempt from rate limiting.
    """

    def __init__(self, app, limit: int | None = None, window_seconds: int = 60):
        super().__init__(app)
        self.limit = limit or settings.rate_limit_requests_per_minute
        self.window_seconds = window_seconds
        self._redis_client = None

    def _get_redis(self):
        if self._redis_client is None:
            self._redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis_client

    async def dispatch(self, request: Request, call_next):
        # Exempt health check from rate limiting
        if request.scope.get("path") == "/health":
            return await call_next(request)

        # Rate limiting enabled by default in production; off in development unless configured
        if not settings.rate_limiting_enabled:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.scope.get("path", "unknown")
        key = f"rate_limit:{client_ip}:{path}"

        try:
            redis_client = self._get_redis()
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, self.window_seconds)
            if current > self.limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(self.window_seconds)},
                )
        except Exception:
            # Fail-closed: if Redis is unavailable, reject rather than allow unlimited
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiting unavailable"},
            )

        response = await call_next(request)
        return response
