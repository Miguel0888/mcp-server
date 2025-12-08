import asyncio
import threading
from typing import Optional

from calibre_mcp_server.config_loader import ServerConfig
from calibre_mcp_server.websocket_server import MCPWebSocketServer


class MCPServerThread(threading.Thread):
    def __init__(self, host: str, port: int, library_path: str):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.library_path = library_path
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server: Optional[MCPWebSocketServer] = None
        self.started_event = threading.Event()
        self._is_running = False
        self.last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def run(self) -> None:
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            cfg = ServerConfig(
                server_host=self.host,
                server_port=self.port,
                calibre_library_path=self.library_path,
            )
            self.server = MCPWebSocketServer(cfg)
            self._is_running = True
            self.started_event.set()
            self.loop.run_until_complete(self._run())
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.started_event.set()
        finally:
            self._is_running = False
            if self.loop:
                self.loop.close()

    async def _run(self) -> None:
        assert self.server is not None
        await self.server.start()
        try:
            await asyncio.Future()
        finally:
            await self.server.stop()

    def wait_until_started(self, timeout: float = 3.0) -> bool:
        return self.started_event.wait(timeout) and self._is_running

    def stop(self) -> None:
        self._is_running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)


