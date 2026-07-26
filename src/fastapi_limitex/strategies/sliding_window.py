from __future__ import annotations

import math
from typing import ClassVar

from fastapi_limitex.backends.base import now
from fastapi_limitex.rate import RateLimitItem
from fastapi_limitex.strategies.base import HitResult, RateLimitStrategy, WindowStats


class SlidingWindowStrategy(RateLimitStrategy):
    """Approximate a rolling window with two adjacent fixed counters.

    The previous window's count is weighted by how much of the current window
    has elapsed, smoothing the boundary bursts of the fixed window strategy
    while remaining cheap to store.
    """

    name: ClassVar[str] = "sliding_window"

    def _keys(self, key: str, item: RateLimitItem, index: int) -> tuple[str, str]:
        base = f"sw:{item.scope()}:{key}"
        return f"{base}:{index}", f"{base}:{index - 1}"

    async def _weighted_count(self, item: RateLimitItem, key: str) -> tuple[float, int, float]:
        window = item.expiry
        current = now()
        index = int(current // window)
        current_key, previous_key = self._keys(key, item, index)
        elapsed = current - index * window
        previous_weight = (window - elapsed) / window
        current_count = await self.storage.get(current_key)
        previous_count = await self.storage.get(previous_key)
        weighted = previous_count * previous_weight + current_count
        reset_at = (index + 1) * window
        return weighted, index, reset_at

    async def hit(
        self,
        item: RateLimitItem,
        key: str,
        *,
        cost: int = 1,
        burst: int | None = None,
    ) -> HitResult:
        weighted, index, reset_at = await self._weighted_count(item, key)
        allowed = weighted + cost <= item.amount
        if allowed:
            current_key, _ = self._keys(key, item, index)
            await self.storage.incr(current_key, item.expiry * 2, cost)
            weighted += cost
        remaining = max(0, item.amount - math.ceil(weighted))
        retry_after = 0 if allowed else max(0, math.ceil(reset_at - now()))
        return HitResult(allowed, WindowStats(item.amount, remaining, reset_at, retry_after))

    async def peek(
        self,
        item: RateLimitItem,
        key: str,
        *,
        burst: int | None = None,
    ) -> WindowStats:
        weighted, _, reset_at = await self._weighted_count(item, key)
        remaining = max(0, item.amount - math.ceil(weighted))
        return WindowStats(item.amount, remaining, reset_at, 0)
