from typing import Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..core.models import Excerpt
from ..core.plugin_registry import PluginRegistry


class ExcerptInput(BaseModel):
    isbn: str = Field(..., description="ISBN of the book.")
    around: Optional[str] = Field(
        None,
        description="Optional text fragment that should appear near the excerpt.",
    )
    max_chars: int = Field(
        1500,
        ge=200,
        le=8000,
        description="Maximum length of returned excerpt in characters.",
    )


class ExcerptOutput(BaseModel):
    book_id: int
    title: str
    isbn: Optional[str]
    text: str
    source_hint: Optional[str]


def _map_excerpt(excerpt: Excerpt) -> ExcerptOutput:
    """Map domain Excerpt to MCP schema."""
    return ExcerptOutput(
        book_id=excerpt.book_id,
        title=excerpt.title,
        isbn=excerpt.isbn,
        text=excerpt.text,
        source_hint=excerpt.source_hint,
    )


def register_excerpt_tool(mcp: FastMCP, registry: PluginRegistry) -> None:
    """Register the excerpt retrieval MCP tool."""

    @mcp.tool()
    def calibre_get_excerpt(input: ExcerptInput) -> ExcerptOutput:
        """Return a short excerpt for a book identified by ISBN."""
        try:
            excerpt = registry.service.get_excerpt_by_isbn(
                isbn=input.isbn,
                around_text=input.around,
                max_chars=input.max_chars,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(
                f"Excerpt retrieval failed: {type(exc).__name__}"
            ) from exc

        if excerpt is None:
            raise RuntimeError("No excerpt found for given ISBN")

        processed = registry.apply_excerpt_plugins(excerpt)
        return _map_excerpt(processed)
