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
import shutil
import subprocess
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
    QCheckBox,
)

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient
from calibre_plugins.mcp_server_recherche.recherche_agent import RechercheAgent


log = logging.getLogger(__name__)


class MCPServerRechercheDialog(QDialog):
    """Main dialog for MCP Server Recherche."""

    def __init__(self, gui, icon, do_user_config):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.do_user_config = do_user_config

        # Use the current database from the GUI
        self.db = gui.current_db

        self.server_running = False
        self.server_process: subprocess.Popen | None = None
        # Trace-Checkbox erst nach UI-Aufbau initialisieren, Agent danach
        self.agent = None
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

        # Neuer Chat-Button: Verlauf loeschen & Agent-Session zuruecksetzen
        self.newchat_button = QPushButton('Neuer Chat', self)
        self.newchat_button.clicked.connect(self.new_chat)
        top_row.addWidget(self.newchat_button)

        # Debug-Checkbox fuer Tool-Trace
        self.debug_checkbox = QCheckBox('Tool-Details anzeigen', self)
        top_row.addWidget(self.debug_checkbox)

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
        # Spaeter koennen wir hier HTML/Markdown anzeigen; derzeit einfache Plain-Append.
        main_layout.addWidget(self.chat_view)

        # --- Input row -----------------------------------------------------
        input_row = QHBoxLayout()

        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText(
            'Frage oder Suchtext fuer die MCP-Recherche eingeben ...'
        )
        self.input_edit.returnPressed.connect(self.send_message)
        input_row.addWidget(self.input_edit)

        self.send_button = QPushButton('Senden', self)
        self.send_button.setDefault(True)
        self.send_button.setAutoDefault(True)
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)

        main_layout.addLayout(input_row)

        # Window setup
        self.setWindowTitle('MCP Server Recherche')
        self.setWindowIcon(icon)
        self.resize(700, 500)

        # Detect initial library path
        self.calibre_library_path = self._detect_calibre_library()
        log.info("Detected Calibre library path: %s", self.calibre_library_path)

        # Agent nach Aufbau der UI initialisieren, damit Trace ins Chatfenster gehen kann
        self.agent = RechercheAgent(prefs, trace_callback=self._append_trace)

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

    # ------------------------------------------------------------------ Server control (external Python)

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
            self.chat_view.append(
                'System: Kein Calibre-Bibliothekspfad konfiguriert und keine aktuelle Bibliothek gefunden.'
            )
            return

        if self.server_running and self.server_process and self.server_process.poll() is None:
            self.chat_view.append('System: MCP Server laeuft bereits.')
            return

        try:
            python_cmd = self._python_executable()
        except RuntimeError as exc:
            log.error("No usable Python interpreter: %s", exc)
            self.chat_view.append(f'System: {exc}')
            return

        env = os.environ.copy()
        env['MCP_SERVER_HOST'] = host
        env['MCP_SERVER_PORT'] = str(port)
        env['CALIBRE_LIBRARY_PATH'] = library_path

        cmd = [python_cmd, '-m', 'calibre_mcp_server.websocket_server']
        log.info(
            "Starting MCP server: cmd=%r host=%s port=%s library_source=%s library=%r",
            cmd,
            host,
            port,
            source,
            library_path,
        )

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
            self.chat_view.append(f'System: MCP Server konnte nicht starten: {exc}')
            self.server_process = None
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self.chat_view.append(f'System: MCP Server gestartet auf ws://{host}:{port}.')
        self.server_monitor.start()

    def _stop_server(self):
        proc = self.server_process
        self.server_process = None
        if not proc:
            self.server_running = False
            self.server_button.setText('Server starten')
            self.server_monitor.stop()
            self.chat_view.append('System: MCP Server wurde gestoppt.')
            return

        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as exc:
            log.exception("Failed to terminate MCP server: %s", exc)

        stdout = ''
        stderr = ''
        try:
            if proc.stdout:
                stdout = proc.stdout.read()
            if proc.stderr:
                stderr = proc.stderr.read()
        except Exception as exc:
            log.exception("Failed to read server output on stop: %s", exc)

        if stderr:
            self.chat_view.append(f'stderr: {stderr.strip()[:500]}')
        if stdout:
            self.chat_view.append(f'stdout: {stdout.strip()[:500]}')

        self.server_running = False
        self.server_button.setText('Server starten')
        self.server_monitor.stop()
        self.chat_view.append('System: MCP Server wurde gestoppt.')

    def _monitor_server(self):
        proc = self.server_process
        if not proc:
            self.server_monitor.stop()
            return

        ret = proc.poll()
        if ret is None:
            return

        stdout = ''
        stderr = ''
        try:
            if proc.stdout:
                stdout = proc.stdout.read()
            if proc.stderr:
                stderr = proc.stderr.read()
        except Exception as exc:
            log.exception("Failed to read server output: %s", exc)

        log.info("MCP server exited with code %s", ret)
        if stdout:
            log.info("MCP server stdout:\\n%s", stdout)
        if stderr:
            log.info("MCP server stderr:\\n%s", stderr)

        if ret != 0:
            msg = f'System: MCP Server beendet (Code {ret}).'
            if stderr:
                first_line = stderr.strip().splitlines()[0]
                msg += f'\\n{first_line}'
        else:
            msg = 'System: MCP Server wurde normal beendet.'

        self.chat_view.append(msg)
        self.server_process = None
        self.server_running = False
        self.server_button.setText('Server starten')
        self.server_monitor.stop()

    def closeEvent(self, event):
        self._stop_server()
        super().closeEvent(event)

    # ------------------------------------------------------------------ Chat

    def new_chat(self):
        """Loesche aktuellen Chatverlauf und setze Agent-Session zurueck."""
        self.chat_view.clear()
        # Agent besitzt Session-Zustand (z. B. letzte Frage/ Treffer); durch Neuinstanzierung zuruecksetzen
        self.agent = RechercheAgent(prefs, trace_callback=self._append_trace)
        self.chat_view.append('System: Neuer Chat gestartet.')

    def send_message(self):
        if self.pending_request:
            return

        text = self.input_edit.text().strip()
        if not text:
            return

        # Einfache Markdown-artige Darstellung: Nutzer fett markieren
        self.chat_view.append(f'**Du:** {text}')
        self.input_edit.clear()
        self._toggle_send_state(True)

        QTimer.singleShot(0, lambda: self._process_chat(text))

    def _process_chat(self, text: str):
        try:
            # Zwischenstatus: Recherche startet
            self.chat_view.append('_System: Starte Recherche uebers MCP-Backend ..._')

            response = self.agent.answer_question(text)
        except Exception as exc:
            log.exception("Research agent failed")
            self.chat_view.append(f'**System:** Fehler in der Recherche-Pipeline: {exc}')
        else:
            if response:
                # Trennstrich
                self.chat_view.append('---')
                # Antwort als Markdown-artiger Block anzeigen
                self.chat_view.append(f'**AI:**\n{response}')
            else:
                self.chat_view.append('**System:** Keine Antwort vom Provider erhalten.')
        finally:
            self._toggle_send_state(False)

    def _toggle_send_state(self, busy: bool):
        self.pending_request = busy
        self.send_button.setEnabled(not busy)
        self.send_button.setText('Senden...' if busy else 'Senden')

    def _python_executable(self) -> str:
        """Resolve Python interpreter based on prefs and auto-detect flag."""
        auto = prefs.get('auto_detect_python', True)
        configured = (prefs.get('python_executable') or '').strip()

        def is_calibre_executable(path):
            """Return True if executable is very likely a calibre launcher."""
            if not path:
                return False
            name = os.path.basename(path).lower()
            return (
                name.startswith('calibre-')
                or name == 'calibre.exe'
                or name == 'calibre-debug.exe'
                or name == 'calibre-parallel.exe'
            )

        def collect_candidates():
            """Collect possible Python executables in order of preference."""
            candidates = []

            # 1) Configured path (only as hint in auto-mode)
            if configured:
                candidates.append(configured)

            # 2) python / python3 from PATH
            candidates.append(shutil.which('python'))
            candidates.append(shutil.which('python3'))

            # 3) sys.executable if it is not a calibre wrapper
            if sys.executable and not is_calibre_executable(sys.executable):
                candidates.append(sys.executable)

            # Deduplicate and filter invalid
            seen = set()
            result = []
            for c in candidates:
                if not c:
                    continue
                if c in seen:
                    continue
                seen.add(c)
                if not os.path.exists(c):
                    continue
                if is_calibre_executable(c):
                    continue
                result.append(c)
            return result

        # --- Manueller Modus: Checkbox aus ---------------------------------
        if not auto:
            if configured and os.path.exists(configured) and not is_calibre_executable(configured):
                log.info("Use configured Python executable (manual mode): %s", configured)
                return configured
            raise RuntimeError(
                "Python-Interpreter ist nicht gueltig konfiguriert. "
                "Entweder einen Pfad setzen oder 'Python automatisch ermitteln' aktivieren."
            )

        # --- Auto-Modus: Checkbox an ---------------------------------------
        candidates = collect_candidates()
        if not candidates:
            raise RuntimeError(
                "Kein geeigneter Python-Interpreter gefunden. "
                "Bitte sicherstellen, dass python/python3 im PATH ist oder einen Pfad konfigurieren."
            )

        chosen = candidates[0]
        log.info("Auto-detected Python executable: %s", chosen)
        return chosen

    def _append_trace(self, line: str) -> None:
        """Optional Tool-/MCP-Trace in das Chatfenster schreiben."""
        if not getattr(self, 'debug_checkbox', None):
            return
        if not self.debug_checkbox.isChecked():
            return
        self.chat_view.append(f'DEBUG: {line}')

def create_dialog(gui, icon, do_user_config):
    d = MCPServerRechercheDialog(gui, icon, do_user_config)
    return d
