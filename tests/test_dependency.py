from __future__ import annotations

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from fastapi_limiterx import Limiter, RateLimiter


def test_dependency_blocks_after_limit() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)

    @app.get("/report", dependencies=[Depends(RateLimiter("2/minute"))])
    async def report() -> dict[str, str]:
        return {"ok": "report"}

    client = TestClient(app)
    assert client.get("/report").status_code == 200
    assert client.get("/report").status_code == 200
    assert client.get("/report").status_code == 429


def test_stacked_dependencies() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)

    @app.get(
        "/expensive",
        dependencies=[
            Depends(RateLimiter("5/minute")),
            Depends(RateLimiter("1/minute")),
        ],
    )
    async def expensive() -> dict[str, str]:
        return {"ok": "expensive"}

    client = TestClient(app)
    assert client.get("/expensive").status_code == 200
    assert client.get("/expensive").status_code == 429


def test_dependency_bound_limiter() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)
    guard = RateLimiter("1/minute", limiter=limiter)

    @app.get("/bound", dependencies=[Depends(guard)])
    async def bound() -> dict[str, str]:
        return {"ok": "bound"}

    client = TestClient(app)
    assert client.get("/bound").status_code == 200
    assert client.get("/bound").status_code == 429


def test_dependency_update_at_runtime() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)
    guard = RateLimiter("5/minute", limiter=limiter)

    @app.get("/dyn", dependencies=[Depends(guard)])
    async def dyn() -> dict[str, str]:
        return {"ok": "dyn"}

    client = TestClient(app)
    assert client.get("/dyn").status_code == 200
    guard.update("1/minute")
    assert client.get("/dyn").status_code == 200
    assert client.get("/dyn").status_code == 429
