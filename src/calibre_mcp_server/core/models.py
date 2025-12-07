from dataclasses import dataclass
from typing import Optional


@dataclass
class FulltextHit(object):
    """Represent a single full-text search hit."""

    book_id: int
    title: str
    isbn: Optional[str]
    snippet: str


@dataclass
class Excerpt(object):
    """Represent a textual excerpt from a book."""

    book_id: int
    title: str
    isbn: Optional[str]
    text: str
    source_hint: Optional[str]
