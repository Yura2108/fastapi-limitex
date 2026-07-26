from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limiterx import Limiter


def build(limiter: Limiter, limit: str, name: str) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    @limiter.limit(limit, name=name)
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    limiter.attach(app)
    return TestClient(app)


def test_set_limit_tightens() -> None:
    limiter = Limiter()
    client = build(limiter, "100/minute", "ep")
    assert client.get("/ping").status_code == 200
    limiter.set_limit("ep", "1/minute")
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_disable_and_enable_limit() -> None:
    limiter = Limiter()
    client = build(limiter, "1/minute", "ep")
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
    limiter.disable_limit("ep")
    assert client.get("/ping").status_code == 200
    limiter.enable_limit("ep")
    assert client.get("/ping").status_code == 429


def test_remove_limit() -> None:
    limiter = Limiter()
    client = build(limiter, "1/minute", "ep")
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
    limiter.remove_limit("ep")
    assert client.get("/ping").status_code == 200
    assert "ep" not in limiter.limit_names()


def test_master_switch() -> None:
    limiter = Limiter()
    client = build(limiter, "1/minute", "ep")
    limiter.disable()
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    limiter.enable()
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
