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
    QComboBox,
    QGroupBox,
    QVBoxLayout,
    QCheckBox,
)

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
ensure_model_prefs(prefs)


class MCPServerRechercheConfigWidget(QWidget):
    """Preference widget for MCP Server Recherche plugin."""

    def __init__(self):
        QWidget.__init__(self)

        layout = QVBoxLayout(self)
        # Network group ----------------------------------------------------
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

        browse_btn = QPushButton(_('Auswahl'), self)
        browse_btn.clicked.connect(self.choose_library)

        lib_row.addWidget(self.library_edit)
        lib_row.addWidget(browse_btn)

        server_form.addRow(_('Calibre-Bibliothek:'), lib_row)

        # ------------------------------------------------------------------
        provider_group = QGroupBox(_('AI Provider'), self)
        provider_layout = QVBoxLayout(provider_group)

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

        layout.addWidget(provider_group)

        # Selection row ----------------------------------------------------
        selection_row = QHBoxLayout()
        self.selected_provider_label = QLabel('', self)
        self.selected_model_label = QLabel('', self)
        selection_row.addWidget(QLabel(_('Aktiv:'), self))
        selection_row.addWidget(self.selected_provider_label)
        selection_row.addSpacing(8)
        selection_row.addWidget(self.selected_model_label)
        choose_btn = QPushButton(_('Modell wählen'), self)
        choose_btn.clicked.connect(self.choose_model)
        selection_row.addWidget(choose_btn)
        layout.addLayout(selection_row)

        # Info label
        info = QLabel(
            _(
                'Host/Port konfigurieren spaeter den MCP WebSocket-Server.\n'
                'AI-Provider Einstellungen gelten fuer den Chat und senden keine Buch-Metadaten.'
            ),
            self,
        )
        layout.addWidget(info)

        self._load_providers()
        self._update_selection_labels()

    def choose_library(self):
        """Select calibre library root directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswaehlen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def save_settings(self):
        """Persist user changes to JSONConfig."""
        prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        prefs['server_port'] = self.port_edit.text().strip() or '8765'
        prefs['library_path'] = self.library_edit.text().strip()

        self._persist_provider_settings()
        self._update_selection_labels()

    # ------------------------------------------------------------------ AI
    def _load_providers(self):
        self._models = ensure_model_prefs(prefs)
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for key, cfg in self._models.items():
            self.provider_combo.addItem(describe_provider(cfg), key)
        self.provider_combo.blockSignals(False)
        self._provider_changed(self.provider_combo.currentIndex())

    def _provider_changed(self, index: int):
        key = self.provider_combo.itemData(index)
        cfg = self._models.get(key, {})
        self.provider_enabled.setChecked(bool(cfg.get('enabled')))
        self.display_name_edit.setText(cfg.get('display_name', ''))
        self.base_url_edit.setText(cfg.get('base_url', ''))
        self.endpoint_edit.setText(cfg.get('chat_endpoint', ''))
        self.model_edit.setText(cfg.get('model', ''))
        self.api_key_edit.setText(cfg.get('api_key', ''))
        self.temperature_edit.setText(str(cfg.get('temperature', '')))

    def _persist_provider_settings(self):
        index = self.provider_combo.currentIndex()
        key = self.provider_combo.itemData(index)
        if not key:
            return
        cfg = self._models.setdefault(key, {})
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
        selected = get_selected_model(prefs)
        current_provider = selected.get('provider')
        models = ensure_model_prefs(prefs)
        enabled = list_enabled_providers(models)
        if not enabled:
            self.selected_provider_label.setText(_('Kein aktiver Provider'))
            self.selected_model_label.setText('')
            return
        # If currently selected provider disabled, pick first enabled
        if not current_provider or current_provider not in enabled:
            first_key = next(iter(enabled.keys()))
            set_selected_model(prefs, first_key, enabled[first_key].get('model', ''))
        else:
            current_cfg = enabled[current_provider]
            set_selected_model(prefs, current_provider, current_cfg.get('model', ''))
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
