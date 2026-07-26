from __future__ import annotations

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import pytest_asyncio

from fastapi_limiterx.backends.base import BaseStorage
from fastapi_limiterx.backends.memory import MemoryStorage
from fastapi_limiterx.backends.redis import RedisStorage
from fastapi_limiterx.backends.sqlite import SQLiteStorage


@pytest_asyncio.fixture(params=["memory", "sqlite", "redis"])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[BaseStorage]:
    """Yield a set-up storage backend for each supported implementation."""
    client: fakeredis.aioredis.FakeRedis | None = None
    if request.param == "memory":
        storage: BaseStorage = MemoryStorage()
    elif request.param == "sqlite":
        storage = SQLiteStorage(":memory:")
    else:
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        storage = RedisStorage(client=client)
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()
        if client is not None:
            await client.aclose()


@pytest_asyncio.fixture
async def memory_backend() -> AsyncIterator[MemoryStorage]:
    """Yield an in-memory backend."""
    storage = MemoryStorage()
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()
