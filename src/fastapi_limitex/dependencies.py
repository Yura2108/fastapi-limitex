from __future__ import annotations

import itertools

from starlette.requests import Request
from starlette.websockets import WebSocket

from fastapi_limitex.errors import ConfigurationError, RateLimitExceeded
from fastapi_limitex.limiter import Limiter
from fastapi_limitex.rate import RateLimitItem, StaticLimit, parse_many
from fastapi_limitex.registry import LimitRule, LimitValue
from fastapi_limitex.types import CostFunc, ExemptFunc, KeyFunc

_counter = itertools.count()


def _limiter_from_app(app: object, provided: Limiter | None) -> Limiter:
    """Return the bound limiter, or resolve it from ``app.state``."""
    if provided is not None:
        return provided
    state = getattr(app, "state", None)
    limiter = getattr(state, "limiter", None)
    if not isinstance(limiter, Limiter):
        raise ConfigurationError(
            "No limiter is attached to the application. "
            "Call limiter.attach(app) or pass limiter=... to the dependency."
        )
    return limiter


class RateLimiter:
    """A FastAPI dependency that enforces a rate limit on an endpoint.

    Use it either as a route dependency
    (``dependencies=[Depends(RateLimiter("5/minute"))]``) or as an argument
    dependency. Multiple instances can be stacked to apply several limits.

    Args:
        limit_value: The limit expression, item, list or callable.
        key_func: A per-limit key function overriding the limiter default.
        strategy: A per-limit strategy name overriding the limiter default.
        cost: How many units a request consumes, or a callable returning it.
        burst: Bucket capacity for the token bucket strategy.
        exempt_when: A predicate that skips the limit when it returns ``True``.
        per_method: When ``True`` each HTTP method gets an independent bucket.
        methods: If set, the limit only applies to these HTTP methods.
        scope: An explicit namespace to share the limit across endpoints.
        name: A stable name enabling runtime edits via the limiter.
        limiter: Bind a specific limiter instead of resolving it per request.
    """

    def __init__(
        self,
        limit_value: LimitValue,
        *,
        key_func: KeyFunc | None = None,
        strategy: str | None = None,
        cost: int | CostFunc = 1,
        burst: int | None = None,
        exempt_when: ExemptFunc | None = None,
        per_method: bool = False,
        methods: list[str] | None = None,
        scope: str | None = None,
        name: str | None = None,
        limiter: Limiter | None = None,
    ) -> None:
        self.rule = LimitRule(
            name=name or f"dependency:{next(_counter)}",
            limit=limit_value,
            key_func=key_func,
            strategy=strategy,
            cost=cost,
            burst=burst,
            exempt_when=exempt_when,
            per_method=per_method,
            methods=frozenset(m.upper() for m in methods) if methods else None,
            scope=scope,
        )
        self._limiter = limiter

    def update(self, limit_value: LimitValue) -> None:
        """Change this dependency's limit at runtime."""
        self.rule.update(limit_value)

    async def __call__(self, request: Request) -> None:
        limiter = _limiter_from_app(request.app, self._limiter)
        await limiter.enforce(request, [self.rule])


class WebSocketRateLimiter:
    """A rate limiter for WebSocket message loops.

    Call the instance inside your receive loop, optionally passing a
    ``context_key`` to distinguish message types. On breach it raises
    :class:`~fastapi_limitex.errors.RateLimitExceeded`, which you can catch to
    send an error frame or close the connection.

    Args:
        limit_value: The limit expression, item, list or callable.
        strategy: A per-limit strategy name overriding the limiter default.
        cost: How many units each message consumes.
        burst: Bucket capacity for the token bucket strategy.
        scope: A namespace for the WebSocket limit's buckets.
        limiter: Bind a specific limiter instead of resolving it per connection.
    """

    def __init__(
        self,
        limit_value: StaticLimit,
        *,
        strategy: str | None = None,
        cost: int = 1,
        burst: int | None = None,
        scope: str = "ws",
        limiter: Limiter | None = None,
    ) -> None:
        self.limit_value = limit_value
        self._strategy = strategy
        self._cost = cost
        self._burst = burst
        self._scope = scope
        self._limiter = limiter

    async def __call__(self, websocket: WebSocket, context_key: str = "") -> None:
        limiter = _limiter_from_app(websocket.app, self._limiter)
        host = websocket.client.host if websocket.client else "testclient"
        key = f"{host}:{context_key}" if context_key else host
        result = await limiter.check(
            key,
            self.limit_value,
            strategy=self._strategy,
            cost=self._cost,
            burst=self._burst,
            scope=self._scope,
        )
        if not result.allowed:
            raise RateLimitExceeded(
                _first_item(self.limit_value),
                limit=result.stats.limit,
                remaining=result.stats.remaining,
                reset_at=result.stats.reset_at,
                retry_after=result.stats.retry_after,
                key=key,
                scope=self._scope,
            )


def _first_item(limit_value: StaticLimit) -> RateLimitItem:
    """Return the first parsed limit item for building an exception."""
    return parse_many(limit_value)[0]
