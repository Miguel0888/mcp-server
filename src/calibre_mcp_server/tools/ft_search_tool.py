from typing import List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field
import logging

from ..core.models import FulltextHit
from ..core.plugin_registry import PluginRegistry

logger = logging.getLogger(__name__)


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
        logger.info(
            "FT search request: query=%r limit=%s library=%r",
            input.query,
            input.limit,
            registry.service._root,
        )
        try:
            raw_hits: List[FulltextHit] = registry.service.fulltext_search(
                query=input.query,
                limit=input.limit,
            )
            processed_hits = registry.apply_fulltext_plugins(raw_hits)
        except FileNotFoundError as exc:
            logger.exception("metadata.db missing for library %r", registry.service._root)
            raise RuntimeError(
                f"Full-text search failed: FileNotFoundError: {exc}"
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Full-text search failed for query %r", input.query)
            raise RuntimeError(
                f"Full-text search failed: {type(exc).__name__}: {exc}"
            ) from exc

        return FulltextSearchOutput(
            hits=[_map_hit(hit) for hit in processed_hits]
        )
