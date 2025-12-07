#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias <https://github.com/Miguel0888/>'
__docformat__ = 'restructuredtext en'

from qt.core import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _

prefs = JSONConfig('plugins/mcp_server')
prefs.defaults['command'] = 'python -m calibre_mcp_server.main'
prefs.defaults['working_dir'] = ''


class MCPServerConfigWidget(QWidget):

    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self.command_edit = QLineEdit(self.prefs['command'], self)
        self.workdir_edit = QLineEdit(self.prefs['working_dir'], self)
        browse_button = QPushButton(_('Auswahl'), self)
        browse_button.clicked.connect(self.choose_workdir)

        layout = QFormLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addRow(_('Startkommando'), self.command_edit)

        workdir_row = QWidget(self)
        row_layout = QHBoxLayout(workdir_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.workdir_edit)
        row_layout.addWidget(browse_button)
        layout.addRow(_('Arbeitsverzeichnis'), workdir_row)

    def choose_workdir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            _('Arbeitsverzeichnis auswählen'),
            self.workdir_edit.text() or '',
        )
        if path:
            self.workdir_edit.setText(path)

    def save_settings(self):
        self.prefs['command'] = self.command_edit.text().strip() or ''
        self.prefs['working_dir'] = self.workdir_edit.text().strip()
