from __future__ import annotations

from fastapi_limitex.backends.base import BaseStorage
from fastapi_limitex.errors import ConfigurationError
from fastapi_limitex.strategies.base import HitResult, RateLimitStrategy, WindowStats
from fastapi_limitex.strategies.fixed_window import FixedWindowStrategy
from fastapi_limitex.strategies.moving_window import MovingWindowStrategy
from fastapi_limitex.strategies.sliding_window import SlidingWindowStrategy
from fastapi_limitex.strategies.token_bucket import TokenBucketStrategy

__all__ = [
    "FixedWindowStrategy",
    "HitResult",
    "MovingWindowStrategy",
    "RateLimitStrategy",
    "SlidingWindowStrategy",
    "TokenBucketStrategy",
    "WindowStats",
    "create_strategy",
]

_STRATEGIES: dict[str, type[RateLimitStrategy]] = {
    FixedWindowStrategy.name: FixedWindowStrategy,
    SlidingWindowStrategy.name: SlidingWindowStrategy,
    MovingWindowStrategy.name: MovingWindowStrategy,
    TokenBucketStrategy.name: TokenBucketStrategy,
}


def create_strategy(name: str, storage: BaseStorage) -> RateLimitStrategy:
    """Instantiate the strategy registered under ``name``.

    Raises:
        ConfigurationError: If ``name`` is not a known strategy.
    """
    try:
        strategy_cls = _STRATEGIES[name]
    except KeyError as exc:
        valid = ", ".join(sorted(_STRATEGIES))
        raise ConfigurationError(f"Unknown strategy {name!r}. Valid strategies: {valid}.") from exc
    return strategy_cls(storage)
