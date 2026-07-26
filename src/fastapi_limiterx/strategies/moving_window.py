from __future__ import annotations

import math
from typing import ClassVar

from fastapi_limiterx.backends.base import now
from fastapi_limiterx.rate import RateLimitItem
from fastapi_limiterx.strategies.base import HitResult, RateLimitStrategy, WindowStats


class MovingWindowStrategy(RateLimitStrategy):
    """Track every request timestamp for a precise rolling window.

    This is the most accurate strategy and never allows more than the limit in
    any window, at the cost of storing one entry per request. It is not
    supported by the memcached backend.
    """

    name: ClassVar[str] = "moving_window"

    def _key(self, key: str, item: RateLimitItem) -> str:
        return f"mw:{item.scope()}:{key}"

    async def _stats(self, item: RateLimitItem, key: str, extra: int) -> WindowStats:
        storage_key = self._key(key, item)
        count = await self.storage.get_num_acquired(storage_key, item.expiry)
        oldest = await self.storage.get_oldest_entry(storage_key, item.expiry)
        reset_at = (oldest + item.expiry) if oldest is not None else now()
        remaining = max(0, item.amount - count - extra)
        retry_after = max(0, math.ceil(reset_at - now())) if remaining == 0 else 0
        return WindowStats(item.amount, remaining, reset_at, retry_after)

    async def hit(
        self,
        item: RateLimitItem,
        key: str,
        *,
        cost: int = 1,
        burst: int | None = None,
    ) -> HitResult:
        storage_key = self._key(key, item)
        allowed = await self.storage.acquire_entry(storage_key, item.amount, item.expiry, cost)
        stats = await self._stats(item, key, 0)
        if not allowed:
            stats = WindowStats(stats.limit, 0, stats.reset_at, stats.retry_after or 1)
        return HitResult(allowed, stats)

    async def peek(
        self,
        item: RateLimitItem,
        key: str,
        *,
        burst: int | None = None,
    ) -> WindowStats:
        return await self._stats(item, key, 0)
