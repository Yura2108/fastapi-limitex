from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limitex import Limiter, get_ip_from_header, global_key, user_key


def extract_user(request: Request) -> str | None:
    return request.headers.get("X-User")


def make_app(limiter: Limiter) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    limiter.attach(app)
    return TestClient(app)


def test_user_key_separate_buckets() -> None:
    client = make_app(Limiter(key_func=user_key(extract_user, on_missing="ip")))
    assert client.get("/ping", headers={"X-User": "alice"}).status_code == 200
    assert client.get("/ping", headers={"X-User": "alice"}).status_code == 429
    assert client.get("/ping", headers={"X-User": "bob"}).status_code == 200


def test_user_key_fallback_to_ip() -> None:
    client = make_app(Limiter(key_func=user_key(extract_user, on_missing="ip")))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_user_key_anonymous_shared() -> None:
    client = make_app(Limiter(key_func=user_key(extract_user, on_missing="anonymous")))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_user_key_error_returns_401() -> None:
    client = make_app(Limiter(key_func=user_key(extract_user, on_missing="error")))
    assert client.get("/ping").status_code == 401
    assert client.get("/ping", headers={"X-User": "alice"}).status_code == 200


def test_global_key() -> None:
    client = make_app(Limiter(key_func=global_key))
    assert client.get("/ping", headers={"X-User": "alice"}).status_code == 200
    assert client.get("/ping", headers={"X-User": "bob"}).status_code == 429


def test_ip_from_header() -> None:
    client = make_app(Limiter(key_func=get_ip_from_header("X-Forwarded-For")))
    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_async_key_func() -> None:
    async def async_key(request: Request) -> str:
        return request.headers.get("X-Client", "anon")

    client = make_app(Limiter(key_func=async_key))
    assert client.get("/ping", headers={"X-Client": "a"}).status_code == 200
    assert client.get("/ping", headers={"X-Client": "a"}).status_code == 429
    assert client.get("/ping", headers={"X-Client": "b"}).status_code == 200
