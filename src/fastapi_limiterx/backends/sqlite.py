from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi_limiterx.backends.base import BaseStorage, TokenBucketState, now
from fastapi_limiterx.errors import BackendNotInstalledError

if TYPE_CHECKING:
    import aiosqlite

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS counters ("
    "  key TEXT PRIMARY KEY, value INTEGER NOT NULL, reset_at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS logs (key TEXT NOT NULL, ts REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS logs_key_ts ON logs (key, ts)",
    "CREATE TABLE IF NOT EXISTS buckets ("
    "  key TEXT PRIMARY KEY, tokens REAL NOT NULL, ts REAL NOT NULL)",
)


class SQLiteStorage(BaseStorage):
    """Persistent storage backed by a SQLite database.

    Suitable for single-node deployments that need limits to survive restarts.
    Cross-process safety is provided by ``BEGIN IMMEDIATE`` write transactions.

    Args:
        path: Path to the database file. Use ``":memory:"`` for an ephemeral
            in-process database.
    """

    def __init__(self, path: str = "limiterx.sqlite3") -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SQLiteStorage.setup() must be awaited before use")
        return self._db

    async def setup(self) -> None:
        if self._db is not None:
            return
        try:
            import aiosqlite
        except ImportError as exc:  # pragma: no cover - import guard
            raise BackendNotInstalledError(
                "The sqlite backend requires the 'aiosqlite' package. "
                "Install it with: pip install 'fastapi-limitex[sqlite]'"
            ) from exc
        self._db = await aiosqlite.connect(self.path, isolation_level=None)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        for statement in _SCHEMA:
            await self._conn.execute(statement)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def check(self) -> bool:
        try:
            await self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def reset(self, key: str) -> None:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute("DELETE FROM counters WHERE key = ?", (key,))
                await self._conn.execute("DELETE FROM logs WHERE key = ?", (key,))
                await self._conn.execute("DELETE FROM buckets WHERE key = ?", (key,))
                await self._conn.execute("COMMIT")
            except Exception:  # pragma: no cover - defensive rollback
                await self._conn.execute("ROLLBACK")
                raise

    async def get(self, key: str) -> int:
        async with self._conn.execute(
            "SELECT value, reset_at FROM counters WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row[1] <= now():
            return 0
        return int(row[0])

    async def incr(
        self,
        key: str,
        expiry: int,
        amount: int = 1,
        elastic_expiry: bool = False,
    ) -> int:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                current = now()
                async with self._conn.execute(
                    "SELECT value, reset_at FROM counters WHERE key = ?", (key,)
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None or row[1] <= current:
                    value, reset_at = amount, current + expiry
                else:
                    value = int(row[0]) + amount
                    reset_at = current + expiry if elastic_expiry else float(row[1])
                await self._conn.execute(
                    "INSERT INTO counters (key, value, reset_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "reset_at = excluded.reset_at",
                    (key, value, reset_at),
                )
                await self._conn.execute("COMMIT")
                return value
            except Exception:  # pragma: no cover - defensive rollback
                await self._conn.execute("ROLLBACK")
                raise

    async def get_expiry(self, key: str) -> float:
        async with self._conn.execute(
            "SELECT reset_at FROM counters WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        current = now()
        if row is None or row[0] <= current:
            return current
        return float(row[0])

    async def acquire_entry(self, key: str, limit: int, expiry: int, amount: int = 1) -> bool:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                current = now()
                await self._conn.execute(
                    "DELETE FROM logs WHERE key = ? AND ts <= ?", (key, current - expiry)
                )
                async with self._conn.execute(
                    "SELECT COUNT(*) FROM logs WHERE key = ?", (key,)
                ) as cursor:
                    row = await cursor.fetchone()
                count = int(row[0]) if row else 0
                if count + amount > limit:
                    await self._conn.execute("COMMIT")
                    return False
                await self._conn.executemany(
                    "INSERT INTO logs (key, ts) VALUES (?, ?)",
                    [(key, current) for _ in range(amount)],
                )
                await self._conn.execute("COMMIT")
                return True
            except Exception:  # pragma: no cover - defensive rollback
                await self._conn.execute("ROLLBACK")
                raise

    async def get_num_acquired(self, key: str, expiry: int) -> int:
        async with self._lock:
            await self._conn.execute(
                "DELETE FROM logs WHERE key = ? AND ts <= ?", (key, now() - expiry)
            )
            async with self._conn.execute(
                "SELECT COUNT(*) FROM logs WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_oldest_entry(self, key: str, expiry: int) -> float | None:
        async with self._lock:
            await self._conn.execute(
                "DELETE FROM logs WHERE key = ? AND ts <= ?", (key, now() - expiry)
            )
            async with self._conn.execute(
                "SELECT MIN(ts) FROM logs WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    async def take_token(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        amount: float = 1.0,
    ) -> TokenBucketState:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                current = now()
                async with self._conn.execute(
                    "SELECT tokens, ts FROM buckets WHERE key = ?", (key,)
                ) as cursor:
                    row = await cursor.fetchone()
                tokens, ts = (float(row[0]), float(row[1])) if row else (capacity, current)
                tokens = min(capacity, tokens + (current - ts) * refill_rate)
                allowed = tokens >= amount
                if allowed:
                    tokens -= amount
                await self._conn.execute(
                    "INSERT INTO buckets (key, tokens, ts) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET tokens = excluded.tokens, ts = excluded.ts",
                    (key, tokens, current),
                )
                await self._conn.execute("COMMIT")
            except Exception:  # pragma: no cover - defensive rollback
                await self._conn.execute("ROLLBACK")
                raise
        reset_after = (capacity - tokens) / refill_rate if refill_rate > 0 else 0.0
        retry_after = 0.0 if allowed else (amount - tokens) / refill_rate
        return TokenBucketState(allowed, tokens, reset_after, retry_after)
