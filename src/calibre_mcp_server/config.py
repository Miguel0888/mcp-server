#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _
from qt.core import (
    QWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)


# Global plugin preferences
prefs = JSONConfig('plugins/mcp_server')

# Default values
prefs.defaults['server_host'] = '127.0.0.1'
prefs.defaults['server_port'] = '8765'
prefs.defaults['library_path'] = ''
prefs.defaults['api_key'] = ''
prefs.defaults['command'] = 'python -m calibre_mcp_server.main'
prefs.defaults['working_dir'] = ''


class MCPServerConfigWidget(QWidget):
    """Preference widget for MCP Server plugin."""

    def __init__(self, prefs_obj, parent=None):
        super(MCPServerConfigWidget, self).__init__(parent)
        # Store reference to prefs
        self.prefs = prefs_obj

        # Build UI layout
        layout = QFormLayout(self)

        # Server host
        self.host_edit = QLineEdit(self)
        self.host_edit.setText(self.prefs['server_host'])
        layout.addRow(_('Server Host:'), self.host_edit)

        # Server port
        self.port_edit = QLineEdit(self)
        self.port_edit.setText(self.prefs['server_port'])
        layout.addRow(_('Server Port:'), self.port_edit)

        # Library path + browse
        library_row = QHBoxLayout()
        self.library_edit = QLineEdit(self)
        self.library_edit.setText(self.prefs['library_path'])
        browse_library_btn = QPushButton(_('Durchsuchen…'), self)
        browse_library_btn.clicked.connect(self.browse_library)

        library_row.addWidget(self.library_edit)
        library_row.addWidget(browse_library_btn)
        layout.addRow(_('Calibre-Bibliothek:'), library_row)

        # API key
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setText(self.prefs['api_key'])
        layout.addRow(_('API Key (optional):'), self.api_key_edit)

        # Command
        self.command_edit = QLineEdit(self)
        self.command_edit.setText(self.prefs['command'])
        layout.addRow(_('Server Kommando:'), self.command_edit)

        # Working directory + browse
        workdir_row = QHBoxLayout()
        self.workdir_edit = QLineEdit(self)
        self.workdir_edit.setText(self.prefs['working_dir'])
        browse_workdir_btn = QPushButton(_('Durchsuchen…'), self)
        browse_workdir_btn.clicked.connect(self.browse_workdir)

        workdir_row.addWidget(self.workdir_edit)
        workdir_row.addWidget(browse_workdir_btn)
        layout.addRow(_('Arbeitsverzeichnis:'), workdir_row)

        # Info label
        info_label = QLabel(
            _(
                'Das Kommando wird für den MCP WebSocket-Server verwendet.\n'
                'CALIBRE_LIBRARY_PATH und API-Key werden als Umgebungsvariablen gesetzt.'
            ),
            self,
        )
        layout.addRow(info_label)

    def browse_library(self):
        """Select Calibre library root directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswählen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def browse_workdir(self):
        """Select working directory for MCP server process."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Arbeitsverzeichnis auswählen'),
            self.workdir_edit.text() or '',
        )
        if path:
            self.workdir_edit.setText(path)

    def save_settings(self):
        """Persist user changes to preferences."""
        self.prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        self.prefs['server_port'] = self.port_edit.text().strip() or '8765'
        self.prefs['library_path'] = self.library_edit.text().strip()
        self.prefs['api_key'] = self.api_key_edit.text().strip()
        self.prefs['command'] = self.command_edit.text().strip() or ''
        self.prefs['working_dir'] = self.workdir_edit.text().strip()
