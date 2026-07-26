from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from fastapi_limitex.strategies.base import WindowStats
from fastapi_limitex.types import RateLimitContext


@dataclass
class HeaderConfig:
    """Configuration for the rate limit headers added to responses.

    Args:
        enabled: Whether to emit rate limit headers at all.
        limit: Header name for the request quota.
        remaining: Header name for the remaining quota.
        reset: Header name for when the window resets.
        retry_after: Header name for the retry delay on blocked responses.
        reset_as_epoch: When ``True`` the reset header is an epoch timestamp,
            otherwise it is the number of seconds until reset.
    """

    enabled: bool = True
    limit: str = "X-RateLimit-Limit"
    remaining: str = "X-RateLimit-Remaining"
    reset: str = "X-RateLimit-Reset"
    retry_after: str = "Retry-After"
    reset_as_epoch: bool = True


def apply_headers(
    response: Response,
    stats: WindowStats,
    config: HeaderConfig,
    *,
    include_retry_after: bool = False,
) -> None:
    """Write rate limit headers onto ``response`` according to ``config``."""
    if not config.enabled:
        return
    response.headers[config.limit] = str(stats.limit)
    response.headers[config.remaining] = str(stats.remaining)
    reset_value = int(stats.reset_at) if config.reset_as_epoch else stats.reset_after
    response.headers[config.reset] = str(reset_value)
    if include_retry_after:
        response.headers[config.retry_after] = str(stats.retry_after)


def default_response(request: Request, context: RateLimitContext) -> Response:
    """Return the default HTTP ``429`` response for a blocked request."""
    detail = (
        "You are temporarily banned due to repeated rate limit violations."
        if context.banned
        else "Rate limit exceeded. Please slow down and try again later."
    )
    payload = {
        "detail": detail,
        "retry_after": context.stats.retry_after,
        "limit": context.stats.limit,
        "remaining": context.stats.remaining,
    }
    return JSONResponse(payload, status_code=429)
