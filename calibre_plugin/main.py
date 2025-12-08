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
import shutil
import subprocess
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

from calibre.gui2 import error_dialog, info_dialog

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient
from calibre_plugins.mcp_server_recherche.providers import (
    ensure_model_prefs,
    get_selected_model,
    set_selected_model,
    describe_provider,
)

log = logging.getLogger(__name__)


class MCPServerRechercheDialog(QDialog):
    """Main dialog for MCP Server Recherche."""

    def __init__(self, gui, icon, do_user_config):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.do_user_config = do_user_config

        # The current database shown in the GUI
        self.db = gui.current_db

        self.server_running = False
        self.server_process = None
        self.server_monitor = None
        self.chat_client = ChatProviderClient(prefs)
        self.pending_request = False

        self.project_root = Path(__file__).resolve().parents[1]
        self.dev_src_path = self.project_root / 'src'
        self.packaged_root = self.project_root / 'calibre_mcp_server'
        self.module_paths = []
        if self.dev_src_path.exists():
            self.module_paths.append(str(self.dev_src_path))
        if self.packaged_root.exists():
            self.module_paths.append(str(self.project_root))

        self._build_ui()
        self._load_initial_state()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        self.setWindowTitle('MCP Server Recherche')
        self.setWindowIcon(get_icons('images/icon.png'))

        layout = QVBoxLayout(self)

        # --- Top row: settings + server toggle -------------------------
        top_row = QHBoxLayout()

        self.settings_button = QPushButton('Einstellungen', self)
        self.settings_button.clicked.connect(self.open_settings)
        top_row.addWidget(self.settings_button)

        self.server_button = QPushButton('Server starten', self)
        self.server_button.clicked.connect(self.toggle_server)
        top_row.addWidget(self.server_button)

        layout.addLayout(top_row)

        # --- Connection info -------------------------------------------
        host = prefs['server_host']
        port = prefs['server_port']
        self.conn_label = QLabel(
            f'Ziel (spaeter): ws://{host}:{port}', self
        )
        layout.addWidget(self.conn_label)

        # --- Chat view -------------------------------------------------
        self.chat_view = QTextEdit(self)
        self.chat_view.setReadOnly(True)
        layout.addWidget(self.chat_view, 1)

        # --- Bottom row: input + send ---------------------------------
        bottom_row = QHBoxLayout()

        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText(
            'Frage oder Suchtext fuer die MCP-Recherche eingeben ...'
        )

        self.send_button = QPushButton('Senden', self)
        self.send_button.clicked.connect(self.send_message)

        bottom_row.addWidget(self.input_edit, 1)
        bottom_row.addWidget(self.send_button)

        layout.addLayout(bottom_row)

    # ----------------------------------------------------------- State -----

    def _load_initial_state(self):
        library = self._detect_calibre_library()
        if library:
            log.info("Detected Calibre library path: %s", library)
        else:
            log.info("No active Calibre library detected")

        ensure_model_prefs(prefs)
        selected = get_selected_model(prefs)
        log.info(
            "Initial selected model: provider=%s model=%s",
            selected.get('provider'),
            selected.get('model'),
        )

    # ---------------------------------------------------------- Settings ---

    def open_settings(self):
        self.do_user_config(parent=self)
        ensure_model_prefs(prefs)
        self.chat_client = ChatProviderClient(prefs)
        host = prefs['server_host']
        port = prefs['server_port']
        self.conn_label.setText(f'Ziel (spaeter): ws://{host}:{port}')

    # ---------------------------------------------------------- Server -----

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

    def _effective_library_path(self) -> (str, str):
        """Resolve library path and return (path, source)."""
        library_override = (prefs.get('library_path') or '').strip()
        use_active = prefs.get('use_active_library', True)

        if use_active:
            library_path = self._detect_calibre_library()
            source = 'current_db'
        else:
            library_path = library_override
            source = 'prefs'
        return library_path, source

    def _start_server(self):
        if self.server_running:
            return

        host = prefs['server_host']
        port = prefs['server_port']
        library_path, source = self._effective_library_path()

        if not library_path:
            self.chat_view.append(
                'System: Kein Calibre-Bibliothekspfad konfiguriert und keine aktuelle Bibliothek gefunden.'
            )
            return

        env = os.environ.copy()
        env['MCP_SERVER_HOST'] = host
        env['MCP_SERVER_PORT'] = str(port)
        env['CALIBRE_LIBRARY_PATH'] = library_path

        if self.module_paths:
            existing = env.get('PYTHONPATH')
            paths = list(self.module_paths)
            if existing:
                paths.append(existing)
            env['PYTHONPATH'] = os.pathsep.join(paths)

        log.info(
            "Starting MCP server: host=%s port=%s library_source=%s library=%r env=%r",
            host,
            port,
            source,
            library_path,
            {
                'MCP_SERVER_HOST': env.get('MCP_SERVER_HOST'),
                'MCP_SERVER_PORT': env.get('MCP_SERVER_PORT'),
                'CALIBRE_LIBRARY_PATH': env.get('CALIBRE_LIBRARY_PATH'),
                'PYTHONPATH': env.get('PYTHONPATH'),
            },
        )

        # Use Calibre's embedded Python to run the websocket server via -c
        python_cmd = self._python_executable()
        code = "from calibre_mcp_server.websocket_server import run_from_env; run_from_env()"
        cmd = [python_cmd, '-c', code]
        log.info("Command: %s", cmd)

        try:
            self.server_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
            )
        except OSError as exc:
            log.exception("Failed to start MCP server process")
            self.chat_view.append(f'System: Start fehlgeschlagen ({exc}).')
            self.server_process = None
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self.chat_view.append(
            f'System: MCP Server gestartet auf {host}:{port} (Bibliothek: {library_path})'
        )

        self._start_server_monitor()

    def _start_server_monitor(self):
        if not self.server_process:
            return

        def poll():
            if not self.server_process:
                return
            ret = self.server_process.poll()
            if ret is None:
                QTimer.singleShot(1000, poll)
                return

            try:
                stdout, stderr = self.server_process.communicate(timeout=0.1)
            except Exception:
                stdout, stderr = '', ''
            log.info("Server exit code: %s", ret)
            if stdout:
                log.info("Server stdout:\n%s", stdout)
            if stderr:
                log.info("Server stderr:\n%s", stderr)

            if ret != 0:
                self.chat_view.append(
                    f'System: MCP Server beendet (Code {ret}).\n{stderr.splitlines()[0] if stderr else ""}'
                )
            else:
                self.chat_view.append('System: MCP Server gestoppt.')

            self.server_process = None
            self.server_running = False
            self.server_button.setText('Server starten')

        QTimer.singleShot(1000, poll)

    def _stop_server(self):
        if not self.server_running or not self.server_process:
            return
        try:
            self.server_process.terminate()
        except Exception as exc:
            log.exception("Failed to terminate MCP server: %s", exc)
        self.server_running = False
        self.server_button.setText('Server starten')
        self.chat_view.append('System: MCP Server wird gestoppt ...')

    # -------------------------------------------------------------- Chat ---

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
        except Exception as exc:
            log.exception("Chat request failed")
            self.chat_view.append(f'System: Fehler beim Chat-Request: {exc}')
        else:
            if response:
                self.chat_view.append(f'AI: {response}')
            else:
                self.chat_view.append('System: Keine Antwort vom Provider erhalten.')
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
        # Default: use Calibre embedded Python (sys.executable)
        return sys.executable


# -----------------------------------------------------------------------


def create_dialog(gui, icon, do_user_config):
    d = MCPServerRechercheDialog(gui, icon, do_user_config)
    return d
