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
prefs.defaults['python_executable'] = ''
prefs.defaults['auto_detect_python'] = True

# Defaults fuer Recherche-Agent
prefs.defaults['max_query_variants'] = 3
prefs.defaults['max_hits_per_query'] = 6
prefs.defaults['max_hits_total'] = 12
prefs.defaults['target_sources'] = 3
prefs.defaults['max_excerpts'] = 4
prefs.defaults['max_excerpt_chars'] = 1200
prefs.defaults['context_hit_limit'] = 8
prefs.defaults['request_timeout'] = 15
prefs.defaults['min_hits_required'] = 3
prefs.defaults['max_refinement_rounds'] = 2
prefs.defaults['context_influence'] = 50
prefs.defaults['max_search_rounds'] = 2
# Benutzeranpassbare Prompt-Zusaetze
prefs.defaults['query_planner_hint'] = ''
prefs.defaults['answer_style_hint'] = ''
# Hint fuer Schlagwort-Extraktion
prefs.defaults['keyword_extraction_hint'] = ''
# Optionaler zusaetzlicher LLM-Schlagwort-Lauf in anderer Sprache
prefs.defaults['second_keyword_language_enabled'] = False
prefs.defaults['second_keyword_language'] = 'Englisch'
# UI-Layout-Defaults fuer den Chat-Dialog
prefs.defaults['window_width'] = 800
prefs.defaults['window_height'] = 600
prefs.defaults['debug_trace_enabled'] = True

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

        python_row = QHBoxLayout()
        self.python_edit = QLineEdit(self)
        self.python_edit.setText(prefs['python_executable'])
        self.python_edit.setPlaceholderText(_('z. B. C:/Python/python.exe'))
        python_browse = QPushButton(_('Auswahl'), self)
        python_browse.clicked.connect(self.choose_python)
        python_row.addWidget(self.python_edit)
        python_row.addWidget(python_browse)
        server_form.addRow(_('Python-Interpreter (optional):'), python_row)
        self.python_browse = python_browse

        # Auto-detect Checkbox
        self.auto_python_checkbox = QCheckBox(_('Python automatisch ermitteln'), self)
        self.auto_python_checkbox.setChecked(prefs.get('auto_detect_python', True))
        self.auto_python_checkbox.stateChanged.connect(self._python_mode_changed)
        server_form.addRow('', self.auto_python_checkbox)

        # Recherche-Parameter ----------------------------------------------
        tuning_group = QGroupBox(_('Recherche-Feintuning'), self)
        tuning_form = QFormLayout(tuning_group)
        tuning_group.setLayout(tuning_form)
        layout.addWidget(tuning_group)

        def _make_int_edit(pref_key: str, default: int) -> QLineEdit:
            edit = QLineEdit(self)
            edit.setText(str(prefs.get(pref_key, default)))
            return edit

        self.max_query_variants_edit = _make_int_edit('max_query_variants', 3)
        tuning_form.addRow(_('Max. Suchvarianten:'), self.max_query_variants_edit)

        self.max_hits_per_query_edit = _make_int_edit('max_hits_per_query', 6)
        tuning_form.addRow(_('Treffer pro Query (Limit):'), self.max_hits_per_query_edit)

        self.max_hits_total_edit = _make_int_edit('max_hits_total', 12)
        tuning_form.addRow(_('Max. Treffer gesamt:'), self.max_hits_total_edit)

        self.target_sources_edit = _make_int_edit('target_sources', 3)
        tuning_form.addRow(_('Anzahl Zielquellen (frueh abbrechen bei genug Treffern):'), self.target_sources_edit)

        self.max_excerpts_edit = _make_int_edit('max_excerpts', 4)
        tuning_form.addRow(_('Max. Excerpts:'), self.max_excerpts_edit)

        self.max_excerpt_chars_edit = _make_int_edit('max_excerpt_chars', 1200)
        tuning_form.addRow(_('Excerpt-Laenge (Zeichen):'), self.max_excerpt_chars_edit)

        self.context_hit_limit_edit = _make_int_edit('context_hit_limit', 8)
        tuning_form.addRow(_('Max. Treffer im Kontextblock:'), self.context_hit_limit_edit)

        self.request_timeout_edit = _make_int_edit('request_timeout', 15)
        tuning_form.addRow(_('Timeout fuer MCP-Anfragen (Sekunden, aktuell nur informativ):'), self.request_timeout_edit)

        self.min_hits_required_edit = _make_int_edit('min_hits_required', 3)
        tuning_form.addRow(_('Mindestanzahl Treffer vor Abbruch/Refinement:'), self.min_hits_required_edit)

        self.max_refinement_rounds_edit = _make_int_edit('max_refinement_rounds', 2)
        tuning_form.addRow(_('Max. Refinement-Runden (LLM-Umformulierung):'), self.max_refinement_rounds_edit)

        self.max_search_rounds_edit = _make_int_edit('max_search_rounds', 2)
        tuning_form.addRow(_('Max. Suchrunden (Volltext + Refinements):'), self.max_search_rounds_edit)

        self.context_influence_edit = _make_int_edit('context_influence', 50)
        tuning_form.addRow(_('Kontext-Einfluss (0-100, hoeher = staerkerer Bezug auf vorige Fragen):'),
                           self.context_influence_edit)

        # Benutzeranpassbare Prompt-Zusaetze
        self.query_planner_hint_edit = QLineEdit(self)
        self.query_planner_hint_edit.setText(prefs.get('query_planner_hint', ''))
        self.query_planner_hint_edit.setPlaceholderText(
            _('Optionaler Zusatz fuer die Query-Planung, z. B. "nutze immer Fachbegriffe aus der Elektrotechnik"')
        )
        tuning_form.addRow(_('Hinweis fuer Query-Planer-Prompt:'), self.query_planner_hint_edit)

        self.answer_style_hint_edit = QLineEdit(self)
        self.answer_style_hint_edit.setText(prefs.get('answer_style_hint', ''))
        self.answer_style_hint_edit.setPlaceholderText(
            _('Optionaler Zusatz fuer die Antwort, z. B. "erklaere verstaendlich fuer Studierende"')
        )
        tuning_form.addRow(_('Hinweis fuer Antwort-Prompt:'), self.answer_style_hint_edit)

        self.keyword_extraction_hint_edit = QLineEdit(self)
        self.keyword_extraction_hint_edit.setText(prefs.get('keyword_extraction_hint', ''))
        self.keyword_extraction_hint_edit.setPlaceholderText(
            _('Optionaler Zusatz fuer die Schlagwort-Extraktion, z. B. "nur deutsche Fachbegriffe verwenden"')
        )
        tuning_form.addRow(_('Hinweis fuer Schlagwort-Prompt:'), self.keyword_extraction_hint_edit)

        # Zusatz: zweite Schlagwortsprache
        self.second_lang_enabled_checkbox = QCheckBox(
            _('Zweiten Schlagwort-Lauf in anderer Sprache verwenden'), self
        )
        self.second_lang_enabled_checkbox.setChecked(
            prefs.get('second_keyword_language_enabled', False)
        )
        tuning_form.addRow('', self.second_lang_enabled_checkbox)

        self.second_lang_edit = QLineEdit(self)
        self.second_lang_edit.setText(prefs.get('second_keyword_language', 'Englisch'))
        self.second_lang_edit.setPlaceholderText(
            _('Sprache fuer zweiten Lauf, z. B. Englisch, French, Spanish')
        )
        tuning_form.addRow(_('Zweite Schlagwort-Sprache:'), self.second_lang_edit)

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
        self._update_python_inputs()

        # Suchmodus ---------------------------------------------------------
        search_group = QGroupBox(_('Suchmodus'), self)
        search_form = QFormLayout(search_group)
        search_group.setLayout(search_form)
        layout.addWidget(search_group)

        self.use_llm_planning_checkbox = QCheckBox(_('LLM fuer Query-Planung verwenden'), self)
        self.use_llm_planning_checkbox.setChecked(prefs.get('use_llm_query_planning', True))
        search_form.addRow('', self.use_llm_planning_checkbox)

        self.max_keywords_edit = QLineEdit(self)
        self.max_keywords_edit.setText(str(prefs.get('max_search_keywords', 5)))
        search_form.addRow(_('Max. Schlagwoerter pro Suche:'), self.max_keywords_edit)

        self.bool_operator_edit = QLineEdit(self)
        self.bool_operator_edit.setText(prefs.get('keyword_boolean_operator', 'AND'))
        self.bool_operator_edit.setPlaceholderText(_('AND oder OR'))
        search_form.addRow(_('Verknuepfung (AND/OR):'), self.bool_operator_edit)

    def choose_library(self):
        """Select calibre library root directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            _('Calibre-Bibliothek auswaehlen'),
            self.library_edit.text() or '',
        )
        if path:
            self.library_edit.setText(path)

    def choose_python(self):
        file_path, selected_filter = QFileDialog.getOpenFileName(
            self,
            _('Python-Interpreter waehlen'),
            self.python_edit.text() or '',
            _('Python (*.exe *.bat *.cmd);;Alle Dateien (*.*)')
        )
        if file_path:
            self.python_edit.setText(file_path)

    def _library_mode_changed(self, state):
        prefs['use_active_library'] = bool(state)
        self._update_library_inputs()

    def _update_library_inputs(self):
        use_active = self.use_active_checkbox.isChecked()
        self.library_edit.setEnabled(not use_active)
        self.browse_btn.setEnabled(not use_active)

    def _python_mode_changed(self, state):
        # Persist auto-detect flag and update inputs
        prefs['auto_detect_python'] = bool(state)
        self._update_python_inputs()

    def _update_python_inputs(self):
        auto = getattr(self, 'auto_python_checkbox', None)
        auto_enabled = auto.isChecked() if auto is not None else True
        self.python_edit.setEnabled(not auto_enabled)
        self.python_browse.setEnabled(not auto_enabled)

    def save_settings(self):
        """Persist user changes to JSONConfig."""
        prefs['server_host'] = self.host_edit.text().strip() or '127.0.0.1'
        prefs['server_port'] = self.port_edit.text().strip() or '8765'

        library_path = self.library_edit.text().strip()
        if library_path:
            library_path = os.path.normpath(library_path)
        prefs['library_path'] = library_path
        prefs['use_active_library'] = self.use_active_checkbox.isChecked()

        prefs['auto_detect_python'] = self.auto_python_checkbox.isChecked()
        prefs['python_executable'] = self.python_edit.text().strip()

        # Recherche-Parameter aus UI lesen (mit einfachen Fallbacks)
        def _read_int(edit: QLineEdit, default: int) -> int:
            try:
                value = int(edit.text().strip())
                if value <= 0:
                    raise ValueError
                return value
            except Exception:
                return default

        prefs['max_query_variants'] = _read_int(self.max_query_variants_edit, 3)
        prefs['max_hits_per_query'] = _read_int(self.max_hits_per_query_edit, 6)
        prefs['max_hits_total'] = _read_int(self.max_hits_total_edit, 12)
        prefs['target_sources'] = _read_int(self.target_sources_edit, 3)
        prefs['max_excerpts'] = _read_int(self.max_excerpts_edit, 4)
        prefs['max_excerpt_chars'] = _read_int(self.max_excerpt_chars_edit, 1200)
        prefs['context_hit_limit'] = _read_int(self.context_hit_limit_edit, 8)
        prefs['request_timeout'] = _read_int(self.request_timeout_edit, 15)
        prefs['min_hits_required'] = _read_int(self.min_hits_required_edit, 3)
        prefs['max_refinement_rounds'] = _read_int(self.max_refinement_rounds_edit, 2)
        prefs['max_search_rounds'] = _read_int(self.max_search_rounds_edit, 2)
        ci = _read_int(self.context_influence_edit, 50)
        prefs['context_influence'] = max(0, min(ci, 100))
        prefs['query_planner_hint'] = self.query_planner_hint_edit.text().strip()
        prefs['answer_style_hint'] = self.answer_style_hint_edit.text().strip()
        prefs['keyword_extraction_hint'] = self.keyword_extraction_hint_edit.text().strip()
        prefs['second_keyword_language_enabled'] = self.second_lang_enabled_checkbox.isChecked()
        prefs['second_keyword_language'] = self.second_lang_edit.text().strip() or 'Englisch'

        # Suchmodus
        prefs['use_llm_query_planning'] = self.use_llm_planning_checkbox.isChecked()
        prefs['max_search_keywords'] = _read_int(self.max_keywords_edit, 5)
        op = (self.bool_operator_edit.text().strip() or 'AND').upper()
        if op not in ('AND', 'OR'):
            op = 'AND'
        prefs['keyword_boolean_operator'] = op

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
