#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Standalone MCP WebSocket server wrapping Calibre tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .config_loader import ServerConfig, load_config_from_env
from .core.plugin_registry import PluginRegistry
from .core.service import LibraryResearchService
from .mcp_protocol import make_error_response, make_result_response
from .tools.excerpt_tool import register_excerpt_tool
from .tools.ft_search_tool import register_ft_search_tool
from fastmcp.server.server import FastMCP
from fastmcp.tools.tool import Tool

log = logging.getLogger(__name__)


def log_startup_context() -> None:
    env_snapshot = {
        "CALIBRE_LIBRARY_PATH": os.environ.get("CALIBRE_LIBRARY_PATH"),
        "CALIBRE_CONFIG_DIRECTORY": os.environ.get("CALIBRE_CONFIG_DIRECTORY"),
    }
    log.info(
        "WebSocket server startup: python=%s argv=%s cwd=%s env=%s",
        sys.executable,
        sys.argv,
        os.getcwd(),
        env_snapshot,
    )


class MCPWebSocketServer:
    """Very small MCP-inspired WebSocket facade for FastMCP tools."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.library_path = config.calibre_library_path
        self._server: Optional[asyncio.AbstractServer] = None
        self._log_library_details(self.library_path)
        self._mcp = self._build_fastmcp(config)
        self._tool_manager = self._mcp._tool_manager  # noqa: SLF001

    def _build_fastmcp(self, cfg: ServerConfig) -> FastMCP:
        service = LibraryResearchService(calibre_root_path=cfg.calibre_library_path)
        registry = PluginRegistry(service)

        mcp = FastMCP("CalibreMCPServer")
        register_ft_search_tool(mcp, registry)
        register_excerpt_tool(mcp, registry)
        return mcp

    def _log_library_details(self, library_path: str) -> None:
        metadata_path = Path(library_path) / "metadata.db"
        log.info(
            "Calibre library setup: path=%r exists=%s isdir=%s metadata=%s metadata_exists=%s",
            library_path,
            os.path.exists(library_path),
            os.path.isdir(library_path),
            metadata_path,
            metadata_path.exists(),
        )

    def _list_tools(self) -> Dict[str, Any]:
        tools = []
        for name, tool in self._tool_manager.get_tools().items():
            tools.append(
                {
                    "name": name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
            )
        return {"tools": tools}

    async def _call_tool(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return make_error_response(request_id, "Missing tool name", code="bad_request")
        if not self._tool_manager.has_tool(name):
            return make_error_response(request_id, f"Unknown tool '{name}'", code="not_found")
        tool = self._tool_manager.get_tool(name)
        prepared_args = self._prepare_arguments(tool, arguments)
        try:
            result_blocks = await self._tool_manager.call_tool(name, prepared_args)
        except Exception as exc:  # noqa: BLE001
            return make_error_response(request_id, f"Tool failed: {exc}")

        # Convert ToolResult (list of TextContent/etc.) into simple JSON payload
        payload = []
        for block in result_blocks:
            payload.append(block.model_dump())
        return make_result_response(request_id, {"content": payload})

    @staticmethod
    def _prepare_arguments(tool: Tool, arguments: Dict[str, Any]) -> Dict[str, Any]:
        parameters = tool.parameters or {}
        properties = parameters.get("properties", {})
        if "input" in properties and len(properties) == 1:
            return {"input": arguments}
        return arguments

    async def start(self):
        cfg = self.config
        log.info("Starting MCP WebSocket server on ws://%s:%s", cfg.server_host, cfg.server_port)
        try:
            self._server = await websockets.serve(self._handle_client, cfg.server_host, cfg.server_port)
        except OSError as exc:
            raise RuntimeError(f"Server konnte Port {cfg.server_port} nicht binden: {exc}") from exc

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        async for message in websocket:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps(make_error_response("-", "Invalid JSON")))
                continue

            request_id = str(payload.get("id") or "-")
            method = payload.get("method")
            params = payload.get("params") or {}

            if method == "list_tools":
                await websocket.send(json.dumps(make_result_response(request_id, self._list_tools())))
            elif method == "call_tool":
                await websocket.send(json.dumps(await self._call_tool(request_id, params)))
            else:
                await websocket.send(json.dumps(make_error_response(request_id, "Unknown method", code="unknown_method")))

async def run_async(config: Optional[ServerConfig] = None) -> None:
    cfg = config or load_config_from_env()
    server = MCPWebSocketServer(cfg)
    await server.start()
    try:
        await asyncio.Future()  # run forever
    finally:
        await server.stop()


def run_from_env() -> None:
    cfg = load_config_from_env()
    log_startup_context()
    try:
        asyncio.run(run_async(cfg))
    except RuntimeError as exc:
        print(str(exc))
        raise
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_from_env()
