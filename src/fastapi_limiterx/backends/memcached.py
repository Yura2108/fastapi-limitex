from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING, Any

from fastapi_limiterx.backends.base import BaseStorage, TokenBucketState, now
from fastapi_limiterx.errors import BackendNotInstalledError, UnsupportedOperationError

if TYPE_CHECKING:
    import aiomcache

_CAS_RETRIES = 8


class MemcachedStorage(BaseStorage):
    """Distributed storage backed by Memcached.

    Provide either a ``host``/``port`` pair or an existing ``client``. A supplied
    client is not closed by :meth:`close`.

    Args:
        host: Memcached server host.
        port: Memcached server port.
        client: A pre-configured ``aiomcache.Client`` instance.
        prefix: A namespace prepended to every key before hashing.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11211,
        *,
        client: aiomcache.Client | None = None,
        prefix: str = "limiterx",
    ) -> None:
        self._host = host
        self._port = port
        self._client_obj: Any = client
        self._owns_client = client is None
        self.prefix = prefix

    @property
    def _client(self) -> Any:
        if self._client_obj is None:
            raise RuntimeError("MemcachedStorage.setup() must be awaited before use")
        return self._client_obj

    def _key(self, key: str) -> bytes:
        digest = hashlib.sha1(f"{self.prefix}:{key}".encode()).hexdigest()
        return digest.encode("ascii")

    async def setup(self) -> None:
        if self._client_obj is None:
            try:
                import aiomcache
            except ImportError as exc:  # pragma: no cover - import guard
                raise BackendNotInstalledError(
                    "The memcached backend requires the 'aiomcache' package. "
                    "Install it with: pip install 'fastapi-limitex[memcached]'"
                ) from exc
            self._client_obj = aiomcache.Client(self._host, self._port)

    async def close(self) -> None:
        if self._client_obj is not None and self._owns_client:
            await self._client_obj.close()
            self._client_obj = None

    async def check(self) -> bool:
        try:
            await self._client.version()
            return True
        except Exception:
            return False

    async def reset(self, key: str) -> None:
        await self._client.delete(self._key(key))
        await self._client.delete(self._key(f"{key}\x00exp"))

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
        storage_key = self._key(key)
        created = await self._client.add(storage_key, b"0", exptime=expiry)
        if created:
            await self._client.set(
                self._key(f"{key}\x00exp"),
                str(now() + expiry).encode("ascii"),
                exptime=expiry,
            )
        elif elastic_expiry:
            await self._client.touch(storage_key, expiry)
        value = await self._client.incr(storage_key, amount)
        return int(value) if value is not None else amount

    async def get_expiry(self, key: str) -> float:
        value = await self._client.get(self._key(f"{key}\x00exp"))
        if value is None:
            return now()
        return float(value)

    async def acquire_entry(self, key: str, limit: int, expiry: int, amount: int = 1) -> bool:
        raise UnsupportedOperationError(
            "The memcached backend does not support the moving window strategy. "
            "Use fixed_window, sliding_window or token_bucket instead."
        )

    async def get_num_acquired(self, key: str, expiry: int) -> int:
        raise UnsupportedOperationError(
            "The memcached backend does not support the moving window strategy."
        )

    async def get_oldest_entry(self, key: str, expiry: int) -> float | None:
        raise UnsupportedOperationError(
            "The memcached backend does not support the moving window strategy."
        )

    async def take_token(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        amount: float = 1.0,
    ) -> TokenBucketState:
        storage_key = self._key(key)
        ttl = math.ceil(capacity / refill_rate) if refill_rate > 0 else 60
        for _ in range(_CAS_RETRIES):
            value, cas_token = await self._client.gets(storage_key)
            current = now()
            if value is None:
                allowed = capacity >= amount
                stored = capacity - amount if allowed else capacity
                payload = f"{stored}:{current}".encode("ascii")
                if await self._client.add(storage_key, payload, exptime=ttl):
                    return self._token_state(allowed, stored, capacity, refill_rate, amount)
                continue
            stored_tokens, ts = (float(part) for part in value.split(b":"))
            tokens = min(capacity, stored_tokens + (current - ts) * refill_rate)
            allowed = tokens >= amount
            new_tokens = tokens - amount if allowed else tokens
            payload = f"{new_tokens}:{current}".encode("ascii")
            if await self._client.cas(storage_key, payload, cas_token, exptime=ttl):
                return self._token_state(allowed, new_tokens, capacity, refill_rate, amount)
        return TokenBucketState(False, 0.0, ttl, ttl)

    @staticmethod
    def _token_state(
        allowed: bool,
        tokens: float,
        capacity: float,
        refill_rate: float,
        amount: float,
    ) -> TokenBucketState:
        reset_after = (capacity - tokens) / refill_rate if refill_rate > 0 else 0.0
        retry_after = 0.0 if allowed else (amount - tokens) / refill_rate
        return TokenBucketState(allowed, tokens, reset_after, retry_after)
