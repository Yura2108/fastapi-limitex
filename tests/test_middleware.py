from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from fastapi_limitex import Exemptions, Limiter


def test_application_limit_shared_across_paths() -> None:
    app = FastAPI()
    limiter = Limiter(application_limits="2/minute")
    limiter.attach(app)

    @app.get("/a")
    async def a() -> dict[str, str]:
        return {"ok": "a"}

    @app.get("/b")
    async def b() -> dict[str, str]:
        return {"ok": "b"}

    client = TestClient(app)
    assert client.get("/a").status_code == 200
    assert client.get("/b").status_code == 200
    assert client.get("/a").status_code == 429


def test_default_limit_per_path() -> None:
    app = FastAPI()
    limiter = Limiter(default_limits="1/minute")
    limiter.attach(app)

    @app.get("/a")
    async def a() -> dict[str, str]:
        return {"ok": "a"}

    @app.get("/b")
    async def b() -> dict[str, str]:
        return {"ok": "b"}

    client = TestClient(app)
    assert client.get("/a").status_code == 200
    assert client.get("/a").status_code == 429
    assert client.get("/b").status_code == 200


def test_global_limit_exemption_by_path() -> None:
    app = FastAPI()
    exemptions = Exemptions(predicates=[lambda r: r.url.path == "/health"])
    limiter = Limiter(application_limits="1/minute", exemptions=exemptions)
    limiter.attach(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"ok": "health"}

    @app.get("/work")
    async def work() -> dict[str, str]:
        return {"ok": "work"}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/work").status_code == 200
    assert client.get("/work").status_code == 429


def test_global_limit_headers_present() -> None:
    app = FastAPI()
    limiter = Limiter(application_limits="5/minute")
    limiter.attach(app)

    @app.get("/a")
    async def a() -> dict[str, str]:
        return {"ok": "a"}

    client = TestClient(app)
    response = client.get("/a")
    assert response.headers["X-RateLimit-Limit"] == "5"
