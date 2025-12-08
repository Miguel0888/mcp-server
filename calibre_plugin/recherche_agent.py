# recherche_agent.py

import logging
import json
import urllib.request
import urllib.error

from calibre_plugins.mcp_server_recherche.config import prefs
from calibre_plugins.mcp_server_recherche.provider_client import ChatProviderClient

log = logging.getLogger(__name__)


class RechercheAgent(object):
    """Coordinate MCP tools and LLM to answer research questions."""

    def __init__(self, prefs_obj):
        self.prefs = prefs_obj
        self.chat_client = ChatProviderClient(self.prefs)

    def answer_question(self, question):
        """Run search tools and get a final LLM answer."""
        # 1) Run fulltext search
        hits = self._run_fulltext_search(question, max_hits=5)

        # 2) Optionally fetch excerpts for top hits
        excerpts = self._fetch_excerpts_for_hits(hits, max_excerpts=3)

        # 3) Build an enriched prompt
        prompt = self._build_prompt(question, hits, excerpts)

        # 4) Send to LLM
        return self.chat_client.send_chat(prompt)

    # ------------------ MCP tool calls ------------------

    def _run_fulltext_search(self, query, max_hits=5):
        """Call MCP fulltext search tool on the server."""
        try:
            host = self.prefs['server_host'] or '127.0.0.1'
            port = self.prefs['server_port'] or '8765'
            url = 'http://%s:%s/tools/call' % (host, port)

            payload = {
                "id": "ft-search-1",
                "method": "tools.call",
                "params": {
                    "name": "calibre_fulltext_search",
                    "arguments": {"query": query, "limit": max_hits},
                },
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
            response = json.loads(raw)
            # Expecting MCP-like result structure
            result = response.get("result") or {}
            return result.get("hits", [])
        except Exception as exc:
            log.exception("Fulltext search via MCP failed: %s", exc)
            return []

    def _fetch_excerpts_for_hits(self, hits, max_excerpts=3):
        """Optionally call an excerpt tool for a couple of top hits."""
        excerpts = []
        for hit in hits[:max_excerpts]:
            book_id = hit.get("book_id")
            if book_id is None:
                continue
            try:
                excerpt = self._call_excerpt_tool(book_id)
                if excerpt:
                    excerpts.append(
                        {
                            "book_id": book_id,
                            "title": hit.get("title", ""),
                            "excerpt": excerpt,
                        }
                    )
            except Exception:
                log.exception("Excerpt fetch failed for book_id=%s", book_id)
        return excerpts

    def _call_excerpt_tool(self, book_id):
        """Call MCP excerpt tool for a single book."""
        host = self.prefs['server_host'] or '127.0.0.1'
        port = self.prefs['server_port'] or '8765'
        url = 'http://%s:%s/tools/call' % (host, port)

        payload = {
            "id": "excerpt-%s" % book_id,
            "method": "tools.call",
            "params": {
                "name": "calibre_excerpt_by_id",
                "arguments": {"book_id": book_id, "max_chars": 1200},
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        response = json.loads(raw)
        result = response.get("result") or {}
        return result.get("excerpt", "")

    # ------------------ Prompt construction ------------------

    def _build_prompt(self, question, hits, excerpts):
        """Combine user question and MCP search results into one LLM prompt."""
        context_lines = []

        if hits:
            context_lines.append("Suchtreffer aus der Calibre-Bibliothek:")
            for idx, hit in enumerate(hits, start=1):
                context_lines.append(
                    "- [%d] %s (ID=%s)" % (
                        idx,
                        hit.get("title", "Unbekannter Titel"),
                        hit.get("book_id", "?"),
                    )
                )

        if excerpts:
            context_lines.append("")
            context_lines.append("Ausgewaehlte Textauszuege:")
            for ex in excerpts:
                context_lines.append(
                    "Titel: %s (ID=%s)" % (ex.get("title", ""), ex.get("book_id", ""))
                )
                context_lines.append(ex.get("excerpt", "")[:1200])
                context_lines.append("")

        context_block = "\n".join(context_lines) if context_lines else "Keine passenden Treffer gefunden."

        prompt = (
            "Du bist ein Assistent, der Fragen auf Basis einer Calibre-Bibliothek beantwortet.\n"
            "Nutze die folgenden Suchtreffer und Auszuege, um die Frage zu beantworten.\n\n"
            "FRAGE:\n%s\n\n"
            "KONTEXT AUS DER BIBLIOTHEK:\n%s\n\n"
            "Antworte strukturiert und erklaere, wie die Treffer zur Antwort beitragen."
            % (question, context_block)
        )
        return prompt
