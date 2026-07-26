from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from functools import wraps
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar, cast
from urllib.parse import urlsplit

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from fastapi_limiterx.backends.base import BaseStorage, now
from fastapi_limiterx.backends.memory import MemoryStorage
from fastapi_limiterx.errors import ConfigurationError, MissingIdentityError, RateLimitExceeded
from fastapi_limiterx.escalation import EscalationPolicy
from fastapi_limiterx.exemptions import Exemptions
from fastapi_limiterx.keys import get_remote_address, resolve_key
from fastapi_limiterx.rate import RateLimitItem, StaticLimit, parse_many
from fastapi_limiterx.registry import LimitRegistry, LimitRule, LimitValue
from fastapi_limiterx.responses import HeaderConfig, apply_headers, default_response
from fastapi_limiterx.strategies import HitResult, RateLimitStrategy, WindowStats, create_strategy
from fastapi_limiterx.types import (
    BreachCallback,
    CostFunc,
    ExemptFunc,
    KeyFunc,
    RateLimitContext,
    ResponseBuilder,
)

if TYPE_CHECKING:
    from starlette.applications import Starlette

F = TypeVar("F", bound=Callable[..., Any])


class Limiter:
    """Coordinates rate limiting for a Starlette or FastAPI application.

    Args:
        key_func: The default function deriving a key from a request. Defaults
            to the client IP reported by the ASGI server.
        default_limits: Limits applied to every request, bucketed per URL path.
        application_limits: Limits applied globally across all paths.
        strategy: The default algorithm name. One of ``"fixed_window"``,
            ``"sliding_window"``, ``"moving_window"`` or ``"token_bucket"``.
        storage: A storage backend instance. Defaults to :class:`MemoryStorage`.
        storage_uri: A convenience URI (``redis://``, ``memcached://``,
            ``sqlite://``, ``memory://``) used when ``storage`` is not given.
        headers: Configuration for rate limit response headers.
        escalation: An optional policy that bans repeatedly abusive clients.
        exemptions: Rules describing which requests bypass limiting.
        on_breach: A callback invoked whenever a request is blocked.
        response_builder: Builds the response returned to blocked clients.
        enabled: Whether limiting is active. Can be toggled at runtime.
    """

    def __init__(
        self,
        key_func: KeyFunc = get_remote_address,
        *,
        default_limits: StaticLimit | None = None,
        application_limits: StaticLimit | None = None,
        strategy: str = "fixed_window",
        storage: BaseStorage | None = None,
        storage_uri: str | None = None,
        headers: HeaderConfig | None = None,
        escalation: EscalationPolicy | None = None,
        exemptions: Exemptions | None = None,
        on_breach: BreachCallback | None = None,
        response_builder: ResponseBuilder = default_response,
        enabled: bool = True,
    ) -> None:
        self._key_func = key_func
        self._strategy_name = strategy
        self._storage = storage or self._build_storage(storage_uri)
        self._header_config = headers or HeaderConfig()
        self._escalation = escalation
        self._exemptions = exemptions or Exemptions()
        self._on_breach = on_breach
        self._response_builder = response_builder
        self._enabled = enabled
        self._registry = LimitRegistry()
        self._strategies: dict[str, RateLimitStrategy] = {}
        self._application_items = parse_many(application_limits) if application_limits else []
        self._default_items = parse_many(default_limits) if default_limits else []
        self._ready = False
        self._setup_lock = asyncio.Lock()

    @staticmethod
    def _build_storage(uri: str | None) -> BaseStorage:
        """Create a storage backend from a convenience URI."""
        if uri is None:
            return MemoryStorage()
        parts = urlsplit(uri)
        scheme = parts.scheme
        if scheme in ("", "memory"):
            return MemoryStorage()
        if scheme in ("redis", "rediss", "unix"):
            from fastapi_limiterx.backends.redis import RedisStorage

            return RedisStorage(uri)
        if scheme == "memcached":
            from fastapi_limiterx.backends.memcached import MemcachedStorage

            return MemcachedStorage(parts.hostname or "localhost", parts.port or 11211)
        if scheme == "sqlite":
            from fastapi_limiterx.backends.sqlite import SQLiteStorage

            path = parts.path.lstrip("/") or ":memory:"
            return SQLiteStorage(path)
        raise ConfigurationError(f"Unsupported storage URI scheme: {scheme!r}")

    @property
    def storage(self) -> BaseStorage:
        """Return the configured storage backend."""
        return self._storage

    @property
    def exemptions(self) -> Exemptions:
        """Return the mutable exemption rules."""
        return self._exemptions

    @property
    def enabled(self) -> bool:
        """Return whether rate limiting is currently active."""
        return self._enabled

    def enable(self) -> None:
        """Activate rate limiting at runtime."""
        self._enabled = True

    def disable(self) -> None:
        """Deactivate rate limiting at runtime."""
        self._enabled = False

    def _strategy_for(self, name: str | None) -> RateLimitStrategy:
        resolved = name or self._strategy_name
        if resolved not in self._strategies:
            self._strategies[resolved] = create_strategy(resolved, self._storage)
        return self._strategies[resolved]

    async def _ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._setup_lock:
            if not self._ready:
                await self._storage.setup()
                self._ready = True

    async def startup(self) -> None:
        """Initialise the storage backend. Safe to call more than once."""
        await self._ensure_ready()

    async def shutdown(self) -> None:
        """Release the storage backend's resources."""
        await self._storage.close()
        self._ready = False

    async def __aenter__(self) -> Limiter:
        await self.startup()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.shutdown()

    def attach(
        self,
        app: Starlette,
        *,
        register_handlers: bool = True,
        add_middleware: bool = True,
    ) -> None:
        """Wire the limiter into ``app``.

        Registers exception handlers for blocked requests and installs the
        middleware that enforces global limits and injects headers.
        """
        from fastapi_limiterx.middleware import RateLimiterMiddleware

        app.state.limiter = self
        if register_handlers:
            app.add_exception_handler(RateLimitExceeded, self._handle_rate_limit)
            app.add_exception_handler(MissingIdentityError, self._handle_missing_identity)
        if add_middleware:
            app.add_middleware(RateLimiterMiddleware, limiter=self)

    def limit(
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
    ) -> Callable[[F], F]:
        """Decorate an endpoint with a rate limit.

        The decorated endpoint must accept a ``request: Request`` parameter so
        the limiter can identify the caller. Works with both ``def`` and
        ``async def`` endpoints.
        """

        def decorator(func: F) -> F:
            rule_name = name or f"{func.__module__}.{func.__qualname__}"
            rule = LimitRule(
                name=rule_name,
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
            self._registry.add(rule)
            request_param = _locate_request_param(func)

            if inspect.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    request = _extract_request(args, kwargs, request_param)
                    blocked = await self.guard(request, [rule])
                    if blocked is not None:
                        return blocked
                    result = await func(*args, **kwargs)
                    self._inject_success(request, result)
                    return result

                return cast(F, async_wrapper)

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                request = _extract_request(args, kwargs, request_param)
                blocked = anyio.from_thread.run(self.guard, request, [rule])
                if blocked is not None:
                    return blocked
                result = func(*args, **kwargs)
                self._inject_success(request, result)
                return result

            return cast(F, sync_wrapper)

        return decorator

    async def enforce(self, request: Request, rules: list[LimitRule]) -> None:
        """Evaluate ``rules`` for ``request``, raising on the first breach.

        Used by the dependency API where raising integrates with FastAPI's
        exception handling.
        """
        await self._ensure_ready()
        stats = await self._apply(request, rules)
        if stats is not None:
            request.state.limiterx_stats = stats

    async def check(
        self,
        key: str,
        limit: StaticLimit,
        *,
        strategy: str | None = None,
        cost: int = 1,
        burst: int | None = None,
        scope: str = "manual",
    ) -> HitResult:
        """Consume a request for an explicit key outside the request lifecycle.

        Useful for WebSocket message loops and background tasks. Returns the
        :class:`~fastapi_limiterx.strategies.HitResult` for the first blocked
        limit, or for the last limit when all are allowed.
        """
        await self._ensure_ready()
        strat = self._strategy_for(strategy)
        identity = f"{scope}:{key}"
        result: HitResult | None = None
        for item in parse_many(limit):
            result = await strat.hit(item, identity, cost=cost, burst=burst)
            if not result.allowed:
                return result
        if result is None:
            raise ConfigurationError("At least one limit must be provided")
        return result

    async def peek(self, request: Request, rule_name: str) -> WindowStats | None:
        """Return statistics for a named limit without consuming a request."""
        await self._ensure_ready()
        rules = self._registry.get(rule_name)
        result: WindowStats | None = None
        for rule in rules:
            key = await resolve_key(rule.key_func or self._key_func, request)
            identity = f"{rule.scope or rule.name}:{key}"
            strategy = self._strategy_for(rule.strategy)
            for item in rule.resolve_items(request):
                stats = await strategy.peek(item, identity, burst=rule.burst)
                result = self._most_restrictive(result, stats)
        return result

    def set_limit(self, name: str, limit: LimitValue) -> None:
        """Change a named limit at runtime without restarting the app."""
        self._registry.set_limit(name, limit)

    def enable_limit(self, name: str) -> None:
        """Re-enable a named limit at runtime."""
        self._registry.enable(name)

    def disable_limit(self, name: str) -> None:
        """Disable a named limit at runtime while keeping it registered."""
        self._registry.disable(name)

    def remove_limit(self, name: str) -> None:
        """Remove a named limit at runtime."""
        self._registry.remove(name)

    def limit_names(self) -> list[str]:
        """Return the names of every registered limit."""
        return self._registry.names()

    async def guard(self, request: Request, rules: list[LimitRule]) -> Response | None:
        """Evaluate ``rules`` and return a response when blocked, else ``None``.

        Used by the decorator and middleware where a response is returned rather
        than raised.
        """
        await self._ensure_ready()
        try:
            stats = await self._apply(request, rules)
        except RateLimitExceeded as exc:
            return await self.build_response(request, exc)
        except MissingIdentityError as exc:
            return self._missing_identity_response(exc)
        if stats is not None:
            existing = getattr(request.state, "limiterx_stats", None)
            request.state.limiterx_stats = self._most_restrictive(existing, stats)
        return None

    async def _apply(self, request: Request, rules: list[LimitRule]) -> WindowStats | None:
        """Evaluate ``rules`` and return the most restrictive window stats."""
        if not self._enabled:
            return None
        primary: WindowStats | None = None
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.methods is not None and request.method not in rule.methods:
                continue
            key = await resolve_key(rule.key_func or self._key_func, request)
            if rule.per_method:
                key = f"{key}:{request.method}"
            if await self._exemptions.is_exempt(request, key):
                continue
            if await self._is_exempt_when(rule.exempt_when, request):
                continue
            scope = rule.scope or rule.name
            identity = f"{scope}:{key}"
            strategy = self._strategy_for(rule.strategy)
            cost = await self._resolve_cost(rule.cost, request)
            if self._escalation is not None and await self._escalation.is_banned(
                self._storage, identity
            ):
                stats = await self._enforce_ban(request, rule, strategy, scope, identity, cost)
                primary = self._most_restrictive(primary, stats)
                continue
            for item in rule.resolve_items(request):
                result = await strategy.hit(item, identity, cost=cost, burst=rule.burst)
                primary = self._most_restrictive(primary, result.stats)
                if not result.allowed:
                    banned = False
                    if self._escalation is not None:
                        banned = await self._escalation.register_breach(self._storage, identity)
                    await self._raise_block(request, item, result.stats, scope, identity, banned)
        return primary

    async def _enforce_ban(
        self,
        request: Request,
        rule: LimitRule,
        strategy: RateLimitStrategy,
        scope: str,
        identity: str,
        cost: int,
    ) -> WindowStats:
        """Enforce the penalty limit (or a hard block) for a banned client."""
        assert self._escalation is not None
        penalty = self._escalation.penalty_item
        if penalty is None:
            stats = WindowStats(
                0, 0, now() + self._escalation.ban_seconds, self._escalation.ban_seconds
            )
            await self._raise_block(
                request,
                RateLimitItem(0, 1, self._escalation.ban_seconds),
                stats,
                scope,
                identity,
                True,
            )
        result = await strategy.hit(penalty, f"pen:{identity}", cost=cost, burst=rule.burst)
        if not result.allowed:
            await self._raise_block(request, penalty, result.stats, scope, identity, True)
        return result.stats

    async def _raise_block(
        self,
        request: Request,
        item: RateLimitItem,
        stats: WindowStats,
        scope: str,
        identity: str,
        banned: bool,
    ) -> NoReturn:
        """Notify the breach callback and raise :class:`RateLimitExceeded`."""
        context = RateLimitContext(request, identity, item, stats, scope, banned)
        await self._call_breach(context)
        raise RateLimitExceeded(
            item,
            limit=stats.limit,
            remaining=stats.remaining,
            reset_at=stats.reset_at,
            retry_after=stats.retry_after,
            key=identity,
            scope=scope,
            banned=banned,
        )

    async def _call_breach(self, context: RateLimitContext) -> None:
        if self._on_breach is None:
            return
        result = self._on_breach(context)
        if isawaitable(result):
            await result

    async def build_response(self, request: Request, exc: RateLimitExceeded) -> Response:
        """Build the HTTP response for a :class:`RateLimitExceeded` exception."""
        stats = WindowStats(exc.limit, exc.remaining, exc.reset_at, exc.retry_after)
        context = RateLimitContext(request, exc.key, exc.item, stats, exc.scope, exc.banned)
        built = self._response_builder(request, context)
        response = await built if isawaitable(built) else built
        apply_headers(response, stats, self._header_config, include_retry_after=True)
        return response

    def _missing_identity_response(self, exc: MissingIdentityError) -> Response:
        return JSONResponse({"detail": str(exc)}, status_code=401)

    def _inject_success(self, request: Request, result: Any) -> None:
        """Attach headers to a returned ``Response`` when limits are known."""
        stats = getattr(request.state, "limiterx_stats", None)
        if stats is not None and isinstance(result, Response):
            apply_headers(result, stats, self._header_config)

    async def _handle_rate_limit(self, request: Request, exc: Exception) -> Response:
        return await self.build_response(request, cast(RateLimitExceeded, exc))

    async def _handle_missing_identity(self, request: Request, exc: Exception) -> Response:
        return self._missing_identity_response(cast(MissingIdentityError, exc))

    def global_rules(self, request: Request) -> list[LimitRule]:
        """Return ad-hoc rules for application and default limits."""
        rules: list[LimitRule] = []
        if self._application_items:
            rules.append(
                LimitRule(
                    name="__application__",
                    limit=list(self._application_items),
                    scope="__application__",
                )
            )
        if self._default_items:
            path = request.url.path
            rules.append(
                LimitRule(
                    name="__default__",
                    limit=list(self._default_items),
                    scope=f"__default__:{path}",
                )
            )
        return rules

    @property
    def header_config(self) -> HeaderConfig:
        """Return the response header configuration."""
        return self._header_config

    @staticmethod
    def _most_restrictive(current: WindowStats | None, candidate: WindowStats) -> WindowStats:
        if current is None or candidate.remaining < current.remaining:
            return candidate
        return current

    @staticmethod
    async def _resolve_cost(cost: int | CostFunc, request: Request) -> int:
        if callable(cost):
            value = cost(request)
            if isawaitable(value):
                value = await value
            return int(value)
        return int(cost)

    @staticmethod
    async def _is_exempt_when(exempt_when: ExemptFunc | None, request: Request) -> bool:
        if exempt_when is None:
            return False
        result = exempt_when(request)
        if isawaitable(result):
            result = await result
        return bool(result)


def _locate_request_param(func: Callable[..., Any]) -> str:
    """Return the name of the ``Request`` parameter in ``func``'s signature."""
    signature = inspect.signature(func)
    fallback: str | None = None
    for param_name, param in signature.parameters.items():
        annotation = param.annotation
        if annotation is Request:
            return param_name
        if isinstance(annotation, str) and annotation.split(".")[-1] == "Request":
            return param_name
        if param_name == "request":
            fallback = param_name
    if fallback is not None:
        return fallback
    raise ConfigurationError(
        f"{func.__qualname__} must declare a 'request: Request' parameter to use @limiter.limit"
    )


def _extract_request(args: tuple[Any, ...], kwargs: dict[str, Any], name: str) -> Request:
    """Find the :class:`Request` instance passed to a decorated endpoint."""
    candidate = kwargs.get(name)
    if isinstance(candidate, Request):
        return candidate
    for value in (*kwargs.values(), *args):
        if isinstance(value, Request):
            return value
    raise ConfigurationError("Could not find a Request argument in the endpoint call")
