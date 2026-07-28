from __future__ import annotations

import hashlib
import time

from redis.asyncio import Redis

MIN_INTERVAL_SECONDS = 2          # minimum gap between two messages from the same user
BURST_WINDOW_SECONDS = 10
BURST_LIMIT = 6                   # more than this many messages within the window -> throttle
DUP_WINDOW_SECONDS = 3600


class SpamGuard:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_throttled(self, user_id: int) -> bool:
        """Returns True if the user is sending messages too fast and should be told to slow down."""
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
            # Not hard-blocked, just noted; caller may still allow it through.
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
