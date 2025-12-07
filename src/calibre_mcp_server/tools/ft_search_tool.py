from typing import List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..core.models import FulltextHit
from ..core.plugin_registry import PluginRegistry


class FulltextSearchInput(BaseModel):
    query: str = Field(..., description="Full-text query string for Calibre.")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of hits.")


class FulltextSearchHit(BaseModel):
    book_id: int
    title: str
    isbn: Optional[str]
    snippet: str


class FulltextSearchOutput(BaseModel):
    hits: List[FulltextSearchHit]


def _map_hit(hit: FulltextHit) -> FulltextSearchHit:
    """Map domain FulltextHit to MCP schema."""
    return FulltextSearchHit(
        book_id=hit.book_id,
        title=hit.title,
        isbn=hit.isbn,
        snippet=hit.snippet,
    )


def register_ft_search_tool(mcp: FastMCP, registry: PluginRegistry) -> None:
    """Register the fulltext search MCP tool."""

    @mcp.tool()
    def calibre_fulltext_search(input: FulltextSearchInput) -> FulltextSearchOutput:
        """Search Calibre full-text index for a query and return matching snippets."""
        try:
            raw_hits: List[FulltextHit] = registry.service.fulltext_search(
                query=input.query,
                limit=input.limit,
            )
            processed_hits = registry.apply_fulltext_plugins(raw_hits)
        except Exception as exc:  # pylint: disable=broad-except
            # Raise generic error so MCP client sees a tool error without
            # depending on fastmcp internals.
            raise RuntimeError(
                f"Full-text search failed: {type(exc).__name__}"
            ) from exc

        return FulltextSearchOutput(
            hits=[_map_hit(hit) for hit in processed_hits]
        )
