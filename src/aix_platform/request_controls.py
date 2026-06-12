from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from time import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

from .config import Settings


class FixedWindowLimiter:
    def __init__(self, settings: Settings):
        self.limit = settings.rate_limit_requests
        self.window = settings.rate_limit_window_seconds
        self.environment = settings.environment
        self.redis = Redis.from_url(settings.redis_url) if settings.redis_url else None
        self.local: dict[str, deque[float]] = defaultdict(deque)

    def consume(self, key: str) -> tuple[bool, int, int]:
        now = int(time())
        reset = now - (now % self.window) + self.window
        if self.redis:
            redis_key = f"aix:rate:{key}:{reset}"
            try:
                count = int(self.redis.incr(redis_key))
                if count == 1:
                    self.redis.expire(redis_key, self.window + 1)
                return count <= self.limit, max(0, self.limit - count), reset
            except RedisError:
                if self.environment == "production":
                    raise
        bucket = self.local[key]
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        bucket.append(now)
        return len(bucket) <= self.limit, max(0, self.limit - len(bucket)), reset
def install_request_controls(app: FastAPI, settings: Settings) -> None:
    limiter = FixedWindowLimiter(settings)

    @app.middleware("http")
    async def request_controls(request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else 0
        except ValueError:
            declared_size = settings.request_max_bytes + 1
        is_evidence_upload = request.url.path.endswith("/evidence/upload")
        maximum = (
            settings.storage_max_bytes + 1024 * 1024
            if is_evidence_upload
            else settings.request_max_bytes
        )
        if declared_size > maximum:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "request_too_large",
                        "message": "Request body exceeds the configured limit",
                        "context": {"max_bytes": maximum},
                    }
                },
            )
        if settings.rate_limit_enabled and not request.url.path.startswith(
            ("/health/", "/metrics")
        ):
            client = request.client.host if request.client else "unknown"
            try:
                allowed, remaining, reset = limiter.consume(client)
            except RedisError:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "rate_limit_unavailable",
                            "message": "Request admission service is unavailable",
                            "context": {},
                        }
                    },
                )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    headers={
                        "Retry-After": str(max(1, reset - int(time()))),
                        "X-RateLimit-Limit": str(limiter.limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                    },
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests",
                            "context": {"reset": reset},
                        }
                    },
                )
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limiter.limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
