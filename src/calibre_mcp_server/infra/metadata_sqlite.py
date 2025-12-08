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

    def search_fulltext(self, query: str, limit: int) -> List[FulltextHit]:
        """Search in title, ISBN and comments using simple LIKE matching.

        Diese Implementierung unterstuetzt auch Mehrwort-Queries.
        Die Query wird in simple Tokens zerlegt (Whitespace-Separation),
        die dann je nach Operator (AND/OR) in mehrere LIKE-Bedingungen
        uebersetzt werden. So koennen Anfragen wie "fahrzeug bussysteme"
        oder "fahrzeug, bussysteme" sinnvoll aufgelöst werden, ohne einen
        vollstaendigen boolschen Parser zu benoetigen.
        """
        raw = (query or "").strip()
        if not raw:
            return []

        # Tokens sehr defensiv extrahieren: Whitespace + Kommata als Trenner
        import re

        tokens = [t for t in re.split(r"[\s,;]+", raw) if t]
        if not tokens:
            tokens = [raw]

        # Aktuell besteht nur eine einfache AND-Semantik: alle Token muessen
        # irgendwo in Titel/ISBN/Kommentar vorkommen. Das kann spaeter ueber
        # Konfiguration erweitert werden.
        operator = "AND"

        hits: List[FulltextHit] = []

        base_clause = "(" + " OR ".join(
            [
                "lower(b.title) LIKE lower(?)",
                "lower(COALESCE(b.isbn, '')) LIKE lower(?)",
                "lower(COALESCE(c.text, '')) LIKE lower(?)",
            ]
        ) + ")"

        if operator == "AND":
            where_clauses = [base_clause for _ in tokens]
            where_sql = " AND ".join(where_clauses)
        else:  # OR-Fallback, falls spaeter verwendet
            where_sql = base_clause
            tokens = [" ".join(tokens)]

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

        params = []
        for tok in tokens:
            pattern = f"%{tok}%"
            params.extend([pattern, pattern, pattern])
        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

        for row in rows:
            comments = row["comments"] or ""
            # Snippet weiterhin auf der Original-Query basieren lassen
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
