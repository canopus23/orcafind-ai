import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


@dataclass
class RateLimitConfig:
    limit: int
    window_seconds: int
    key_prefix: str


def _redis_client():
    url = os.getenv("REDIS_URL", "").strip()
    if not url or not redis:
        return None
    return redis.Redis.from_url(url, decode_responses=True)


def _key_for(request: Request, prefix: str, identity: str, window_seconds: int) -> str:
    bucket = int(time.time() // window_seconds)
    path = request.url.path
    return f"rl:{prefix}:{identity}:{path}:{window_seconds}:{bucket}"


def rate_limit(config: RateLimitConfig):
    """
    Fixed-window rate limiting via Redis.
    If Redis is not configured, it is a no-op (dev mode).
    """

    async def _dep(request: Request):
        client = _redis_client()
        if not client:
            return

        xff = (request.headers.get("X-Forwarded-For") or "").strip()
        identity = (xff.split(",")[0].strip() if xff else "") or (request.client.host if request.client else "unknown")
        key = _key_for(request, config.key_prefix, identity, config.window_seconds)

        # Atomic-ish: INCR then set TTL on first hit.
        current = client.incr(key)
        if current == 1:
            client.expire(key, config.window_seconds)

        if current > config.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return _dep
