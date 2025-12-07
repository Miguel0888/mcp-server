"""
Manual connectivity test for the Calibre MCP Server WebSocket transport.

1. Check raw TCP connectivity to the given host:port.
2. Optionally perform a WebSocket handshake using the 'websockets' package.

Use this script while the Calibre MCP server is running
(e.g. via the Calibre GUI plugin or `python -m calibre_mcp_server.main`).
"""

import asyncio
import socket
from urllib.parse import urlparse

try:
    import websockets  # type: ignore
except ImportError:
    websockets = None  # type: ignore[assignment]

WEBSOCKET_URL = "ws://127.0.0.1:8765"
CONNECT_TIMEOUT_SECONDS = 3.0


def test_tcp_connectivity(url: str) -> bool:
    """Check whether a TCP connection to the WebSocket host:port is possible."""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"

    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "wss":
        port = 443
    else:
        port = 80

    print("=== TCP connectivity check ===")
    print("Target host:", host)
    print("Target port:", port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT_SECONDS)

    try:
        sock.connect((host, port))
    except OSError as exc:
        print()
        print("TCP connect failed:", repr(exc))
        print()
        print("Most likely causes:")
        print(" - MCP server process is not running")
        print(" - MCP server is listening on a different host or port")
        print(" - Local firewall or security tool blocks the connection")
        return False
    else:
        print("TCP connect successful – port is open.")
        return True
    finally:
        try:
            sock.close()
        except OSError:
            # Ignore errors while closing the socket
            pass


async def test_websocket_handshake(url: str) -> None:
    """Try to perform a WebSocket handshake and exchange a small message."""
    if websockets is None:
        print()
        print("WebSocket handshake test skipped:")
        print(" 'websockets' package is not available in this environment.")
        print(" Install it with: python -m pip install websockets")
        return

    print()
    print("=== WebSocket handshake test ===")
    print("Target URL:", url)

    try:
        async with websockets.connect(url) as ws:  # type: ignore[attr-defined]
            print("WebSocket handshake successful.")
            print("Send test message 'ping'...")
            await ws.send("ping")
            reply = await ws.recv()
            print("Received frame from server:", repr(reply))
    except Exception as exc:
        print("WebSocket handshake failed:", repr(exc))
        print()
        print("Possible reasons:")
        print(" - MCP server is not a WebSocket server on this port")
        print(" - TLS/URL mismatch (ws:// vs wss://)")
        print(" - Reverse proxy or middleware closes the connection")


def main() -> None:
    """Run both TCP and optional WebSocket connectivity checks."""
    print("Manual WebSocket connectivity test for Calibre MCP Server")
    print("Target URL:", WEBSOCKET_URL)
    print("=" * 60)

    tcp_ok = test_tcp_connectivity(WEBSOCKET_URL)
    if not tcp_ok:
        # If TCP fails, a WebSocket handshake cannot succeed
        return

    print("=" * 60)
    asyncio.run(test_websocket_handshake(WEBSOCKET_URL))


if __name__ == "__main__":
    main()
