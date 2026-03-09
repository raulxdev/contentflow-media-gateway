from collections import deque
from threading import Lock
from time import time

from fastapi import HTTPException, Request, status

from app.config import get_settings


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._store: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time()
        with self._lock:
            bucket = self._store.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
            bucket.append(now)


limiter = SlidingWindowRateLimiter(limit=get_settings().write_rate_limit_per_minute)


def enforce_write_rate_limit(request: Request) -> None:
    key = request.headers.get("X-API-Key") or request.client.host or "unknown"
    limiter.check(key)
