from typing import List, Optional

from .models import FulltextHit, Excerpt


class LibraryResearchService(object):
    """Provide high-level research operations on a Calibre library.

    This implementation currently returns stub data so the MCP wiring
    can be tested. Later it will talk to Calibre's full-text index and
    metadata database.
    """

    def __init__(self, calibre_root_path: str):
        self._root = calibre_root_path
        # Inject infrastructure helpers later (FTS, metadata, EPUB access).

    def fulltext_search(self, query: str, limit: int = 10) -> List[FulltextHit]:
        """Return a couple of stub hits for testing the MCP plumbing.

        This implementation ignores the query and limit parameters and
        returns static example data. Replace this with real full-text
        search against full-text-search.db in the next step.
        """
        hits = []

        # Create one synthetic hit so MCP clients can verify the tool works.
        hits.append(
            FulltextHit(
                book_id=1,
                title="Stub Book",
                isbn="0000000000",
                snippet=(
                    "This is a stub full-text search result for query '%s'. "
                    "Replace it with real data later." % query
                ),
            )
        )

        return hits[:limit]

    def get_excerpt_by_isbn(
        self,
        isbn: str,
        around_text: Optional[str] = None,
        max_chars: int = 1500,
    ) -> Optional[Excerpt]:
        """Return a static excerpt for testing the MCP plumbing.

        This implementation returns a fixed text block regardless of
        the requested ISBN. Later this method will resolve the ISBN to
        a book in the Calibre library and extract real EPUB content.
        """
        dummy_title = "Stub Excerpt Book"

        text = (
            "This is a stub excerpt returned by LibraryResearchService for ISBN %s. "
            "Replace this implementation with real EPUB reading logic. "
            "The optional around_text parameter is currently ignored."
            % isbn
        )

        return Excerpt(
            book_id=1,
            title=dummy_title,
            isbn=isbn,
            text=text[:max_chars],
            source_hint="stub",
        )
