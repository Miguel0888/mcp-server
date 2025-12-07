import os
import sqlite3
from typing import List, Optional, Tuple

from ..core.models import FulltextHit


class MetadataRepository(object):
    """Access Calibre's metadata.db using SQLite.

    This repository focuses on read-only operations that are needed
    for research: basic search and looking up books by ISBN.
    """

    def __init__(self, library_root: str):
        self._db_path = os.path.join(library_root, "metadata.db")

    def _connect(self) -> sqlite3.Connection:
        """Open a new read-only SQLite connection to metadata.db."""
        # Use URI mode to enforce read-only access.
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def search_fulltext(self, query: str, limit: int) -> List[FulltextHit]:
        """Search in title, ISBN and comments using simple LIKE matching.

        This is a pragmatic first step before wiring up Calibre's dedicated
        full-text-search.db index. It already returns real data from the
        library and can later be swapped out without changing callers.
        """
        pattern = f"%{query}%"
        hits: List[FulltextHit] = []

        sql = """
        SELECT
            b.id AS book_id,
            b.title AS title,
            b.isbn AS isbn,
            COALESCE(c.text, '') AS comments
        FROM books b
        LEFT JOIN comments c ON c.book = b.id
        WHERE
            lower(b.title) LIKE lower(?)
            OR lower(COALESCE(b.isbn, '')) LIKE lower(?)
            OR lower(COALESCE(c.text, '')) LIKE lower(?)
        ORDER BY b.id
        LIMIT ?
        """

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, (pattern, pattern, pattern, limit))
            rows = cur.fetchall()

        for row in rows:
            comments = row["comments"] or ""
            snippet = self._build_snippet(comments, query)
            if not snippet:
                # Fall back to title if there is no useful comment text.
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

    def get_book_by_isbn(self, isbn: str) -> Optional[Tuple[int, str, Optional[str], str]]:
        """Look up a single book by ISBN and return its metadata plus comments."""
        sql = """
        SELECT
            b.id AS book_id,
            b.title AS title,
            b.isbn AS isbn,
            COALESCE(c.text, '') AS comments
        FROM books b
        LEFT JOIN comments c ON c.book = b.id
        WHERE b.isbn = ?
        LIMIT 1
        """

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, (isbn,))
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
