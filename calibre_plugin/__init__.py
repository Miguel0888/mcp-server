#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

# The class that all Interface Action plugin wrappers must inherit from
from calibre.customize import InterfaceActionBase

from calibre_plugins.mcp_server.config import prefs


class MCPServerInterfacePlugin(InterfaceActionBase):
    name = 'MCP Server'
    description = 'Startet und stoppt den Rackserver direkt aus calibre'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'MCP Server Team'
    version = (1, 0, 0)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = 'calibre_plugins.mcp_server.ui:MCPServerAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.mcp_server.config import MCPServerConfigWidget

        return MCPServerConfigWidget(prefs)

    def save_settings(self, config_widget):
        config_widget.save_settings()

        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
