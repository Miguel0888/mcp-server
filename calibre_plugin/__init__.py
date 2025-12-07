#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase

from calibre_plugins.mcp_server.config import prefs


class MCPServerPlugin(InterfaceActionBase):
    """InterfaceAction wrapper for MCP Server plugin."""

    name = 'MCP Server'
    description = 'Steuert einen lokalen MCP WebSocket-Server und bietet eine Recherche-Oberfläche.'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Miguel Iglesias'
    version = (1, 0, 0)
    minimum_calibre_version = (6, 0, 0)

    actual_plugin = 'calibre_plugins.mcp_server.ui:MCPServerAction'

    def is_customizable(self):
        """Return True to show plugin in preferences dialog."""
        return True

    def config_widget(self):
        """Return configuration widget instance."""
        from calibre_plugins.mcp_server.config import MCPServerConfigWidget
        return MCPServerConfigWidget(prefs)

    def save_settings(self, config_widget):
        """Persist settings from configuration widget."""
        config_widget.save_settings()

        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
