from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limiterx import Limiter
from fastapi_limiterx.errors import ConfigurationError


def build_client(limiter: Limiter, app: FastAPI) -> TestClient:
    limiter.attach(app)
    return TestClient(app)


def test_async_endpoint_blocks_after_limit() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/ping")
    @limiter.limit("2/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"pong": "ok"}

    client = build_client(limiter, app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert blocked.json()["detail"]


def test_sync_endpoint_supported() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/sync")
    @limiter.limit("1/minute")
    def sync_endpoint(request: Request) -> dict[str, str]:
        return {"pong": "sync"}

    client = build_client(limiter, app)
    assert client.get("/sync").status_code == 200
    assert client.get("/sync").status_code == 429


def test_success_headers_present() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/ping")
    @limiter.limit("5/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"pong": "ok"}

    client = build_client(limiter, app)
    response = client.get("/ping")
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"
    assert "X-RateLimit-Reset" in response.headers


def test_stacked_limits() -> None:
    app = FastAPI()
    limiter = Limiter()

    @app.get("/search")
    @limiter.limit("100/hour")
    @limiter.limit("2/minute")
    async def search(request: Request) -> dict[str, str]:
        return {"ok": "search"}

    client = build_client(limiter, app)
    assert client.get("/search").status_code == 200
    assert client.get("/search").status_code == 200
    assert client.get("/search").status_code == 429


def test_missing_request_param_raises() -> None:
    limiter = Limiter()

    try:

        @limiter.limit("1/minute")
        async def bad() -> dict[str, str]:
            return {}

    except ConfigurationError:
        return
    raise AssertionError("ConfigurationError was not raised")


def test_disabled_limiter_allows_all() -> None:
    app = FastAPI()
    limiter = Limiter(enabled=False)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"pong": "ok"}

    client = build_client(limiter, app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
