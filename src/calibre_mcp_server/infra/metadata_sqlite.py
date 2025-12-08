import os
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from ..core.models import FulltextHit


class MetadataRepository(object):
    """Access Calibre's metadata.db using SQLite.

    This repository focuses on read-only operations that are needed
    for research: basic search and looking up books by ISBN.
    """

    def __init__(self, library_root: str):
        self._root = library_root
        self._db_path = os.path.join(library_root, "metadata.db")

    def _connect(self) -> sqlite3.Connection:
        """Open a new read-only SQLite connection to metadata.db."""
        db_file = Path(self._db_path)
        if not db_file.exists():
            raise FileNotFoundError(
                f"metadata.db wurde nicht gefunden unter: {db_file}. "
                "Bitte CALIBRE_LIBRARY_PATH korrekt setzen."
            )
        # Use URI mode to enforce read-only access.
        uri = f"file:{self._db_path}?mode=ro"
        try:
            return sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as exc:  # pragma: no cover
            raise RuntimeError(
                f"metadata.db konnte nicht geoeffnet werden ({db_file}): {exc}"
            ) from exc

    def _parse_boolean_query(self, raw: str) -> List[List[str]]:
        """Parse a simple boolean query string into OR-of-AND keyword groups.

        Beispiel:
        - "fahrzeug AND bussysteme" -> [["fahrzeug", "bussysteme"]]
        - "fahrzeug AND bussysteme OR ethernet" -> [["fahrzeug", "bussysteme"], ["ethernet"]]

        Unterstuetzt nur die Operatoren AND/OR (case-insensitive) ohne Klammern
        und NOT. Alles andere wird als normales Suchwort behandelt.
        """
        import re

        raw = (raw or "").strip()
        if not raw:
            return []

        # Tokenize: Worte und Operatoren AND/OR
        # Wir splitten zunaechst auf Whitespace/Komma/Semikolon und behandeln
        # dann explizit 'and'/'or' als Operatoren.
        rough_tokens = [t for t in re.split(r"[\s,;]+", raw) if t]
        tokens: List[str] = []
        for tok in rough_tokens:
            if tok.upper() in ("AND", "OR"):
                tokens.append(tok.upper())
            else:
                tokens.append(tok)

        if not tokens:
            return []

        groups: List[List[str]] = [[]]
        current = groups[0]
        last_op = "AND"

        for tok in tokens:
            if tok == "AND":
                last_op = "AND"
                continue
            if tok == "OR":
                last_op = "OR"
                continue

            # Normales Suchwort
            if last_op == "OR" and current:
                # Neue OR-Gruppe beginnen
                current = [tok]
                groups.append(current)
            else:  # AND oder Start
                current.append(tok)
            last_op = "AND"

        # Leere Gruppen entfernen
        groups = [g for g in groups if g]
        return groups

    def search_fulltext(self, query: str, limit: int) -> List[FulltextHit]:
        """Search in title, ISBN and comments using simple LIKE matching.

        Unterstuetzt eine kleine Teilmenge der Calibre-FT-Sprache:
        - Mehrere Suchbegriffe
        - Operatoren AND / OR (case-insensitive), ohne Klammern/NOT

        Beispiele:
        - "fahrzeug AND bussysteme"
        - "fahrzeug OR auto"
        - "fahrzeug bussysteme" (enthaelt implizites AND ueber alle Worte)
        """
        raw = (query or "").strip()
        if not raw:
            return []

        groups = self._parse_boolean_query(raw)
        if not groups:
            return []

        hits: List[FulltextHit] = []

        # Einzelne LIKE-Klausel fuer ein Suchwort
        base_clause = "(" + " OR ".join(
            [
                "lower(b.title) LIKE lower(?)",
                "lower(COALESCE(b.isbn, '')) LIKE lower(?)",
                "lower(COALESCE(c.text, '')) LIKE lower(?)",
            ]
        ) + ")"

        # OR ueber Gruppen, AND ueber Begriffe innerhalb einer Gruppe
        or_clauses = []
        params: List[str] = []

        for group in groups:
            # implizites AND ueber alle Begriffe in der Gruppe
            and_clauses = [base_clause for _ in group]
            or_clauses.append("(" + " AND ".join(and_clauses) + ")")
            for term in group:
                pattern = f"%{term}%"
                params.extend([pattern, pattern, pattern])

        where_sql = " OR ".join(or_clauses)

        sql = f"""
        SELECT
            b.id AS book_id,
            b.title AS title,
            b.isbn AS isbn,
            COALESCE(c.text, '') AS comments
        FROM books b
        LEFT JOIN comments c ON c.book = b.id
        WHERE
            {where_sql}
        ORDER BY b.id
        LIMIT ?
        """

        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        for row in rows:
            comments = row["comments"] or ""
            snippet = self._build_snippet(comments, raw)
            if not snippet:
                snippet = row["title"] or ""

            hits.append(
                FulltextHit(
                    book_id=row["book_id"],
                    title=row["title"],
                    isbn=row["isbn"],
                    snippet=snippet,
                )
            )

        return hits

    from typing import List, Optional, Tuple
    # ... Rest der Importe bleibt

    def get_book_by_isbn(self, isbn: str) -> Optional[Tuple[int, str, Optional[str], str]]:
        """Look up a single book by ISBN and return its metadata plus comments.

        The lookup tries both books.isbn and the identifiers table. This is
        necessary because Calibre often stores ISBNs only in identifiers.
        """
        # Normalize requested ISBN: keep digits and 'X' only
        normalized_chars = []
        for ch in isbn:
            if ch.isdigit() or ch.upper() == "X":
                normalized_chars.append(ch)
        normalized = "".join(normalized_chars)

        if not normalized:
            return None

        # 1) Try identifiers table (isbn / isbn13) – das ist in deiner DB der Fall
        sql_ident = """
            SELECT
                b.id AS book_id,
                b.title AS title,
                COALESCE(b.isbn, i.val) AS isbn,
                COALESCE(c.text, '') AS comments
            FROM books b
            JOIN identifiers i ON i.book = b.id
            LEFT JOIN comments c ON c.book = b.id
            WHERE
                lower(i.type) IN ('isbn', 'isbn13')
                AND REPLACE(REPLACE(i.val, '-', ''), ' ', '') = ?
            LIMIT 1
            """

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql_ident, (normalized,))
            row = cur.fetchone()

            if row is not None:
                return (
                    row["book_id"],
                    row["title"],
                    row["isbn"],
                    row["comments"],
                )

            # 2) Fallback: direct match on books.isbn (für andere Bücher)
            sql_books = """
                SELECT
                    b.id AS book_id,
                    b.title AS title,
                    b.isbn AS isbn,
                    COALESCE(c.text, '') AS comments
                FROM books b
                LEFT JOIN comments c ON c.book = b.id
                WHERE REPLACE(REPLACE(COALESCE(b.isbn, ''), '-', ''), ' ', '') = ?
                LIMIT 1
                """
            cur.execute(sql_books, (normalized,))
            row = cur.fetchone()

        if row is None:
            return None

        return (
            row["book_id"],
            row["title"],
            row["isbn"],
            row["comments"],
        )

    @staticmethod
    def _build_snippet(text: str, query: str, window: int = 200) -> str:
        """Build a small snippet around the first occurrence of query.

        If the query is not found, return the first window characters.
        """
        cleaned = text.strip()
        if not cleaned:
            return ""

        lower_text = cleaned.lower()
        lower_query = query.lower()
        idx = lower_text.find(lower_query)
        if idx < 0:
            return cleaned[:window]

        start = max(idx - window // 2, 0)
        end = start + window
        return cleaned[start:end]
