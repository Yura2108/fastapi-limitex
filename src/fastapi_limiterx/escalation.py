from __future__ import annotations

from dataclasses import dataclass, field

from fastapi_limiterx.backends.base import BaseStorage
from fastapi_limiterx.errors import ConfigurationError
from fastapi_limiterx.rate import RateLimitItem, parse


@dataclass
class EscalationPolicy:
    """Temporarily punish clients that repeatedly exceed their limit.

    When a client breaches its limit ``threshold`` times within
    ``track_seconds``, a ban is applied for ``ban_seconds``. During the ban the
    stricter ``penalty_limit`` is enforced instead of the normal limit; when
    ``penalty_limit`` is ``None`` the client is blocked outright.

    Args:
        threshold: Number of breaches within the tracking window that trigger a
            ban.
        track_seconds: Length of the window over which breaches are counted.
        ban_seconds: How long a ban lasts.
        penalty_limit: The limit enforced while banned (for example
            ``"1/minute"``). ``None`` blocks the client completely.
    """

    threshold: int
    track_seconds: int
    ban_seconds: int
    penalty_limit: str | RateLimitItem | None = None
    _penalty_item: RateLimitItem | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.threshold <= 0 or self.track_seconds <= 0 or self.ban_seconds <= 0:
            raise ConfigurationError("EscalationPolicy values must be positive")
        if self.penalty_limit is not None:
            self._penalty_item = parse(self.penalty_limit)

    @property
    def penalty_item(self) -> RateLimitItem | None:
        """Return the parsed penalty limit, or ``None`` for a hard block."""
        return self._penalty_item

    @staticmethod
    def _violation_key(key: str) -> str:
        return f"escv:{key}"

    @staticmethod
    def _ban_key(key: str) -> str:
        return f"escb:{key}"

    async def is_banned(self, storage: BaseStorage, key: str) -> bool:
        """Return ``True`` when ``key`` is currently banned."""
        return await storage.get(self._ban_key(key)) > 0

    async def register_breach(self, storage: BaseStorage, key: str) -> bool:
        """Record a breach for ``key`` and ban it once the threshold is reached.

        Returns ``True`` when this breach results in an active ban.
        """
        count = await storage.incr(self._violation_key(key), self.track_seconds)
        if count >= self.threshold:
            await storage.reset(self._ban_key(key))
            await storage.incr(self._ban_key(key), self.ban_seconds)
            return True
        return False

    async def clear(self, storage: BaseStorage, key: str) -> None:
        """Lift any ban and reset the breach counter for ``key``."""
        await storage.reset(self._ban_key(key))
        await storage.reset(self._violation_key(key))
