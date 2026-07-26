from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from fastapi_limiterx import (
    EscalationPolicy,
    Exemptions,
    Limiter,
    RateLimiter,
    global_key,
)

app = FastAPI(title="fastapi-limitex example")

limiter = Limiter(
    default_limits="120/minute",
    strategy="fixed_window",
    escalation=EscalationPolicy(
        threshold=10,
        track_seconds=60,
        ban_seconds=300,
        penalty_limit="1/minute",
    ),
    exemptions=Exemptions(predicates=[lambda request: request.url.path == "/health"]),
)
limiter.attach(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Exempt from all limits via the exemption predicate above."""
    return {"status": "ok"}


@app.get("/ping")
@limiter.limit("5/minute")
async def ping(request: Request) -> dict[str, str]:
    """Per-IP fixed window limit using the decorator API."""
    return {"pong": "ok"}


@app.get("/burstable")
@limiter.limit("5/minute", strategy="token_bucket", burst=10)
async def burstable(request: Request) -> dict[str, str]:
    """Token bucket: sustained 5/minute with bursts of up to 10."""
    return {"pong": "burst"}


@app.get("/report", dependencies=[Depends(RateLimiter("2/minute"))])
async def report() -> dict[str, str]:
    """Dependency API, keeping the limit out of the function body."""
    return {"status": "report"}


@app.get("/global")
@limiter.limit("1000/minute", key_func=global_key)
async def global_endpoint(request: Request) -> dict[str, str]:
    """A single shared limit for every caller."""
    return {"scope": "global"}
