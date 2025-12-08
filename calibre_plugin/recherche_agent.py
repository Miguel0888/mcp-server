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

    def identity_key(self) -> Tuple[Any, Any]:
        return (self.book_id, self.isbn)


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
        self.min_hits_required = int(self.prefs.get("min_hits_required", 3))
        self.max_refinement_rounds = int(self.prefs.get("max_refinement_rounds", 2))
        self.context_influence = int(self.prefs.get("context_influence", 50))
        # Cache der vom Server gemeldeten Tools (name -> schema)
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}
        # Session-State fuer Folgefragen
        self._last_question: Optional[str] = None
        self._last_hits: List[EnrichedHit] = []

    def _trace_log(self, message: str) -> None:
        """Optionaler Hook, um Tool-Nutzung ins UI zu loggen."""
        if callable(self._trace):
            try:
                self._trace(message)
            except Exception:  # pragma: no cover - UI-Fehler sollen nie den Agenten crashen
                log.exception("Trace callback failed")

    # ------------------------------------------------------------------ Public API

    def answer_with_sources(self, question: str) -> Tuple[str, List[EnrichedHit]]:
        """Vollstaendigen Recherche-Workflow ausfuehren und sowohl LLM-Antwort
        als auch die angereicherten Treffer (mit Excerpts) zurueckgeben.

        Diese Methode ist die neue Hauptschnittstelle fuer das UI. Die
        bisherige answer_question bleibt als Wrapper fuer die reine
        Textantwort erhalten.
        """
        question = (question or "").strip()
        if not question:
            return "", []

        log.info("Recherche-Agent gestartet: %s", question)

        try:
            self._ensure_tools_cached()

            effective_question = self._resolve_effective_question(question)

            # Mehrstufiger Such-Loop: zuerst eine einfache Kernbegriff-Suche,
            # dann optional KI-verfeinerte Runden.
            max_rounds = int(self._pref_value("max_search_rounds", 3))
            min_hits = int(self._pref_value("min_hits_before_stop", 3))
            max_hits_total = int(self._pref_value("max_total_hits", 20))

            all_hits: list[SearchHit] = []
            all_ids: set[tuple[int | None, str | None]] = set()
            all_queries: list[str] = []

            for round_index in range(max_rounds):
                if round_index == 0:
                    # Runde 1: Keywords fuer Haupt- und Zweitsprache getrennt holen
                    primary_kws, secondary_kws = self._extract_keywords_multi(effective_question)
                    if not primary_kws and not secondary_kws:
                        primary_kws = [effective_question]

                    # Queries fuer die Hauptsprache vorbereiten (wie bisherige Logik)
                    primary_queries: list[str] = []
                    if len(primary_kws) == 1:
                        first = primary_kws[0]
                        tokens = [t for t in re.split(r"\s+", first) if t]
                        if len(tokens) > 1:
                            primary_queries.append(first)
                            for t in tokens:
                                if t not in primary_queries:
                                    primary_queries.append(t)
                        else:
                            primary_queries.append(first)
                    else:
                        primary_queries = [q for q in primary_kws if q]

                    # Queries fuer die Sekundaersprache analog vorbereiten
                    secondary_queries: list[str] = []
                    if secondary_kws:
                        if len(secondary_kws) == 1:
                            first = secondary_kws[0]
                            tokens = [t for t in re.split(r"\s+", first) if t]
                            if len(tokens) > 1:
                                secondary_queries.append(first)
                                for t in tokens:
                                    if t not in secondary_queries:
                                        secondary_queries.append(t)
                            else:
                                secondary_queries.append(first)
                        else:
                            secondary_queries = [q for q in secondary_kws if q]

                    self._trace_log(f"Suchrunde 1 (Kernbegriffe, Hauptsprache): {primary_queries!r}")
                    if secondary_queries:
                        lang_label = str(self._pref_value("second_keyword_language", "Englisch") or "Englisch").strip()
                        self._trace_log(f"Suchrunde 1b (Kernbegriffe, {lang_label}): {secondary_queries!r}")

                    round_hits: list[SearchHit] = []

                    # Zuerst Hauptsprache durchsuchen
                    if primary_queries:
                        hits_primary = self._run_search_plan(primary_queries)
                        round_hits.extend(hits_primary)
                        all_queries.extend(primary_queries)

                    # Danach immer auch Zweitsprache (falls konfiguriert/Keywords vorhanden)
                    if secondary_queries:
                        hits_secondary = self._run_search_plan(secondary_queries)
                        round_hits.extend(hits_secondary)
                        all_queries.extend(secondary_queries)

                else:
                    # Bestehende Refinement-Logik bleibt unveraendert
                    self._trace_log(f"Suchrunde {round_index + 1}: Verfeinerung basierend auf bisherigen Treffern")
                    followup_query = self._plan_followup_query(question, all_hits)
                    if not followup_query:
                        self._trace_log("Keine sinnvolle Folge-Query mehr geplant, breche ab.")
                        break
                    self._trace_log(f"Folge-Query: {followup_query!r}")
                    round_hits = self._run_search_plan([followup_query])
                    all_queries.append(followup_query)

                # Rundenhits deduplizieren und zu all_hits hinzufuegen
                new_in_round = 0
                for hit in round_hits:
                    key = hit.identity_key()
                    if key in all_ids:
                        continue
                    all_ids.add(key)
                    all_hits.append(hit)
                    new_in_round += 1
                    if len(all_hits) >= max_hits_total:
                        self._trace_log("Maximale Gesamtzahl an Treffern erreicht, beende Suche.")
                        break

                self._trace_log(f"Neue Treffer in Runde {round_index + 1}: {new_in_round}")
                if len(all_hits) >= max_hits_total:
                    break
                if len(all_hits) >= min_hits:
                    self._trace_log(
                        f"Ausreichend Treffer gesammelt ({len(all_hits)} >= {min_hits}), breche Suchschleife ab."
                    )
                    break

            if not all_hits:
                return "System: Keine passenden Treffer im MCP-Server gefunden.", []

            enriched_hits = self._enrich_hits_with_excerpts(all_hits)
            # Session-State aktualisieren
            self._last_question = question
            self._last_hits = enriched_hits
        except MCPTransportError as exc:
            log.error("MCP-Workflow fehlgeschlagen: %s", exc)
            return f"System: Recherche via MCP fehlgeschlagen: {exc}", []

        prompt = self._build_prompt(question, enriched_hits)
        answer_text = self._ask_llm(prompt)
        return answer_text, enriched_hits

    def answer_question(self, question: str) -> str:
        """Rueckwaerts-kompatible API: nur den Antworttext liefern."""
        answer, _hits = self.answer_with_sources(question)
        return answer

    def _resolve_effective_question(self, question: str) -> str:
        """Erweitere sehr kurze Nachfragen um Kontext der letzten Frage.

        Beispiel: letzte Frage "Welche Fahrzeug-Bussysteme gibt es?",
        neue Frage "Was genau ist LIN" -> kombiniert zu
        "Was genau ist LIN im Kontext von: Welche Fahrzeug-Bussysteme gibt es?".
        """
        base = (question or "").strip()
        if not self._last_question:
            return base

        # Heuristik: sehr kurze Fragen (<= 6 Woerter) als Nachfrage behandeln
        if len(base.split()) <= 6:
            combined = f"{base} (im Kontext von: {self._last_question})"
            self._trace_log(f"Kombinierte Nachfrage-Frage: {combined!r}")
            return combined
        return base

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
        """Alte Query-Planungsmethode (derzeit nicht mehr direkt verwendet).

        Wird aus Kompatibilitaetsgruenden beibehalten, der eigentliche
        mehrstufige Suchablauf findet in ``answer_question`` statt.
        """
        use_llm = bool(self.prefs.get('use_llm_query_planning', True))
        llm_queries: List[str] = []

        # Kontext fuer den Planner aufbauen: aktuelle + vorherige Frage
        context_lines: List[str] = []
        if self._last_question:
            context_lines.append("Vorherige Frage im Dialog:")
            context_lines.append(self._last_question)
            context_lines.append("")

        context_lines.append("Aktuelle Frage:")
        context_lines.append(question)
        context_text = "\n".join(context_lines)

        if use_llm:
            extra_hint = str(self.prefs.get('query_planner_hint', '') or '').strip()
            hint_block = f"\n\nZUSAETZLICHER HINWEIS DES BENUTZERS FUER DIE QUERY-PLANUNG:\n{extra_hint}" if extra_hint else ""

            planning_prompt = (
                "Du agierst als Query-Planer fuer eine Volltextsuche in einer technischen Bibliothek.\n"
                "Deine Aufgabe ist es, aus der Nutzerfrage (und dem vorangegangenen Kontext)\n"
                "eine kleine Menge von Suchabfragen zu generieren, wie man sie einer Suchmaschine\n"
                "oder Volltextsuche uebergibt.\n\n"
                "Rahmenbedingungen:\n"
                "- Bevorzuge einfache Suchphrasen mit Leerzeichen (OR-Effekt), z. B. 'fahrzeug bussysteme'.\n"
                "- Verwende AND nur sparsam, wenn mehrere Begriffe unbedingt gemeinsam auftreten sollen\n"
                "  und ein einzelner Begriff alleine zu viele irrelevante Treffer liefern wuerde.\n"
                "- Extrahiere und kombiniere nur die wichtigsten Fachbegriffe, Abkuerzungen und Synonyme.\n"
                "- Du darfst bei Bedarf boolsche Operatoren AND/OR nutzen, aber vermeide lange UND-Ketten.\n"
                "- Jede Zeile soll eine eigenstaendige Suchanfrage sein (wie bei einer Suchmaschine).\n"
                "- Vermeide Hoeflichkeitsfloskeln und Funktionsverben (z. B. 'erklaere', 'sag mir', 'bitte').\n"
                "- Nutze gegebenenfalls auch anderssprachige Fachbegriffe, wenn diese ueblich sind.\n"
                f"{hint_block}\n\n"
                f"KONTEXT:\n{context_text}\n\n"
                "Gib bis zu drei Suchabfragen aus, jeweils eine pro Zeile, ohne weitere Erklaerungen."
            )

            try:
                response = self.chat_client.send_chat(planning_prompt)
                llm_queries = [q.strip() for q in self._extract_queries(response) if q.strip()]
            except Exception as exc:  # noqa: BLE001 - fallback zu heuristischer Suche
                log.warning("LLM-Query-Planung fehlgeschlagen: %s", exc)
                llm_queries = []

        # Basiskompatibilitaet: Keywords + Planner-Queries zusammenführen
        keywords = self._extract_keywords(question)
        base_query = self._keywords_to_query(keywords) if keywords else ""

        queries: List[str] = []
        if base_query:
            queries.append(base_query)
        for q in llm_queries:
            if q and q not in queries:
                queries.append(q)
        if not queries:
            queries = [question]
        return queries[: self.max_query_variants]

    def _keywords_to_query(self, keywords: List[str]) -> str:
        """Baue eine boolsche Volltextquery aus Schlagwoertern.

        Der Operator (AND/OR) ist ueber die Einstellung 'keyword_boolean_operator'
        steuerbar und dient als *heuristische* Basis; der LLM kann zusaetzlich
        eigene AND/OR-Kombinationen vorschlagen.
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

    def _pref_value(self, key: str, default: Any = None) -> Any:
        return self.prefs.get(key, default)

    # ------------------------------------------------------------------
    # Schlagwort-Extraktion (ein- und mehrsprachig)
    # ------------------------------------------------------------------

    def _extract_keywords_multi(self, text: str) -> tuple[list[str], list[str]]:
        """Liefert (primary_keywords, secondary_keywords).

        - primary_keywords: Schlagwoerter in der Sprache der Frage
        - secondary_keywords: Schlagwoerter in der zweiten Sprache, falls
          second_keyword_language_enabled == True.

        Nutzt die bestehende LLM-Logik (send_chat, max_search_keywords,
        keyword_extraction_hint usw.). Wenn use_llm_query_planning == False,
        wird ein einfacher heuristischer Fallback fuer die Primärsprache
        verwendet und die Zweitsprache bleibt leer.
        """
        text = (text or "").strip()
        if not text:
            return [], []

        use_llm = bool(self._pref_value("use_llm_query_planning", True))
        max_kws = int(self._pref_value("max_search_keywords", 5))
        extra_hint = str(self._pref_value("keyword_extraction_hint", "") or "").strip()

        # Heuristischer Fallback ohne LLM: nur primäre Keywords aus der Frage
        if not use_llm:
            cleaned = re.sub(r"[^\wäöüÄÖÜß]+", " ", text.lower())
            tokens = [t.strip() for t in cleaned.split() if t.strip()]
            return tokens[:max_kws], []

        hint_block = "" if not extra_hint else (
            "Zusaetzlicher Hinweis des Benutzers fuer die Schlagwort-Extraktion:\n"
            f"{extra_hint}\n\n"
        )

        base_prompt = (
            "Du erstellst Schlagwoerter fuer eine Volltextsuche.\n"
            "Aus der folgenden Frage sollst du nur die wichtigsten Suchbegriffe\n"
            "und einfachen Suchphrasen extrahieren.\n\n"
            "Vorgaben:\n"
            "- Bevorzuge kurze Phrasen mit Leerzeichen, z. B. 'fahrzeug bussysteme',\n"
            "  was einer ODER-Suche ueber beide Begriffe entspricht.\n"
            "- Verwende AND nur, wenn zwei Begriffe wirklich gemeinsam auftreten muessen,\n"
            "  z. B. 'penetration testing' AND 'hacking'. Lange UND-Ketten sollen vermieden werden.\n"
            "- Du darfst OR verwenden, aber halte die Ausdruecke einfach (z. B. 'CAN OR LIN OR FlexRay').\n"
            "- Kein Erklaertext, keine Saetze, nur eine Liste von Begriffen/Queries,\n"
            "  jeweils eine pro Zeile.\n\n"
            f"{hint_block}Frage:\n{text}\n"
        )

        def _run_llm(prompt: str) -> list[str]:
            try:
                response = self.chat_client.send_chat(prompt)
            except Exception as exc:
                log.warning("LLM-Schlagwort-Extraktion fehlgeschlagen: %s", exc)
                return []
            raw_lines = [line.strip() for line in response.splitlines() if line.strip()]
            out: list[str] = []
            for line in raw_lines:
                if line and line not in out:
                    out.append(line)
                if len(out) >= max_kws:
                    break
            return out

        # Primärsprache
        primary_keywords = _run_llm(base_prompt)
        self._trace_log(f"Schlagwoerter (Hauptsprache): {primary_keywords!r}")

        # Sekundärsprache (optional) mit zusaetzlichen Regeln
        secondary_keywords: list[str] = []
        second_enabled = bool(self._pref_value("second_keyword_language_enabled", False))
        lang_for_trace = None
        if second_enabled:
            lang_for_trace = str(self._pref_value("second_keyword_language", "Englisch") or "Englisch").strip()
            second_rules = (
                "Zusätzliche Regeln NUR für die Suchbegriffe in der zweiten Sprache:\n"
                "- Liefere NUR Suchbegriffe und Suchphrasen, die fachlich typischerweise in dieser Sprache verwendet werden.\n"
                "- Vermeide generische Wörter wie 'system', 'data', 'information', 'business', 'use', 'example' ohne klaren fachlichen Bezug.\n"
                "- Gib KEINE einzelnen Wörter zurück, die auch häufige englische Verben oder Funktionswörter sind "
                "(z. B. 'can', 'will', 'may', 'must', 'be', 'do', 'have').\n"
                "- Wenn eine sehr kurze Abkürzung fachlich notwendig ist (z. B. 'CAN', 'LIN', 'MOST'), kombiniere sie IMMER mit einem Kontext:\n"
                "  - entweder als Phrase, z. B. 'CAN bus', 'CAN bus automotive', 'CAN bus networking'\n"
                "  - oder mit AND, z. B. 'CAN AND vehicle bus systems', 'CAN AND automotive network'.\n"
                "- Nutze AND nur, um einen Fachbegriff mit einem Kontextbegriff zu verknüpfen. Erzeuge keine langen UND-Ketten.\n"
                "- Jede Zeile enthält genau EINE Suchphrase.\n"
                f"- Gib maximal {max_kws} wirklich prägnante Suchphrasen zurück.\n\n"
            )

            second_prompt = (
                "Dies ist die gleiche Aufgabe, aber bitte liefere die Suchbegriffe explizit "
                f"in der Sprache: {lang_for_trace}.\n\n"
                + second_rules
                + base_prompt
            )

            secondary_keywords = _run_llm(second_prompt)

            # Simple safeguard fuer Sekundaersprache: reine Hilfsverben entfernen
            blocklist = {"can", "will", "may", "must", "be", "do", "have"}
            cleaned_secondary: list[str] = []
            for kw in secondary_keywords:
                if not kw:
                    continue
                tokens = [t for t in kw.split() if t]
                if len(tokens) == 1 and tokens[0].lower() in blocklist:
                    # Skip pure helper verb from second language
                    continue
                cleaned_secondary.append(kw)
            secondary_keywords = cleaned_secondary

            self._trace_log(f"Schlagwoerter ({lang_for_trace}): {secondary_keywords!r}")

        return primary_keywords, secondary_keywords

    def _extract_keywords(self, text: str) -> list[str]:
        """Rueckwaertskompatible Einsprach-Variante.

        Fuer aeltere Aufrufer liefern wir eine gemergte Liste aus primaeren
        und (falls konfiguriert) sekundaeren Keywords zurueck.
        """
        primary, secondary = self._extract_keywords_multi(text)
        merged: list[str] = []
        for kw in primary + secondary:
            if kw and kw not in merged:
                merged.append(kw)
        return merged

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

        extra_answer_hint = str(self._pref_value('answer_style_hint', '') or '').strip()
        hint_line = "" if not extra_answer_hint else (
            "Zusaetzlicher Stil-/Inhalts-Hinweis des Benutzers fuer die Antwort:\n"
            f"{extra_answer_hint}\n\n"
        )

        prompt = (
            "Du bist ein Recherche-Assistent fuer eine Calibre-Bibliothek.\n"
            "Nutze ausschliesslich den Kontext unten, antworte in sachlichem Deutsch\n"
            "und verweise auf Quellen als [Nr] mit ISBN.\n"
            "Wenn fuer ein Buch keine ISBN im Kontext steht, schreibe 'ISBN: unbekannt',\n"
            "aber mache daraus keine eigenen offenen Punkte.\n"
            "Trenne klar zwischen Wissen aus den Treffern und allgemeinem Hintergrundwissen,\n"
            "das du nur sparsam und deutlich gekennzeichnet einsetzen sollst.\n\n"
            f"{hint_line}"
            f"FRAGE:\n{question}\n\n"
            f"KONTEXT AUS DER BIBLIOTHEK:\n{context_block}\n\n"
            "Strukturiere deine Antwort in genau drei Teilen:\n"
            "### (1) Kurze Zusammenfassung\n"
            "- Eine kompakte, 3–5 Saetze lange Einfuehrung, was die Quellen zur Frage aussagen.\n\n"
            "### (2) Relevante Buecher mit Kurznotizen\n"
            "- Liste die wichtigsten Quellen als Aufzaehlung mit Titel und sehr kurzer Einordnung.\n"
            "- Verweise dabei immer mit [Nr] und ISBN, wenn verfuegbar.\n\n"
            "### (3) Ausfuehrliche Beantwortung der Frage\n"
            "- Gib hier die eigentliche, zusammenhaengende Antwort auf die Nutzerfrage.\n"
            "- Erklaere Fachbegriffe, ordne Technologien ein und nenne typische Beispiele.\n"
            "- Verweise an passenden Stellen auf Quellen (z. B. [1], [3]).\n"
            "- Nenne hier keine organisatorischen offenen Punkte (z. B. fehlende ISBNs\n"
            "  oder weitere Rechercheschritte), sondern fokussiere dich auf die fachliche Antwort.\n"
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

    def _refine_search_queries(
        self,
        original_question: str,
        effective_question: str,
        previous_queries: List[str],
        hits: List[SearchHit],
    ) -> List[str]:
        """Nutze den LLM, um auf Basis bisheriger Ergebnisse bessere FT-Queries zu erzeugen."""
        # Kontextblock fuer den LLM bauen
        lines: List[str] = []
        lines.append("Frage des Nutzers:")
        lines.append(original_question)
        lines.append("")

        if self._last_question and self.context_influence > 0:
            lines.append("Vorherige Frage im Dialog:")
            lines.append(self._last_question)
            lines.append("")

        lines.append("Bisher verwendete Volltext-Suchabfragen:")
        for q in previous_queries:
            lines.append(f"- {q!r}")
        lines.append("")

        if hits:
            lines.append("Ausschnitt der bisherigen Treffer (Titel + Snippets):")
            for h in hits[:3]:
                lines.append(f"* {h.title or 'Unbekannt'} (ISBN: {h.isbn or 'Unbekannt'})")
                lines.append(f"  Snippet: {self._trim_text(h.snippet)}")
            lines.append("")

        instruction = (
            "Auf Basis der obigen Information:\n"
            "- Formuliere bis zu drei neue, alternative Suchabfragen fuer eine Volltextsuche "
            "in einer technischen Fachbibliothek.\n"
            "- Nutze vor allem zentrale Fachbegriffe aus der Fahrzeugtechnik und Bussystemen, "
            "z. B. bekannte Protokolle oder Abkuerzungen (CAN, LIN, FlexRay, MOST etc.).\n"
            "- Die Queries muessen in der Calibre-Suchsprache mit einfachen Begriffen, AND/OR "
            "oder Begriffskombinationen stehen (z. B. 'lin AND fahrzeugbus' oder 'local interconnect network').\n"
            "- Gib jede Suchabfrage in einer eigenen Zeile aus, ohne Erklaertext."
        )

        prompt = "\n".join(lines) + "\n" + instruction

        try:
            llm_response = self.chat_client.send_chat(prompt)
            new_queries = self._extract_queries(llm_response)
        except Exception as exc:
            log.warning("LLM-Refinement fehlgeschlagen: %s", exc)
            return []

        # Doppelte und identische Queries herausfiltern
        filtered: List[str] = []
        prev_set = set(previous_queries)
        for q in new_queries:
            if q in prev_set:
                continue
            if q not in filtered:
                filtered.append(q)

        return filtered[: self.max_query_variants]
