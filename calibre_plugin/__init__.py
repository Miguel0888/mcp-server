#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias <https://github.com/Miguel0888/>'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase

from calibre_plugins.mcp_server.config import MCPServerConfigWidget, prefs


class MCPServerPlugin(InterfaceActionBase):
    """Wrap interface action for MCP server / research UI."""

    name = 'MCP Server Recherche'
    description = 'UI-Rahmen fuer MCP WebSocket-Server und Recherche.'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Miguel Iglesias'
    version = (0, 2, 0)
    minimum_calibre_version = (6, 0, 0)

    # Path to the actual Qt-based action implementation
    actual_plugin = 'calibre_plugins.mcp_server.ui:MCPResearchUI'

    def is_customizable(self):
        """Return True to show plugin in calibre preferences."""
        return True

    def config_widget(self):
        """Return the configuration widget for the preferences dialog."""
        return MCPServerConfigWidget(prefs)

    def save_settings(self, config_widget):
        """Persist settings and notify running UI plugin if present."""
        config_widget.save_settings()

        # Let running UI instance pick up new configuration
        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
