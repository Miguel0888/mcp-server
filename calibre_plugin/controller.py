#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias <https://github.com/Miguel0888/>'
__docformat__ = 'restructuredtext en'

from calibre_plugins.mcp_server.config import prefs


class MCPServerController(object):
    """Manage MCP server lifecycle for UI (stub - no real server yet)."""

    def __init__(self):
        # Store prefs for later use when real server is wired in
        self._prefs = prefs
        self._running = False

    @property
    def is_running(self):
        """Return True if server is logically running."""
        return self._running

    def start_server(self):
        """Mark server as started (hook real start here later)."""
        # TODO: Start real MCP WebSocket server here
        self._running = True

    def stop_server(self):
        """Mark server as stopped (hook real stop here later)."""
        # TODO: Stop real MCP WebSocket server here
        self._running = False

    def toggle_server(self):
        """Toggle server running flag."""
        if self._running:
            self.stop_server()
        else:
            self.start_server()
