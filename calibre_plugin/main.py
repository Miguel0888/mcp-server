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
    QWidget,
    QScrollArea,
    QFrame,
    QTextBrowser,
    QToolButton,
)

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient
from calibre_plugins.mcp_server_recherche.recherche_agent import RechercheAgent


log = logging.getLogger(__name__)


class ChatMessageWidget(QFrame):
    """Eine einzelne Chat-Nachricht (User, AI, System, Debug) mit optionalen Tool-Details."""

    def __init__(self, role: str, text: str, tool_trace: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self.tool_trace = tool_trace

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        layout = QVBoxLayout(self)

        # Kopfzeile mit Rollen-Label
        header = QHBoxLayout()
        role_label = QLabel(self._role_label(), self)
        role_label.setStyleSheet(self._role_style())
        header.addWidget(role_label)
        header.addStretch(1)
        layout.addLayout(header)

        # Inhalt als QTextBrowser (unterstuetzt einfache Markdown/HTML)
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(True)
        # Wenn verfuegbar, einfachen Markdown anzeigen, sonst HTML-Fallback
        try:
            # Qt6: QTextBrowser.setMarkdown; kann in aelteren Umgebungen fehlen
            setter = getattr(self.text_browser, 'setMarkdown', None)
        except Exception:
            setter = None
        if callable(setter):
            setter(text)
        else:
            self.text_browser.setHtml(self._to_html(text))
        self.text_browser.setFrameStyle(QFrame.NoFrame)
        layout.addWidget(self.text_browser)

        # Optionaler aufklappbarer Tool-Trace
        self.trace_widget = None
        if tool_trace:
            toggle_row = QHBoxLayout()
            self.toggle_button = QToolButton(self)
            self.toggle_button.setText('Tool-Details anzeigen')
            self.toggle_button.setCheckable(True)
            self.toggle_button.toggled.connect(self._toggle_trace)
            toggle_row.addWidget(self.toggle_button)
            toggle_row.addStretch(1)
            layout.addLayout(toggle_row)

            self.trace_widget = QTextEdit(self)
            self.trace_widget.setReadOnly(True)
            self.trace_widget.setPlainText(tool_trace)
            self.trace_widget.setVisible(False)
            self.trace_widget.setStyleSheet('font-size: 10px; color: #555;')
            layout.addWidget(self.trace_widget)

    def _role_label(self) -> str:
        if self.role == 'user':
            return 'Du'
        if self.role == 'ai':
            return 'AI'
        if self.role == 'system':
            return 'System'
        if self.role == 'debug':
            return 'Debug'
        return self.role

    def _role_style(self) -> str:
        if self.role == 'user':
            return 'font-weight: bold; color: #0055aa;'
        if self.role == 'ai':
            return 'font-weight: bold; color: #228822;'
        if self.role == 'system':
            return 'font-weight: bold; color: #aa5500;'
        if self.role == 'debug':
            return 'font-weight: bold; color: #777777;'
        return 'font-weight: bold;'

    def _to_html(self, text: str) -> str:
        """Sehr einfacher Markdown-zu-HTML-Fallback fuer Umgebungen ohne setMarkdown."""
        escaped = (
            text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )
        # Zeilenumbrueche in <br> umsetzen, damit die Struktur lesbar bleibt
        escaped = escaped.replace('\n', '<br/>')
        html = '<div style="white-space: normal;">%s</div>' % escaped
        return html

    def _toggle_trace(self, checked: bool):
        if self.trace_widget is not None:
            self.trace_widget.setVisible(checked)
            self.toggle_button.setText('Tool-Details verbergen' if checked else 'Tool-Details anzeigen')


class ChatPanel(QWidget):
    """Scrollbares Chatpanel mit einzelnen ChatMessageWidgets."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        container = QWidget(self.scroll)
        self.messages_layout = QVBoxLayout(container)
        self.messages_layout.setContentsMargins(4, 4, 4, 4)
        self.messages_layout.setSpacing(6)
        self.messages_layout.addStretch(1)

        self.scroll.setWidget(container)

    def add_message(self, role: str, text: str, tool_trace: str | None = None):
        widget = ChatMessageWidget(role=role, text=text, tool_trace=tool_trace, parent=self)
        # Stretch am Ende entfernen, Nachricht einfuegen, Stretch wieder anfuegen
        count = self.messages_layout.count()
        if count > 0:
            last_item = self.messages_layout.itemAt(count - 1)
            if last_item is not None and last_item.spacerItem() is not None:
                self.messages_layout.removeItem(last_item)
        self.messages_layout.addWidget(widget)
        self.messages_layout.addStretch(1)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def add_user_message(self, text: str):
        self.add_message('user', text)

    def add_ai_message(self, text: str, tool_trace: str | None = None):
        self.add_message('ai', text, tool_trace=tool_trace)

    def add_system_message(self, text: str):
        self.add_message('system', text)

    def add_debug_message(self, text: str):
        self.add_message('debug', text)

    def clear(self):
        # Alle Nachrichten entfernen
        while self.messages_layout.count() > 0:
            item = self.messages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.messages_layout.addStretch(1)

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())


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
        # Altes QTextEdit durch ein flexibleres ChatPanel ersetzen
        self.chat_panel = ChatPanel(self)
        main_layout.addWidget(self.chat_panel)

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
        self._trace_buffer: list[str] = []
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
            self.chat_panel.add_system_message(
                'Kein Calibre-Bibliothekspfad konfiguriert und keine aktuelle Bibliothek gefunden.'
            )
            return

        if self.server_running and self.server_process and self.server_process.poll() is None:
            self.chat_panel.add_system_message('MCP Server laeuft bereits.')
            return

        try:
            python_cmd = self._python_executable()
        except RuntimeError as exc:
            log.error("No usable Python interpreter: %s", exc)
            self.chat_panel.add_system_message(f'System: {exc}')
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
            self.chat_panel.add_system_message(f'MCP Server konnte nicht starten: {exc}')
            self.server_process = None
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self.chat_panel.add_system_message(f'MCP Server gestartet auf ws://{host}:{port}.')
        self.server_monitor.start()

    def _stop_server(self):
        proc = self.server_process
        self.server_process = None
        if not proc:
            self.server_running = False
            self.server_button.setText('Server starten')
            self.server_monitor.stop()
            self.chat_panel.add_system_message('MCP Server wurde gestoppt.')
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
            self.chat_panel.add_system_message(f'stderr: {stderr.strip()[:500]}')
        if stdout:
            self.chat_panel.add_system_message(f'stdout: {stdout.strip()[:500]}')

        self.server_running = False
        self.server_button.setText('Server starten')
        self.server_monitor.stop()
        self.chat_panel.add_system_message('MCP Server wurde gestoppt.')

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

        self.chat_panel.add_system_message(msg)
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
        self.chat_panel.clear()
        self._trace_buffer = []
        self.agent = RechercheAgent(prefs, trace_callback=self._append_trace)
        self.chat_panel.add_system_message('Neuer Chat gestartet.')

    def send_message(self):
        if self.pending_request:
            return

        text = self.input_edit.text().strip()
        if not text:
            return

        self.chat_panel.add_user_message(text)
        self.input_edit.clear()
        self._toggle_send_state(True)

        QTimer.singleShot(0, lambda: self._process_chat(text))

    def _process_chat(self, text: str):
        try:
            self.chat_panel.add_system_message('Starte Recherche uebers MCP-Backend ...')
            self._trace_buffer = []
            response = self.agent.answer_question(text)
        except Exception as exc:
            log.exception("Research agent failed")
            self.chat_panel.add_system_message(f'Fehler in der Recherche-Pipeline: {exc}')
        else:
            if response:
                # Gesammelte Traces zu einem Block zusammenfassen
                tool_trace = None
                if self.debug_checkbox.isChecked() and self._trace_buffer:
                    tool_trace = "\n".join(self._trace_buffer)
                self.chat_panel.add_ai_message(response, tool_trace=tool_trace)
            else:
                self.chat_panel.add_system_message('Keine Antwort vom Provider erhalten.')
        finally:
            self._toggle_send_state(False)

    def _append_trace(self, message: str):
        """Trace-Callback fuer den Agenten.

        Statt jede Trace-Zeile sofort anzuzeigen, werden sie im aktuellen
        Chat-Durchlauf gesammelt und als aufklappbare Tool-Details an die
        naechste AI-Antwort angehaengt (sofern Debug aktiviert ist).
        """
        # Immer puffern, damit wir die Infos fuer die naechste Antwort haben
        self._trace_buffer.append(message)
        # Optional zusaetzlich inline als Debug-Nachricht anzeigen
        if self.debug_checkbox.isChecked():
            self.chat_panel.add_debug_message(message)

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

def create_dialog(gui, icon, do_user_config):
    d = MCPServerRechercheDialog(gui, icon, do_user_config)
    return d
