from __future__ import annotations

from collections.abc import Iterable
from inspect import isawaitable

from starlette.requests import Request

from fastapi_limiterx.keys import get_remote_address
from fastapi_limiterx.types import ExemptFunc


class Exemptions:
    """A mutable collection of exemption rules.

    Requests are exempt when their client IP is in :attr:`ips`, their resolved
    key is in :attr:`keys`, or any registered predicate returns ``True``. All
    collections may be edited at runtime.

    Args:
        ips: IP addresses that are never limited.
        keys: Resolved keys (for example ``"user:42"``) that are never limited.
        predicates: Callables that exempt a request when they return ``True``.
    """

    def __init__(
        self,
        ips: Iterable[str] | None = None,
        keys: Iterable[str] | None = None,
        predicates: Iterable[ExemptFunc] | None = None,
    ) -> None:
        self.ips: set[str] = set(ips or ())
        self.keys: set[str] = set(keys or ())
        self.predicates: list[ExemptFunc] = list(predicates or ())

    def exempt_ip(self, ip: str) -> None:
        """Exempt an IP address from all limits."""
        self.ips.add(ip)

    def remove_ip(self, ip: str) -> None:
        """Stop exempting an IP address."""
        self.ips.discard(ip)

    def exempt_key(self, key: str) -> None:
        """Exempt a resolved key (such as a user key) from all limits."""
        self.keys.add(key)

    def remove_key(self, key: str) -> None:
        """Stop exempting a resolved key."""
        self.keys.discard(key)

    def add_predicate(self, predicate: ExemptFunc) -> None:
        """Register a predicate that can exempt requests dynamically."""
        self.predicates.append(predicate)

    async def is_exempt(self, request: Request, key: str) -> bool:
        """Return ``True`` when ``request`` should bypass rate limiting."""
        if self.ips and get_remote_address(request) in self.ips:
            return True
        if key in self.keys:
            return True
        for predicate in self.predicates:
            result = predicate(request)
            if isawaitable(result):
                result = await result
            if result:
                return True
        return False
