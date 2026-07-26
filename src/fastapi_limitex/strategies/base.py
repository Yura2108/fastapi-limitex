from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from fastapi_limitex.backends.base import BaseStorage, now
from fastapi_limitex.rate import RateLimitItem


@dataclass(frozen=True)
class WindowStats:
    """A snapshot of a limit's state used to build response headers.

    Attributes:
        limit: The maximum number of requests permitted in the window.
        remaining: The number of requests still available.
        reset_at: The epoch time at which the window fully resets.
        retry_after: Seconds a blocked client should wait before retrying.
    """

    limit: int
    remaining: int
    reset_at: float
    retry_after: int

    @property
    def reset_after(self) -> int:
        """Return the whole seconds until :attr:`reset_at`."""
        return max(0, math.ceil(self.reset_at - now()))


@dataclass(frozen=True)
class HitResult:
    """The result of consuming a request against a limit."""

    allowed: bool
    stats: WindowStats


class RateLimitStrategy(ABC):
    """Base class for rate limiting algorithms.

    A strategy translates a :class:`~fastapi_limitex.rate.RateLimitItem` and a
    caller-supplied ``key`` into calls against a :class:`BaseStorage` backend.
    """

    name: ClassVar[str]

    def __init__(self, storage: BaseStorage) -> None:
        self.storage = storage

    @abstractmethod
    async def hit(
        self,
        item: RateLimitItem,
        key: str,
        *,
        cost: int = 1,
        burst: int | None = None,
    ) -> HitResult:
        """Consume ``cost`` units against ``item`` for ``key``."""

    @abstractmethod
    async def peek(
        self,
        item: RateLimitItem,
        key: str,
        *,
        burst: int | None = None,
    ) -> WindowStats:
        """Return current statistics for ``key`` without consuming anything."""
