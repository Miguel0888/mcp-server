from typing import List, Optional

from .models import FulltextHit, Excerpt
from ..infra.metadata_sqlite import MetadataRepository


class LibraryResearchService(object):
    """Provide high-level research operations on a Calibre library.

    This implementation uses Calibre's metadata.db through a small
    repository wrapper. Later it can be extended to use the dedicated
    full-text-search.db index and real EPUB content extraction.
    """

    def __init__(self, calibre_root_path: str):
        self._root = calibre_root_path
        self._metadata_repo = MetadataRepository(calibre_root_path)

    def fulltext_search(self, query: str, limit: int = 10) -> List[FulltextHit]:
        """Search the Calibre library using metadata.db.

        Delegate to MetadataRepository.search_fulltext, which uses simple
        LIKE matching over title, ISBN and comments. This can later be
        replaced with a more advanced implementation without changing the
        MCP tools or their callers.
        """
        return self._metadata_repo.search_fulltext(query=query, limit=limit)

    def get_excerpt_by_isbn(
        self,
        isbn: str,
        around_text: Optional[str] = None,
        max_chars: int = 1500,
    ) -> Optional[Excerpt]:
        """Return a simple excerpt based on comments in metadata.db.

        This method resolves the ISBN via metadata.db and returns an
        excerpt derived from the comments field. It is intentionally
        simple and will later be replaced by real EPUB content access.
        """
        row = self._metadata_repo.get_book_by_isbn(isbn)
        if row is None:
            return None

        book_id, title, resolved_isbn, comments = row
        text_source = comments or title or ""
        if not text_source:
            return None

        cleaned = text_source.strip()

        if around_text:
            # Try to focus the excerpt around the given fragment.
            lower_text = cleaned.lower()
            lower_fragment = around_text.lower()
            idx = lower_text.find(lower_fragment)
            if idx >= 0:
                start = max(idx - max_chars // 2, 0)
                end = start + max_chars
                excerpt_text = cleaned[start:end]
            else:
                excerpt_text = cleaned[:max_chars]
        else:
            excerpt_text = cleaned[:max_chars]

        return Excerpt(
            book_id=book_id,
            title=title,
            isbn=resolved_isbn,
            text=excerpt_text,
            source_hint="metadata.comments",
        )
