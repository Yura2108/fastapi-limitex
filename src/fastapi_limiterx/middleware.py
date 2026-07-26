from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from fastapi_limiterx.limiter import Limiter
from fastapi_limiterx.responses import apply_headers


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Applies application-wide and default limits and adds response headers.

    Installed automatically by :meth:`Limiter.attach`. Application limits share a
    single bucket per client across all paths, while default limits are bucketed
    per URL path.
    """

    def __init__(self, app: ASGIApp, limiter: Limiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rules = self.limiter.global_rules(request)
        if rules:
            blocked = await self.limiter.guard(request, rules)
            if blocked is not None:
                return blocked
        response = await call_next(request)
        stats = getattr(request.state, "limiterx_stats", None)
        if stats is not None:
            apply_headers(response, stats, self.limiter.header_config)
        return response
