from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi_limitex.backends.base import BaseStorage, TokenBucketState
from fastapi_limitex.backends.memory import MemoryStorage

if TYPE_CHECKING:
    from fastapi_limitex.backends.memcached import MemcachedStorage
    from fastapi_limitex.backends.redis import RedisStorage
    from fastapi_limitex.backends.sqlite import SQLiteStorage

__all__ = [
    "BaseStorage",
    "MemcachedStorage",
    "MemoryStorage",
    "RedisStorage",
    "SQLiteStorage",
    "TokenBucketState",
]

_LAZY: dict[str, tuple[str, str]] = {
    "RedisStorage": ("fastapi_limitex.backends.redis", "RedisStorage"),
    "MemcachedStorage": ("fastapi_limitex.backends.memcached", "MemcachedStorage"),
    "SQLiteStorage": ("fastapi_limitex.backends.sqlite", "SQLiteStorage"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib

        module_name, attr = _LAZY[name]
        module = importlib.import_module(module_name)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
