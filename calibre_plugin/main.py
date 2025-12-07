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

import os
import subprocess
import sys

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
        self.server_process: subprocess.Popen | None = None
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

    def _start_server(self):
        if self.server_process and self.server_process.poll() is None:
            self.chat_view.append('System: MCP Server laeuft bereits.')
            return

        host = (prefs['server_host'] or '127.0.0.1').strip() or '127.0.0.1'
        try:
            port = int((prefs['server_port'] or '8765').strip() or '8765')
        except ValueError:
            port = 8765

        library_path = prefs['library_path'].strip()
        if not library_path:
            library_path = getattr(self.db, 'library_path', '') or ''

        env = os.environ.copy()
        env['MCP_SERVER_HOST'] = host
        env['MCP_SERVER_PORT'] = str(port)
        if library_path:
            env['CALIBRE_LIBRARY_PATH'] = library_path

        cmd = [sys.executable, '-m', 'calibre_mcp_server.websocket_server']

        try:
            self.server_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
            )
        except OSError as exc:
            self.chat_view.append(f'System: Start fehlgeschlagen ({exc}).')
            self.server_process = None
            return

        # Wait briefly for immediate failure
        try:
            code = self.server_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            code = None

        if code is not None:
            details = self._drain_process_stderr(self.server_process)
            self.server_process = None
            self.chat_view.append(f'System: MCP Server konnte nicht starten (Code {code}).')
            if details:
                self.chat_view.append(f'Details: {details}')
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self.chat_view.append(f'System: MCP Server gestartet auf ws://{host}:{port}.')
        self.server_monitor.start()

    def _stop_server(self):
        proc = self.server_process
        self.server_process = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc:
            details = self._drain_process_stderr(proc)
            if details and self.server_running:
                self.chat_view.append(f'System: Server-Log: {details}')
        self.server_running = False
        self.server_button.setText('Server starten')
        self.chat_view.append('System: MCP Server wurde gestoppt.')
        self.server_monitor.stop()

    def _monitor_server(self):
        if not self.server_process:
            return
        code = self.server_process.poll()
        if code is not None:
            details = self._drain_process_stderr(self.server_process)
            self.server_process = None
            self.server_running = False
            self.server_button.setText('Server starten')
            self.chat_view.append(f'System: MCP Server beendet (Code {code}).')
            if details:
                self.chat_view.append(f'Details: {details}')
            self.server_monitor.stop()

    def _drain_process_stderr(self, proc: subprocess.Popen | None) -> str:
        if not proc or not proc.stderr:
            return ''
        try:
            proc.stderr.seek(0)  # ensure pointer at start if possible
        except Exception:
            pass
        data = proc.stderr.read() or ''
        try:
            proc.stderr.close()
        except Exception:
            pass
        text = data.strip()
        return text[:1000]

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
