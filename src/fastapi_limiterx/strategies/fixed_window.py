from __future__ import annotations

from typing import ClassVar

from fastapi_limiterx.backends.base import now
from fastapi_limiterx.rate import RateLimitItem
from fastapi_limiterx.strategies.base import HitResult, RateLimitStrategy, WindowStats


class FixedWindowStrategy(RateLimitStrategy):
    """Count requests in discrete, non-overlapping windows.

    Simple and memory efficient, but permits up to twice the limit across a
    window boundary.
    """

    name: ClassVar[str] = "fixed_window"

    def _key(self, key: str, item: RateLimitItem) -> str:
        return f"fw:{item.scope()}:{key}"

    async def hit(
        self,
        item: RateLimitItem,
        key: str,
        *,
        cost: int = 1,
        burst: int | None = None,
    ) -> HitResult:
        storage_key = self._key(key, item)
        value = await self.storage.incr(storage_key, item.expiry, cost)
        reset_at = await self.storage.get_expiry(storage_key)
        allowed = value <= item.amount
        remaining = max(0, item.amount - value)
        retry_after = 0 if allowed else max(0, round(reset_at - now()))
        return HitResult(allowed, WindowStats(item.amount, remaining, reset_at, retry_after))

    async def peek(
        self,
        item: RateLimitItem,
        key: str,
        *,
        burst: int | None = None,
    ) -> WindowStats:
        storage_key = self._key(key, item)
        value = await self.storage.get(storage_key)
        reset_at = await self.storage.get_expiry(storage_key)
        remaining = max(0, item.amount - value)
        return WindowStats(item.amount, remaining, reset_at, 0)
