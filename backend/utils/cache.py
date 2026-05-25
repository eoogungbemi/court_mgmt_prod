"""
Optional Redis cache for ETA estimates.
All calls fail gracefully — if Redis is unavailable the system keeps working
via the LLM or rule-based fallback without any errors surfacing to callers.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ETA_TTL = 4 * 3600  # 4 hours — estimates are stable within a court day

_redis: Any = None   # None = not yet tried; False = tried and unavailable


def _client():
    global _redis
    if _redis is None:
        try:
            import redis as _lib
            from config import REDIS_URL
            r = _lib.from_url(REDIS_URL, socket_timeout=1, decode_responses=True)
            r.ping()
            _redis = r
            logger.info("Redis connected: %s", REDIS_URL)
        except Exception as exc:
            logger.warning("Redis unavailable — ETA caching disabled: %s", exc)
            _redis = False
    return _redis if _redis else None


def ping() -> bool:
    """Return True if Redis is reachable, False otherwise."""
    r = _client()
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def get(key: str) -> dict | None:
    r = _client()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set(key: str, value: dict, ttl: int = _ETA_TTL) -> None:
    r = _client()
    if r is None:
        return
    try:
        r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass
