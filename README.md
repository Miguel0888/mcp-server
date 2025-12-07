# calibre-mcp-server

MCP server for Calibre full-text research and excerpts.

- Provides tools for full-text search over a Calibre library.
- Returns short excerpts for books, addressed by ISBN.
- Includes a simple plugin registry so other components can post-process hits and excerpts.

The core service layer is designed so it can later be moved into a Calibre fork alongside the existing content server.
