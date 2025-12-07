from calibre.customize import InterfaceActionBase


class McpInterfacePlugin(InterfaceActionBase):
    """Calibre GUI plugin entry point for the MCP server.

    Calibre loads this class to discover the actual interface action
    implementation defined in action.py.
    """

    name = "Calibre MCP Server"
    description = (
        "Start/stop MCP research server for the current Calibre library."
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "Miguel"
    version = (0, 0, 1)
    minimum_calibre_version = (6, 0, 0)

    # Point Calibre to the actual plugin implementation in action.py
    actual_plugin = "action:McpInterfaceAction"
