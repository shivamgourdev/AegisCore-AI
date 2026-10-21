"""Rate limiting unit tests.

These tests use a mock Redis client and do NOT verify real Redis operation.
Real Redis verification is BLOCKED unless a Redis server is available locally.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.middleware.rate_limit import RateLimitMiddleware


class FakeRedis:
    """In-memory fake Redis for unit testing rate-limit logic."""

    def __init__(self):
        self._store = {}
        self._expires = {}
        self._should_fail = False

    def incr(self, key):
        if self._should_fail:
            raise ConnectionError("Redis unavailable")
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    def expire(self, key, seconds):
        self._expires[key] = seconds

    def set_fail(self, should_fail: bool):
        self._should_fail = should_fail


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture(autouse=True)
def enable_rate_limiting():
    """Enable rate limiting for these tests."""
    settings.enable_rate_limiting = True
    yield
    settings.enable_rate_limiting = False


def _make_request(path: str, client_ip: str = "127.0.0.1"):
    """Build a minimal Starlette Request with required scope fields."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": (client_ip, 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


async def _call_next(request):
    return JSONResponse(status_code=200, content={"ok": True})


def test_rate_limit_allows_under_threshold(fake_redis):
    """Requests under the limit are allowed."""
    with patch("app.middleware.rate_limit.redis.Redis.from_url", return_value=fake_redis):
        import asyncio

        middleware = RateLimitMiddleware(app=None, limit=3, window_seconds=60)

        for i in range(3):
            request = _make_request("/test")
            response = asyncio.run(middleware.dispatch(request, _call_next))
            assert response.status_code == 200, f"Request {i+1} should be allowed"


def test_rate_limit_returns_429_over_threshold(fake_redis):
    """Requests over the limit return 429."""
    with patch("app.middleware.rate_limit.redis.Redis.from_url", return_value=fake_redis):
        import asyncio

        middleware = RateLimitMiddleware(app=None, limit=3, window_seconds=60)

        # First 3 allowed
        for i in range(3):
            request = _make_request("/test")
            response = asyncio.run(middleware.dispatch(request, _call_next))
            assert response.status_code == 200

        # 4th should be 429
        request = _make_request("/test")
        response = asyncio.run(middleware.dispatch(request, _call_next))
        assert response.status_code == 429


def test_rate_limit_redis_unavailable_fail_closed(fake_redis):
    """When Redis is unavailable, middleware returns 503 (fail-closed)."""
    fake_redis.set_fail(True)
    with patch("app.middleware.rate_limit.redis.Redis.from_url", return_value=fake_redis):
        import asyncio

        middleware = RateLimitMiddleware(app=None, limit=3, window_seconds=60)

        request = _make_request("/test")
        response = asyncio.run(middleware.dispatch(request, _call_next))
        assert response.status_code == 503


def test_rate_limit_endpoint_isolation(fake_redis):
    """Different endpoints have separate rate-limit counters."""
    with patch("app.middleware.rate_limit.redis.Redis.from_url", return_value=fake_redis):
        import asyncio

        middleware = RateLimitMiddleware(app=None, limit=2, window_seconds=60)

        # Endpoint A gets 2 requests (allowed)
        for path in ["/api/v1/auth/login", "/api/v1/auth/login"]:
            request = _make_request(path)
            response = asyncio.run(middleware.dispatch(request, _call_next))
            assert response.status_code == 200

        # Endpoint B (different path) still has its own counter
        request = _make_request("/api/v1/auth/register")
        response = asyncio.run(middleware.dispatch(request, _call_next))
        assert response.status_code == 200
