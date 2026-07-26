# fastapi-limitex

[![CI](https://github.com/Yura2108/fastapi-limitex/actions/workflows/ci.yml/badge.svg)](https://github.com/Yura2108/fastapi-limitex/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Yura2108/fastapi-limitex/branch/main/graph/badge.svg)](https://codecov.io/gh/Yura2108/fastapi-limitex)
[![PyPI version](https://img.shields.io/pypi/v/fastapi-limitex.svg)](https://pypi.org/project/fastapi-limitex/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastapi-limitex.svg)](https://pypi.org/project/fastapi-limitex/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Flexible, backend-agnostic rate limiting for FastAPI and Starlette.**

`fastapi-limitex` combines the ergonomics of a `slowapi`-style decorator with
the atomic, distributed backends of `fastapi-limiter`, and adds much more:
pluggable async storage, four algorithms, escalating bans, runtime-editable
limits and fully customizable responses.

```python
from fastapi import FastAPI, Request
from fastapi_limitex import Limiter

app = FastAPI()
limiter = Limiter()
limiter.attach(app)


@app.get("/ping")
@limiter.limit("5/minute")
async def ping(request: Request) -> dict[str, str]:
    return {"pong": "ok"}
```

---

## Table of contents

- [Features](#features)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Two ways to apply a limit](#two-ways-to-apply-a-limit)
- [Using APIRouter and avoiding circular imports](#using-apirouter-and-avoiding-circular-imports)
- [Storage backends](#storage-backends)
- [Algorithms](#algorithms)
- [Key strategies](#key-strategies)
- [Escalating bans](#escalating-bans)
- [Editing limits at runtime](#editing-limits-at-runtime)
- [Customizing the response](#customizing-the-response)
- [Exemptions](#exemptions)
- [Global and default limits](#global-and-default-limits)
- [WebSockets](#websockets)
- [Configuration reference](#configuration-reference)
- [Development](#development)
- [License](#license)

## Features

- **Two APIs.** A `slowapi`-style decorator (`@limiter.limit("5/minute")`) as the
  default, plus a `fastapi-limiter`-style dependency
  (`Depends(RateLimiter("5/minute"))`).
- **Pluggable async backends.** In-memory (default, zero dependencies), Redis,
  Memcached and SQLite — each installed as an optional extra.
- **Four algorithms.** `fixed_window` (default), `sliding_window`,
  `moving_window` and `token_bucket` (moving window + burst).
- **Escalating bans.** Temporarily tighten limits for clients that keep abusing
  your API, with a callback for your own logging or alerting.
- **Runtime editing.** Change limits without redeploying.
- **Customizable everything.** Key functions, responses, headers, costs and
  exemptions are all configurable, never hard-coded.
- **Sync and async endpoints.** Both `def` and `async def` are supported.
- **Fully typed.** Ships with `py.typed` and passes `mypy --strict`.

## Installation

```bash
# In-memory only (no extra dependencies)
pip install fastapi-limitex

# With a specific backend
pip install "fastapi-limitex[redis]"
pip install "fastapi-limitex[memcached]"
pip install "fastapi-limitex[sqlite]"

# Everything
pip install "fastapi-limitex[all]"
```

Using [uv](https://docs.astral.sh/uv/):

```bash
uv add "fastapi-limitex[redis]"
```

## Quickstart

```python
from fastapi import FastAPI, Request
from fastapi_limitex import Limiter

app = FastAPI()
limiter = Limiter()  # in-memory, fixed window, per-IP
limiter.attach(app)  # registers handlers + middleware


@app.get("/ping")
@limiter.limit("5/minute")
async def ping(request: Request) -> dict[str, str]:
    return {"pong": "ok"}
```

`limiter.attach(app)` registers the exception handler that turns a breach into a
`429` response, installs the middleware that injects rate limit headers, and
makes the limiter discoverable by the dependency API. The storage backend is
initialized lazily on first use, so no lifespan wiring is required for the
in-memory backend.

> The decorated endpoint **must** declare a `request: Request` parameter. The
> limiter uses it to identify the caller.

## Two ways to apply a limit

### Decorator (default)

```python
@app.get("/items")
@limiter.limit("10/minute")
async def list_items(request: Request) -> list[str]:
    return ["a", "b"]
```

Stack decorators to apply several limits at once:

```python
@app.get("/search")
@limiter.limit("5/second")
@limiter.limit("100/hour")
async def search(request: Request) -> dict[str, int]:
    return {"results": 0}
```

### Dependency

Prefer dependencies when you want to keep limits out of the function body, or to
apply them to whole routers:

```python
from fastapi import Depends
from fastapi_limitex import RateLimiter


@app.get("/report", dependencies=[Depends(RateLimiter("2/#minute"))])
async def report() -> dict[str, str]:
    return {"status": "ok"}
```

Stack several dependencies for multiple limits (put the strictest first):

```python
@app.get(
    "/expensive",
    dependencies=[
        Depends(RateLimiter("1/second")),
        Depends(RateLimiter("30/minute")),
    ],
)
async def expensive() -> dict[str, str]:
    return {"status": "ok"}
```

The dependency API requires `limiter.attach(app)` (so the exception handler is
registered), or you can bind a limiter explicitly with
`RateLimiter("2/minute", limiter=limiter)`.

## Using APIRouter and avoiding circular imports

Everything works with `APIRouter`. Put the router decorator on top and the
limit decorator directly below it:

```python
from fastapi import APIRouter, Request
from fastapi_limitex import limit

router = APIRouter(prefix="/api")


@router.get("/items")
@limit("5/minute")
async def items(request: Request) -> list[str]:
    return ["a", "b"]
```

In a real project the app and the limiter live in `main.py`, while routers live
in their own modules. Importing the limiter from `main.py` into a router would
create a **circular import** (`main` imports the router, the router imports
`main`). There are three ways to avoid it.

### Option 1: the module-level `limit` decorator (no import of the limiter)

`limit(...)` resolves the limiter from `request.app.state.limiter` at request
time, so a router never imports the limiter instance at all:

```python
# app/routers/items.py
from fastapi import APIRouter, Request
from fastapi_limitex import limit

router = APIRouter()


@router.get("/items")
@limit("5/minute")
async def items(request: Request) -> list[str]:
    return ["a", "b"]
```

```python
# app/main.py
from fastapi import FastAPI
from fastapi_limitex import Limiter

from app.routers import items

app = FastAPI()
limiter = Limiter()
limiter.attach(app)              # makes the limiter discoverable to @limit
app.include_router(items.router)
```

### Option 2: the dependency API (also no import of the limiter)

`RateLimiter(...)` resolves the limiter the same way, so it is equally
import-safe:

```python
# app/routers/report.py
from fastapi import APIRouter, Depends
from fastapi_limitex import RateLimiter

router = APIRouter()


@router.get("/report", dependencies=[Depends(RateLimiter("2/minute"))])
async def report() -> dict[str, str]:
    return {"status": "ok"}
```

You can also rate limit an entire router:

```python
router = APIRouter(dependencies=[Depends(RateLimiter("100/minute"))])
```

### Option 3: keep the limiter in its own module

If you prefer the bound `@limiter.limit`, define the limiter in a small leaf
module that imports nothing else from your app, then import it anywhere:

```python
# app/limiter.py
from fastapi_limitex import Limiter

limiter = Limiter()
```

```python
# app/routers/items.py
from fastapi import APIRouter, Request

from app.limiter import limiter

router = APIRouter()


@router.get("/items")
@limiter.limit("5/minute")
async def items(request: Request) -> list[str]:
    return ["a", "b"]
```

```python
# app/main.py
from fastapi import FastAPI

from app.limiter import limiter
from app.routers import items

app = FastAPI()
limiter.attach(app)
app.include_router(items.router)
```

> Whichever option you choose, put `@router.get(...)` **above** the limit
> decorator so FastAPI registers the wrapped endpoint.

## Storage backends

The default backend is **in-memory** and requires no extra dependencies. All
backends are async and their connection settings are fully configurable.

### In-memory (default)

State lives in the process and is bounded by entry count and TTL. Great for a
single process, development and tests.

```python
from fastapi_limitex import Limiter, MemoryStorage

limiter = Limiter(storage=MemoryStorage(max_entries=50_000))
```

| Option | Default | Meaning |
| --- | --- | --- |
| `max_entries` | `10_000` | Maximum distinct keys; least-recently-used keys are evicted. |
| `prune_interval_ops` | `256` | How often expired entries are swept. |

### Redis

```python
from fastapi_limitex import Limiter, RedisStorage

limiter = Limiter(storage=RedisStorage("redis://localhost:6379/0"))
# or reuse an existing client:
# limiter = Limiter(storage=RedisStorage(client=my_redis))
# or via URI:
# limiter = Limiter(storage_uri="redis://localhost:6379/0")
```

Uses atomic Lua scripts, so counts are correct across many workers and hosts.
Keys are namespaced with a configurable `prefix` (default `"limitex"`) and
expire automatically via Redis TTLs.

### Memcached

```python
from fastapi_limitex import Limiter, MemcachedStorage

limiter = Limiter(storage=MemcachedStorage("localhost", 11211))
```

Supports `fixed_window`, `sliding_window` and `token_bucket`. The
`moving_window` strategy is **not** available on Memcached (it has no sorted
structures); use one of the others.

### SQLite

```python
from fastapi_limitex import Limiter, SQLiteStorage

limiter = Limiter(storage=SQLiteStorage("limitex.sqlite3"))
# in-memory database: SQLiteStorage(":memory:")
```

Persists across restarts and is safe for multiple processes on one host via
`BEGIN IMMEDIATE` write transactions.

### Backend capability matrix

| Backend | fixed_window | sliding_window | moving_window | token_bucket | Shared across processes |
| --- | :---: | :---: | :---: | :---: | :---: |
| Memory | ✅ | ✅ | ✅ | ✅ | ❌ |
| Redis | ✅ | ✅ | ✅ | ✅ | ✅ |
| SQLite | ✅ | ✅ | ✅ | ✅ | ✅ (single host) |
| Memcached | ✅ | ✅ | ❌ | ✅ | ✅ |

## Algorithms

Choose a default at the limiter level, or override per limit with
`strategy=...`.

```python
limiter = Limiter(strategy="sliding_window")


@app.get("/a")
@limiter.limit("10/minute", strategy="moving_window")
async def a(request: Request) -> dict[str, str]:
    return {"ok": "a"}
```

| Strategy | Description |
| --- | --- |
| `fixed_window` (default) | One counter per window. Cheapest; can allow a burst at window edges. |
| `sliding_window` | Weighted blend of the current and previous windows; smooths edges. |
| `moving_window` | Exact log of timestamps; never exceeds the limit. Most precise. |
| `token_bucket` | Steady refill (`amount/period`) with a burst capacity. |

### Token bucket with burst

The bucket refills at `amount / period` tokens per second and holds up to
`burst` tokens (defaulting to `amount`). This lets a client spike briefly while
keeping the long-term average bounded.

```python
# Sustained 5/minute, but allow bursts of up to 10 requests.
@app.get("/burstable")
@limiter.limit("5/minute", strategy="token_bucket", burst=10)
async def burstable(request: Request) -> dict[str, str]:
    return {"ok": "burst"}
```

## Key strategies

### Per-IP (default)

By default clients are identified by the IP address reported by the ASGI server
(uvicorn). Forwarding headers such as `X-Forwarded-For` are **not** trusted by
default because they can be spoofed.

Behind a proxy you control, opt in explicitly:

```python
from fastapi_limitex import Limiter, get_ip_from_header

limiter = Limiter(key_func=get_ip_from_header("X-Forwarded-For"))
```

### Per-user

```python
from fastapi_limitex import Limiter, user_key


def current_user(request: Request) -> str | None:
    return getattr(request.state, "user_id", None)


# Fall back to IP for anonymous callers (default).
limiter = Limiter(key_func=user_key(current_user, on_missing="ip"))
```

`on_missing` decides what happens when no identity is found:

| Value | Behaviour |
| --- | --- |
| `"ip"` (default) | Fall back to the client IP. |
| `"anonymous"` | All anonymous callers share one bucket. |
| `"error"` | Raise `MissingIdentityError` (a `401` by default). |

You can also set a key function per limit:

```python
@app.get("/profile")
@limiter.limit("20/minute", key_func=user_key(current_user, on_missing="error"))
async def profile(request: Request) -> dict[str, str]:
    return {"ok": "profile"}
```

### Global (one bucket for everyone)

```python
from fastapi_limitex import global_key


@app.get("/global")
@limiter.limit("1000/minute", key_func=global_key)
async def global_endpoint(request: Request) -> dict[str, str]:
    return {"ok": "global"}
```

### Custom key function

Any callable `(Request) -> str` (sync or async) works:

```python
def api_key(request: Request) -> str:
    return request.headers.get("X-API-Key", "anonymous")


@app.get("/by-api-key")
@limiter.limit("100/hour", key_func=api_key)
async def by_api_key(request: Request) -> dict[str, str]:
    return {"ok": "api"}
```

## Escalating bans

Punish clients that keep exceeding their limit. After `threshold` breaches
within `track_seconds`, the client is banned for `ban_seconds`. During the ban a
stricter `penalty_limit` is enforced (or the client is blocked entirely when
`penalty_limit` is `None`).

```python
from fastapi_limitex import EscalationPolicy, Limiter

limiter = Limiter(
    escalation=EscalationPolicy(
        threshold=5,  # 5 breaches...
        track_seconds=60,  # ...within a minute...
        ban_seconds=300,  # ...triggers a 5-minute ban.
        penalty_limit="1/minute",  # limit during the ban (None = hard block)
    )
)
```

Hook your own logging or alerting with `on_breach`, which is called on every
block (including bans):

```python
from fastapi_limitex import RateLimitContext


async def report_breach(ctx: RateLimitContext) -> None:
    logger.warning("blocked %s (banned=%s)", ctx.key, ctx.banned)


limiter = Limiter(on_breach=report_breach, escalation=...)
```

## Editing limits at runtime

Give a limit a stable `name`, then change it without restarting:

```python
@app.get("/dynamic")
@limiter.limit("5/minute", name="dynamic")
async def dynamic(request: Request) -> dict[str, str]:
    return {"ok": "dynamic"}


# Later, e.g. from an admin endpoint:
limiter.set_limit("dynamic", "1/minute")  # tighten
limiter.disable_limit("dynamic")  # turn off
limiter.enable_limit("dynamic")  # turn back on
```

Dependency limits are editable too — keep a reference and call `.update(...)`:

```python
report_limit = RateLimiter("2/minute", limiter=limiter)


@app.get("/report", dependencies=[Depends(report_limit)])
async def report() -> dict[str, str]:
    return {"ok": "report"}


report_limit.update("10/minute")
```

You can also toggle the whole limiter with `limiter.disable()` /
`limiter.enable()`.

## Customizing the response

By default a blocked request receives a `429` JSON body plus `Retry-After` and
`X-RateLimit-*` headers. Override the body with a `response_builder`:

```python
from starlette.responses import JSONResponse, Response
from fastapi_limitex import Limiter, RateLimitContext


def build_response(request: Request, ctx: RateLimitContext) -> Response:
    return JSONResponse(
        {"error": "slow down", "retry_after": ctx.stats.retry_after},
        status_code=429,
    )


limiter = Limiter(response_builder=build_response)
```

Configure or rename the headers:

```python
from fastapi_limitex import HeaderConfig, Limiter

limiter = Limiter(
    headers=HeaderConfig(
        enabled=True,
        limit="X-RateLimit-Limit",
        remaining="X-RateLimit-Remaining",
        reset="X-RateLimit-Reset",
        retry_after="Retry-After",
        reset_as_epoch=True,  # False = seconds until reset
    )
)
```

## Exemptions

Skip limiting for specific IPs, resolved keys, or arbitrary predicates. All
collections are editable at runtime.

```python
from fastapi_limitex import Exemptions, Limiter

exemptions = Exemptions(
    ips={"127.0.0.1"},
    keys={"user:42"},
    predicates=[lambda request: request.url.path.startswith("/health")],
)
limiter = Limiter(exemptions=exemptions)

# Runtime edits:
limiter.exemptions.exempt_ip("10.0.0.5")
limiter.exemptions.exempt_key("user:99")
```

Per-limit exemptions via `exempt_when`:

```python
@app.get("/maybe")
@limiter.limit("5/minute", exempt_when=lambda r: r.headers.get("X-Internal") == "1")
async def maybe(request: Request) -> dict[str, str]:
    return {"ok": "maybe"}
```

## Global and default limits

Apply limits to every request without decorating each endpoint:

```python
limiter = Limiter(
    application_limits="1000/hour",  # one shared bucket per client, all paths
    default_limits="60/minute",  # per client, bucketed per URL path
)
limiter.attach(app)  # enforced by the middleware
```

Use exemption predicates to exclude paths (for example `/health`) from these
global limits.

## WebSockets

Rate limit messages inside a WebSocket loop:

```python
from fastapi import WebSocket
from fastapi_limitex import RateLimitExceeded, WebSocketRateLimiter

ws_limiter = WebSocketRateLimiter("5/minute", limiter=limiter)


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        try:
            await ws_limiter(websocket, context_key=data)
        except RateLimitExceeded:
            await websocket.send_text("slow down")
            continue
        await websocket.send_text(f"echo: {data}")
```

## Configuration reference

`Limiter(...)` accepts:

| Parameter | Default | Description |
| --- | --- | --- |
| `key_func` | `get_remote_address` | Default key function. |
| `default_limits` | `None` | Per-path limits applied to every request. |
| `application_limits` | `None` | Global limits applied to every request. |
| `strategy` | `"fixed_window"` | Default algorithm. |
| `storage` | `MemoryStorage()` | Backend instance. |
| `storage_uri` | `None` | Convenience URI when `storage` is not given. |
| `headers` | `HeaderConfig()` | Response header configuration. |
| `escalation` | `None` | Escalating ban policy. |
| `exemptions` | `Exemptions()` | Exemption rules. |
| `on_breach` | `None` | Callback invoked on every block. |
| `response_builder` | `default_response` | Builds the `429` response. |
| `enabled` | `True` | Master on/off switch. |

Per-limit options (`limit(...)` and `RateLimiter(...)`): `key_func`, `strategy`,
`cost`, `burst`, `exempt_when`, `per_method`, `methods`, `scope`, `name`.

## Development

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra all          # install everything
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy                  # strict type check
uv run pytest                # tests + coverage
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE) © 2026 Yura2108
