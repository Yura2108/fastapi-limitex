from __future__ import annotations

import asyncio
from collections import OrderedDict

from fastapi_limitex.backends.base import BaseStorage, TokenBucketState, now


class MemoryStorage(BaseStorage):
    """Thread-safe, in-process storage bounded by entry count and TTL.

    All state lives in the current process, so limits are not shared across
    workers. It is ideal for single-process deployments, development and tests.

    Args:
        max_entries: The maximum number of distinct keys retained. When the cap
            is reached the least recently used keys are evicted.
        prune_interval_ops: How many write operations may pass before expired
            entries are swept eagerly.
    """

    def __init__(self, max_entries: int = 10_000, prune_interval_ops: int = 256) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self.prune_interval_ops = prune_interval_ops
        self._counters: dict[str, tuple[int, float]] = {}
        self._logs: dict[str, list[float]] = {}
        self._buckets: dict[str, tuple[float, float]] = {}
        self._index: OrderedDict[str, str] = OrderedDict()
        self._lock = asyncio.Lock()
        self._ops = 0

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        async with self._lock:
            self._counters.clear()
            self._logs.clear()
            self._buckets.clear()
            self._index.clear()

    async def check(self) -> bool:
        return True

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._counters.pop(key, None)
            self._logs.pop(key, None)
            self._buckets.pop(key, None)
            self._index.pop(key, None)

    async def get(self, key: str) -> int:
        async with self._lock:
            entry = self._counters.get(key)
            if entry is None or entry[1] <= now():
                return 0
            self._index.move_to_end(key)
            return entry[0]

    async def incr(
        self,
        key: str,
        expiry: int,
        amount: int = 1,
        elastic_expiry: bool = False,
    ) -> int:
        async with self._lock:
            current = now()
            entry = self._counters.get(key)
            if entry is None or entry[1] <= current:
                value, reset_at = amount, current + expiry
            else:
                value = entry[0] + amount
                reset_at = current + expiry if elastic_expiry else entry[1]
            self._counters[key] = (value, reset_at)
            self._touch(key, "counter")
            return value

    async def get_expiry(self, key: str) -> float:
        async with self._lock:
            entry = self._counters.get(key)
            current = now()
            if entry is None or entry[1] <= current:
                return current
            return entry[1]

    async def acquire_entry(self, key: str, limit: int, expiry: int, amount: int = 1) -> bool:
        async with self._lock:
            current = now()
            cutoff = current - expiry
            log = [ts for ts in self._logs.get(key, []) if ts > cutoff]
            if len(log) + amount > limit:
                self._logs[key] = log
                self._touch(key, "log")
                return False
            log.extend([current] * amount)
            self._logs[key] = log
            self._touch(key, "log")
            return True

    async def get_num_acquired(self, key: str, expiry: int) -> int:
        async with self._lock:
            cutoff = now() - expiry
            log = [ts for ts in self._logs.get(key, []) if ts > cutoff]
            self._logs[key] = log
            return len(log)

    async def get_oldest_entry(self, key: str, expiry: int) -> float | None:
        async with self._lock:
            cutoff = now() - expiry
            log = [ts for ts in self._logs.get(key, []) if ts > cutoff]
            self._logs[key] = log
            return log[0] if log else None

    async def take_token(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        amount: float = 1.0,
    ) -> TokenBucketState:
        async with self._lock:
            current = now()
            tokens, last = self._buckets.get(key, (capacity, current))
            tokens = min(capacity, tokens + (current - last) * refill_rate)
            allowed = tokens >= amount
            if allowed:
                tokens -= amount
            self._buckets[key] = (tokens, current)
            self._touch(key, "bucket")
            reset_after = (capacity - tokens) / refill_rate if refill_rate > 0 else 0.0
            retry_after = 0.0 if allowed else (amount - tokens) / refill_rate
            return TokenBucketState(allowed, tokens, reset_after, retry_after)

    def _touch(self, key: str, store: str) -> None:
        """Mark ``key`` as most recently used and enforce capacity and TTL."""
        self._index[key] = store
        self._index.move_to_end(key)
        self._ops += 1
        if self._ops % self.prune_interval_ops == 0:
            self._prune_expired()
        while len(self._index) > self.max_entries:
            oldest, _ = self._index.popitem(last=False)
            self._counters.pop(oldest, None)
            self._logs.pop(oldest, None)
            self._buckets.pop(oldest, None)

    def _prune_expired(self) -> None:
        """Drop counters and empty logs whose window has fully elapsed."""
        current = now()
        for key, (_, reset_at) in list(self._counters.items()):
            if reset_at <= current:
                self._counters.pop(key, None)
                self._index.pop(key, None)
        for key, log in list(self._logs.items()):
            if not log:
                self._logs.pop(key, None)
                self._index.pop(key, None)
