from __future__ import annotations

import pytest

from fastapi_limiterx.backends.base import BaseStorage
from fastapi_limiterx.rate import parse
from fastapi_limiterx.strategies import create_strategy


@pytest.mark.parametrize("strategy_name", ["fixed_window", "sliding_window", "moving_window"])
async def test_window_allows_then_blocks(backend: BaseStorage, strategy_name: str) -> None:
    strategy = create_strategy(strategy_name, backend)
    item = parse("3/minute")
    results = [await strategy.hit(item, "client") for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[-1].stats.retry_after > 0


@pytest.mark.parametrize("strategy_name", ["fixed_window", "sliding_window", "moving_window"])
async def test_remaining_decreases(backend: BaseStorage, strategy_name: str) -> None:
    strategy = create_strategy(strategy_name, backend)
    item = parse("5/minute")
    first = await strategy.hit(item, "client")
    assert first.stats.limit == 5
    assert first.stats.remaining == 4
    second = await strategy.hit(item, "client")
    assert second.stats.remaining == 3


@pytest.mark.parametrize("strategy_name", ["fixed_window", "sliding_window", "moving_window"])
async def test_peek_does_not_consume(backend: BaseStorage, strategy_name: str) -> None:
    strategy = create_strategy(strategy_name, backend)
    item = parse("2/minute")
    await strategy.hit(item, "client")
    peek_one = await strategy.peek(item, "client")
    peek_two = await strategy.peek(item, "client")
    assert peek_one.remaining == peek_two.remaining == 1


async def test_token_bucket_burst(backend: BaseStorage) -> None:
    strategy = create_strategy("token_bucket", backend)
    item = parse("1/second")
    results = [await strategy.hit(item, "client", burst=3) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[0].stats.limit == 3


async def test_cost_consumes_multiple(backend: BaseStorage) -> None:
    strategy = create_strategy("fixed_window", backend)
    item = parse("10/minute")
    result = await strategy.hit(item, "client", cost=4)
    assert result.allowed is True
    assert result.stats.remaining == 6


async def test_independent_keys(backend: BaseStorage) -> None:
    strategy = create_strategy("fixed_window", backend)
    item = parse("1/minute")
    assert (await strategy.hit(item, "a")).allowed is True
    assert (await strategy.hit(item, "b")).allowed is True
    assert (await strategy.hit(item, "a")).allowed is False
