````markdown
# Calibre MCP Server

Ein experimenteller [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol) Server, der auf eine lokale [Calibre](https://calibre-ebook.com/) Bibliothek zugreift. Ziel ist es, KI-Agenten (z. B. ChatGPT, Copilot, Claude Desktop) ein Research-API auf deine E-Book-Sammlung zu geben – inklusive Fulltext-Suche und strukturierten Excerpts.

Zusätzlich gibt es ein Calibre-GUI-Plugin, das den MCP-Server direkt aus Calibre heraus startet und stoppt.

---

## Features (aktueller Stand)

- MCP-Server auf Basis von `fastmcp`
  - Tool `calibre_fulltext_search`
  - Tool `calibre_get_excerpt`
- Zugriff auf Calibre-`metadata.db` via SQLite (read-only)
  - Volltext-ähnliche Suche über Titel, ISBN und Kommentare (`books` + `comments`)
  - Auflösen von Büchern über ISBN (inkl. `identifiers`-Tabelle)
- Domänenschicht `LibraryResearchService` als zentrale API
- Calibre-GUI-Plugin, das den MCP-Server als Subprozess startet/stoppt
- Zwei kleine Testskripte zum manuellen Testen gegen eine echte Bibliothek

---

## Repository-Struktur

Wichtige Verzeichnisse/Dateien:

- `pyproject.toml` – Projekt- und Dependency-Definitionen
- `src/calibre_mcp_server/` – MCP-Server und Domänencode
  - `core/models.py` – einfache Domain-Modelle (`FulltextHit`, `Excerpt` …)
  - `core/service.py` – `LibraryResearchService`, zentrale Research-API
  - `infra/metadata_sqlite.py` – Zugriff auf `metadata.db` über SQLite
  - `tools/ft_search_tool.py` – MCP-Tool `calibre_fulltext_search`
  - `tools/excerpt_tool.py` – MCP-Tool `calibre_get_excerpt`
  - `main.py` – Einstiegspunkt für den MCP-Server (`python -m calibre_mcp_server.main`)
- `calibre_plugin/` – Calibre-GUI-Plugin
  - `__init__.py` – Plugin-Metadaten für Calibre
  - `action.py` – GUI-Action, startet/stoppt den MCP-Server
- `tests/` – manuelle Testskripte
  - `manual_test_service.py` – einfacher End-to-End-Test für den Service
  - `inspect_metadata_isbn.py` – Debug-Script, das zeigt, wie eine ISBN in `metadata.db` gespeichert ist

---

## Voraussetzungen

- Python 3.10+ (getestet mit 3.12)
- Eine lokale Calibre-Bibliothek
  - z. B. `X:\E-Books` mit `metadata.db` im Root
- Entwicklungsabhängigkeiten (werden über `pip` installiert):
  - `fastmcp`
  - `pydantic`
  - plus alles, was in `pyproject.toml` steht

---

## Installation (Development Setup)

```bash
# Repository klonen
git clone https://github.com/Miguel0888/mcp-server.git
cd mcp-server

# Optional: virtuelles Environment anlegen
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Paket im Editable-Mode installieren (inkl. Dependencies)
python -m pip install -e .
````

Danach ist das Paket `calibre_mcp_server` im aktiven Python-Interpreter importierbar.

---

## MCP-Server manuell starten

Voraussetzung: Environment-Variable `CALIBRE_LIBRARY_PATH` muss auf den Root deiner Calibre-Bibliothek zeigen (dort, wo `metadata.db` liegt).

Beispiel (Windows):

```bash
set CALIBRE_LIBRARY_PATH=X:\E-Books
python -m calibre_mcp_server.main
```

Du solltest die FastMCP-Banner-Ausgabe sehen und der Server wartet dann auf MCP-Client-Verbindungen über STDIO.

In einer MCP-fähigen IDE / einem MCP-Client (z. B. ChatGPT, Claude Desktop, Copilot Agent Mode) kann dieser Command als MCP-Server registriert werden und die Tools `calibre_fulltext_search` und `calibre_get_excerpt` verwenden.

---

## Manuelle Tests gegen eine echte Bibliothek

### 1. `tests/manual_test_service.py`

Dieses Script testet die Domänenschicht `LibraryResearchService` direkt – ohne MCP und ohne Calibre-Plugin.

Anpassen in `tests/manual_test_service.py`:

```python
library_path = r"X:\E-Books"  # Pfad zu deiner Calibre-Bibliothek

# Eine Query, von der du erwartest, dass sie Treffer liefert
query = "der"

# Eine echte ISBN aus deiner Bibliothek
test_isbn = "9783446429338"
```

Ausführen:

```bash
python tests\manual_test_service.py
```

Erwartetes Verhalten:

* `fulltext_search` gibt eine Liste von Treffern (`FulltextHit`) mit `book_id`, `title`, `isbn` (falls vorhanden) und einem kurzen Snippet aus Kommentaren/Titel zurück.
* `get_excerpt_by_isbn` findet das Buch zu `test_isbn` über die `identifiers`-Tabelle und gibt einen einfachen Excerpt zurück (aktuell aus `comments` oder – wenn leer – dem Titel).

### 2. `tests/inspect_metadata_isbn.py`

Dieses Script hilft beim Debuggen von ISBN-Mapping und zeigt, wie Calibre die Daten in `metadata.db` speichert.

Konfiguration im Script:

```python
library_root = r"X:\E-Books"
# Default-ISBN (kann per CLI-Argument überschrieben werden)
raw_isbn = "9783446429338"
```

Ausführen ohne Argument (nutzt die Default-ISBN):

```bash
python tests\inspect_metadata_isbn.py
```

Oder mit einer anderen ISBN:

```bash
python tests\inspect_metadata_isbn.py 9781484265611
```

Das Script zeigt u. a.:

* Schema von `books` und `identifiers`
* alle Zeilen in `books.isbn`, die zur normalisierten ISBN passen
* alle Zeilen in `identifiers.val`, die passen (inkl. `book`-ID und Typ)
* zugehörige Bücher inkl. Kommentaren (falls vorhanden)

---

## Calibre-GUI-Plugin

Im Ordner `calibre_plugin/` liegt ein einfaches GUI-Plugin, mit dem du den MCP-Server direkt aus Calibre heraus starten und stoppen kannst.

### Aufbau

* `calibre_plugin/__init__.py`

  * beschreibt das Plugin für Calibre (Name, Version, min. Calibre-Version, etc.)
  * verweist mit `actual_plugin = "action:McpInterfaceAction"` auf die Implementierung
* `calibre_plugin/action.py`

  * definiert `McpInterfaceAction` (Unterklasse von `InterfaceAction`)
  * fügt eine Toolbar-/Menü-Aktion "MCP Server" hinzu
  * beim Klick: Start/Stopp eines Subprozesses mit `python -m calibre_mcp_server.main`
  * setzt `CALIBRE_LIBRARY_PATH` automatisch auf die aktuell geöffnete Bibliothek (`self.gui.current_db.library_path`)

### Manuell ein Plugin-ZIP bauen

Im Projekt-Root:

```bash
mkdir -p dist
cd calibre_plugin
zip -r ..\dist\calibre-mcp-plugin.zip .
```

Die ZIP-Datei `dist/calibre-mcp-plugin.zip` enthält dann direkt `__init__.py` und `action.py` (genau so erwartet Calibre das).

### Plugin in Calibre installieren

1. Calibre öffnen
2. Einstellungen → Plugins → "Plugin aus Datei laden"
3. `calibre-mcp-plugin.zip` auswählen
4. Calibre neu starten

Danach sollte in der Toolbar oder im Menü ein Eintrag "MCP Server" vorhanden sein.

* Erster Klick → startet den MCP-Server (externes `python`), setzt `CALIBRE_LIBRARY_PATH`
* Zweiter Klick → beendet den Serverprozess

Wichtig: In der Python-Umgebung, die Calibre für `python` nutzt, muss das Paket `calibre_mcp_server` installiert sein, z. B.:

```bash
python -m pip install -e .
```

(ggf. mit dem Python, das in PATH liegt oder explizit in `action.py` konfiguriert wird.)

---

## GitHub Actions: automatischer Build & Release des Plugins

Lege die Datei `.github/workflows/release.yml` an mit:

```yaml
name: Release Calibre MCP Server

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-release:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install package (editable)
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e .

      - name: Smoke test (compile sources)
        run: |
          python -m compileall src

      - name: Build Calibre plugin zip
        run: |
          mkdir -p dist
          cd calibre_plugin
          zip -r ../dist/calibre-mcp-plugin.zip .

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/calibre-mcp-plugin.zip
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Was der Workflow tut:

1. Läuft bei `push` auf Tags, die mit `v` beginnen (z. B. `v0.1.0`).
2. Checkt das Repo aus.
3. Installiert dein Paket im Editable-Mode.
4. Führt einen kleinen Smoke-Test aus (`compileall`).
5. Baut `dist/calibre-mcp-plugin.zip` aus dem Ordner `calibre_plugin`.
6. Erzeugt (falls nötig) einen GitHub Release zum Tag und hängt das ZIP als Asset an.

### Release auslösen

Im Repo-Root:

```bash
# Version bump + commit (optional)
git commit -am "Bump version to v0.1.0"

# Tag erstellen
git tag v0.1.0

# Tag pushen
git push origin v0.1.0
```

Danach solltest du im GitHub-UI unter „Actions“ den Workflow sehen und unter „Releases“ dann den neuen Release mit angehängter `calibre-mcp-plugin.zip`.
