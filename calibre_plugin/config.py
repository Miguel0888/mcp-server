#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _
from qt.core import (
    QWidget,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QGroupBox,
    QComboBox,
    QCheckBox,
)
import os

from .providers import (
    ensure_model_prefs,
    get_selected_model,
    list_enabled_providers,
    set_selected_model,
    describe_provider,
)


# This is where all preferences for this plugin will be stored.
# Name is global, so keep it reasonably unique.
prefs = JSONConfig('plugins/mcp_server_recherche')

# New settings for MCP server / AI
prefs.defaults['server_host'] = '127.0.0.1'
prefs.defaults['server_port'] = '8765'
prefs.defaults['library_path'] = ''   # Use current calibre library when empty
prefs.defaults['api_key'] = ''        # Optional AI key (e.g. OpenAI)
prefs.defaults['models'] = {}
prefs.defaults['selected_model'] = {}
prefs.defaults['use_active_library'] = True
ensure_model_prefs(prefs)


class MCPServerRechercheConfigWidget(QWidget):
    """Preference widget for MCP Server Recherche plugin."""

    def __init__(self):
        QWidget.__init__(self)

        layout = QVBoxLayout(self)

        # Connection settings ------------------------------------------------
        server_group = QGroupBox(_('MCP Server Einstellungen'), self)
        server_form = QFormLayout(server_group)
        server_group.setLayout(server_form)
        layout.addWidget(server_group)

        # Server host
        self.host_edit = QLineEdit(self)
        self.host_edit.setText(prefs['server_host'])
        server_form.addRow(_('Server-Host:'), self.host_edit)

        # Server port
        self.port_edit = QLineEdit(self)
        self.port_edit.setText(prefs['server_port'])
        server_form.addRow(_('Server-Port:'), self.port_edit)

        # Library path + browse button
        lib_row = QHBoxLayout()
        self.library_edit = QLineEdit(self)
        self.library_edit.setText(prefs['library_path'])
        self.library_edit.setPlaceholderText(_('z. B. X:/E-Books'))

        self.use_active_checkbox = QCheckBox(_('Aktive Calibre-Bibliothek verwenden'), self)
        self.use_active_checkbox.setChecked(prefs['use_active_library'])
        self.use_active_checkbox.stateChanged.connect(self._library_mode_changed)
        server_form.addRow('', self.use_active_checkbox)

        browse_btn = QPushButton(_('Auswahl'), self)
        browse_btn.clicked.connect(self.choose_library)
        self.browse_btn = browse_btn

        lib_row.addWidget(self.library_edit)
        lib_row.addWidget(browse_btn)

        server_form.addRow(_('Calibre-Bibliothek:'), lib_row)

        # Info label
        info = QLabel(
            _(
                'Host/Port konfigurieren spaeter den MCP WebSocket-Server.\n'
                'Der Bibliothekspfad ueberschreibt optional die aktuelle Calibre-Bibliothek.'
            ),
            self,
        )
        server_form.addRow(info)

        # AI provider settings ----------------------------------------------
        provider_group = QGroupBox(_('AI Provider'), self)
        provider_layout = QVBoxLayout(provider_group)
        layout.addWidget(provider_group)

        self.provider_combo = QComboBox(self)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        provider_layout.addWidget(self.provider_combo)

        form = QFormLayout()
        provider_layout.addLayout(form)

        self.provider_enabled = QCheckBox(_('Provider aktiviert'), self)
        form.addRow('', self.provider_enabled)

        self.display_name_edit = QLineEdit(self)
        form.addRow(_('Anzeige-Name:'), self.display_name_edit)

        self.base_url_edit = QLineEdit(self)
        form.addRow(_('Base URL:'), self.base_url_edit)

        self.endpoint_edit = QLineEdit(self)
        form.addRow(_('Chat Endpoint:'), self.endpoint_edit)

        self.model_edit = QLineEdit(self)
        form.addRow(_('Standardmodell:'), self.model_edit)

        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow(_('API Key:'), self.api_key_edit)

        self.temperature_edit = QLineEdit(self)
        form.addRow(_('Temperatur:'), self.temperature_edit)

        selection_row = QHBoxLayout()
        self.selected_provider_label = QLabel(_('Kein Provider'), self)
        self.selected_model_label = QLabel('', self)
        selection_row.addWidget(QLabel(_('Aktiv:'), self))
        selection_row.addWidget(self.selected_provider_label)
        selection_row.addSpacing(8)
        selection_row.addWidget(self.selected_model_label)
        choose_btn = QPushButton(_('Standard setzen'), self)
        choose_btn.clicked.connect(self.choose_model)
        selection_row.addWidget(choose_btn)
        provider_layout.addLayout(selection_row)

        self._load_providers()
        self._update_selection_labels()
        self._update_library_inputs()

    def choose_library(self):
        """Select calibre library root directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswaehlen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def _library_mode_changed(self, state):
        prefs['use_active_library'] = bool(state)
        self._update_library_inputs()

    def _update_library_inputs(self):
        use_active = self.use_active_checkbox.isChecked()
        self.library_edit.setEnabled(not use_active)
        self.browse_btn.setEnabled(not use_active)

    def save_settings(self):
        """Persist user changes to JSONConfig."""
        prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        prefs['server_port'] = self.port_edit.text().strip() or '8765'
        library_path = self.library_edit.text().strip()
        if library_path:
            library_path = os.path.normpath(library_path)
        prefs['library_path'] = library_path
        prefs['use_active_library'] = self.use_active_checkbox.isChecked()
        self._persist_provider_settings()
        self._update_selection_labels()

    # ------------------------------------------------------------------ AI helpers
    def _load_providers(self):
        self._models = ensure_model_prefs(prefs)
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for key, cfg in self._models.items():
            self.provider_combo.addItem(describe_provider(cfg), key)
        self.provider_combo.blockSignals(False)
        self._provider_changed(self.provider_combo.currentIndex())

    def _provider_changed(self, index: int):
        provider_key = self.provider_combo.itemData(index)
        cfg = self._models.get(provider_key, {})
        self.provider_enabled.setChecked(bool(cfg.get('enabled')))
        self.display_name_edit.setText(cfg.get('display_name', ''))
        self.base_url_edit.setText(cfg.get('base_url', ''))
        self.endpoint_edit.setText(cfg.get('chat_endpoint', ''))
        self.model_edit.setText(cfg.get('model', ''))
        self.api_key_edit.setText(cfg.get('api_key', ''))
        self.temperature_edit.setText(str(cfg.get('temperature', '')))

    def _persist_provider_settings(self):
        index = self.provider_combo.currentIndex()
        provider_key = self.provider_combo.itemData(index)
        if not provider_key:
            return
        cfg = self._models.setdefault(provider_key, {})
        cfg['enabled'] = self.provider_enabled.isChecked()
        cfg['display_name'] = self.display_name_edit.text().strip()
        cfg['base_url'] = self.base_url_edit.text().strip()
        cfg['chat_endpoint'] = self.endpoint_edit.text().strip()
        cfg['model'] = self.model_edit.text().strip()
        cfg['api_key'] = self.api_key_edit.text().strip()
        try:
            cfg['temperature'] = float(self.temperature_edit.text().strip())
        except ValueError:
            cfg['temperature'] = 0.4
        prefs['models'] = self._models

    def choose_model(self):
        models = ensure_model_prefs(prefs)
        enabled = list_enabled_providers(models)
        if not enabled:
            self.selected_provider_label.setText(_('Kein aktiver Provider'))
            self.selected_model_label.setText('')
            return
        key = self.provider_combo.itemData(self.provider_combo.currentIndex())
        if key not in enabled:
            key = next(iter(enabled.keys()))
        model_name = enabled[key].get('model', '')
        set_selected_model(prefs, key, model_name)
        self._update_selection_labels()

    def _update_selection_labels(self):
        selected = get_selected_model(prefs)
        models = ensure_model_prefs(prefs)
        cfg = models.get(selected.get('provider'))
        if not cfg:
            self.selected_provider_label.setText(_('Kein Provider'))
            self.selected_model_label.setText('')
            return
        self.selected_provider_label.setText(describe_provider(cfg))
        self.selected_model_label.setText(selected.get('model') or '')
        self._update_library_inputs()
