from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi_limiterx.backends.base import BaseStorage, TokenBucketState
from fastapi_limiterx.backends.memory import MemoryStorage
from fastapi_limiterx.dependencies import RateLimiter, WebSocketRateLimiter
from fastapi_limiterx.errors import (
    BackendNotInstalledError,
    ConfigurationError,
    FastAPILimiterError,
    MissingIdentityError,
    RateLimitExceeded,
    UnsupportedOperationError,
)
from fastapi_limiterx.escalation import EscalationPolicy
from fastapi_limiterx.exemptions import Exemptions
from fastapi_limiterx.keys import (
    get_ip_from_header,
    get_remote_address,
    global_key,
    user_key,
)
from fastapi_limiterx.limiter import Limiter
from fastapi_limiterx.middleware import RateLimiterMiddleware
from fastapi_limiterx.rate import RateLimitItem, parse, parse_many
from fastapi_limiterx.registry import LimitRule
from fastapi_limiterx.responses import HeaderConfig, default_response
from fastapi_limiterx.strategies import HitResult, WindowStats
from fastapi_limiterx.types import (
    BreachCallback,
    CostFunc,
    ExemptFunc,
    KeyFunc,
    RateLimitContext,
    ResponseBuilder,
)

if TYPE_CHECKING:
    from fastapi_limiterx.backends.memcached import MemcachedStorage
    from fastapi_limiterx.backends.redis import RedisStorage
    from fastapi_limiterx.backends.sqlite import SQLiteStorage

__version__ = "0.1.0"

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
    "parse",
    "parse_many",
    "user_key",
]

_LAZY_BACKENDS = {"RedisStorage", "MemcachedStorage", "SQLiteStorage"}


def __getattr__(name: str) -> Any:
    if name in _LAZY_BACKENDS:
        from fastapi_limiterx import backends

        return getattr(backends, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
