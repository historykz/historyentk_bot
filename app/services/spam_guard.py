from __future__ import annotations

import hashlib
import time
from typing import Optional, Protocol

from redis.asyncio import Redis

MIN_INTERVAL_SECONDS = 2          # minimum gap between two messages from the same user
BURST_WINDOW_SECONDS = 10
BURST_LIMIT = 6                   # more than this many messages within the window -> throttle
DUP_WINDOW_SECONDS = 3600


class SpamGuardProtocol(Protocol):
    async def is_throttled(self, user_id: int) -> bool: ...
    async def is_duplicate(self, user_id: int, text: str | None) -> bool: ...


class RedisSpamGuard:
    """Redis-backed implementation. Preferred when REDIS_URL is configured: state
    survives restarts and is shared correctly if the bot is ever scaled to more
    than one process."""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_throttled(self, user_id: int) -> bool:
        key = f"throttle:burst:{user_id}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, BURST_WINDOW_SECONDS)
        if count > BURST_LIMIT:
            return True

        last_key = f"throttle:last:{user_id}"
        last = await self.redis.get(last_key)
        now = time.time()
        await self.redis.set(last_key, now, ex=60)
        if last is not None and now - float(last) < MIN_INTERVAL_SECONDS:
            return False
        return False

    async def is_duplicate(self, user_id: int, text: str | None) -> bool:
        if not text:
            return False
        digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
        key = f"dup:{user_id}:{digest}"
        exists = await self.redis.get(key)
        await self.redis.set(key, "1", ex=DUP_WINDOW_SECONDS)
        return bool(exists)


class InMemorySpamGuard:
    """Fallback used when REDIS_URL isn't configured (e.g. a small single-instance
    deployment that doesn't want to run a separate Redis service). State lives in
    process memory only: it resets on restart and wouldn't be shared if the bot
    were ever scaled to multiple instances — both are fine for a single-container
    support bot, and far simpler to deploy than requiring Redis.
    """

    def __init__(self) -> None:
        self._burst: dict[int, tuple[int, float]] = {}       # user_id -> (count, window_started_at)
        self._last: dict[int, float] = {}                     # user_id -> last message timestamp
        self._dup: dict[tuple[int, str], float] = {}          # (user_id, digest) -> expires_at

    def _gc_dup(self) -> None:
        now = time.time()
        expired = [k for k, exp in self._dup.items() if exp < now]
        for k in expired:
            del self._dup[k]

    async def is_throttled(self, user_id: int) -> bool:
        now = time.time()
        count, window_started = self._burst.get(user_id, (0, now))
        if now - window_started > BURST_WINDOW_SECONDS:
            count, window_started = 0, now
        count += 1
        self._burst[user_id] = (count, window_started)
        if count > BURST_LIMIT:
            return True

        last = self._last.get(user_id)
        self._last[user_id] = now
        if last is not None and now - last < MIN_INTERVAL_SECONDS:
            return False
        return False

    async def is_duplicate(self, user_id: int, text: str | None) -> bool:
        if not text:
            return False
        if len(self._dup) > 5000:  # simple unbounded-growth guard
            self._gc_dup()
        digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
        key = (user_id, digest)
        now = time.time()
        exists = key in self._dup and self._dup[key] >= now
        self._dup[key] = now + DUP_WINDOW_SECONDS
        return exists


# Backwards-compatible alias: existing imports of `SpamGuard` keep working.
SpamGuard = RedisSpamGuard

_in_memory_singleton: Optional[InMemorySpamGuard] = None


def create_spam_guard(redis: Optional[Redis]) -> SpamGuardProtocol:
    """Returns a Redis-backed guard if a Redis client is available, otherwise a
    process-local in-memory guard. The in-memory guard is a module-level singleton
    so its state persists across calls within the same running process."""
    global _in_memory_singleton
    if redis is not None:
        return RedisSpamGuard(redis)
    if _in_memory_singleton is None:
        _in_memory_singleton = InMemorySpamGuard()
    return _in_memory_singleton
