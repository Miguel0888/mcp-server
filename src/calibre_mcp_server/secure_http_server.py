#!/usr/bin/env python
from __future__ import annotations

import contextlib
import os
from typing import Optional

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount

import uvicorn

from .config_loader import load_config_from_env
from .main import create_mcp_server


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, expected_token: str) -> None:
        super().__init__(app)
        self._expected_header_value = "Bearer " + (expected_token or "")

    async def dispatch(self, request: Request, call_next):
        # Allow simple health check without auth (optional)
        if request.url.path in ("/health",):
            return PlainTextResponse("ok", status_code=200)

        auth = request.headers.get("authorization", "")
        if auth != self._expected_header_value:
            return PlainTextResponse("Unauthorized", status_code=401)

        return await call_next(request)


def _read_required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def create_app(shared_secret: str) -> Starlette:
    cfg = load_config_from_env()
    mcp = create_mcp_server(cfg)

    # NOTE: This follows the MCP SDK mounting pattern (run session manager in lifespan).
    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # If your FastMCP implementation exposes session_manager, keep this.
        # If not available in your fastmcp version, remove this block.
        session_manager = getattr(mcp, "session_manager", None)
        if session_manager is None:
            yield
            return

        async with session_manager.run():
            yield

    # Streamable HTTP is typically exposed at /mcp by default when mounted. :contentReference[oaicite:4]{index=4}
    streamable_app_factory = getattr(mcp, "streamable_http_app", None)
    if not callable(streamable_app_factory):
        raise RuntimeError("FastMCP does not provide streamable_http_app(); cannot expose /mcp endpoint.")

    app = Starlette(
        routes=[Mount("/", app=streamable_app_factory())],
        lifespan=lifespan,
    )

    app.add_middleware(BearerTokenAuthMiddleware, expected_token=shared_secret)
    return app


def run_from_env() -> None:
    host = (os.environ.get("MCP_HTTP_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("MCP_HTTP_PORT") or "8000").strip())
    shared_secret = _read_required_env("MCP_SHARED_SECRET")

    app = create_app(shared_secret)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_from_env()
