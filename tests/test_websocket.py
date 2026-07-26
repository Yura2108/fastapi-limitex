from __future__ import annotations

from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fastapi_limitex import Limiter, RateLimitExceeded, WebSocketRateLimiter


def test_websocket_rate_limit() -> None:
    app = FastAPI()
    limiter = Limiter()
    limiter.attach(app)
    ws_limiter = WebSocketRateLimiter("2/minute", limiter=limiter)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    await ws_limiter(websocket, context_key="msg")
                except RateLimitExceeded:
                    await websocket.send_text("blocked")
                    continue
                await websocket.send_text(f"echo {data}")
        except WebSocketDisconnect:
            return

    client = TestClient(app)
    with client.websocket_connect("/ws") as connection:
        connection.send_text("a")
        assert connection.receive_text() == "echo a"
        connection.send_text("b")
        assert connection.receive_text() == "echo b"
        connection.send_text("c")
        assert connection.receive_text() == "blocked"
