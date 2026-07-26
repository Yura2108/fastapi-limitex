from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi_limiterx.rate import RateLimitItem
    from fastapi_limiterx.strategies.base import WindowStats

KeyFunc = Callable[[Request], str | Awaitable[str]]
"""A function that derives a rate limiting key from a request."""

ExemptFunc = Callable[[Request], bool | Awaitable[bool]]
"""A predicate that exempts a request from rate limiting when it returns ``True``."""

CostFunc = Callable[[Request], int | Awaitable[int]]
"""A function that returns how many units a request costs."""


@dataclass(frozen=True)
class RateLimitContext:
    """Details about a rate limit decision passed to callbacks and responses."""

    request: Request
    key: str
    item: RateLimitItem
    stats: WindowStats
    scope: str
    banned: bool


ResponseBuilder = Callable[
    [Request, RateLimitContext],
    Response | Awaitable[Response],
]
"""Builds the HTTP response returned when a request is blocked."""

BreachCallback = Callable[
    [RateLimitContext],
    Awaitable[None] | None,
]
"""Invoked whenever a request is blocked, for logging or alerting."""
