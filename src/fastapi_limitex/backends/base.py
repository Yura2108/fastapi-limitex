from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


def now() -> float:
    """Return the current wall-clock time in seconds since the epoch."""
    return time.time()


@dataclass(frozen=True)
class TokenBucketState:
    """The outcome of a token-bucket acquisition attempt.

    Attributes:
        allowed: Whether the request was permitted.
        remaining: Tokens remaining in the bucket after the attempt.
        reset_after: Seconds until the bucket is completely refilled.
        retry_after: Seconds until enough tokens exist for the request.
    """

    allowed: bool
    remaining: float
    reset_after: float
    retry_after: float


class BaseStorage(ABC):
    """Async storage backend used by rate limiting strategies.

    A backend exposes a small set of atomic primitives. Counter primitives
    (:meth:`incr`, :meth:`get`, :meth:`get_expiry`) power the fixed and sliding
    window strategies; log primitives (:meth:`acquire_entry`,
    :meth:`get_num_acquired`, :meth:`get_oldest_entry`) power the moving window
    strategy; and :meth:`take_token` powers the token bucket strategy.
    """

    @abstractmethod
    async def setup(self) -> None:
        """Establish connections or create schema. Idempotent."""

    @abstractmethod
    async def close(self) -> None:
        """Release connections and background resources."""

    @abstractmethod
    async def check(self) -> bool:
        """Return ``True`` when the backend is reachable and healthy."""

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Remove all state associated with ``key``."""

    @abstractmethod
    async def get(self, key: str) -> int:
        """Return the current counter value for ``key`` (``0`` when absent)."""

    @abstractmethod
    async def incr(
        self,
        key: str,
        expiry: int,
        amount: int = 1,
        elastic_expiry: bool = False,
    ) -> int:
        """Atomically increment ``key`` by ``amount`` and return the new value.

        The expiry is applied when the counter is first created. When
        ``elastic_expiry`` is ``True`` the expiry is refreshed on every hit.
        """

    @abstractmethod
    async def get_expiry(self, key: str) -> float:
        """Return the epoch time at which ``key`` resets (``now`` when absent)."""

    @abstractmethod
    async def acquire_entry(self, key: str, limit: int, expiry: int, amount: int = 1) -> bool:
        """Atomically record ``amount`` log entries if the window has room.

        Returns ``True`` when the entries were recorded, ``False`` otherwise.
        """

    @abstractmethod
    async def get_num_acquired(self, key: str, expiry: int) -> int:
        """Return the number of log entries still inside the ``expiry`` window."""

    @abstractmethod
    async def get_oldest_entry(self, key: str, expiry: int) -> float | None:
        """Return the timestamp of the oldest live log entry, or ``None``."""

    @abstractmethod
    async def take_token(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        amount: float = 1.0,
    ) -> TokenBucketState:
        """Atomically attempt to remove ``amount`` tokens from a leaky bucket."""
