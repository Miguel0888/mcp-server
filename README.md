# Calibre MCP Server & Recherche-Plugin

Ein experimenteller [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol) Server, der auf eine lokale [Calibre](https://calibre-ebook.com/) Bibliothek zugreift. Ziel ist es, KI-Agenten (z. B. ChatGPT, Copilot, Claude Desktop) ein Research-API auf deine E‑Book‑Sammlung zu geben – inklusive Volltextsuche und strukturierten Excerpts.

Zusätzlich gibt es ein Calibre‑GUI‑Plugin, das

- den MCP‑Server als **WebSocket**-Dienst startet (`ws://127.0.0.1:8765`) und
- einen **Recherche‑Agenten** bereitstellt, der
  - Volltext‑Tools des MCP‑Servers verwendet,
  - Schlagworte per LLM ableitet und
  - Antworten inkl. Quellen (Titel + ISBN) im Calibre‑Dialog anzeigt.

---

## Features (aktueller Stand)

### MCP‑Server

- Implementiert mit [`fastmcp`](https://github.com/modelcontextprotocol/fastmcp)
- Bietet aktuell zwei Tools an:
  - `calibre_fulltext_search`
    - Eingabe: `query: str`, `limit: int`
    - Liefert Treffer (`book_id`, `title`, `isbn`, `snippet`)
    - Sucht in `metadata.db` über `books` + `comments` (Titel, ISBN, Kommentare)
  - `calibre_get_excerpt`
    - Eingabe: `isbn: str`, `max_chars: int`
    - Liefert einen kurzen Textausschnitt plus Metadaten (`book_id`, `title`)
- Domänenschicht `LibraryResearchService` als zentrale API
- Zugriff auf Calibre‑`metadata.db` via SQLite (read‑only)
  - ISBN‑Lookup über `identifiers` + Fallback auf `books.isbn`

### Calibre‑Plugin `mcp_server_recherche`

- Startet / stoppt den MCP‑Server über WebSocket (`ws://host:port`)
- Stellt einen **Recherche‑Dialog** bereit, der
  - Fragen an einen konfigurierten LLM‑Provider sendet,
  - automatisch MCP‑Tools für Volltextsuche und Excerpts nutzt,
  - Suchtreffer und Auszüge anzeigt und
  - eine strukturierte Antwort mit Quellen (inkl. ISBN) generiert.
- Unterstützt **Follow‑up‑Fragen**:
  - Kurze Nachfragen werden mit der vorherigen Frage kombiniert
    (z. B. „Sag mir mehr zu LIN (im Kontext von: Welche Fahrzeug‑Bussysteme gibt es?)“).
  - Der Agent sucht erneut in der Bibliothek, nutzt aber den bisherigen Kontext.
- Debug‑Ausgabe im Dialog (optional), z. B.:
  - `Suchrunde 1 (Kernbegriffe): ['hacking', 'Sicherheit', ...]`
  - `Toolcall calibre_fulltext_search: query='hacking', limit=6`
  - `MCP -> list_tools`, `MCP <- call_tool` usw.

---

## Repository‑Struktur (Kurzüberblick)

Wichtige Verzeichnisse/Dateien:

- `pyproject.toml` – Projekt‑ und Dependency‑Definitionen
- `src/calibre_mcp_server/` – MCP‑Server und Domänencode
  - `core/models.py` – einfache Domain‑Modelle (`FulltextHit`, `Excerpt`, ...)
  - `core/service.py` – `LibraryResearchService`, zentrale Research‑API
  - `infra/metadata_sqlite.py` – Zugriff auf `metadata.db` über SQLite
  - `tools/ft_search_tool.py` – MCP‑Tool `calibre_fulltext_search`
  - `tools/excerpt_tool.py` – MCP‑Tool `calibre_get_excerpt`
  - `websocket_server.py` – kleiner WebSocket‑RPC‑Server für MCP‑Calls
  - `mcp_protocol.py` – einfache MCP‑Request/Response‑Strukturen
  - `main.py` – Einstiegspunkt für den Server
- `calibre_plugin/` – Calibre‑GUI‑Plugin
  - `__init__.py` – Plugin‑Metadaten für Calibre
  - `config.py` – Plugin‑Einstellungen / UI
  - `main.py` – Dialog, Recherche‑Agent, Start/Stopp des WebSocket‑Servers
  - `providers.py` – Konfiguration der LLM‑Provider (OpenAI‑kompatibel, o. Ä.)
  - `recherche_agent.py` – Orchestrierung von LLM + MCP‑Tools
  - `ui.py` – Qt‑Dialog und UI‑Logik
- `tests/`
  - `inspect_metadata_isbn.py` – Debug‑Script, zeigt ISBN‑Mapping in `metadata.db`
  - `manual_test_websocket_connectivity.py` – Testet WS‑Server mit einem einfachen Client

---

## Installation (Development Setup)

Voraussetzungen:

- Python 3.10+ (getestet mit 3.12)
- Lokale Calibre‑Bibliothek (mit `metadata.db`)

Setup (Entwicklungsumgebung):

```bash
# Repository klonen
git clone https://github.com/Miguel0888/mcp-server.git
cd mcp-server

# Optional: virtuelles Environment anlegen
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Paket im Editable‑Mode installieren (inkl. Dependencies)
python -m pip install --upgrade pip
python -m pip install -e .
```

Danach ist das Paket `calibre_mcp_server` im aktiven Python‑Interpreter verfügbar.

---

## MCP‑Server manuell starten (WebSocket‑Modus)

Der Calibre‑Plugin‑Workflow startet den Server automatisch. Für manuelle Tests kannst du ihn aber auch direkt ausführen.

### 1. Konfiguration über Umgebungsvariablen

Der Server liest die Bibliotheks‑Konfiguration aus `src/calibre_mcp_server/config.py`. Standard: aktuelle Calibre‑Bibliothek oder ein konfigurierten Pfad.

Für einen manuellen Test kannst du z. B. `CALIBRE_LIBRARY_PATH` setzen:

```bash
set CALIBRE_LIBRARY_PATH=X:\E-Books
python -m calibre_mcp_server.main
```

Der Server startet dann einen WebSocket‑Endpoint, z. B. `ws://127.0.0.1:8765`, und akzeptiert MCP‑ähnliche Requests (`list_tools`, `call_tool`).

### 2. Tools testen (z. B. via WebSocket‑Client oder Testskript)

Siehe `tests/manual_test_websocket_connectivity.py` für ein Minimalbeispiel, das:

- eine Verbindung zu `ws://127.0.0.1:8765` herstellt,
- `list_tools` sendet und
- anschließend `call_tool` für `calibre_fulltext_search` ausführt.

---

## Calibre‑Plugin: Installation & Konfiguration

### Plugin‑ZIP bauen (falls nicht über GitHub Release bezogen)

Im Projekt‑Root:

```bash
mkdir dist
cd calibre_plugin
zip -r ..\dist\calibre-mcp-plugin.zip .
```

Die ZIP‑Datei `dist/calibre-mcp-plugin.zip` enthält dann die Plugin‑Dateien im Root, wie Calibre es erwartet.

### Plugin in Calibre installieren

1. Calibre öffnen
2. Einstellungen → Plugins → "Plugin aus Datei laden"
3. `dist/calibre-mcp-plugin.zip` auswählen
4. Calibre neu starten

Danach erscheint das Plugin (z. B. "MCP‑Recherche") im Menü / der Toolbar.

### Wichtige Einstellungen im Plugin

Im Plugin‑Dialog (`Einstellungen → Plugins → MCP Server Recherche → Konfigurieren`):

- **MCP Server Einstellungen**
  - `Server-Host` (Default: `127.0.0.1`)
  - `Server-Port` (Default: `8765`)
  - `Calibre-Bibliothek` (optional fester Pfad; sonst aktive Bibliothek verwenden)
  - Optional: Python‑Interpreter für den MCP‑Server (falls nicht der globale genutzt werden soll)
- **Recherche‑Feintuning**
  - `max_query_variants` – Wie viele Varianten an Suchqueries pro Runde maximal genutzt werden.
  - `max_hits_per_query` – Limit für Treffer pro Query.
  - `max_hits_total` – Globales Limit an Treffern, die in den Kontext übernommen werden.
  - `target_sources` – Wie viele unterschiedliche Quellen (Bücher) der Agent mindestens finden soll.
  - `max_excerpts` / `max_excerpt_chars` – Anzahl und Länge der Excerpts.
  - `min_hits_required` – Mindestanzahl an Treffern, bevor die Suche beendet wird.
  - `max_search_rounds` – Wie viele Suchrunden der Agent maximal macht (z. B. 2: einfache Keywords + Refinement).
  - `context_influence` – Wie stark vorherige Fragen den Kontext neuer Nachfragen beeinflussen (0–100).
- **Prompt‑Hints**
  - `Hinweis für Query-Planer-Prompt` (`query_planner_hint`)
    - Zusatztext, den du der KI geben kannst, um die Art der Suchqueries zu steuern
      (z. B. „nutze bevorzugt deutsche Fachbegriffe aus der Fahrzeugtechnik“).
  - `Hinweis für Schlagwort-Prompt` (`keyword_extraction_hint`)
    - Feintuning für die Keyword‑Extraktion, z. B. „nutze zunächst breite Begriffe ohne AND, keine langen UND‑Ketten“.
  - `Hinweis für Antwort-Prompt` (`answer_style_hint`)
    - Ergänze, wie die Antworten formuliert werden sollen (z. B. „erkläre auf Bachelor‑Niveau“).
- **Suchmodus**
  - `LLM für Query-Planung verwenden` – Schaltet die LLM‑gestützte Schlagwort‑/Query‑Planung ein/aus.
  - `Max. Schlagwörter pro Suche` (`max_search_keywords`)
  - `Verknüpfung (AND/OR)` (`keyword_boolean_operator`) – wird vor allem für klassische, heuristische Queries genutzt.

---

## Wie der Recherche‑Agent arbeitet (High‑Level)

Der Kern der Logik steckt in `calibre_plugin/recherche_agent.py`:

1. **Frage normalisieren**
   - Leere Eingaben werden ignoriert.
   - Kurze Nachfragen werden mit der vorherigen Frage kombiniert, um Kontext zu erhalten.

2. **Suchrunden ausführen**
   - Runde 1:
     - `_extract_keywords` (LLM) erzeugt eine Wortliste / einfache Phrasen.
     - Wenn es nur eine Liste ist (z. B. "hacking cyberangriffe sicherheit …"),
       werden die Wörter gesplittet und **einzeln** als Queries ausgeführt (`hacking`, `Sicherheit`, ...).
       → Effektiv eine OR‑Suche über die einzelnen Begriffe.
     - Wenn mehrere Phrasen zurückkommen, wird jede als eigene Query verwendet.
   - Runde 2+ (optional, bis `max_search_rounds`):
     - `_refine_search_queries` nutzt den LLM, um auf Basis bisheriger Treffer
       alternative oder verfeinerte Suchqueries zu erzeugen.
     - Die Ergebnisse werden mit den bisherigen Treffern zusammengeführt und dedupliziert.

3. **Treffer mit Excerpts anreichern**
   - Für eine begrenzte Anzahl an Treffern mit ISBN ruft der Agent `calibre_get_excerpt` auf,
     um kurze Textausschnitte (z. B. aus Kommentaren) zu laden.

4. **Prompt bauen & LLM‑Antwort holen**
   - Der Agent baut einen Markdown‑Prompt mit drei Teilen:
     1. Kurze Zusammenfassung
     2. Relevante Bücher mit Kurznotizen und ISBN
     3. Ausführliche Beantwortung der Frage
   - Der LLM‑Provider wird über `ChatProviderClient` angesprochen.

5. **Antwort im Dialog anzeigen**
   - Der Dialog zeigt die Antwort (Markdown) und optional das Debug‑Log der Tool‑Nutzung.

---

## Debugging & Tests

- **FT‑Suche direkt testen**
  - `src/calibre_mcp_server/tools/ft_search_tool.py` nutzt `LibraryResearchService.fulltext_search`.
  - Manuelle Tests kannst du mit einem einfachen WebSocket‑Client oder dem Testskript durchführen.
- **ISBN‑Mapping prüfen**
  - `tests/inspect_metadata_isbn.py` hilft zu verstehen, wie Calibre ISBNs in `books` und `identifiers` ablegt.

Beispielaufruf:

```bash
python tests\inspect_metadata_isbn.py 9783658024192
```

---

## Roadmap / Ideen

- Weitere MCP‑Tools, z. B. für
  - Schlagwort‑Suche (Tags, Serien)
  - Autorensuche
  - Volltextsuche über den tatsächlichen Buchinhalt (sofern indiziert)
- Bessere Unterstützung für Streaming‑Antworten im Calibre‑Dialog
- Konfigurierbare Anzeige von Tool‑Traces (Debugpanel ein-/ausblendbar)
- Erweiterte Mehrphasen‑Strategien für den Recherche‑Agenten (z. B. mehr als 2 Suchrunden, gewichtete Treffer)

---

Dieses Projekt ist experimentell – Feedback, Issues und Pull Requests sind willkommen.
