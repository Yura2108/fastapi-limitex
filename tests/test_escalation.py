from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from fastapi_limiterx import EscalationPolicy, Limiter, RateLimitContext


def test_hard_block_ban() -> None:
    app = FastAPI()
    limiter = Limiter(
        escalation=EscalationPolicy(
            threshold=1, track_seconds=60, ban_seconds=60, penalty_limit=None
        )
    )
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    first_block = client.get("/ping")
    assert first_block.status_code == 429
    banned = client.get("/ping")
    assert banned.status_code == 429
    assert "banned" in banned.json()["detail"].lower()


def test_penalty_limit_applies_during_ban() -> None:
    app = FastAPI()
    limiter = Limiter(
        escalation=EscalationPolicy(
            threshold=1, track_seconds=60, ban_seconds=60, penalty_limit="2/minute"
        )
    )
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_on_breach_callback_invoked() -> None:
    app = FastAPI()
    events: list[RateLimitContext] = []

    async def on_breach(ctx: RateLimitContext) -> None:
        events.append(ctx)

    limiter = Limiter(on_breach=on_breach)
    limiter.attach(app)

    @app.get("/ping")
    @limiter.limit("1/minute")
    async def ping(request: Request) -> dict[str, str]:
        return {"ok": "ping"}

    client = TestClient(app)
    client.get("/ping")
    client.get("/ping")
    assert len(events) == 1
    assert events[0].banned is False
    assert events[0].stats.limit == 1
