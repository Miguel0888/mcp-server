#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Standalone MCP WebSocket server wrapping Calibre tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .config_loader import ServerConfig, load_config_from_env
from .core.plugin_registry import PluginRegistry
from .core.service import LibraryResearchService
from .mcp_protocol import make_error_response, make_result_response
from .tools.excerpt_tool import register_excerpt_tool
from .tools.ft_search_tool import register_ft_search_tool

log = logging.getLogger(__name__)


class MCPWebSocketServer:
    """Very small MCP-inspired WebSocket facade for FastMCP tools."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._server: Optional[asyncio.AbstractServer] = None
        self._mcp = self._build_fastmcp(config)
        self._tool_map = self._discover_tools(self._mcp)

    def _build_fastmcp(self, cfg: ServerConfig):
        service = LibraryResearchService(calibre_root_path=cfg.calibre_library_path)
        registry = PluginRegistry(service)

        from fastmcp import FastMCP

        mcp = FastMCP("CalibreMCPServer")
        register_ft_search_tool(mcp, registry)
        register_excerpt_tool(mcp, registry)
        return mcp

    def _discover_tools(self, mcp):
        tool_map = {}
        # FastMCP stores tools in _tool_manager
        manager = getattr(mcp, '_tool_manager', None)
        if manager:
            try:
                tool_map.update(manager.get_tools())
            except Exception:  # noqa: BLE001
                pass
        if tool_map:
            return tool_map

        # Fallback: inspect FastMCP instance for callables decorated via @FastMCP.tool
        for attr_name in dir(mcp):
            attr = getattr(mcp, attr_name)
            # FastMCP decorators attach __fastmcp_tool__ metadata on wrapper functions
            metadata = getattr(attr, '__fastmcp_tool__', None)
            if metadata:
                tool_map[metadata.name] = metadata
            elif callable(attr):
                # Some versions store tool meta on function attributes
                if hasattr(attr, 'input_model') and hasattr(attr, 'func'):
                    tool_map[attr_name] = attr
        return tool_map

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

    def _list_tools(self) -> Dict[str, Any]:
        tools = []
        for name, tool in self._tool_map.items():
            schema = tool.input_model.model_json_schema()
            tools.append({
                "name": name,
                "description": tool.func.__doc__ or "",
                "input_schema": schema,
            })
        return {"tools": tools}

    async def _call_tool(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return make_error_response(request_id, "Missing tool name", code="bad_request")
        tool = self._tool_map.get(name)
        if not tool:
            return make_error_response(request_id, f"Unknown tool '{name}'", code="not_found")
        try:
            result_model = tool.func(tool.input_model(**arguments))
        except Exception as exc:  # noqa: BLE001
            return make_error_response(request_id, f"Tool failed: {exc}")
        return make_result_response(request_id, json.loads(result_model.model_dump_json()))

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
    try:
        asyncio.run(run_async(cfg))
    except RuntimeError as exc:
        print(str(exc))
        raise
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_from_env()
