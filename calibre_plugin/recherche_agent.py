from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Tuple, Set

try:
    import websockets
except ImportError as exc:  # pragma: no cover - runtime environment
    websockets = None

from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient

log = logging.getLogger(__name__)


class MCPTransportError(RuntimeError):
    """Raised when the MCP bridge cannot fulfil a request."""


class RechercheAgent(object):
    """Coordinate MCP tools and LLM to answer research questions."""

    def __init__(self, prefs_obj):
        self.prefs = prefs_obj
        self.chat_client = ChatProviderClient(self.prefs)
        self.max_query_variants = 3
        self.max_hits_per_query = 6
        self.max_hits_total = 12
        self.target_sources = 3
        self.max_excerpts = 4
        self.max_excerpt_chars = 1200
        self.context_hit_limit = 8
        self.request_timeout = 15
        # Cache der vom Server gemeldeten Tools (name -> schema)
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}

    def answer_question(self, question):
        """Run planning, tool orchestration, and summarisation."""
        question = (question or "").strip()
        if not question:
            return ""

        log.info("Recherche-Agent gestartet: %s", question)

        try:
            # Sicherstellen, dass die Tool-Liste initialisiert ist
            self._ensure_tools_cached()
            queries = self._plan_search_queries(question)
            hits = self._collect_fulltext_hits(queries)
            if not hits:
                return "System: Keine passenden Treffer im MCP-Server gefunden."
            enriched_hits = self._fetch_excerpts_for_hits(hits)
        except MCPTransportError as exc:
            log.error("MCP-Workflow fehlgeschlagen: %s", exc)
            return f"System: Recherche via MCP fehlgeschlagen: {exc}"

        prompt = self._build_prompt(question, enriched_hits)
        return self.chat_client.send_chat(prompt)

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
        """Ask the LLM to suggest targeted search queries."""
        planning_prompt = (
            "Du hilfst dabei, Fragen anhand einer Calibre-Bibliothek zu beantworten.\n"
            "Formuliere bis zu drei kurze Suchabfragen (eine pro Zeile).\n"
            "Die erste Abfrage soll der Originalfrage entsprechen, die folgenden beleuchten andere Aspekte.\n\n"
            f"Frage:\n{question}\n\n"
            "Gib nur die Suchabfragen ohne Erklaerungen aus."
        )

        try:
            response = self.chat_client.send_chat(planning_prompt)
            queries = self._extract_queries(response)
        except Exception as exc:  # noqa: BLE001 - fallback to base question
            log.warning("LLM-Query-Planung fehlgeschlagen: %s", exc)
            queries = []

        if not queries:
            queries = [question]
        elif question not in queries:
            queries.insert(0, question)

        return queries[: self.max_query_variants]

    @staticmethod
    def _extract_queries(raw_response: str) -> List[str]:
        queries: List[str] = []
        for line in raw_response.splitlines():
            cleaned = re.sub(r"^[\-•\d\)\s]+", "", line.strip())
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
        return queries

    # ------------------ MCP tool calls ------------------

    def _collect_fulltext_hits(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Run the full-text search for each query and aggregate unique hits."""
        if not self._has_tool("calibre_fulltext_search"):
            raise MCPTransportError("Tool 'calibre_fulltext_search' ist auf dem MCP-Server nicht verfuegbar.")

        aggregated: List[Dict[str, Any]] = []
        seen_ids: Set[Tuple[Any, Any]] = set()

        for query in queries:
            hits = self._run_fulltext_search(query, max_hits=self.max_hits_per_query)
            log.info("Fulltext-Suche %r lieferte %d Treffer", query, len(hits))
            for hit in hits:
                identifier = (hit.get("book_id"), hit.get("isbn"))
                if identifier in seen_ids:
                    continue
                entry = dict(hit)
                entry.setdefault("origin_query", query)
                aggregated.append(entry)
                seen_ids.add(identifier)
                if len(aggregated) >= self.max_hits_total:
                    break
            if len(aggregated) >= self.target_sources:
                break

        return aggregated[: self.max_hits_total]

    def _run_fulltext_search(self, query, max_hits=5):
        # FastMCP erzeugt fuer unsere Tools typischerweise ein Schema mit "input"-Property
        arguments = {"query": query, "limit": max_hits}
        payload = {
            "name": "calibre_fulltext_search",
            "arguments": self._wrap_arguments("calibre_fulltext_search", arguments),
        }
        response = self._call_mcp("call_tool", params=payload, request_id="ft-search")
        result = (response.get("result") or {})
        hits = result.get("hits")
        if hits is None and "content" in result:
            hits = self._extract_hits_from_content(result["content"])
        return hits or []

    def _wrap_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Passe Argument-Struktur an das gemeldete input_schema an.

        Viele FastMCP-Tools verwenden ein Schema der Form
        {"properties": {"input": {"$ref": ...}}, "required": ["input"]}.
        In diesem Fall muessen wir unsere arguments unter "input" schachteln.
        """
        schema_entry = self._tool_schemas.get(tool_name) or {}
        input_schema = schema_entry.get("input_schema") or {}
        props = input_schema.get("properties") or {}

        if "input" in props and list(props.keys()) == ["input"]:
            return {"input": arguments}
        return arguments

    def _extract_hits_from_content(self, content: Any) -> List[Dict[str, Any]]:
        """Best-effort extraction of hits from FastMCP-style content blocks."""
        if not content:
            return []

        hits: List[Dict[str, Any]] = []
        for block in content:
            # Expect something like {"type": "object", "value": {...}}
            value = None
            if isinstance(block, dict):
                # direct hits-list
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

    def _fetch_excerpts_for_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._has_tool("calibre_get_excerpt"):
            # Ohne Excerpt-Tool liefern wir nur Snippets, keine harte Fehlermeldung
            return list(hits)

        enriched: List[Dict[str, Any]] = []
        excerpt_count = 0
        for hit in hits:
            entry = dict(hit)
            isbn = entry.get("isbn") or entry.get("book_id")
            if isbn and excerpt_count < self.max_excerpts:
                try:
                    excerpt_payload = self._call_excerpt_tool(isbn)
                except MCPTransportError as exc:
                    log.warning("Excerpt-Tool fehlgeschlagen fuer ISBN %s: %s", isbn, exc)
                else:
                    entry["excerpt"] = (
                        excerpt_payload.get("text")
                        or excerpt_payload.get("excerpt")
                        or ""
                    )
                    entry["excerpt_source"] = excerpt_payload.get("source_hint")
                    excerpt_count += 1
            enriched.append(entry)
        return enriched

    def _call_excerpt_tool(self, isbn: str) -> Dict[str, Any]:
        arguments = {
            "isbn": isbn,
            "max_chars": self.max_excerpt_chars,
        }
        payload = {
            "name": "calibre_get_excerpt",
            "arguments": self._wrap_arguments("calibre_get_excerpt", arguments),
        }
        response = self._call_mcp("call_tool", params=payload, request_id=f"excerpt-{isbn}")
        result = response.get("result")
        if not result:
            raise MCPTransportError("Excerpt-Tool lieferte kein Ergebnis")
        return result

    # ------------------ Low-level MCP/WebSocket transport ------------------

    def _call_mcp(self, method: str, params: Dict[str, Any], request_id: str | None = None) -> Dict[str, Any]:
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

        async def _do_call() -> Dict[str, Any]:
            data = json.dumps(payload)
            try:
                async with websockets.connect(url) as websocket:
                    await websocket.send(data)
                    raw = await websocket.recv()
            except Exception as exc:  # noqa: BLE001
                raise MCPTransportError(f"Verbindung zum MCP-Server fehlgeschlagen: {exc}") from exc

            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise MCPTransportError(
                    "Antwort des MCP-Servers konnte nicht gelesen werden"
                ) from exc

        try:
            response = asyncio.run(_do_call())
        except RuntimeError as exc:
            # Falls bereits ein Eventloop laeuft (z. B. in manchen Qt-Konstellationen)
            log.error("Async-Call im laufenden Eventloop fehlgeschlagen: %s", exc)
            raise MCPTransportError(
                "Konnte keine WebSocket-Verbindung zum MCP-Server herstellen (Eventloop-Konflikt)."
            ) from exc

        if "error" in response:
            message = response["error"].get("message", "Unbekannter MCP-Fehler")
            raise MCPTransportError(message)
        return response

    def _tool_endpoint(self) -> str:
        host, port = self._server_config()
        # WebSocket-URL; Server lauscht auf ws://host:port
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
            except Exception:  # noqa: BLE001 - prefs may not implement __getitem__
                value = default
        return value if value not in (None, "") else default

    # ------------------ Prompt construction ------------------

    def _build_prompt(self, question: str, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            context_block = "Keine passenden Treffer gefunden."
        else:
            lines: List[str] = ["Suchtreffer und Auszuege:"]
            for idx, hit in enumerate(hits[: self.context_hit_limit], start=1):
                title = hit.get("title") or "Unbekannter Titel"
                isbn = hit.get("isbn") or "Unbekannt"
                lines.append(f"[{idx}] {title} (ISBN: {isbn})")
                snippet = self._trim_text(hit.get("snippet"))
                if snippet:
                    lines.append(f"Snippet: {snippet}")
                excerpt = self._trim_text(hit.get("excerpt"))
                if excerpt:
                    lines.append(f"Excerpt: {excerpt}")
                origin = hit.get("origin_query")
                if origin:
                    lines.append(f"Suchbegriff: {origin}")
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

    @staticmethod
    def _trim_text(text: Any, limit: int = 600) -> str:
        if not text:
            return ""
        cleaned = str(text).strip().replace("\n", " ")
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

