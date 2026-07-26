from __future__ import annotations

from typing import Any, cast

import pytest

from fastapi_limiterx.backends.base import now
from fastapi_limiterx.backends.memcached import MemcachedStorage
from fastapi_limiterx.errors import UnsupportedOperationError


class FakeMemcached:
    """A minimal in-process stand-in for ``aiomcache.Client``."""

    def __init__(self) -> None:
        self._data: dict[bytes, tuple[bytes, int]] = {}
        self._cas = 0

    async def get(self, key: bytes) -> bytes | None:
        entry = self._data.get(key)
        return entry[0] if entry else None

    async def set(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        self._cas += 1
        self._data[key] = (value, self._cas)
        return True

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        if key in self._data:
            return False
        self._cas += 1
        self._data[key] = (value, self._cas)
        return True

    async def incr(self, key: bytes, amount: int) -> int | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        new_value = int(entry[0]) + amount
        self._data[key] = (str(new_value).encode("ascii"), entry[1])
        return new_value

    async def touch(self, key: bytes, exptime: int) -> bool:
        return key in self._data

    async def delete(self, key: bytes) -> bool:
        return self._data.pop(key, None) is not None

    async def gets(self, key: bytes) -> tuple[bytes | None, int | None]:
        entry = self._data.get(key)
        if entry is None:
            return None, None
        return entry[0], entry[1]

    async def cas(self, key: bytes, value: bytes, cas_token: int, exptime: int = 0) -> bool:
        entry = self._data.get(key)
        if entry is None or entry[1] != cas_token:
            return False
        self._cas += 1
        self._data[key] = (value, self._cas)
        return True

    async def version(self) -> bytes:
        return b"fake"

    async def close(self) -> None:
        self._data.clear()


async def make_storage() -> MemcachedStorage:
    storage = MemcachedStorage(client=cast(Any, FakeMemcached()))
    await storage.setup()
    return storage


async def test_fixed_window_incr_and_get() -> None:
    storage = await make_storage()
    assert await storage.incr("k", 60) == 1
    assert await storage.incr("k", 60) == 2
    assert await storage.get("k") == 2
    assert await storage.get_expiry("k") > now()


async def test_reset() -> None:
    storage = await make_storage()
    await storage.incr("k", 60)
    await storage.reset("k")
    assert await storage.get("k") == 0


async def test_moving_window_unsupported() -> None:
    storage = await make_storage()
    with pytest.raises(UnsupportedOperationError):
        await storage.acquire_entry("k", 1, 60)
    with pytest.raises(UnsupportedOperationError):
        await storage.get_num_acquired("k", 60)
    with pytest.raises(UnsupportedOperationError):
        await storage.get_oldest_entry("k", 60)


async def test_token_bucket() -> None:
    storage = await make_storage()
    first = await storage.take_token("tb", capacity=2, refill_rate=1.0)
    second = await storage.take_token("tb", capacity=2, refill_rate=1.0)
    third = await storage.take_token("tb", capacity=2, refill_rate=1.0)
    assert first.allowed and second.allowed
    assert not third.allowed


async def test_token_bucket_peek() -> None:
    storage = await make_storage()
    peek = await storage.take_token("tb", capacity=3, refill_rate=1.0, amount=0.0)
    assert peek.remaining == 3
    assert peek.allowed is True


async def test_check() -> None:
    storage = await make_storage()
    assert await storage.check() is True


async def test_elastic_expiry_touch() -> None:
    storage = await make_storage()
    assert await storage.incr("k", 60) == 1
    assert await storage.incr("k", 60, elastic_expiry=True) == 2


async def test_get_expiry_missing_returns_now() -> None:
    storage = await make_storage()
    assert await storage.get_expiry("missing") <= now() + 1


class AlwaysContendingMemcached(FakeMemcached):
    """A fake whose optimistic writes always fail, forcing retry exhaustion."""

    async def add(self, key: bytes, value: bytes, exptime: int = 0) -> bool:
        return False

    async def cas(self, key: bytes, value: bytes, cas_token: int, exptime: int = 0) -> bool:
        return False


async def test_token_bucket_cas_exhaustion() -> None:
    storage = MemcachedStorage(client=cast(Any, AlwaysContendingMemcached()))
    await storage.setup()
    result = await storage.take_token("tb", capacity=5, refill_rate=1.0)
    assert result.allowed is False


async def test_default_client_setup_and_close() -> None:
    storage = MemcachedStorage()
    await storage.setup()
    assert storage.__class__.__name__ == "MemcachedStorage"
    await storage.close()
