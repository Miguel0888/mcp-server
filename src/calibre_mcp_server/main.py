from fastmcp import FastMCP
from fastmcp.transports.websockets import WebSocketSettings, WebSocketTransport

from .config import load_config
from .core.service import LibraryResearchService
from .core.plugin_registry import PluginRegistry
from .tools.ft_search_tool import register_ft_search_tool
from .tools.excerpt_tool import register_excerpt_tool


def create_mcp_server() -> FastMCP:
    """Create MCP server with all registered tools."""
    cfg = load_config()
    service = LibraryResearchService(calibre_root_path=cfg.calibre_library_path)
    registry = PluginRegistry(service)

    mcp = FastMCP("CalibreMCPServer")

    register_ft_search_tool(mcp, registry)
    register_excerpt_tool(mcp, registry)

    return mcp


def run() -> None:
    """Run MCP server using stdio transport."""
    server = create_mcp_server()
    transport = WebSocketTransport(settings=WebSocketSettings())
    server.run(transport=transport)


if __name__ == "__main__":
    run()
