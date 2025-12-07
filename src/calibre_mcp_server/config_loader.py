#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Lightweight config loader for running the WebSocket server standalone."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerConfig:
    server_host: str
    server_port: int
    calibre_library_path: str
    server_password: str | None = None


def load_config_from_env() -> ServerConfig:
    host = os.environ.get("MCP_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_SERVER_PORT", "8765"))
    library = os.environ.get("CALIBRE_LIBRARY_PATH", "")
    if not library:
        default_path = Path.home() / "Calibre Library"
        library = str(default_path)
    password = os.environ.get("MCP_SERVER_PASSWORD")
    return ServerConfig(server_host=host, server_port=port, calibre_library_path=library, server_password=password)
