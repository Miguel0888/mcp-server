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

import collections
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
    QStyle,
    Qt,
    QSizePolicy,
    QThread,
    QObject,
    pyqtSignal,
    QFileDialog,
)

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient
from calibre_plugins.mcp_server_recherche.recherche_agent import RechercheAgent, EnrichedHit


log = logging.getLogger(__name__)


class AgentWorker(QObject):
    """Worker-Objekt, das den RechercheAgent im Hintergrund ausfuehrt."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, agent: RechercheAgent, question: str, parent: QObject | None = None):
        super().__init__(parent)
        self._agent = agent
        self._question = question

    def run(self) -> None:
        try:
            # Liefere Antworttext und EnrichedHits, damit das UI
            # parallel die Quellen anzeigen kann.
            response = self._agent.answer_with_sources(self._question)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(response)


class ChatMessageWidget(QFrame):
    """Eine einzelne Chat-Nachricht (User, AI, System, Debug) mit optionalen Tool-Details."""

    def __init__(self, role: str, text: str = "", tool_trace: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self.tool_trace = tool_trace

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Kopfzeile mit Rollen-Label
        header = QHBoxLayout()
        role_label = QLabel(self._role_label(), self)
        role_label.setStyleSheet(self._role_style())
        header.addWidget(role_label)
        header.addStretch(1)
        layout.addLayout(header)

        # Optionaler aufklappbarer Tool-Trace mit Pfeilsymbol und dynamischem Titel
        self.trace_widget = None
        self.trace_title_label = None
        self.toggle_button = None
        # Debug-Pfeil direkt UNTER der Kopfzeile, also VOR der eigentlichen AI-Antwort,
        # damit er schon waehrend der Tool-Ausfuehrung sinnvoll wirkt.
        if self.role == 'ai' or tool_trace is not None:
            toggle_row = QHBoxLayout()
            toggle_row.setContentsMargins(0, 0, 0, 0)
            toggle_row.setSpacing(2)
            self.toggle_button = QToolButton(self)
            self.toggle_button.setCheckable(True)
            self.toggle_button.setArrowType(Qt.RightArrow)
            self.toggle_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.toggle_button.toggled.connect(self._toggle_trace)
            toggle_row.addWidget(self.toggle_button)

            self.trace_title_label = QLabel('', self)
            self.trace_title_label.setStyleSheet('font-size: 10px; color: #555;')
            toggle_row.addWidget(self.trace_title_label)

            toggle_row.addStretch(1)
            layout.addLayout(toggle_row)

            self.trace_widget = QTextEdit(self)
            self.trace_widget.setReadOnly(True)
            self.trace_widget.setPlainText(tool_trace or "")
            self.trace_widget.setVisible(False)
            self.trace_widget.setStyleSheet('font-size: 10px; color: #555;')
            self.trace_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
            layout.addWidget(self.trace_widget)

        # Inhalt als QTextBrowser (unterstuetzt einfache Markdown/HTML)
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        # Scrollbar EXPLIZIT beibehalten, damit lange Antworten scrollbar sind
        # und nicht das gesamte Chatlayout sprengen.
        # Wir koppeln nur Min/Max-Hoehe an den Inhalt, damit kurze Nachrichten
        # nicht unnoetig viel Platz einnehmen.
        # Horizontal weiterhin ohne Scrollbar.
        self.text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_browser.setFrameStyle(QFrame.NoFrame)
        layout.addWidget(self.text_browser)
        # Initialen Text setzen (kann leer sein und spaeter gefuellt werden)
        self.set_message_text(text)

    def set_message_text(self, text: str) -> None:
        """Antworttext setzen und Groesse an Inhalt anpassen.

        Darf auch mehrfach aufgerufen werden (zunaechst leer, spaeter
        mit der endgueltigen Antwort).
        """
        text = text or ""
        try:
            setter = getattr(self.text_browser, 'setMarkdown', None)
        except Exception:
            setter = None
        if callable(setter):
            self.text_browser.setMarkdown(text)
        else:
            self.text_browser.setHtml(self._to_html(text))

        # Dokumentgroesse an Inhalt anpassen und daraus eine Widgethoehe ableiten,
        # damit die Box nur so gross ist wie ihr Inhalt. Wir setzen sowohl
        # Minimum- als auch Maximalhoehe, damit jede Nachricht eine eigene,
        # inhaltsabhaengige Hoehe erhaelt.
        doc = self.text_browser.document()
        doc.adjustSize()
        doc_size = doc.size()
        min_height = int(doc_size.height()) + 4
        if min_height < 20:
            # Sehr kurze Texte (oder leer) nicht zu hoch machen
            min_height = 20
        self.text_browser.setMinimumHeight(min_height)
        self.text_browser.setMaximumHeight(min_height)
        self.text_browser.updateGeometry()
        self.updateGeometry()

    def update_trace(self, title: str | None, content: str):
        """Trace-Inhalt und optionalen Titel aktualisieren."""
        if self.trace_widget is None:
            return
        self.trace_widget.setPlainText(content or "")
        if self.trace_title_label is not None:
            self.trace_title_label.setText(title or '')

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
            # Pfeilrichtung anpassen
            self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)


class ChatPanel(QWidget):
    """Scrollbares Chatpanel mit einzelnen ChatMessageWidgets."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea(self)
        # Wichtiger Punkt: das innere Widget bestimmt seine Groesse selbst,
        # wir wollen, dass jede Chat-Box nur so hoch ist wie ihr Inhalt.
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll)

        container = QWidget(self.scroll)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.messages_layout = QVBoxLayout(container)
        self.messages_layout.setContentsMargins(4, 4, 4, 4)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch(1)

        self.scroll.setWidget(container)

    def add_message(self, role: str, text: str, tool_trace: str | None = None) -> ChatMessageWidget:
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
        return widget

    def add_user_message(self, text: str) -> ChatMessageWidget:
        return self.add_message('user', text)

    def add_ai_message(self, text: str, tool_trace: str | None = None) -> ChatMessageWidget:
        return self.add_message('ai', text, tool_trace=tool_trace)

    def add_system_message(self, text: str) -> ChatMessageWidget:
        return self.add_message('system', text)

    def add_debug_message(self, text: str) -> ChatMessageWidget:
        return self.add_message('debug', text)

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

    trace_signal = pyqtSignal(str)

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

        # Statusleisten-Queue fuer Systemmeldungen
        self._status_queue = collections.deque()
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._show_next_status)

        # Quellen-Panel interner Zustand
        self._source_hits = []  # Liste von Dicts mit {book_id, title, isbn, excerpt}

        # Oberes Layout mit Steuerleiste bleibt wie gehabt
        outer_layout = QVBoxLayout(self)
        self.setLayout(outer_layout)

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

        # Debug-Checkbox fuer Tool-Trace, Zustand aus Prefs wiederherstellen
        self.debug_checkbox = QCheckBox('Tool-Details anzeigen', self)
        self.debug_checkbox.setChecked(prefs.get('debug_trace_enabled', True))
        top_row.addWidget(self.debug_checkbox)

        # Toggle fuer das Quellen-Panel
        self.sources_toggle = QCheckBox('Quellen anzeigen', self)
        self.sources_toggle.setChecked(True)
        self.sources_toggle.stateChanged.connect(self._toggle_sources_panel)
        top_row.addWidget(self.sources_toggle)

        # Export-Button fuer Quellen (JSON)
        self.export_sources_button = QPushButton('Quellen exportieren', self)
        self.export_sources_button.clicked.connect(self._export_sources_to_file)
        top_row.addWidget(self.export_sources_button)

        top_row.addStretch(1)
        outer_layout.addLayout(top_row)

        # Optional connection info from prefs
        host = prefs['server_host']
        port = prefs['server_port']
        self.conn_label = QLabel(
            f'Ziel (spaeter): ws://{host}:{port}', self
        )
        outer_layout.addWidget(self.conn_label)

        # Hauptrahmen: links Chat, rechts Quellen
        main_split = QHBoxLayout()
        outer_layout.addLayout(main_split)

        # Linke Seite: Chat
        chat_column = QVBoxLayout()
        main_split.addLayout(chat_column, 3)

        self.chat_panel = ChatPanel(self)
        chat_column.addWidget(self.chat_panel)

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

        chat_column.addLayout(input_row)

        # Rechte Seite: Quellen-Panel
        self.sources_panel = QScrollArea(self)
        self.sources_panel.setWidgetResizable(True)
        self.sources_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sources_container = QWidget(self.sources_panel)
        self.sources_layout = QVBoxLayout(sources_container)
        self.sources_layout.setContentsMargins(4, 4, 4, 4)
        self.sources_layout.setSpacing(6)
        self.sources_layout.addStretch(1)
        self.sources_panel.setWidget(sources_container)
        main_split.addWidget(self.sources_panel, 2)

        # Statusleiste unten wie gehabt
        status_row = QHBoxLayout()
        self.status_label = QLabel('', self)
        self.status_label.setStyleSheet('color: #555555; font-size: 10px;')
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        outer_layout.addLayout(status_row)

        # Window setup
        self.setWindowTitle('MCP Server Recherche')
        self.setWindowIcon(icon)
        # Fenstergroesse aus Prefs wiederherstellen oder beim ersten Mal
        # an die Groesse des Calibre-Hauptfensters anlehnen.
        w = prefs.get('window_width', 0) or 0
        h = prefs.get('window_height', 0) or 0
        if w > 0 and h > 0:
            self.resize(w, h)
        else:
            try:
                main_size = gui.size()
                self.resize(main_size)
            except Exception:
                self.resize(800, 600)

        # Detect initial library path
        self.calibre_library_path = self._detect_calibre_library()
        log.info("Detected Calibre library path: %s", self.calibre_library_path)

        # Agent nach Aufbau der UI initialisieren, damit Trace ins Chatfenster gehen kann
        self._trace_buffer: list[str] = []
        self._trace_title: str | None = None
        self._current_ai_message: ChatMessageWidget | None = None

        # Trace-Signal vom Worker in den UI-Thread verbinden
        self.trace_signal.connect(self._append_trace)

        self.agent = RechercheAgent(prefs, trace_callback=self._trace_from_worker)

    def closeEvent(self, event):
        # Fenstergroesse und Debug-Checkbox-Zustand in Prefs sichern,
        # bevor der Dialog geschlossen wird.
        try:
            size = self.size()
            prefs['window_width'] = size.width()
            prefs['window_height'] = size.height()
            prefs['debug_trace_enabled'] = self.debug_checkbox.isChecked()
        except Exception:
            log.exception("Failed to persist dialog geometry / debug flag")
        self._stop_server()
        super().closeEvent(event)

    # ----------------------------- Statusbar-Helfer ---------------------

    def _enqueue_status(self, message: str, min_ms: int = 3000):
        """Neue Statusmeldung in die Queue stellen und ggf. sofort anzeigen."""
        self._status_queue.append((message, min_ms))
        if not self._status_timer.isActive() and self._status_queue:
            self._show_next_status()

    def _show_next_status(self):
        if not self._status_queue:
            self.status_label.setText('')
            return
        message, min_ms = self._status_queue.popleft()
        self.status_label.setText(message)
        self._status_timer.start(max(1000, min_ms))

    # ------------------------------------------------------------------ UI

    def open_settings(self):
        """Open calibre's plugin configuration dialog."""
        self.do_user_config(parent=self)
        self.chat_client = ChatProviderClient(prefs)
        self._update_conn_label()
        self._enqueue_status('Einstellungen aktualisiert.')

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
            self._enqueue_status('Kein Calibre-Bibliothekspfad konfiguriert und keine aktuelle Bibliothek gefunden.')
            return

        if self.server_running and self.server_process and self.server_process.poll() is None:
            self._enqueue_status('MCP Server laeuft bereits.')
            return

        try:
            python_cmd = self._python_executable()
        except RuntimeError as exc:
            log.error("No usable Python interpreter: %s", exc)
            self._enqueue_status(f'System: {exc}')
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

        popen_kwargs = {
            'env': env,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'encoding': 'utf-8',
        }
        # Unter Windows das Konsolenfenster unterdruecken, damit der Server
        # im Hintergrund laeuft und keine zusaetzliche Shell auftaucht.
        if os.name == 'nt':
            try:
                flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            except AttributeError:
                flags = 0
            popen_kwargs['creationflags'] = flags

        try:
            self.server_process = subprocess.Popen(cmd, **popen_kwargs)
        except OSError as exc:
            log.exception("Failed to start MCP server process")
            self._enqueue_status(f'MCP Server konnte nicht starten: {exc}')
            self.server_process = None
            return

        self.server_running = True
        self.server_button.setText('Server stoppen')
        self._enqueue_status(f'MCP Server gestartet auf ws://{host}:{port}.')
        self.server_monitor.start()

    def _stop_server(self):
        proc = self.server_process
        self.server_process = None
        if not proc:
            self.server_running = False
            self.server_button.setText('Server starten')
            self.server_monitor.stop()
            self._enqueue_status('MCP Server wurde gestoppt.')
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
            self._enqueue_status(f'stderr: {stderr.strip()[:500]}')
        if stdout:
            self._enqueue_status(f'stdout: {stdout.strip()[:500]}')

        self.server_running = False
        self.server_button.setText('Server starten')
        self.server_monitor.stop()
        self._enqueue_status('MCP Server wurde gestoppt.')

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
        self._enqueue_status(msg)

    def closeEvent(self, event):
        # Fenstergroesse und Debug-Checkbox-Zustand in Prefs sichern,
        # bevor der Dialog geschlossen wird.
        try:
            size = self.size()
            prefs['window_width'] = size.width()
            prefs['window_height'] = size.height()
            prefs['debug_trace_enabled'] = self.debug_checkbox.isChecked()
        except Exception:
            log.exception("Failed to persist dialog geometry / debug flag")
        self._stop_server()
        super().closeEvent(event)

    # ------------------------------------------------------------------ Chat

    def new_chat(self):
        """Loesche aktuellen Chatverlauf und setze Agent-Session zurueck."""
        self.chat_panel.clear()
        self._trace_buffer = []
        self._trace_title = None
        self._current_ai_message = None
        # Quellenliste und Panel ebenfalls zuruecksetzen, damit alte Treffer
        # nicht im neuen Chat sichtbar bleiben.
        self._source_hits = []
        # Alle Widgets aus dem Quellen-Layout entfernen und einen Stretch
        # hinzufuegen, damit das Panel leer erscheint.
        while self.sources_layout.count() > 0:
            item = self.sources_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.sources_layout.addStretch(1)

        self.agent = RechercheAgent(prefs, trace_callback=self._trace_from_worker)
        self._enqueue_status('Neuer Chat gestartet.')

    def _trace_from_worker(self, message: str) -> None:
        """Trace-Callback, der aus dem Worker-Thread kommt.

        Wir leiten die Meldung per Qt-Signal in den UI-Thread weiter,
        damit _append_trace niemals direkt aus dem Worker heraus UI
        anfassen muss.
        """
        self.trace_signal.emit(message or "")

    def send_message(self):
        if self.pending_request:
            return

        text = self.input_edit.text().strip()
        if not text:
            return

        # Falls der MCP-Server noch nicht laeuft, automatisch starten.
        # Damit bleibt das Verhalten konsistent mit dem Start-Button,
        # inklusive Statusmeldungen und Button-Text.
        if not self.server_running:
            self._start_server()
            # Wenn der Start fehlgeschlagen ist (server_running weiterhin False),
            # brechen wir hier ab, statt eine Anfrage ins Leere zu schicken.
            if not self.server_running:
                return

        self.chat_panel.add_user_message(text)
        self.input_edit.clear()
        self._toggle_send_state(True)

        # Sofort einen leeren AI-Block mit Debug-Bereich anzeigen, damit
        # die folgenden Trace-Updates sichtbar sind, waehrend der Agent
        # arbeitet.
        self._trace_buffer = []
        self._trace_title = None
        self._current_ai_message = self.chat_panel.add_ai_message("", tool_trace="")

        QTimer.singleShot(0, lambda: self._process_chat(text))

    def _process_chat(self, text: str):
        """Starte den Agenten in einem eigenen Thread."""
        self._enqueue_status('Starte Recherche uebers MCP-Backend ...')

        self._agent_thread = QThread(self)
        # AgentWorker soll jetzt answer_with_sources aufrufen; zur
        # Vereinfachung uebergeben wir weiterhin nur die Frage und
        # interpretieren das Ergebnis in _on_agent_finished.
        self._agent_worker = AgentWorker(self.agent, text)
        self._agent_worker.moveToThread(self._agent_thread)

        self._agent_thread.started.connect(self._agent_worker.run)
        self._agent_worker.finished.connect(self._on_agent_finished)
        self._agent_worker.failed.connect(self._on_agent_failed)
        self._agent_worker.finished.connect(self._agent_thread.quit)
        self._agent_worker.failed.connect(self._agent_thread.quit)
        self._agent_thread.finished.connect(self._agent_worker.deleteLater)
        self._agent_thread.finished.connect(self._agent_thread.deleteLater)

        self._agent_thread.start()

    def _on_agent_finished(self, response_with_sources: str | tuple) -> None:
        """Wird im UI-Thread aufgerufen, wenn der Agent fertig ist.

        Der Agent liefert jetzt ueber answer_with_sources sowohl den
        Antworttext als auch die Trefferliste. Zur Rueckwaertskompatibilitaet
        akzeptieren wir hier aber weiterhin reine Textantworten.
        """
        # Rueckwaertskompatible Entpacklogik
        if isinstance(response_with_sources, tuple):
            response, hits = response_with_sources
        else:
            response, hits = response_with_sources, []

        # Quellenpanel aktualisieren, wenn Hits vorhanden sind
        try:
            if hits:
                source_items = []
                for eh in hits:
                    # EnrichedHit aus recherche_agent
                    if isinstance(eh, EnrichedHit):
                        hit = eh.hit
                        source_items.append({
                            "book_id": hit.book_id,
                            "title": hit.title,
                            "isbn": hit.isbn,
                            "excerpt": eh.excerpt_text or hit.snippet or "",
                        })
                if source_items:
                    self.update_sources(source_items)
        except Exception:
            log.exception("Failed to update sources panel from agent hits")

        if response:
            if self._current_ai_message is not None:
                self._current_ai_message.set_message_text(response)
                if self._trace_buffer:
                    content = "\n".join(self._trace_buffer)
                    # Nach erfolgreichem Abschluss klaren End-Status
                    # neben dem Pfeil anzeigen (Unicode-Haken), damit
                    # keine sprachabhaengigen Texte noetig sind.
                    final_title = "✓"
                    self._current_ai_message.update_trace(final_title, content)
            else:
                tool_trace = "\n".join(self._trace_buffer) if self._trace_buffer else None
                self._current_ai_message = self.chat_panel.add_ai_message(response, tool_trace=tool_trace)
        else:
            self._enqueue_status('Keine Antwort vom Provider erhalten.')
        self._toggle_send_state(False)

    def _on_agent_failed(self, error_text: str) -> None:
        """Agent hat mit Fehler abgebrochen (UI-Thread)."""
        # Fehlermeldung sowohl in der Statusleiste als auch über ein
        # Unicode-Fehler-Symbol im Debug-Titel sichtbar machen.
        self._enqueue_status(f'Fehler in der Recherche-Pipeline: {error_text}')
        if self._current_ai_message is not None:
            content = "\n".join(self._trace_buffer)
            # Kurzer, sprachneutraler Fehler-Indikator
            final_title = "⚠"
            self._current_ai_message.update_trace(final_title, content)
        self._toggle_send_state(False)

    def _append_trace(self, message: str):
        """Trace-Callback fuer den Agenten (immer im UI-Thread).

        Debug-Ausgaben werden pro Frage als ein Block gesammelt. Der
        Beschreibungstext (Titel) spiegelt immer den *aktuellen* Schritt
        wider (letzte Trace-Zeile), waehrend der aufgeklappte Bereich
        den gesamten Verlauf des Toolschritts zeigt.
        """
        text = (message or '').strip()
        if text:
            # Aktuellen Schritt immer als Titel verwenden und Trace-Verlauf
            # erweitern. So bleibt der Text rechts neben dem Pfeil nicht auf
            # der ersten Aktion haengen, sondern zeigt den jeweils letzten
            # Agenten-Step (z.B. aktuell laufenden Toolcall).
            self._trace_title = text
            self._trace_buffer.append(text)

        if self._current_ai_message is not None:
            content = "\n".join(self._trace_buffer)
            title = self._trace_title if self.debug_checkbox.isChecked() else None
            self._current_ai_message.update_trace(title, content)

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

    def _toggle_sources_panel(self, state: int) -> None:
        """Quellen-Panel ein-/ausblenden.

        Wird direkt an die entsprechende Checkbox gebunden.
        """
        visible = bool(state)
        self.sources_panel.setVisible(visible)

    def _export_sources_to_file(self) -> None:
        """Aktuelle Quellenliste als JSON-Datei exportieren.

        Es wird der in update_sources gepflegte _source_hits-Status
        verwendet. Die Datei enthaelt eine Liste von Objekten mit
        mindestens book_id, title, isbn und excerpt.
        """
        if not self._source_hits:
            self._enqueue_status('Keine Quellen zum Exportieren vorhanden.')
            return
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                'Quellen als JSON speichern',
                '',
                'JSON-Dateien (*.json);;Alle Dateien (*.*)'
            )
        except Exception:
            log.exception('Fehler beim Oeffnen des Dateidialogs fuer Quellenexport')
            return
        if not path:
            return
        try:
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._source_hits, f, ensure_ascii=False, indent=2)
            self._enqueue_status(f'Quellen nach {path} exportiert.')
        except Exception:
            log.exception('Fehler beim Schreiben der Quellen-Exportdatei')
            self._enqueue_status('Fehler beim Speichern der Quellen-Exportdatei.')

    def update_sources(self, source_hits: list[dict]):
        """Aktualisiere die angezeigten Quellen im rechten Panel.

        Fuehrt die folgenden Schritte aus:
        - Interne _source_hits-Liste aktualisieren
        - UI-Elemente im Quellen-Panel neu aufbauen
        """
        if not source_hits:
            return

        # Interne Quelle-Liste aktualisieren
        self._source_hits = source_hits

        # Quellen-Panel leeren
        self.sources_layout.clear()

        # Fuer jeden Treffer ein Panel mit Titel, ISBN, Excerpt-Vorschau
        # und aufklappbarem Volltext.
        for hit in self._source_hits:
            container = QWidget(self.sources_panel)
            lay = QVBoxLayout(container)
            lay.setContentsMargins(4, 4, 4, 4)
            lay.setSpacing(2)

            title = hit.get('title') or 'Unbekannter Titel'
            isbn = hit.get('isbn') or ''
            book_id = int(hit.get('book_id')) if hit.get('book_id') is not None else None

            header_row = QHBoxLayout()
            # Markierungs-Button LINKS neben dem Titel, damit er auch bei
            # kleiner Fensterbreite sichtbar bleibt.
            mark_btn = QToolButton(container)
            mark_btn.setText('☆')
            mark_btn.setCheckable(True)
            mark_btn.setToolTip('Buch in Calibre markieren/entmarkieren (marked:true)')
            mark_btn.clicked.connect(
                lambda checked, bid=book_id: self._toggle_mark_book(bid, checked)
            )
            header_row.addWidget(mark_btn)

            header_label = QLabel(f"{title}", container)
            header_label.setStyleSheet('font-weight: bold;')
            header_row.addWidget(header_label)
            if isbn:
                header_row.addWidget(QLabel(f"ISBN: {isbn}", container))
            header_row.addStretch(1)
            lay.addLayout(header_row)

            excerpt_full = (hit.get('excerpt') or '').strip()
            if excerpt_full:
                # Preview (erste Zeilen des aktuellen Excerpts)
                preview_lines = '\n'.join(excerpt_full.splitlines()[:3])
                preview_label = QLabel(preview_lines, container)
                preview_label.setStyleSheet('font-size: 10px; color: #555;')
                preview_label.setWordWrap(True)
                lay.addWidget(preview_label)

                # Aufklappbarer Voll-Excerpt
                toggle_row = QHBoxLayout()
                toggle_row.setContentsMargins(0, 0, 0, 0)
                toggle_row.setSpacing(2)
                toggle_btn = QToolButton(container)
                toggle_btn.setCheckable(True)
                toggle_btn.setArrowType(Qt.RightArrow)
                toggle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                toggle_row.addWidget(toggle_btn)
                desc_label = QLabel('Auszug anzeigen', container)
                desc_label.setStyleSheet('font-size: 9px; color: #555;')
                toggle_row.addWidget(desc_label)
                toggle_row.addStretch(1)
                lay.addLayout(toggle_row)

                full_label = QTextEdit(container)
                full_label.setReadOnly(True)
                full_label.setPlainText(excerpt_full)
                full_label.setVisible(False)
                full_label.setStyleSheet('font-size: 10px; color: #555;')
                full_label.setMaximumHeight(160)
                lay.addWidget(full_label)

                def _toggle_full(checked: bool, widget=full_label, btn=toggle_btn):
                    widget.setVisible(checked)
                    btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

                toggle_btn.toggled.connect(_toggle_full)

            self.sources_layout.addWidget(container)

        self.sources_layout.addStretch(1)

    def _toggle_mark_book(self, book_id: int | None, checked: bool) -> None:
        """Buch im Calibre-Hauptfenster markieren oder entmarkieren.

        Verwendet die offizielle marked:true-Mechanik von Calibre:
        - Alle aktuell markierten IDs werden ueber db.set_marked_ids verwaltet.
        - Die GUI-Suche kann optional auf 'marked:true' gesetzt werden, damit
          der Nutzer alle markierten Buecher sieht.
        """
        if book_id is None:
            return
        try:
            db = self.db
            current = set(getattr(db, 'marked_ids', []) or [])
            if checked:
                current.add(int(book_id))
            else:
                current.discard(int(book_id))
            db.set_marked_ids(current)

            # Optional: Suche auf marked:true setzen, damit der Nutzer die
            # markierten Buecher sofort sieht. Wir erzwingen das hier nicht
            # global, koennen es aber spaeter ueber eine Einstellung steuern.
            try:
                if current:
                    self.gui.search.setEditText('marked:true')
                    self.gui.search.do_search()
                else:
                    # Wenn keine Markierungen mehr vorhanden sind, Loeschung
                    # der Suchanfrage dem Nutzer ueberlassen.
                    pass
            except Exception:
                log.exception('Konnte Suche marked:true nicht aktualisieren')
        except Exception:
            log.exception('Failed to toggle marked state for book_id=%r', book_id)

