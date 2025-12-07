#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias <https://github.com/Miguel0888/>'
__docformat__ = 'restructuredtext en'

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
    """Basic AI / search UI dialog without backend."""

    def __init__(self, gui, controller, prefs, parent=None):
        QDialog.__init__(self, parent or gui)
        self.gui = gui
        self.controller = controller
        self.prefs = prefs

        self.setWindowTitle(_('MCP Recherche'))
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)

        # Connection info
        conn_row = QHBoxLayout()
        host = self.prefs.get('server_host') or '127.0.0.1'
        port = self.prefs.get('server_port') or '8765'
        self.conn_label = QLabel(
            _('Verbindung (spaeter): ws://{0}:{1}').format(host, port),
            self,
        )
        conn_row.addWidget(self.conn_label)
        main_layout.addLayout(conn_row)

        # Query row
        query_row = QHBoxLayout()
        self.query_edit = QLineEdit(self)
        self.query_edit.setPlaceholderText(
            _('Frage oder Suchtext eingeben ...')
        )
        send_btn = QPushButton(_('Senden (Stub)'), self)
        send_btn.clicked.connect(self.on_send_clicked)

        query_row.addWidget(self.query_edit, 3)
        query_row.addWidget(send_btn, 1)

        main_layout.addLayout(query_row)

        # Output area
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        main_layout.addWidget(self.output, 1)

        # Status label
        self.status_label = QLabel(
            _('Backend ist noch nicht angeschlossen - nur UI-Test.'),
            self,
        )
        main_layout.addWidget(self.status_label)

    def append_output(self, text):
        """Append a line of text to the output."""
        self.output.append(text)

    def on_send_clicked(self):
        """Handle send button click (UI stub)."""
        text = self.query_edit.text().strip()
        if not text:
            self.append_output(_('Keine Eingabe - nichts zu senden.'))
            return

        # Log fake conversation
        self.append_output(_('Du: {0}').format(text))
        self.append_output(
            _(
                'AI (Stub): Hier wuerde spaeter die Antwort des MCP Servers '
                'und AI-Dienstes erscheinen.'
            )
        )
        self.query_edit.clear()
