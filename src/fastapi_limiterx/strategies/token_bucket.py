from __future__ import annotations

import math
from typing import ClassVar

from fastapi_limiterx.backends.base import now
from fastapi_limiterx.rate import RateLimitItem
from fastapi_limiterx.strategies.base import HitResult, RateLimitStrategy, WindowStats


class TokenBucketStrategy(RateLimitStrategy):
    """Refill tokens at a steady rate while allowing short bursts.

    The steady rate is ``amount / period`` tokens per second and the bucket
    capacity is ``burst`` (defaulting to ``amount``). This is the recommended
    strategy for absorbing spikes without exceeding a long-term average.
    """

    name: ClassVar[str] = "token_bucket"

    def _key(self, key: str, item: RateLimitItem) -> str:
        return f"tb:{item.scope()}:{key}"

    @staticmethod
    def _params(item: RateLimitItem, burst: int | None) -> tuple[float, float]:
        capacity = float(burst) if burst is not None else float(item.amount)
        refill_rate = item.amount / item.expiry
        return capacity, refill_rate

    async def hit(
        self,
        item: RateLimitItem,
        key: str,
        *,
        cost: int = 1,
        burst: int | None = None,
    ) -> HitResult:
        capacity, refill_rate = self._params(item, burst)
        state = await self.storage.take_token(self._key(key, item), capacity, refill_rate, cost)
        reset_at = now() + state.reset_after
        retry_after = 0 if state.allowed else math.ceil(state.retry_after)
        stats = WindowStats(int(capacity), math.floor(state.remaining), reset_at, retry_after)
        return HitResult(state.allowed, stats)

    async def peek(
        self,
        item: RateLimitItem,
        key: str,
        *,
        burst: int | None = None,
    ) -> WindowStats:
        capacity, refill_rate = self._params(item, burst)
        state = await self.storage.take_token(self._key(key, item), capacity, refill_rate, 0.0)
        reset_at = now() + state.reset_after
        return WindowStats(int(capacity), math.floor(state.remaining), reset_at, 0)
