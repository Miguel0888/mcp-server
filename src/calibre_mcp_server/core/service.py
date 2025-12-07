from typing import List, Optional

from .models import FulltextHit, Excerpt


class LibraryResearchService(object):
    """Provide high-level research operations on a Calibre library."""

    def __init__(self, calibre_root_path: str):
        self._root = calibre_root_path
        # Inject infrastructure helpers later (FTS, metadata, EPUB access).

    def fulltext_search(self, query: str, limit: int = 10) -> List[FulltextHit]:
        """Use Calibre full-text index to search for query and return hits.

        Implement this method by querying full-text-search.db and metadata.db.
        """
        raise NotImplementedError("Implement fulltext_search")

    def get_excerpt_by_isbn(
        self,
        isbn: str,
        around_text: Optional[str] = None,
        max_chars: int = 1500,
    ) -> Optional[Excerpt]:
        """Return excerpt for given ISBN, optionally around some text fragment.

        Implement this by resolving ISBN -> book_id, then reading EPUB content.
        """
        raise NotImplementedError("Implement get_excerpt_by_isbn")
