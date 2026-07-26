from __future__ import annotations

import asyncio

import pytest

from fastapi_limitex.backends.memory import MemoryStorage
from fastapi_limitex.backends.redis import RedisStorage


def test_memory_rejects_bad_max_entries() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        MemoryStorage(max_entries=0)


async def test_memory_prunes_expired() -> None:
    storage = MemoryStorage(prune_interval_ops=1)
    await storage.setup()
    await storage.incr("short", 1)
    await asyncio.sleep(1.1)
    await storage.incr("trigger", 60)
    assert await storage.get("short") == 0


async def test_redis_url_setup_and_close() -> None:
    storage = RedisStorage("redis://localhost:6399/0")
    await storage.setup()
    await storage.close()


async def test_redis_check_false_when_unreachable() -> None:
    storage = RedisStorage("redis://localhost:6399/0")
    await storage.setup()
    assert await storage.check() is False
    await storage.close()
