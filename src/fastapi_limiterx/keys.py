from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Literal

from starlette.requests import Request

from fastapi_limiterx.errors import MissingIdentityError
from fastapi_limiterx.types import KeyFunc

OnMissing = Literal["ip", "anonymous", "error"]


def get_remote_address(request: Request) -> str:
    """Return the client IP as reported by the ASGI server (uvicorn).

    This deliberately trusts only ``request.client`` and ignores forwarding
    headers, which can be spoofed. Behind a trusted proxy, supply a custom key
    function or use :func:`get_ip_from_header`.
    """
    if request.client is None:
        return "testclient"
    return request.client.host


def get_ip_from_header(header: str = "X-Forwarded-For", index: int = 0) -> KeyFunc:
    """Build a key function that reads the client IP from a forwarding header.

    Only use this behind a proxy you control that overwrites the header.

    Args:
        header: The header to read.
        index: Which comma-separated entry to use (``0`` is the closest client).
    """

    def key_func(request: Request) -> str:
        value = request.headers.get(header)
        if not value:
            return get_remote_address(request)
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            return get_remote_address(request)
        return parts[min(index, len(parts) - 1)]

    return key_func


def global_key(request: Request) -> str:
    """Return a constant key so every request shares a single global limit."""
    return "global"


def user_key(
    extractor: Callable[[Request], str | Awaitable[str | None] | None],
    *,
    on_missing: OnMissing = "ip",
    prefix: str = "user",
) -> KeyFunc:
    """Build a key function that limits by an application user identity.

    Args:
        extractor: Returns the user identity for a request, or ``None`` when the
            request is unauthenticated. May be sync or async.
        on_missing: What to do when no identity is found. ``"ip"`` falls back to
            the client IP, ``"anonymous"`` shares one bucket across all
            anonymous callers, and ``"error"`` raises
            :class:`~fastapi_limiterx.errors.MissingIdentityError`.
        prefix: A namespace prepended to the identity.
    """

    async def key_func(request: Request) -> str:
        identity = extractor(request)
        if isawaitable(identity):
            identity = await identity
        if identity is None or identity == "":
            if on_missing == "ip":
                return f"ip:{get_remote_address(request)}"
            if on_missing == "anonymous":
                return f"{prefix}:anonymous"
            raise MissingIdentityError()
        return f"{prefix}:{identity}"

    return key_func


async def resolve_key(key_func: KeyFunc, request: Request) -> str:
    """Call ``key_func`` and await it if it returns a coroutine."""
    result = key_func(request)
    if isawaitable(result):
        return await result
    return result
