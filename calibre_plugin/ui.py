#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.utils.localization import _
from qt.core import QAction, QMenu

from calibre_plugins.mcp_server.controller import MCPServerController


def get_icons(name, plugin_name):
    from calibre.gui2 import get_icons as calibre_get_icons

    return calibre_get_icons(name, plugin_name)


class MCPServerAction(InterfaceAction):

    name = 'MCP Server'
    action_spec = (_('MCP Server'), None, _('MCP Server starten oder stoppen'), None)

    def genesis(self):
        self.controller = MCPServerController(library_path=self._current_library_path())
        icon = get_icons('images/icon.png', _('MCP Server'))

        self.qaction.setIcon(icon)
        self.qaction.setCheckable(True)
        self.qaction.setToolTip(_('Startet oder stoppt den MCP Server'))
        self.qaction.triggered.connect(self.toggle_server)

        self.menu = QMenu(_('MCP Server'), self.gui)
        self.menu.setIcon(icon)
        self.menu.addAction(self.qaction)
        self.gui.menuBar().addMenu(self.menu)

        self.update_toggle()

    def toggle_server(self, checked=False):  # pylint: disable=unused-argument
        library_path = self._current_library_path()
        if not library_path:
            error_dialog(self.gui, _('MCP Server'), _('Calibre-Bibliothek konnte nicht ermittelt werden.'), show=True)
            return
        self.controller.set_library_path(library_path)
        try:
            if not self.controller.toggle():
                return
        except Exception as exc:
            error_dialog(self.gui, _('MCP Server'), _('Fehler beim Umschalten des Servers'), det_msg=str(exc), show=True)
            return
        if self.controller.is_running:
            info_dialog(self.gui, _('MCP Server'), _('Server wurde gestartet.'), show=True)
        else:
            info_dialog(self.gui, _('MCP Server'), _('Server wurde gestoppt.'), show=True)
        self.update_toggle()

    def update_toggle(self):
        running = self.controller.is_running
        self.qaction.blockSignals(True)
        self.qaction.setChecked(running)
        self.qaction.blockSignals(False)
        self.qaction.setText(_('MCP Server stoppen') if running else _('MCP Server starten'))

    def apply_settings(self):
        # Called after preferences change, ensure menu state matches
        self.update_toggle()

    def _current_library_path(self):
        db = getattr(self.gui, 'current_db', None)
        return getattr(db, 'library_path', None) if db is not None else None
