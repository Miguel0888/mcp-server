#!/usr/bin/env python
from __future__ import annotations

import contextlib
import os

from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

from .config_loader import load_config_from_env
from .main import create_mcp_server


def create_app() -> Starlette:
    # Create MCP server and mount the Streamable HTTP app under Starlette.
    cfg = load_config_from_env()
    mcp = create_mcp_server(cfg)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # Run session manager if available.
        session_manager = getattr(mcp, "session_manager", None)
        if session_manager is None:
            yield
            return
        async with session_manager.run():
            yield

    streamable_app_factory = getattr(mcp, "streamable_http_app", None)
    if not callable(streamable_app_factory):
        raise RuntimeError("FastMCP does not provide streamable_http_app(); cannot expose /mcp endpoint.")

    return Starlette(
        routes=[Mount("/", app=streamable_app_factory())],
        lifespan=lifespan,
    )


def run_from_env() -> None:
    # Read host/port from environment and serve via Uvicorn.
    host = (os.environ.get("MCP_HTTP_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("MCP_HTTP_PORT") or "8000").strip())

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_from_env()
