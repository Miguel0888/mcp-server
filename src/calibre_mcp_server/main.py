#!/usr/bin/env python
import anyio

from fastmcp import FastMCP
from fastmcp.server.server import stdio_server

from .config_loader import ServerConfig, load_config_from_env
from .core.service import LibraryResearchService
from .core.plugin_registry import PluginRegistry
from .tools.ft_search_tool import register_ft_search_tool
from .tools.excerpt_tool import register_excerpt_tool


def create_mcp_server(config: ServerConfig | None = None) -> FastMCP:
    """Create MCP server with all registered tools."""
    cfg = config or load_config_from_env()
    service = LibraryResearchService(calibre_root_path=cfg.calibre_library_path)
    registry = PluginRegistry(service)

    mcp = FastMCP("CalibreMCPServer")

    register_ft_search_tool(mcp, registry)
    register_excerpt_tool(mcp, registry)

    return mcp


def run(config: ServerConfig | None = None) -> None:
    """Run MCP server using stdio transport (MCP clients connect via pipes)."""

    cfg = config or load_config_from_env()
    server = create_mcp_server(cfg)

    async def _serve():
        async with stdio_server() as transport:
            await server.run(transport=transport)

    anyio.run(_serve)


if __name__ == "__main__":
    run()
