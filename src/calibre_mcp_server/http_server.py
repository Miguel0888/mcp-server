#!/usr/bin/env python
from __future__ import annotations

import os

from .config_loader import load_config_from_env
from .main import create_mcp_server


def run_from_env() -> None:
    # Read configuration from environment variables.
    cfg = load_config_from_env()

    # Create the MCP server with all tools registered.
    mcp = create_mcp_server(cfg)

    # Prefer dedicated HTTP env vars to avoid clashing with the WS port.
    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
    path = os.environ.get("MCP_HTTP_PATH", "/mcp")

    # Expose a remote-compatible MCP endpoint over Streamable HTTP.
    mcp.run(transport="http", host=host, port=port, path=path)


if __name__ == "__main__":
    run_from_env()
