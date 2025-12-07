import argparse
import asyncio
from typing import Any, Dict

from fastmcp.client import Client

API_FULLTEXT = "calibre_fulltext_search"
API_EXCERPT = "calibre_get_excerpt"


def build_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


async def run_fulltext(client: Client, query: str, limit: int) -> None:
    arguments = build_payload({"query": query, "limit": limit})
    result = await client.call_tool(API_FULLTEXT, arguments)
    hits = result.data or []
    print("Fulltext hits for query '%s':" % query)
    if not hits:
        print("  (no hits found)")
    else:
        for hit in hits:
            print("  book_id =", hit["book_id"])
            print("  title   =", hit["title"])
            print("  isbn    =", hit["isbn"])
            snippet = hit.get("snippet", "") or ""
            print("  snippet =", snippet[:120].replace("\n", " "))
            print()


async def run_excerpt(client: Client, isbn: str, around_text: str | None, max_chars: int) -> None:
    arguments = build_payload(
        {"isbn": isbn, "around_text": around_text, "max_chars": max_chars}
    )
    result = await client.call_tool(API_EXCERPT, arguments)
    excerpt = result.data
    print()
    print("Excerpt for ISBN %s:" % isbn)
    if not excerpt:
        print("  (no book found or no comments/title to build excerpt)")
    else:
        print("  book_id    =", excerpt.get("book_id"))
        print("  title      =", excerpt.get("title"))
        print("  isbn       =", excerpt.get("isbn"))
        print("  source_hint=", excerpt.get("source_hint"))
        text = excerpt.get("text", "") or ""
        print("  text       =", text[:400])


async def async_main(args: argparse.Namespace) -> None:
    client = Client(args.ws_url)
    async with client:
        await client.list_tools()
        await run_fulltext(client, args.query, args.limit)
        await run_excerpt(client, args.isbn, args.around_text, args.max_chars)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually exercise the Calibre MCP server via WebSocket"
    )
    parser.add_argument(
        "--ws-url",
        default="ws://127.0.0.1:8777",
        help="WebSocket endpoint exposed by calibre MCP server",
    )
    parser.add_argument("--query", default="der", help="Fulltext query")
    parser.add_argument("--limit", type=int, default=5, help="Limit for search results")
    parser.add_argument("--isbn", default="9783446429338", help="ISBN to fetch excerpt for")
    parser.add_argument(
        "--around-text",
        default=None,
        help="Optional fragment to anchor excerpt selection",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=400,
        help="Maximum characters returned for the excerpt",
    )

    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
