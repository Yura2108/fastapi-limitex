from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

import fastapi_limiterx
from fastapi_limiterx import (
    ConfigurationError,
    EscalationPolicy,
    Exemptions,
    Limiter,
    MemoryStorage,
    get_ip_from_header,
    get_remote_address,
)
from fastapi_limiterx import backends as backends_pkg
from fastapi_limiterx.backends.base import now
from fastapi_limiterx.backends.memory import MemoryStorage as MemoryStorageImpl
from fastapi_limiterx.backends.redis import RedisStorage
from fastapi_limiterx.backends.sqlite import SQLiteStorage
from fastapi_limiterx.keys import resolve_key
from fastapi_limiterx.rate import parse
from fastapi_limiterx.registry import LimitRegistry, LimitRule
from fastapi_limiterx.strategies import create_strategy


def make_request(
    client: tuple[str, int] | None = ("1.2.3.4", 0), headers: dict[str, str] | None = None
) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "client": client, "headers": raw_headers, "method": "GET"})


def test_build_storage_from_uri() -> None:
    assert isinstance(Limiter(storage_uri="memory://").storage, MemoryStorageImpl)
    assert isinstance(Limiter(storage_uri="redis://localhost:6379/0").storage, RedisStorage)
    assert isinstance(Limiter(storage_uri="sqlite:///data.db").storage, SQLiteStorage)
    memcached = Limiter(storage_uri="memcached://localhost:11211").storage
    assert memcached.__class__.__name__ == "MemcachedStorage"


def test_build_storage_invalid_scheme() -> None:
    with pytest.raises(ConfigurationError):
        Limiter(storage_uri="mongodb://localhost")


def test_redis_storage_requires_url_or_client() -> None:
    with pytest.raises(ValueError, match="url or a client"):
        RedisStorage()


def test_create_strategy_unknown() -> None:
    with pytest.raises(ConfigurationError):
        create_strategy("nonsense", MemoryStorage())


def test_lazy_backend_getattr_error() -> None:
    with pytest.raises(AttributeError):
        backends_pkg.__getattr__("DoesNotExist")


def test_package_getattr_error() -> None:
    with pytest.raises(AttributeError):
        fastapi_limiterx.__getattr__("DoesNotExist")


def test_package_lazy_backend() -> None:
    assert fastapi_limiterx.SQLiteStorage is SQLiteStorage


async def test_async_context_manager() -> None:
    async with Limiter() as limiter:
        assert await limiter.storage.check() is True
    await limiter.startup()
    await limiter.shutdown()


async def test_peek_reports_stats() -> None:
    limiter = Limiter()

    @limiter.limit("5/minute", name="ep")
    async def endpoint(request: Request) -> dict[str, str]:
        return {}

    request = make_request()
    stats = await limiter.peek(request, "ep")
    assert stats is not None
    assert stats.limit == 5
    assert stats.remaining == 5


async def test_peek_unknown_returns_none() -> None:
    limiter = Limiter()
    assert await limiter.peek(make_request(), "missing") is None


def test_cost_integer() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/ping")
    @limiter.limit("10/minute", cost=5)
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    limiter.attach(app)
    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_cost_callable() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/ping")
    @limiter.limit("10/minute", cost=lambda r: int(r.headers.get("X-Cost", "1")))
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    limiter.attach(app)
    client = TestClient(app)
    assert client.get("/ping", headers={"X-Cost": "10"}).status_code == 200
    assert client.get("/ping", headers={"X-Cost": "1"}).status_code == 429


def test_per_method_buckets() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.api_route("/res", methods=["GET", "POST"])
    @limiter.limit("1/minute", per_method=True)
    async def res(request: Request) -> dict[str, str]:
        return {"ok": "res"}

    limiter.attach(app)
    client = TestClient(app)
    assert client.get("/res").status_code == 200
    assert client.post("/res").status_code == 200
    assert client.get("/res").status_code == 429


def test_methods_filter() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.api_route("/res", methods=["GET", "POST"])
    @limiter.limit("1/minute", methods=["POST"])
    async def res(request: Request) -> dict[str, str]:
        return {"ok": "res"}

    limiter.attach(app)
    client = TestClient(app)
    assert client.get("/res").status_code == 200
    assert client.get("/res").status_code == 200
    assert client.post("/res").status_code == 200
    assert client.post("/res").status_code == 429


def test_get_remote_address_no_client() -> None:
    assert get_remote_address(make_request(client=None)) == "testclient"


def test_ip_from_header_variants() -> None:
    key_func = get_ip_from_header("X-Forwarded-For", index=1)
    assert key_func(make_request(headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2"})) == "2.2.2.2"
    assert key_func(make_request()) == "1.2.3.4"
    assert key_func(make_request(headers={"X-Forwarded-For": " "})) == "1.2.3.4"


async def test_resolve_key_sync_and_async() -> None:
    request = make_request()
    assert await resolve_key(lambda r: "sync", request) == "sync"

    async def async_key(r: Request) -> str:
        return "async"

    assert await resolve_key(async_key, request) == "async"


def test_escalation_validation() -> None:
    with pytest.raises(ConfigurationError):
        EscalationPolicy(threshold=0, track_seconds=60, ban_seconds=60)


async def test_escalation_clear() -> None:
    policy = EscalationPolicy(threshold=1, track_seconds=60, ban_seconds=60)
    storage = MemoryStorage()
    await storage.setup()
    await policy.register_breach(storage, "client")
    assert await policy.is_banned(storage, "client") is True
    await policy.clear(storage, "client")
    assert await policy.is_banned(storage, "client") is False


def test_registry_set_limit_unknown() -> None:
    registry = LimitRegistry()
    with pytest.raises(KeyError):
        registry.set_limit("missing", "1/minute")


def test_registry_names_and_remove() -> None:
    registry = LimitRegistry()
    registry.add(LimitRule(name="a", limit="1/minute"))
    assert registry.names() == ["a"]
    registry.remove("a")
    assert registry.names() == []


async def test_token_bucket_peek_strategy() -> None:
    storage = MemoryStorage()
    await storage.setup()
    strategy = create_strategy("token_bucket", storage)
    item = parse("5/minute")
    stats = await strategy.peek(item, "client", burst=5)
    assert stats.limit == 5
    assert stats.remaining == 5


async def test_memory_eviction() -> None:
    storage = MemoryStorage(max_entries=3, prune_interval_ops=1000)
    await storage.setup()
    for index in range(5):
        await storage.incr(f"key-{index}", 60)
    live = 0
    for index in range(5):
        if await storage.get(f"key-{index}") > 0:
            live += 1
    assert live <= 3


def test_exemptions_removal() -> None:
    exemptions = Exemptions(ips={"1.1.1.1"}, keys={"k"})
    exemptions.remove_ip("1.1.1.1")
    exemptions.remove_key("k")
    assert exemptions.ips == set()
    assert exemptions.keys == set()


def test_rate_item_str_and_now() -> None:
    assert "per" in str(parse("5/minute"))
    assert now() > 0
