from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from starlette.requests import Request

from fastapi_limitex.rate import RateLimitItem, StaticLimit, parse_many
from fastapi_limitex.types import CostFunc, ExemptFunc, KeyFunc

LimitValue = StaticLimit | Callable[[Request], str]


@dataclass
class LimitRule:
    """A single configured limit and its per-limit overrides.

    Attributes:
        name: The identifier used to look up and edit this limit at runtime.
        limit: The limit expression, a parsed item, a list of them, or a
            callable that returns an expression for the current request.
        key_func: A per-limit key function overriding the limiter default.
        strategy: A per-limit strategy name overriding the limiter default.
        cost: How many units a request consumes, or a callable returning it.
        burst: Bucket capacity for the token bucket strategy.
        exempt_when: A predicate that skips this limit when it returns ``True``.
        per_method: When ``True``, each HTTP method gets an independent bucket.
        methods: If set, the limit only applies to these HTTP methods.
        scope: An explicit namespace to share a limit across endpoints.
        enabled: Whether the limit is currently active.
    """

    name: str
    limit: LimitValue
    key_func: KeyFunc | None = None
    strategy: str | None = None
    cost: int | CostFunc = 1
    burst: int | None = None
    exempt_when: ExemptFunc | None = None
    per_method: bool = False
    methods: frozenset[str] | None = None
    scope: str | None = None
    enabled: bool = True
    _cache: list[RateLimitItem] | None = field(init=False, default=None, repr=False)

    def resolve_items(self, request: Request) -> list[RateLimitItem]:
        """Return the parsed limits for ``request``, evaluating callables."""
        if callable(self.limit) and not isinstance(self.limit, RateLimitItem):
            return parse_many(self.limit(request))
        if self._cache is None:
            self._cache = parse_many(self.limit)
        return self._cache

    def update(self, limit: LimitValue) -> None:
        """Replace the limit value and invalidate any cached parse."""
        self.limit = limit
        self._cache = None


class LimitRegistry:
    """Stores limits by name and supports editing them without a restart."""

    def __init__(self) -> None:
        self._rules: dict[str, list[LimitRule]] = {}

    def add(self, rule: LimitRule) -> None:
        """Register ``rule`` under its name."""
        self._rules.setdefault(rule.name, []).append(rule)

    def get(self, name: str) -> list[LimitRule]:
        """Return every rule registered under ``name``."""
        return self._rules.get(name, [])

    def names(self) -> list[str]:
        """Return all registered names."""
        return list(self._rules)

    def set_limit(self, name: str, limit: LimitValue) -> None:
        """Change the limit value for every rule registered under ``name``.

        Raises:
            KeyError: If ``name`` has no registered rules.
        """
        rules = self._rules.get(name)
        if not rules:
            raise KeyError(name)
        for rule in rules:
            rule.update(limit)

    def enable(self, name: str) -> None:
        """Enable every rule registered under ``name``."""
        for rule in self._rules.get(name, []):
            rule.enabled = True

    def disable(self, name: str) -> None:
        """Disable every rule registered under ``name`` without removing it."""
        for rule in self._rules.get(name, []):
            rule.enabled = False

    def remove(self, name: str) -> None:
        """Remove every rule registered under ``name``.

        Removed rules are also disabled so that any decorator closures still
        holding a reference stop enforcing them.
        """
        for rule in self._rules.get(name, []):
            rule.enabled = False
        self._rules.pop(name, None)
