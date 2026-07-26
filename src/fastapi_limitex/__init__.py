from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi_limitex.backends.base import BaseStorage, TokenBucketState
from fastapi_limitex.backends.memory import MemoryStorage
from fastapi_limitex.dependencies import RateLimiter, WebSocketRateLimiter
from fastapi_limitex.errors import (
    BackendNotInstalledError,
    ConfigurationError,
    FastAPILimiterError,
    MissingIdentityError,
    RateLimitExceeded,
    UnsupportedOperationError,
)
from fastapi_limitex.escalation import EscalationPolicy
from fastapi_limitex.exemptions import Exemptions
from fastapi_limitex.keys import (
    get_ip_from_header,
    get_remote_address,
    global_key,
    user_key,
)
from fastapi_limitex.limiter import Limiter, limit
from fastapi_limitex.middleware import RateLimiterMiddleware
from fastapi_limitex.rate import RateLimitItem, parse, parse_many
from fastapi_limitex.registry import LimitRule
from fastapi_limitex.responses import HeaderConfig, default_response
from fastapi_limitex.strategies import HitResult, WindowStats
from fastapi_limitex.types import (
    BreachCallback,
    CostFunc,
    ExemptFunc,
    KeyFunc,
    RateLimitContext,
    ResponseBuilder,
)

if TYPE_CHECKING:
    from fastapi_limitex.backends.memcached import MemcachedStorage
    from fastapi_limitex.backends.redis import RedisStorage
    from fastapi_limitex.backends.sqlite import SQLiteStorage

__version__ = "1.1.0"

__all__ = [
    "BackendNotInstalledError",
    "BaseStorage",
    "BreachCallback",
    "ConfigurationError",
    "CostFunc",
    "EscalationPolicy",
    "ExemptFunc",
    "Exemptions",
    "FastAPILimiterError",
    "HeaderConfig",
    "HitResult",
    "KeyFunc",
    "LimitRule",
    "Limiter",
    "MemcachedStorage",
    "MemoryStorage",
    "MissingIdentityError",
    "RateLimitContext",
    "RateLimitExceeded",
    "RateLimitItem",
    "RateLimiter",
    "RateLimiterMiddleware",
    "RedisStorage",
    "ResponseBuilder",
    "SQLiteStorage",
    "TokenBucketState",
    "UnsupportedOperationError",
    "WebSocketRateLimiter",
    "WindowStats",
    "__version__",
    "default_response",
    "get_ip_from_header",
    "get_remote_address",
    "global_key",
    "limit",
    "parse",
    "parse_many",
    "user_key",
]

_LAZY_BACKENDS = {"RedisStorage", "MemcachedStorage", "SQLiteStorage"}


def __getattr__(name: str) -> Any:
    if name in _LAZY_BACKENDS:
        from fastapi_limitex import backends

        return getattr(backends, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
