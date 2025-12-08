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

import logging
import os
import sys
from pathlib import Path

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
from calibre_plugins.mcp_server_recherche.server_runner import MCPServerThread


log = logging.getLogger(__name__)


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
        self.server_thread: MCPServerThread | None = None
        self.chat_client = ChatProviderClient(prefs)
        self.pending_request = False

        self.server_monitor = QTimer(self)
        self.server_monitor.setInterval(1000)
        self.server_monitor.timeout.connect(self._monitor_server)

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

        self.calibre_library_path = self._detect_calibre_library()
        log.info("Detected Calibre library path: %s", self.calibre_library_path)

        self.project_root = Path(__file__).resolve().parents[1]
        self.plugin_root = Path(__file__).resolve().parent
        self.server_package = self.plugin_root / 'calibre_mcp_server'
        self.module_roots = []
        self.server_cwd = Path.cwd()
        log.info("Detected Calibre library path: %s", self.calibre_library_path)

    # ------------------------------------------------------------------ UI

    def open_settings(self):
        """Open calibre's plugin configuration dialog."""
        self.do_user_config(parent=self)
        self.chat_client = ChatProviderClient(prefs)
        self._update_conn_label()

    def _update_conn_label(self):
        host = prefs['server_host'] or '127.0.0.1'
        port = prefs['server_port'] or '8765'
        self.conn_label.setText(f'Ziel (spaeter): ws://{host}:{port}')

    def toggle_server(self):
        if self.server_running:
            self._stop_server()
        else:
            self._start_server()

    def _detect_calibre_library(self) -> str:
        path = ""
        try:
            if hasattr(self.db, 'library_path') and self.db.library_path:
                path = self.db.library_path
            elif hasattr(self.db, 'new_api') and getattr(self.db.new_api, 'library_path', None):
                path = self.db.new_api.library_path
        except Exception as exc:
            log.exception("Could not detect calibre library path: %s", exc)
        return path or ""

    def _start_server(self):
        host = (prefs['server_host'] or '127.0.0.1').strip() or '127.0.0.1'
        try:
            port = int((prefs['server_port'] or '8765').strip() or '8765')
        except ValueError:
            port = 8765

        library_override = prefs['library_path'].strip()
        use_active = prefs.get('use_active_library', True)
        if use_active or not library_override:
            library_path = self.calibre_library_path
            source = 'current_db'
        else:
            library_path = library_override
            source = 'prefs'
        if not library_path:
            self.chat_view.append('System: Kein Calibre-Bibliothekspfad konfiguriert und kein aktuelle Bibliothek gefunden.')
            return

        if self.server_thread and self.server_thread.is_running:
            self.chat_view.append('System: MCP Server laeuft bereits.')
            return

        self.server_thread = MCPServerThread(host, port, library_path)
        self.server_thread.start()
        if not self.server_thread.wait_until_started(timeout=3):
            error = self.server_thread.last_error or 'Unbekannter Fehler'
            self.chat_view.append(f'System: MCP Server konnte nicht starten: {error}')
            self.server_thread = None
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self.chat_view.append(f'System: MCP Server gestartet auf ws://{host}:{port}.')
        self.server_monitor.start()

    def _stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
        self.server_running = False
        self.server_button.setText('Server starten')
        self.chat_view.append('System: MCP Server wurde gestoppt.')
        self.server_monitor.stop()

    def _monitor_server(self):
        if self.server_thread and not self.server_thread.is_running:
            error = self.server_thread.last_error
            self.server_thread = None
            self.server_running = False
            self.server_button.setText('Server starten')
            msg = 'System: MCP Server beendet.'
            if error:
                msg += f' Fehler: {error}'
            self.chat_view.append(msg)
            self.server_monitor.stop()

    def closeEvent(self, event):
        self._stop_server()
        super().closeEvent(event)

    def send_message(self):
        if self.pending_request:
            return
        text = self.input_edit.text().strip()
        if not text:
            return
        self.chat_view.append(f'Du: {text}')
        self.input_edit.clear()
        self._toggle_send_state(True)
        QTimer.singleShot(0, lambda: self._process_chat(text))

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

    def _python_executable(self) -> str:
        override = prefs.get('python_executable', '').strip()
        if override:
            return override
        python_cmd = sys.executable
        basename = os.path.basename(python_cmd).lower()
        if basename.startswith('calibre-') or basename == 'pythonw.exe':
            preferred = shutil.which('python') or shutil.which('python3')
            if preferred:
                python_cmd = preferred
        return python_cmd
