"""Fixed-window rate limiting backed by Redis.

Limits are declared as "N/seconds" strings, e.g. "30/60" = 30 requests per minute.
Keys are scoped per user (or per IP for unauthenticated traffic) per bucket.
"""
import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.redis_client import get_redis


def _parse(limit: str) -> tuple[int, int]:
    count, window = limit.split("/")
    return int(count), int(window)


def enforce_rate_limit(request: Request, bucket: str, identity: str) -> None:
    settings = get_settings()
    limit_str = {
        "chat": settings.rate_limit_chat,
        "upload": settings.rate_limit_upload,
    }.get(bucket, settings.rate_limit_default)
    max_requests, window = _parse(limit_str)

    window_id = int(time.time()) // window
    key = f"ratelimit:{bucket}:{identity}:{window_id}"
    r = get_redis()
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, window + 1)
    current, _ = pipe.execute()
    if int(current) > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit_str} for '{bucket}'. Try again shortly.",
        )
