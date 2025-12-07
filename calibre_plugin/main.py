#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

if False:
    # This is here to keep my python error checker from complaining about
    # the builtin functions that will be defined by the plugin loading system
    # You do not need this code in your plugins
    get_icons = get_resources = None

from qt.core import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QTimer,
)

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient


class MCPServerRechercheDialog(QDialog):
    """Main dialog for MCP Server Recherche (pure UI stub)."""

    def __init__(self, gui, icon, do_user_config):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.do_user_config = do_user_config

        # The current database shown in the GUI
        # db is an instance of the class LibraryDatabase from db/legacy.py
        # This class has many, many methods that allow you to do a lot of
        # things. For most purposes you should use db.new_api, which has
        # a much nicer interface from db/cache.py
        self.db = gui.current_db

        self.server_running = False
        self.chat_client = ChatProviderClient(prefs)
        self.pending_request = False

        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)

        # --- Top row: settings + server start/stop -------------------------
        top_row = QHBoxLayout()

        self.settings_button = QPushButton('Einstellungen', self)
        self.settings_button.clicked.connect(self.open_settings)
        top_row.addWidget(self.settings_button)

        self.server_button = QPushButton('Server starten', self)
        self.server_button.clicked.connect(self.toggle_server)
        top_row.addWidget(self.server_button)

        top_row.addStretch(1)
        main_layout.addLayout(top_row)

        # Optional connection info from prefs
        host = prefs['server_host']
        port = prefs['server_port']
        self.conn_label = QLabel(
            f'Ziel (spaeter): ws://{host}:{port}', self
        )
        main_layout.addWidget(self.conn_label)

        # --- Chat view -----------------------------------------------------
        self.chat_view = QTextEdit(self)
        self.chat_view.setReadOnly(True)
        main_layout.addWidget(self.chat_view, 1)

        # --- Bottom row: input + send -------------------------------------
        bottom_row = QHBoxLayout()

        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText(
            'Frage oder Suchtext fuer die MCP-Recherche eingeben ...'
        )

        self.send_button = QPushButton('Senden', self)
        self.send_button.clicked.connect(self.send_message)

        bottom_row.addWidget(self.input_edit, 1)
        bottom_row.addWidget(self.send_button)

        main_layout.addLayout(bottom_row)

        self.setWindowTitle('MCP Server Recherche')
        self.setWindowIcon(icon)
        self.resize(700, 500)

    # ------------------------------------------------------------------ UI

    def open_settings(self):
        """Open calibre's plugin configuration dialog."""
        self.do_user_config(parent=self)
        self.chat_client = ChatProviderClient(prefs)

        # Update connection label after changes
        host = prefs['server_host']
        port = prefs['server_port']
        self.conn_label.setText(f'Ziel (spaeter): ws://{host}:{port}')

    def toggle_server(self):
        """Toggle server running flag (no real server yet)."""
        self.server_running = not self.server_running
        if self.server_running:
            self.server_button.setText('Server stoppen')
            self.chat_view.append('System: MCP Server wurde (logisch) gestartet.')
        else:
            self.server_button.setText('Server starten')
            self.chat_view.append('System: MCP Server wurde (logisch) gestoppt.')

    def send_message(self):
        """Send message via configured provider."""
        if self.pending_request:
            return
        text = self.input_edit.text().strip()
        if not text:
            return
        self.chat_view.append(f'Du: {text}')
        self.input_edit.clear()
        self._toggle_send_state(True)
        QTimer.singleShot(0, lambda: self._process_chat(text))

    # ------------------------------------------------------------------ chat
    def _process_chat(self, text: str):
        try:
            response = self.chat_client.send_chat(text)
        except Exception as exc:  # noqa: BLE001
            self.chat_view.append(f'Fehler: {exc}')
        else:
            self.chat_view.append(f'AI: {response or "(leer)"}')
            self.chat_view.append('')
        finally:
            self._toggle_send_state(False)

    def _toggle_send_state(self, busy: bool):
        self.pending_request = busy
        self.send_button.setEnabled(not busy)
        self.send_button.setText('Senden...' if busy else 'Senden')
