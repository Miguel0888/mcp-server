#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog
from calibre.utils.localization import _
from qt.core import QAction

from calibre_plugins.mcp_server.config import prefs
from calibre_plugins.mcp_server.controller import MCPServerController
from calibre_plugins.mcp_server.client_dialog import MCPClientDialog


class MCPServerAction(InterfaceAction):
    """Calibre interface action for MCP server and research dialog."""

    name = 'MCP Server'

    action_spec = (
        _('MCP Recherche'),
        None,
        _('MCP WebSocket-Server steuern und Recherche starten'),
        None,
    )

    def genesis(self):
        """Create toolbar/menu action and controller."""
        # Create controller using current Calibre library path as fallback
        library_path = self.gui.current_db.library_path
        self.controller = MCPServerController(library_path=library_path, prefs_obj=prefs)

        # Use plugin icon if available
        icon = get_icons('images/icon.png', _('MCP Server'))

        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_client_dialog)
        self.qaction.setToolTip(_('Öffnet das MCP-Recherchefenster'))

        # Keep last opened dialog reference
        self._dialog = None

    def show_client_dialog(self):
        """Open the MCP client dialog window."""
        try:
            if self._dialog is None:
                self._dialog = MCPClientDialog(self.gui, self.controller, prefs)
                self._dialog.finished.connect(self._on_dialog_closed)

            self._dialog.show()
            self._dialog.raise_()
            self._dialog.activateWindow()
        except Exception as exc:
            error_dialog(
                self.gui,
                _('MCP Server'),
                _('Fehler beim Öffnen des MCP-Fensters:\n{0}').format(repr(exc)),
                show=True,
            )

    def _on_dialog_closed(self, result):
        """Reset dialog reference when closed."""
        self._dialog = None

    def apply_settings(self):
        """React to preference changes if needed."""
        # Right now controller reads prefs lazily, so no extra code is required.
        # Add logic here if behaviour shall change on preference updates.
        return
