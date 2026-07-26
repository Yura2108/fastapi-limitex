from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limitex import Limiter, RateLimiter, limit


def test_decorator_on_apirouter() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter()

    @router.get("/items")
    @limiter.limit("2/minute")
    async def items(request: Request) -> dict[str, str]:
        return {"ok": "items"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/items").status_code == 200
    assert client.get("/items").status_code == 200
    assert client.get("/items").status_code == 429


def test_decorator_on_apirouter_with_prefix() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter(prefix="/api/v1")

    @router.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/api/v1/ping").status_code == 429


def test_sync_decorator_on_apirouter() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter()

    @router.get("/sync")
    @limiter.limit("1/minute")
    def sync_endpoint(request: Request) -> dict[str, str]:
        return {"ok": "sync"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/sync").status_code == 200
    assert client.get("/sync").status_code == 429


def test_two_routers_have_independent_buckets() -> None:
    app = FastAPI()
    limiter = Limiter()
    router_a = APIRouter(prefix="/a")
    router_b = APIRouter(prefix="/b")

    @router_a.get("/ping")
    @limiter.limit("1/minute")
    async def ping_a(request: Request) -> dict[str, str]:
        return {"ok": "a"}

    @router_b.get("/ping")
    @limiter.limit("1/minute")
    async def ping_b(request: Request) -> dict[str, str]:
        return {"ok": "b"}

    app.include_router(router_a)
    app.include_router(router_b)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/a/ping").status_code == 200
    assert client.get("/b/ping").status_code == 200
    assert client.get("/a/ping").status_code == 429
    assert client.get("/b/ping").status_code == 429


def test_router_level_dependency() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)
    router = APIRouter(dependencies=[Depends(RateLimiter("1/minute"))])

    @router.get("/guarded")
    async def guarded() -> dict[str, str]:
        return {"ok": "guarded"}

    app.include_router(router)

    client = TestClient(app)
    assert client.get("/guarded").status_code == 200
    assert client.get("/guarded").status_code == 429


def test_module_level_limit_resolves_from_app_state() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter()

    @router.get("/free")
    @limit("2/minute")
    async def free(request: Request) -> dict[str, str]:
        return {"ok": "free"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/free").status_code == 200
    assert client.get("/free").status_code == 200
    assert client.get("/free").status_code == 429


def test_module_level_limit_sync() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter()

    @router.get("/free-sync")
    @limit("1/minute")
    def free_sync(request: Request) -> dict[str, str]:
        return {"ok": "free-sync"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/free-sync").status_code == 200
    assert client.get("/free-sync").status_code == 429


def test_module_level_limit_runtime_edit() -> None:
    app = FastAPI()
    limiter = Limiter()
    router = APIRouter()

    @router.get("/dyn")
    @limit("5/minute", name="dyn")
    async def dyn(request: Request) -> dict[str, str]:
        return {"ok": "dyn"}

    app.include_router(router)
    limiter.attach(app)

    client = TestClient(app)
    assert client.get("/dyn").status_code == 200
    assert "dyn" in limiter.limit_names()
    limiter.set_limit("dyn", "1/minute")
    assert client.get("/dyn").status_code == 200
    assert client.get("/dyn").status_code == 429


def test_module_level_limit_without_attach_errors() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/x")
    @limit("1/minute")
    async def endpoint(request: Request) -> dict[str, str]:
        return {"ok": "x"}

    app.include_router(router)

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/x").status_code == 500
