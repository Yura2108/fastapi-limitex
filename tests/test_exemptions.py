from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limiterx import Exemptions, Limiter


def header_key(request: Request) -> str:
    return request.headers.get("X-Client", "anonymous")


def test_exempt_by_ip() -> None:
    app = FastAPI()
    limiter = Limiter(exemptions=Exemptions(ips={"testclient"}))
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200


def test_exempt_by_key() -> None:
    app = FastAPI()
    limiter = Limiter(key_func=header_key, exemptions=Exemptions(keys={"vip"}))
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping", headers={"X-Client": "vip"}).status_code == 200
    assert client.get("/ping", headers={"X-Client": "vip"}).status_code == 200
    assert client.get("/ping", headers={"X-Client": "normal"}).status_code == 200
    assert client.get("/ping", headers={"X-Client": "normal"}).status_code == 429


def test_exempt_when_predicate() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute", exempt_when=lambda r: r.headers.get("X-Internal") == "1")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping", headers={"X-Internal": "1"}).status_code == 200
    assert client.get("/ping", headers={"X-Internal": "1"}).status_code == 200


def test_runtime_exemption() -> None:
    app = FastAPI()
    limiter = Limiter(key_func=header_key)
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping", headers={"X-Client": "bob"}).status_code == 200
    assert client.get("/ping", headers={"X-Client": "bob"}).status_code == 429
    limiter.exemptions.exempt_key("bob")
    assert client.get("/ping", headers={"X-Client": "bob"}).status_code == 200
