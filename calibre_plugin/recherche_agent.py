from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Set

try:
    import websockets
except ImportError as exc:  # pragma: no cover - runtime environment
    websockets = None

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient

log = logging.getLogger(__name__)

FULLTEXT_TOOL = "calibre_fulltext_search"
EXCERPT_TOOL = "calibre_get_excerpt"


class MCPTransportError(RuntimeError):
    """Raised when the MCP bridge cannot fulfil a request."""


@dataclass
class SearchHit:
    book_id: Any
    title: str
    isbn: Optional[str]
    snippet: str
    origin_query: Optional[str] = None


@dataclass
class EnrichedHit:
    hit: SearchHit
    excerpt_text: Optional[str] = None
    excerpt_source: Optional[str] = None


class RechercheAgent(object):
    """Coordinate MCP tools and LLM to answer research questions."""

    def __init__(self, prefs_obj, trace_callback=None):
        self.prefs = prefs_obj
        self.chat_client = ChatProviderClient(self.prefs)
        self._trace = trace_callback
        # Werte aus Preferences mit Defaults lesen
        self.max_query_variants = int(self.prefs.get("max_query_variants", 3))
        self.max_hits_per_query = int(self.prefs.get("max_hits_per_query", 6))
        self.max_hits_total = int(self.prefs.get("max_hits_total", 12))
        self.target_sources = int(self.prefs.get("target_sources", 3))
        self.max_excerpts = int(self.prefs.get("max_excerpts", 4))
        self.max_excerpt_chars = int(self.prefs.get("max_excerpt_chars", 1200))
        self.context_hit_limit = int(self.prefs.get("context_hit_limit", 8))
        self.request_timeout = int(self.prefs.get("request_timeout", 15))
        # Cache der vom Server gemeldeten Tools (name -> schema)
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}

    def _trace_log(self, message: str) -> None:
        """Optionaler Hook, um Tool-Nutzung ins UI zu loggen."""
        if callable(self._trace):
            try:
                self._trace(message)
            except Exception:  # pragma: no cover - UI-Fehler sollen nie den Agenten crashen
                log.exception("Trace callback failed")

    # ------------------------------------------------------------------ Public API

    def answer_question(self, question: str) -> str:
        """Vollständigen Recherche-Workflow ausführen und LLM-Antwort zurückgeben.

        Workflow:
        1. Suchqueries planen (LLM-gestützt oder Fallback: Originalfrage)
        2. Volltextsuche via MCP-Tools ausführen und Treffer sammeln
        3. Ausgewählte Treffer mit Excerpts anreichern
        4. Prompt auf Basis der Treffer bauen
        5. LLM mit dem Prompt abfragen
        """
        question = (question or "").strip()
        if not question:
            return ""

        log.info("Recherche-Agent gestartet: %s", question)

        try:
            self._ensure_tools_cached()

            search_queries = self._plan_search_queries(question)
            search_hits = self._run_search_plan(search_queries)
            if not search_hits:
                return "System: Keine passenden Treffer im MCP-Server gefunden."

            enriched_hits = self._enrich_hits_with_excerpts(search_hits)
        except MCPTransportError as exc:
            log.error("MCP-Workflow fehlgeschlagen: %s", exc)
            return f"System: Recherche via MCP fehlgeschlagen: {exc}"

        prompt = self._build_prompt(question, enriched_hits)
        return self._ask_llm(prompt)

    # ------------------ Tool discovery ------------------

    def _ensure_tools_cached(self) -> None:
        """Lade die Tool-Liste einmalig vom Server (list_tools)."""
        if self._tool_schemas:
            return

        response = self._call_mcp("list_tools", params={})
        result = response.get("result") or {}
        tools = result.get("tools") or []
        if not tools:
            raise MCPTransportError("MCP-Server meldet keine Tools ueber list_tools")

        schemas: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            name = tool.get("name")
            if not name:
                continue
            schemas[name] = tool
        self._tool_schemas = schemas
        log.info("MCP list_tools lieferte: %s", list(schemas.keys()))

    def _has_tool(self, name: str) -> bool:
        return name in self._tool_schemas

    # ------------------ Planning helpers ------------------

    def _plan_search_queries(self, question: str) -> List[str]:
        """Erzeuge Suchabfragen fuer die Volltextsuchen.

        Wenn use_llm_query_planning aktiviert ist, wird zunaechst der LLM
        benutzt, um Suchphrasen vorzuschlagen. Anschliessend werden aus der
        Frage (und optional den LLM-Vorschlaegen) Schlagwoerter extrahiert
        und in boolsche Volltextqueries (z. B. "bus AND fahrzeug AND can")
        umgewandelt.
        """
        use_llm = bool(self.prefs.get('use_llm_query_planning', True))
        raw_queries: List[str] = []

        if use_llm:
            planning_prompt = (
                "Du hilfst dabei, Fragen anhand einer Calibre-Bibliothek zu beantworten.\n"
                "Formuliere bis zu drei kurze Suchabfragen fuer eine Volltextsuche, eine pro Zeile.\n"
                "Nutze dabei vor allem zentrale Fachbegriffe und Titelwoerter, keine ganzen Saetze.\n\n"
                f"Frage:\n{question}\n\n"
                "Gib nur die Suchabfragen ohne Erklaerungen aus."
            )

            try:
                response = self.chat_client.send_chat(planning_prompt)
                raw_queries = self._extract_queries(response)
            except Exception as exc:  # noqa: BLE001 - fallback to heuristische Suche
                log.warning("LLM-Query-Planung fehlgeschlagen: %s", exc)
                raw_queries = []

        # Immer sicherstellen, dass die Originalfrage als Basis vorhanden ist
        if not raw_queries:
            raw_queries = [question]
        elif question not in raw_queries:
            raw_queries.insert(0, question)

        raw_queries = raw_queries[: self.max_query_variants]

        # Nun Schlagwoerter extrahieren und in boolsche Volltextqueries
        keyword_queries: List[str] = []
        for q in raw_queries:
            kws = self._extract_keywords(q)
            if not kws:
                continue
            keyword_queries.append(self._keywords_to_query(kws))

        # Fallback: wenn keine Keywords erkannt wurden, nehme Roh-Queries
        if not keyword_queries:
            keyword_queries = raw_queries

        log.info("Geplante Volltext-Queries: %r", keyword_queries)
        self._trace_log(f"Geplante Volltext-Queries: {keyword_queries!r}")
        return keyword_queries

    def _extract_keywords(self, text: str) -> List[str]:
        """Einfache Schlagwort-Extraktion fuer Volltextsuchen.

        - Kleinbuchstaben
        - nicht alphanumerische Zeichen zu Leerzeichen
        - Stoppworte entfernen
        - Laengenfilter (>= 3 Zeichen)
        - Limit aus prefs (max_search_keywords)
        """
        if not text:
            return []

        max_kws = int(self.prefs.get('max_search_keywords', 5))
        cleaned = re.sub(r"[^\wäöüÄÖÜß]+", " ", text.lower())
        tokens = [t.strip() for t in cleaned.split() if t.strip()]

        # sehr einfache deutsche/englische Stoppwortliste
        stopwords = {
            'und', 'oder', 'der', 'die', 'das', 'ein', 'eine', 'einer', 'eines',
            'ist', 'sind', 'was', 'wie', 'warum', 'welche', 'welcher', 'welches',
            'gibt', 'es', 'zu', 'im', 'in', 'am', 'an', 'den', 'dem', 'des',
            'the', 'a', 'an', 'of', 'for', 'to', 'on', 'in', 'and', 'or',
        }

        keywords: List[str] = []
        for tok in tokens:
            if len(tok) < 3:
                continue
            if tok in stopwords:
                continue
            if tok not in keywords:
                keywords.append(tok)
            if len(keywords) >= max_kws:
                break

        return keywords

    def _keywords_to_query(self, keywords: List[str]) -> str:
        """Baue eine boolsche Volltextquery aus Schlagwoertern.

        Beispiel: ['fahrzeug', 'bus', 'can'] + AND -> "fahrzeug AND bus AND can"
        """
        if not keywords:
            return ""
        op = str(self.prefs.get('keyword_boolean_operator', 'AND')).upper()
        if op not in ('AND', 'OR'):
            op = 'AND'
        return f" {op} ".join(keywords)

    # ------------------ Search plan execution ------------------

    def _run_search_plan(self, queries: List[str]) -> List[SearchHit]:
        """Alle Suchqueries nacheinander ausführen und deduplizierte Treffer liefern."""
        if not self._has_tool(FULLTEXT_TOOL):
            raise MCPTransportError(
                f"Tool '{FULLTEXT_TOOL}' ist auf dem MCP-Server nicht verfuegbar."
            )

        aggregated: List[SearchHit] = []
        seen_ids: Set[Tuple[Any, Any]] = set()

        for query in queries:
            hits = self._run_fulltext_search(query, max_hits=self.max_hits_per_query)
            log.info("Fulltext-Suche %r lieferte %d Treffer", query, len(hits))

            for hit in hits:
                identifier = (hit.book_id, hit.isbn)
                if identifier in seen_ids:
                    continue
                aggregated.append(hit)
                seen_ids.add(identifier)
                if len(aggregated) >= self.max_hits_total:
                    break
            if len(aggregated) >= self.target_sources:
                break

        return aggregated[: self.max_hits_total]

    def _run_fulltext_search(self, query: str, max_hits: int = 5) -> List[SearchHit]:
        arguments = {"query": query, "limit": max_hits}
        payload = {
            "name": FULLTEXT_TOOL,
            "arguments": self._wrap_arguments(FULLTEXT_TOOL, arguments),
        }
        self._trace_log(f"Toolcall {FULLTEXT_TOOL}: query={query!r}, limit={max_hits}")
        response = self._call_mcp("call_tool", params=payload, request_id="ft-search")
        result = (response.get("result") or {})
        raw_hits = result.get("hits")
        if raw_hits is None and "content" in result:
            raw_hits = self._extract_hits_from_content(result["content"])

        hits: List[SearchHit] = []
        for raw in raw_hits or []:
            if not isinstance(raw, dict):
                continue
            hits.append(
                SearchHit(
                    book_id=raw.get("book_id"),
                    title=raw.get("title") or "",
                    isbn=raw.get("isbn"),
                    snippet=raw.get("snippet") or "",
                    origin_query=query,
                )
            )
        return hits

    def _wrap_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Passe Argument-Struktur an das gemeldete input_schema an.

        Aktuell werden FastMCP-Tools so registriert, dass die Signatur bereits
        ein einzelnes Pydantic-Modell als Parameter nutzt (z. B. FulltextSearchInput),
        FastMCP wickelt die Eingabe passend, daher senden wir hier direkt
        das arguments-Dict ohne weitere "input"-Verschachtelung.
        """
        return arguments

    def _extract_hits_from_content(self, content: Any) -> List[Dict[str, Any]]:
        """Best-effort extraction of hits from FastMCP-style content blocks.

        Erwartete Struktur (wie von FastMCP serialisiert):
        result = {
            "content": [
                {"type": "text", "text": "{\n  \"hits\": [...]}"},
                ...
            ]
        }
        """
        if not content:
            return []

        hits: List[Dict[str, Any]] = []

        for block in content:
            # FastMCP text blocks: {"type": "text", "text": "{ \"hits\": [...]}"}
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                raw_text = block.get("text", "")
                try:
                    parsed = json.loads(raw_text)
                except Exception:
                    # Kein JSON, dann koennen wir hier nichts extrahieren
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get("hits"), list):
                    for h in parsed["hits"]:
                        if isinstance(h, dict):
                            hits.append(h)
                continue

            # Aeltere/andere Struktur: direktes Objekt mit 'hits' oder 'value.hits'
            value = None
            if isinstance(block, dict):
                if "hits" in block:
                    value = block
                else:
                    value = block.get("value")
            if not isinstance(value, dict):
                continue
            raw_hits = value.get("hits")
            if isinstance(raw_hits, list):
                for h in raw_hits:
                    if isinstance(h, dict):
                        hits.append(h)

        return hits

    # ------------------ Excerpt enrichment ------------------

    def _enrich_hits_with_excerpts(self, hits: List[SearchHit]) -> List[EnrichedHit]:
        """Ausgewählte Treffer mit Excerpts anreichern."""
        if not self._has_tool(EXCERPT_TOOL):
            # Ohne Excerpt-Tool liefern wir nur Snippets, keine harte Fehlermeldung
            return [EnrichedHit(hit=h) for h in hits]

        enriched: List[EnrichedHit] = []
        excerpt_count = 0

        for hit in hits:
            excerpt_text: Optional[str] = None
            excerpt_source: Optional[str] = None

            if hit.isbn and excerpt_count < self.max_excerpts:
                try:
                    payload = self._call_excerpt_tool(hit.isbn)
                except MCPTransportError as exc:
                    log.warning(
                        "Excerpt-Tool fehlgeschlagen fuer ISBN %s: %s", hit.isbn, exc
                    )
                else:
                    excerpt_text = (
                        payload.get("text")
                        or payload.get("excerpt")
                        or ""
                    )
                    excerpt_source = payload.get("source_hint")
                    excerpt_count += 1

            enriched.append(EnrichedHit(hit=hit, excerpt_text=excerpt_text, excerpt_source=excerpt_source))

        return enriched

    def _call_excerpt_tool(self, isbn: str) -> Dict[str, Any]:
        arguments = {
            "isbn": isbn,
            "max_chars": self.max_excerpt_chars,
        }
        self._trace_log(f"Toolcall {EXCERPT_TOOL}: isbn={isbn!r}, max_chars={self.max_excerpt_chars}")
        payload = {
            "name": EXCERPT_TOOL,
            "arguments": self._wrap_arguments(EXCERPT_TOOL, arguments),
        }
        response = self._call_mcp(
            "call_tool", params=payload, request_id=f"excerpt-{isbn}"
        )
        result = response.get("result")
        if not result:
            raise MCPTransportError("Excerpt-Tool lieferte kein Ergebnis")
        return result

    # ------------------ Low-level MCP/WebSocket transport ------------------

    def _call_mcp(
        self, method: str, params: Dict[str, Any], request_id: str | None = None
    ) -> Dict[str, Any]:
        """Allgemeiner synchroner MCP-RPC-Wrapper ueber WebSocket."""

        if websockets is None:  # pragma: no cover - nur Laufzeitumgebung
            raise MCPTransportError(
                "Python-Paket 'websockets' ist im Calibre-Plugin nicht verfuegbar."
            )

        rid = request_id or "mcp-client"
        url = self._tool_endpoint()
        payload = {
            "id": rid,
            "method": method,
            "params": params,
        }
        self._trace_log(f"MCP -> {method}: {json.dumps(payload, ensure_ascii=False)}")

        async def _do_call() -> Dict[str, Any]:
            data = json.dumps(payload)
            try:
                async with websockets.connect(url) as websocket:
                    await websocket.send(data)
                    raw = await websocket.recv()
            except Exception as exc:  # noqa: BLE001
                raise MCPTransportError(
                    f"Verbindung zum MCP-Server fehlgeschlagen: {exc}"
                ) from exc

            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise MCPTransportError(
                    "Antwort des MCP-Servers konnte nicht gelesen werden"
                ) from exc

        try:
            response = asyncio.run(_do_call())
        except RuntimeError as exc:
            log.error("Async-Call im laufenden Eventloop fehlgeschlagen: %s", exc)
            raise MCPTransportError(
                "Konnte keine WebSocket-Verbindung zum MCP-Server herstellen (Eventloop-Konflikt)."
            ) from exc

        self._trace_log(f"MCP <- {method}: {json.dumps(response, ensure_ascii=False)[:500]}")
        if "error" in response:
            message = response["error"].get("message", "Unbekannter MCP-Fehler")
            raise MCPTransportError(message)
        return response

    def _tool_endpoint(self) -> str:
        host, port = self._server_config()
        return f"ws://{host}:{port}"

    def _server_config(self) -> Tuple[str, int]:
        host = self._pref_value("server_host", "127.0.0.1")
        port_raw = self._pref_value("server_port", "8765")
        try:
            port = int(str(port_raw).strip() or "8765")
        except (TypeError, ValueError):
            port = 8765
        return (str(host).strip() or "127.0.0.1", port)

    def _pref_value(self, key: str, default: Any) -> Any:
        getter = getattr(self.prefs, "get", None)
        if callable(getter):
            value = getter(key, default)
        else:
            try:
                value = self.prefs[key]
            except Exception:  # noqa: BLE001
                value = default
        return value if value not in (None, "") else default

    # ------------------ Prompt construction & LLM ------------------

    def _build_prompt(self, question: str, hits: List[EnrichedHit]) -> str:
        if not hits:
            context_block = "Keine passenden Treffer gefunden."
        else:
            lines: List[str] = ["Suchtreffer und Auszuege:"]
            for idx, enriched in enumerate(hits[: self.context_hit_limit], start=1):
                hit = enriched.hit
                title = hit.title or "Unbekannter Titel"
                isbn = hit.isbn or "Unbekannt"
                lines.append(f"[{idx}] {title} (ISBN: {isbn})")

                snippet = self._trim_text(hit.snippet)
                if snippet:
                    lines.append(f"Snippet: {snippet}")

                excerpt = self._trim_text(enriched.excerpt_text)
                if excerpt:
                    lines.append(f"Excerpt: {excerpt}")

                if hit.origin_query:
                    lines.append(f"Suchbegriff: {hit.origin_query}")

                lines.append("")
            context_block = "\n".join(lines)

        prompt = (
            "Du bist ein Recherche-Assistent fuer eine Calibre-Bibliothek.\n"
            "Nutze ausschliesslich den Kontext unten, antworte in sachlichem Deutsch\n"
            "und verweise auf Quellen als [Nr] mit ISBN. Trenne klar zwischen Wissen aus\n"
            "den Treffern und allgemeinem Hintergrund, falls noetig.\n\n"
            f"FRAGE:\n{question}\n\n"
            f"KONTEXT AUS DER BIBLIOTHEK:\n{context_block}\n\n"
            "Gebe einen Bericht mit (1) Zusammenfassung, (2) Relevante Buecher mit Kurznotizen,"
            " (3) Offene Punkte."
        )
        return prompt

    def _ask_llm(self, prompt: str) -> str:
        return self.chat_client.send_chat(prompt)

    @staticmethod
    def _trim_text(text: Any, limit: int = 600) -> str:
        if not text:
            return ""
        cleaned = str(text).strip().replace("\n", " ")
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

