"""Redis caching layer for VoxDoc.

Phase 8: Optional Redis-backed cache for RAG embeddings, model outputs,
and rate limit windows. Falls back to in-memory LRU when Redis is unavailable.

Set ``REDIS_URL`` env var or ``redis_url`` in config to enable.
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory fallback (bounded LRU)
# ---------------------------------------------------------------------------

class _LRUCache:
    """Simple thread-safe-ish LRU cache for single-process fallback."""

    def __init__(self, maxsize: int = 512):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.time() > expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        expires_at = (time.time() + ttl) if ttl > 0 else 0.0
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expires_at)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Redis-backed cache
# ---------------------------------------------------------------------------

class _RedisCache:
    """Async Redis cache wrapper."""

    def __init__(self, url: str, default_ttl: int = 300):
        self._url = url
        self._default_ttl = default_ttl
        self._redis = None

    async def _connect(self):
        if self._redis is not None:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Redis cache connected: %s", self._url.split("@")[-1])
        except Exception as e:
            logger.warning("Redis connection failed, falling back to memory cache: %s", e)
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        await self._connect()
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.debug("Redis GET error for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 0) -> None:
        await self._connect()
        if self._redis is None:
            return
        try:
            ttl = ttl or self._default_ttl
            await self._redis.setex(key, ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.debug("Redis SET error for key %s: %s", key, e)

    async def delete(self, key: str) -> None:
        await self._connect()
        if self._redis is None:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.debug("Redis DELETE error for key %s: %s", key, e)

    async def clear(self) -> None:
        await self._connect()
        if self._redis is None:
            return
        try:
            await self._redis.flushdb(asynchronous=True)
        except Exception as e:
            logger.debug("Redis CLEAR error: %s", e)


# ---------------------------------------------------------------------------
# Unified cache interface
# ---------------------------------------------------------------------------

class CacheService:
    """Unified cache with Redis primary and LRU fallback."""

    def __init__(self):
        self._memory = _LRUCache(maxsize=512)
        self._redis: Optional[_RedisCache] = None
        if settings.redis_url:
            self._redis = _RedisCache(
                url=settings.redis_url,
                default_ttl=settings.redis_cache_ttl_seconds,
            )

    @staticmethod
    def make_key(*parts: str) -> str:
        """Build a namespaced cache key."""
        raw = ":".join(str(p) for p in parts)
        return f"voxdoc:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def get(self, key: str) -> Optional[Any]:
        """Get from Redis first, then memory fallback."""
        if self._redis:
            val = await self._redis.get(key)
            if val is not None:
                return val
        return self._memory.get(key)

    async def set(self, key: str, value: Any, ttl: int = 0) -> None:
        """Set in both Redis and memory."""
        self._memory.set(key, value, ttl)
        if self._redis:
            await self._redis.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        self._memory.delete(key)
        if self._redis:
            await self._redis.delete(key)

    async def clear(self) -> None:
        self._memory.clear()
        if self._redis:
            await self._redis.clear()

    @property
    def redis_enabled(self) -> bool:
        return self._redis is not None


# Singleton
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the global cache service."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
