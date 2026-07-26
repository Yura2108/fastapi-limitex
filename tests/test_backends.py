from __future__ import annotations

import asyncio

from fastapi_limiterx.backends.base import BaseStorage, now


async def test_incr_counts_and_expiry(backend: BaseStorage) -> None:
    assert await backend.incr("k", 60) == 1
    assert await backend.incr("k", 60) == 2
    assert await backend.incr("k", 60, amount=3) == 5
    assert await backend.get("k") == 5
    expiry = await backend.get_expiry("k")
    assert expiry > now()


async def test_get_missing_returns_zero(backend: BaseStorage) -> None:
    assert await backend.get("missing") == 0
    assert await backend.get_expiry("missing") <= now() + 1


async def test_reset(backend: BaseStorage) -> None:
    await backend.incr("k", 60)
    await backend.reset("k")
    assert await backend.get("k") == 0


async def test_acquire_entry_respects_limit(backend: BaseStorage) -> None:
    assert await backend.acquire_entry("log", limit=2, expiry=60) is True
    assert await backend.acquire_entry("log", limit=2, expiry=60) is True
    assert await backend.acquire_entry("log", limit=2, expiry=60) is False
    assert await backend.get_num_acquired("log", 60) == 2


async def test_acquire_entry_amount(backend: BaseStorage) -> None:
    assert await backend.acquire_entry("log", limit=5, expiry=60, amount=3) is True
    assert await backend.acquire_entry("log", limit=5, expiry=60, amount=3) is False
    assert await backend.get_num_acquired("log", 60) == 3


async def test_oldest_entry(backend: BaseStorage) -> None:
    assert await backend.get_oldest_entry("log", 60) is None
    await backend.acquire_entry("log", limit=5, expiry=60)
    oldest = await backend.get_oldest_entry("log", 60)
    assert oldest is not None
    assert oldest <= now()


async def test_moving_window_expires(backend: BaseStorage) -> None:
    assert await backend.acquire_entry("log", limit=1, expiry=1) is True
    assert await backend.acquire_entry("log", limit=1, expiry=1) is False
    await asyncio.sleep(1.1)
    assert await backend.get_num_acquired("log", 1) == 0
    assert await backend.acquire_entry("log", limit=1, expiry=1) is True


async def test_take_token_capacity_and_block(backend: BaseStorage) -> None:
    first = await backend.take_token("tb", capacity=2, refill_rate=1.0)
    second = await backend.take_token("tb", capacity=2, refill_rate=1.0)
    third = await backend.take_token("tb", capacity=2, refill_rate=1.0)
    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after > 0


async def test_take_token_peek_does_not_consume(backend: BaseStorage) -> None:
    peek = await backend.take_token("tb", capacity=3, refill_rate=1.0, amount=0.0)
    assert peek.allowed is True
    assert peek.remaining == 3
    consumed = await backend.take_token("tb", capacity=3, refill_rate=1.0, amount=1.0)
    assert consumed.remaining == 2


async def test_check(backend: BaseStorage) -> None:
    assert await backend.check() is True
