#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias <https://github.com/Miguel0888/>'
__docformat__ = 'restructuredtext en'

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _
from qt.core import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


# Store all preferences for this plugin
prefs = JSONConfig('plugins/mcp_server')

# Default values
prefs.defaults['server_host'] = '127.0.0.1'
prefs.defaults['server_port'] = '8765'
prefs.defaults['library_path'] = ''  # Use current calibre library when empty
prefs.defaults['api_key'] = ''       # Optional AI key


class MCPServerConfigWidget(QWidget):
    """Preference widget for MCP server and AI settings."""

    def __init__(self, prefs_obj, parent=None):
        QWidget.__init__(self, parent)
        self.prefs = prefs_obj

        layout = QFormLayout(self)

        # Host
        self.host_edit = QLineEdit(self)
        self.host_edit.setText(self.prefs.get('server_host', '127.0.0.1'))
        layout.addRow(_('Server-Host'), self.host_edit)

        # Port
        self.port_edit = QLineEdit(self)
        self.port_edit.setText(self.prefs.get('server_port', '8765'))
        layout.addRow(_('Server-Port'), self.port_edit)

        # Library path + browse button
        lib_row = QHBoxLayout()
        self.library_edit = QLineEdit(self)
        self.library_edit.setText(self.prefs.get('library_path', ''))

        browse_btn = QPushButton(_('Auswahl'), self)
        browse_btn.clicked.connect(self.choose_library)

        lib_row.addWidget(self.library_edit)
        lib_row.addWidget(browse_btn)

        layout.addRow(_('Calibre-Bibliothek'), lib_row)

        # API key
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setText(self.prefs.get('api_key', ''))
        layout.addRow(_('API Key (z. B. OpenAI)'), self.api_key_edit)

        info = QLabel(
            _(
                'Host/Port konfigurieren den MCP WebSocket-Server.\n'
                'Der Bibliothekspfad überschreibt optional die aktuelle Calibre-Bibliothek.\n'
                'Der API Key wird später für den AI-Dienst genutzt.'
            ),
            self,
        )
        layout.addRow(info)

    def choose_library(self):
        """Let user select calibre library path."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswählen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def save_settings(self):
        """Persist values in calibre JSON configuration."""
        self.prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        self.prefs['server_port'] = self.port_edit.text().strip() or '8765'
        self.prefs['library_path'] = self.library_edit.text().strip()
        self.prefs['api_key'] = self.api_key_edit.text().strip()
