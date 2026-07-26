from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi_limiterx.backends.base import BaseStorage, TokenBucketState
from fastapi_limiterx.backends.memory import MemoryStorage

if TYPE_CHECKING:
    from fastapi_limiterx.backends.memcached import MemcachedStorage
    from fastapi_limiterx.backends.redis import RedisStorage
    from fastapi_limiterx.backends.sqlite import SQLiteStorage

__all__ = [
    "BaseStorage",
    "MemcachedStorage",
    "MemoryStorage",
    "RedisStorage",
    "SQLiteStorage",
    "TokenBucketState",
]

_LAZY: dict[str, tuple[str, str]] = {
    "RedisStorage": ("fastapi_limiterx.backends.redis", "RedisStorage"),
    "MemcachedStorage": ("fastapi_limiterx.backends.memcached", "MemcachedStorage"),
    "SQLiteStorage": ("fastapi_limiterx.backends.sqlite", "SQLiteStorage"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib

        module_name, attr = _LAZY[name]
        module = importlib.import_module(module_name)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
