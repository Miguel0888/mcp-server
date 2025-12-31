#!/usr/bin/env python
from __future__ import annotations

import contextlib
import os

from starlette.applications import Starlette
from starlette.routing import Mount

import uvicorn

from .config_loader import load_config_from_env
from .main import create_mcp_server


class BearerAuthASGIMiddleware:
    def __init__(self, app, expected_token: str) -> None:
        self._app = app
        self._expected = "Bearer " + (expected_token or "")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path == "/health":
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if auth != self._expected:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return

        await self._app(scope, receive, send)


def _read_required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def create_app(shared_secret: str):
    cfg = load_config_from_env()
    mcp = create_mcp_server(cfg)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        session_manager = getattr(mcp, "session_manager", None)
        if session_manager is None:
            yield
            return
        async with session_manager.run():
            yield

    streamable_app_factory = getattr(mcp, "streamable_http_app", None)
    if not callable(streamable_app_factory):
        raise RuntimeError("FastMCP does not provide streamable_http_app(); cannot expose /mcp endpoint.")

    inner_app = Starlette(
        routes=[Mount("/", app=streamable_app_factory())],
        lifespan=lifespan,
    )

    return BearerAuthASGIMiddleware(inner_app, expected_token=shared_secret)


def run_from_env() -> None:
    host = (os.environ.get("MCP_HTTP_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("MCP_HTTP_PORT") or "8000").strip())
    shared_secret = _read_required_env("MCP_SHARED_SECRET")

    app = create_app(shared_secret)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_from_env()
