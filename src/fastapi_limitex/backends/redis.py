from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi_limitex.backends.base import BaseStorage, TokenBucketState, now
from fastapi_limitex.errors import BackendNotInstalledError

if TYPE_CHECKING:
    from redis.asyncio import Redis

_FIXED_WINDOW = """
local current = redis.call('INCRBY', KEYS[1], ARGV[1])
if current == tonumber(ARGV[1]) or ARGV[3] == '1' then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return current
"""

_MOVING_WINDOW = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local amount = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local count = redis.call('ZCARD', KEYS[1])
if count + amount > limit then
    return 0
end
for i = 1, amount do
    redis.call('ZADD', KEYS[1], now, ARGV[4 + i])
end
redis.call('EXPIRE', KEYS[1], math.ceil(window))
return 1
"""

_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local amount = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end
tokens = math.min(capacity, tokens + (now - ts) * rate)
local allowed = 0
if tokens >= amount then
    tokens = tokens - amount
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
local ttl = 1
if rate > 0 then
    ttl = math.ceil(capacity / rate)
end
redis.call('EXPIRE', KEYS[1], ttl)
return {allowed, tostring(tokens)}
"""


class RedisStorage(BaseStorage):
    """Distributed storage backed by Redis.

    Provide either a connection ``url`` or an existing async ``client``. When a
    client is supplied it is not closed by :meth:`close`.

    Args:
        url: A ``redis://`` connection URL.
        client: A pre-configured ``redis.asyncio.Redis`` instance.
        prefix: A namespace prepended to every key.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        client: Redis | None = None,
        prefix: str = "limitex",
    ) -> None:
        if url is None and client is None:
            raise ValueError("RedisStorage requires either a url or a client")
        self._url = url
        self._redis: Redis | None = client
        self._owns_client = client is None
        self.prefix = prefix
        self._fixed: Any = None
        self._moving: Any = None
        self._bucket: Any = None

    @property
    def _client(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("RedisStorage.setup() must be awaited before use")
        return self._redis

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def setup(self) -> None:
        if self._redis is None:
            if self._url is None:  # pragma: no cover - guarded by __init__
                raise ValueError("RedisStorage requires either a url or a client")
            try:
                from redis.asyncio import Redis as RedisClient
            except ImportError as exc:  # pragma: no cover - import guard
                raise BackendNotInstalledError(
                    "The redis backend requires the 'redis' package. "
                    "Install it with: pip install 'fastapi-limitex[redis]'"
                ) from exc
            self._redis = RedisClient.from_url(self._url, decode_responses=True)
        self._fixed = self._client.register_script(_FIXED_WINDOW)
        self._moving = self._client.register_script(_MOVING_WINDOW)
        self._bucket = self._client.register_script(_TOKEN_BUCKET)

    async def close(self) -> None:
        if self._redis is not None and self._owns_client:
            await self._redis.aclose()
            self._redis = None

    async def check(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def reset(self, key: str) -> None:
        await self._client.delete(self._key(key))

    async def get(self, key: str) -> int:
        value = await self._client.get(self._key(key))
        return int(value) if value is not None else 0

    async def incr(
        self,
        key: str,
        expiry: int,
        amount: int = 1,
        elastic_expiry: bool = False,
    ) -> int:
        result = await self._fixed(
            keys=[self._key(key)],
            args=[amount, expiry, "1" if elastic_expiry else "0"],
        )
        return int(result)

    async def get_expiry(self, key: str) -> float:
        pttl = await self._client.pttl(self._key(key))
        if pttl is None or pttl < 0:
            return now()
        return now() + pttl / 1000.0

    async def acquire_entry(self, key: str, limit: int, expiry: int, amount: int = 1) -> bool:
        members = [f"{now():.6f}-{uuid.uuid4().hex}" for _ in range(amount)]
        result = await self._moving(
            keys=[self._key(key)],
            args=[now(), expiry, limit, amount, *members],
        )
        return bool(int(result))

    async def get_num_acquired(self, key: str, expiry: int) -> int:
        redis_key = self._key(key)
        await self._client.zremrangebyscore(redis_key, 0, now() - expiry)
        return int(await self._client.zcard(redis_key))

    async def get_oldest_entry(self, key: str, expiry: int) -> float | None:
        redis_key = self._key(key)
        await self._client.zremrangebyscore(redis_key, 0, now() - expiry)
        entries = await self._client.zrange(redis_key, 0, 0, withscores=True)
        if not entries:
            return None
        return float(entries[0][1])

    async def take_token(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        amount: float = 1.0,
    ) -> TokenBucketState:
        allowed_raw, tokens_raw = await self._bucket(
            keys=[self._key(key)],
            args=[capacity, refill_rate, amount, now()],
        )
        allowed = bool(int(allowed_raw))
        tokens = float(tokens_raw)
        reset_after = (capacity - tokens) / refill_rate if refill_rate > 0 else 0.0
        retry_after = 0.0 if allowed else (amount - tokens) / refill_rate
        return TokenBucketState(allowed, tokens, reset_after, retry_after)
