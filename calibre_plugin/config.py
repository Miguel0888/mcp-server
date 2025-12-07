#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _
from qt.core import (
    QWidget,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
)


# This is where all preferences for this plugin will be stored.
# Name is global, so keep it reasonably unique.
prefs = JSONConfig('plugins/mcp_server_recherche')

# New settings for MCP server / AI
prefs.defaults['server_host'] = '127.0.0.1'
prefs.defaults['server_port'] = '8765'
prefs.defaults['library_path'] = ''   # Use current calibre library when empty
prefs.defaults['api_key'] = ''        # Optional AI key (e.g. OpenAI)


class MCPServerRechercheConfigWidget(QWidget):
    """Preference widget for MCP Server Recherche plugin."""

    def __init__(self):
        QWidget.__init__(self)

        layout = QFormLayout(self)
        self.setLayout(layout)

        # Server host
        self.host_edit = QLineEdit(self)
        self.host_edit.setText(prefs['server_host'])
        layout.addRow(_('Server-Host:'), self.host_edit)

        # Server port
        self.port_edit = QLineEdit(self)
        self.port_edit.setText(prefs['server_port'])
        layout.addRow(_('Server-Port:'), self.port_edit)

        # Library path + browse button
        lib_row = QHBoxLayout()
        self.library_edit = QLineEdit(self)
        self.library_edit.setText(prefs['library_path'])

        browse_btn = QPushButton(_('Auswahl'), self)
        browse_btn.clicked.connect(self.choose_library)

        lib_row.addWidget(self.library_edit)
        lib_row.addWidget(browse_btn)

        layout.addRow(_('Calibre-Bibliothek:'), lib_row)

        # API key
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setText(prefs['api_key'])
        layout.addRow(_('API Key (z. B. OpenAI):'), self.api_key_edit)

        # Info label
        info = QLabel(
            _(
                'Host/Port konfigurieren spaeter den MCP WebSocket-Server.\n'
                'Der Bibliothekspfad ueberschreibt optional die aktuelle '
                'Calibre-Bibliothek.\n'
                'Der API Key wird fuer den AI-Dienst genutzt.'
            ),
            self,
        )
        layout.addRow(info)

    def choose_library(self):
        """Select calibre library root directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswaehlen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def save_settings(self):
        """Persist user changes to JSONConfig."""
        prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        prefs['server_port'] = self.port_edit.text().strip() or '8765'
        prefs['library_path'] = self.library_edit.text().strip()
        prefs['api_key'] = self.api_key_edit.text().strip()
