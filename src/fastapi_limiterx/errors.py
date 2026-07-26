from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi_limiterx.rate import RateLimitItem


class FastAPILimiterError(Exception):
    """Base class for every error raised by the library."""


class ConfigurationError(FastAPILimiterError):
    """Raised when the limiter or a backend is configured incorrectly."""


class BackendNotInstalledError(ConfigurationError):
    """Raised when a backend is used without its optional dependency installed."""


class UnsupportedOperationError(FastAPILimiterError):
    """Raised when a backend does not support a requested strategy."""


class MissingIdentityError(FastAPILimiterError):
    """Raised by a key function when a required identity cannot be resolved."""

    def __init__(self, message: str = "Could not resolve a rate limiting identity") -> None:
        super().__init__(message)


class RateLimitExceeded(FastAPILimiterError):
    """Raised when a request exceeds a configured rate limit.

    The bundled exception handler converts this into an HTTP ``429`` response.
    """

    def __init__(
        self,
        item: RateLimitItem,
        *,
        limit: int,
        remaining: int,
        reset_at: float,
        retry_after: int,
        key: str,
        scope: str = "",
        banned: bool = False,
    ) -> None:
        self.item = item
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after = retry_after
        self.key = key
        self.scope = scope
        self.banned = banned
        message = f"Rate limit exceeded: {item}" if not banned else f"Temporarily banned: {item}"
        super().__init__(message)
