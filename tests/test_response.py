from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response
from starlette.testclient import TestClient

from fastapi_limitex import HeaderConfig, Limiter, RateLimitContext


def make_app(limiter: Limiter) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    limiter.attach(app)
    return TestClient(app)


def test_custom_response_builder() -> None:
    def builder(request: Request, ctx: RateLimitContext) -> Response:
        return JSONResponse({"error": "slow down", "key": ctx.key}, status_code=429)

    client = make_app(Limiter(response_builder=builder))
    assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "slow down"


def test_headers_can_be_disabled() -> None:
    client = make_app(Limiter(headers=HeaderConfig(enabled=False)))
    response = client.get("/ping")
    assert "X-RateLimit-Limit" not in response.headers


def test_reset_as_seconds() -> None:
    client = make_app(Limiter(headers=HeaderConfig(reset_as_epoch=False)))
    response = client.get("/ping")
    assert int(response.headers["X-RateLimit-Reset"]) <= 60


def test_custom_header_names() -> None:
    config = HeaderConfig(limit="X-Limit", remaining="X-Remaining", reset="X-Reset")
    client = make_app(Limiter(headers=config))
    response = client.get("/ping")
    assert response.headers["X-Limit"] == "1"
    assert response.headers["X-Remaining"] == "0"
    assert "X-Reset" in response.headers
