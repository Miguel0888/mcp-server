#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

import socket

from calibre.utils.localization import _
from qt.core import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
)


class MCPClientDialog(QDialog):
    """Simple dialog to control MCP server and test connectivity."""

    def __init__(self, gui, controller, prefs, parent=None):
        super(MCPClientDialog, self).__init__(parent or gui)
        # Store references for later usage
        self.gui = gui
        self.controller = controller
        self.prefs = prefs

        self.setWindowTitle(_('MCP Recherche'))
        self.resize(700, 500)

        main_layout = QVBoxLayout(self)

        # Status row
        status_row = QHBoxLayout()
        self.status_label = QLabel(self)
        self._update_status_label()
        status_row.addWidget(QLabel(_('Serverstatus:'), self))
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)

        self.toggle_server_btn = QPushButton(self)
        self._update_toggle_button_text()
        self.toggle_server_btn.clicked.connect(self.on_toggle_server)
        status_row.addWidget(self.toggle_server_btn)

        main_layout.addLayout(status_row)

        # Connection test
        conn_row = QHBoxLayout()
        self.host_edit = QLineEdit(self)
        self.host_edit.setText(self.prefs.get('server_host') or '127.0.0.1')

        self.port_edit = QLineEdit(self)
        self.port_edit.setText(self.prefs.get('server_port') or '8765')

        test_btn = QPushButton(_('Verbindung testen'), self)
        test_btn.clicked.connect(self.on_test_connection)

        conn_row.addWidget(QLabel(_('Host:'), self))
        conn_row.addWidget(self.host_edit, 2)
        conn_row.addWidget(QLabel(_('Port:'), self))
        conn_row.addWidget(self.port_edit, 1)
        conn_row.addWidget(test_btn)

        main_layout.addLayout(conn_row)

        # Query input
        self.query_edit = QLineEdit(self)
        self.query_edit.setPlaceholderText(
            _('Recherche-Frage eingeben (Stub – hier eigenes Protokoll einbauen)…')
        )

        start_btn = QPushButton(_('Recherche starten'), self)
        start_btn.clicked.connect(self.on_start_research)

        query_row = QHBoxLayout()
        query_row.addWidget(self.query_edit, 3)
        query_row.addWidget(start_btn, 1)

        main_layout.addLayout(query_row)

        # Output area
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        main_layout.addWidget(self.output, 1)

    def _update_status_label(self):
        """Update status label based on server running state."""
        if self.controller.is_running:
            self.status_label.setText(_('läuft'))
        else:
            self.status_label.setText(_('gestoppt'))

    def _update_toggle_button_text(self):
        """Update text of start/stop button."""
        if self.controller.is_running:
            self.toggle_server_btn.setText(_('Server stoppen'))
        else:
            self.toggle_server_btn.setText(_('Server starten'))

    def append_output(self, text):
        """Append a line of text to the output area."""
        self.output.append(text)

    def on_toggle_server(self):
        """Handle start/stop of MCP server process."""
        started = self.controller.toggle()
        self._update_status_label()
        self._update_toggle_button_text()
        if started:
            self.append_output(_('Server wurde gestartet.'))
        else:
            self.append_output(_('Server wurde gestoppt.'))

    def on_test_connection(self):
        """Test raw TCP connectivity to configured host and port."""
        host = self.host_edit.text().strip() or '127.0.0.1'
        port_text = self.port_edit.text().strip() or '8765'

        try:
            port = int(port_text)
        except ValueError:
            self.append_output(_('Ungültiger Port: {0}').format(port_text))
            return

        self.append_output(
            _('Teste Verbindung zu {0}:{1} …').format(host, port)
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)

        try:
            sock.connect((host, port))
        except OSError as exc:
            self.append_output(
                _('Verbindung fehlgeschlagen: {0}').format(repr(exc))
            )
        else:
            self.append_output(_('Verbindung erfolgreich – Port ist offen.'))
        finally:
            try:
                sock.close()
            except OSError:
                # Ignore close errors
                pass

    def on_start_research(self):
        """Stub for starting research over WebSocket."""
        query = self.query_edit.text().strip()
        if not query:
            self.append_output(_('Keine Frage eingegeben.'))
            return

        # At this point the dialog knows:
        # - self.host_edit / self.port_edit
        # - self.prefs (API key, library path)
        #
        # Implement real WebSocket protocol here, for example:
        #   1. Open WebSocket ws://host:port
        #   2. Send JSON message with query text and metadata
        #   3. Receive streamed response and append lines to self.output
        #
        # Use a worker thread to avoid blocking the GUI.
        self.append_output(
            _(
                'Stub: Würde jetzt Recherche mit Frage starten: "{0}".\n'
                'Füge hier deine echte WebSocket-Client-Logik ein.'
            ).format(query)
        )
