#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, get_icons
from calibre.utils.localization import _
from qt.core import QMenu, QAction

from calibre_plugins.mcp_server.config import prefs
from calibre_plugins.mcp_server.controller import MCPServerController
from calibre_plugins.mcp_server.client_dialog import MCPClientDialog


class MCPResearchUI(InterfaceAction):
    """Interface action that adds MCP button under the search bar."""

    name = 'MCP Recherche'

    # Name, icon, tooltip, shortcut
    action_spec = (
        _('MCP Recherche'),
        'images/icon.png',
        _('MCP Recherche-Fenster öffnen'),
        None,
    )

    # Make this a global toolbar button (next to the search bar)
    action_type = 'global'

    def genesis(self):
        """Create toolbar action, drop-down menu and controller."""
        # Create simple controller with server state stub
        self.controller = MCPServerController()

        # Set icon and tooltip
        icon = get_icons('images/icon.png', _('MCP Recherche'))
        self.qaction.setIcon(icon)
        self.qaction.setToolTip(_('MCP Recherche und Serversteuerung'))

        # Create menu for the action (similar to Ask AI)
        self.menu = QMenu(self.gui)

        # 1) Open research dialog
        self.open_dialog_action = QAction(_('MCP Recherche öffnen'), self.gui)
        self.open_dialog_action.triggered.connect(self.show_dialog)
        self.menu.addAction(self.open_dialog_action)

        self.menu.addSeparator()

        # 2) Start/stop MCP server (UI stub only)
        self.toggle_server_action = QAction('', self.gui)
        self.toggle_server_action.triggered.connect(self.on_toggle_server)
        self.menu.addAction(self.toggle_server_action)
        self._update_server_action_text()

        self.menu.addSeparator()

        # 3) Hint for settings
        self.settings_action = QAction(_('Einstellungen anzeigen…'), self.gui)
        self.settings_action.triggered.connect(self.show_settings_hint)
        self.menu.addAction(self.settings_action)

        # Attach menu to main action
        self.qaction.setMenu(self.menu)

        # Left-click on button opens dialog directly
        self.qaction.triggered.connect(self.show_dialog)

        # Keep reference to dialog instance
        self._dialog = None

    def _update_server_action_text(self):
        """Update menu entry text based on server running flag."""
        if self.controller.is_running:
            self.toggle_server_action.setText(_('MCP Server stoppen'))
        else:
            self.toggle_server_action.setText(_('MCP Server starten'))

    def on_toggle_server(self):
        """Handle start/stop of MCP server (stub only)."""
        try:
            self.controller.toggle_server()
        except Exception as exc:
            error_dialog(
                self.gui,
                _('MCP Server'),
                _('Fehler beim Umschalten des MCP Servers:\n{0}').format(repr(exc)),
                show=True,
            )
            return

        self._update_server_action_text()

    def show_settings_hint(self):
        """Show hint where to find plugin settings."""
        error_dialog(
            self.gui,
            _('MCP Einstellungen'),
            _(
                'Die Einstellungen für den MCP Server findest du unter:\n'
                'Einstellungen → Plugins → MCP Server Recherche → Konfigurieren.'
            ),
            show=True,
        )

    def show_dialog(self):
        """Open (or raise) the MCP research dialog."""
        if self._dialog is None:
            self._dialog = MCPClientDialog(self.gui, self.controller, prefs)
            self._dialog.finished.connect(self._on_dialog_closed)

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _on_dialog_closed(self, result):
        """Clear dialog reference when the window is closed."""
        # Ignore result value
        del result
        self._dialog = None

    def apply_settings(self):
        """React to changed settings (no logic yet)."""
        # Later: update dialog labels if needed
        return
