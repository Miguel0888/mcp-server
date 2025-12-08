import sys
from pathlib import Path

import asyncio
import threading
from typing import Optional


def _install_site_packages() -> None:
    """
    Ensure that the bundled 'site-packages' directory is on sys.path.

    This must work in two Szenarien:
    - Entwicklermodus (Plugin als normaler Ordner):  <plugin_dir>/site-packages
    - Calibre-Plugin als ZIP:  <plugin.zip>/site-packages  (zip-subdir Pfad)
    """
    plugin_file = Path(__file__).resolve()
    plugin_str = str(plugin_file)

    candidate_paths = []

    # 1) ZIP-Plugin-Fall: .../mcp_server_recherche.zip/...
    if ".zip" in plugin_str:
        zip_prefix, _, _ = plugin_str.partition(".zip")
        zip_path = zip_prefix + ".zip"
        # zip-subdir Pfad: <zip>.zip/site-packages
        candidate_paths.append(zip_path + "/site-packages")

    # 2) Normaler Ordner-Fall: <plugin_dir>/site-packages
    plugin_dir = plugin_file.parent
    candidate_paths.append(str(plugin_dir / "site-packages"))

    for p in candidate_paths:
        if p and p not in sys.path:
            sys.path.insert(0, p)


_install_site_packages()


class MCPServerThread(threading.Thread):
    def __init__(self, host: str, port: int, library_path: str):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.library_path = library_path
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server = None
        self.started_event = threading.Event()
        self._shutdown_event: Optional[asyncio.Event] = None
        self._is_running = False
        self.last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def run(self) -> None:
        try:
            from calibre_mcp_server.config_loader import ServerConfig
            from calibre_mcp_server.websocket_server import MCPWebSocketServer
        except ModuleNotFoundError as exc:  # pylint: disable=broad-except
            missing = exc.name or 'unbekannt'
            # This is what you currently siehst in der UI:
            self.last_error = (
                f"Abhaengigkeit '{missing}' fehlt. Bitte websockets/fastmcp in das Plugin "
                "bundle oder in Calibre installieren."
            )
            self.started_event.set()
            return
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.started_event.set()
            return

        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            cfg = ServerConfig(
                server_host=self.host,
                server_port=self.port,
                calibre_library_path=self.library_path,
            )
            self.server = MCPWebSocketServer(cfg)
            self._shutdown_event = asyncio.Event()
            self.loop.run_until_complete(self._run_server())
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.started_event.set()
        finally:
            self._is_running = False
            try:
                if self.loop and self.loop.is_running():
                    self.loop.stop()
            except Exception:
                pass
            if self.loop:
                self.loop.close()

    async def _run_server(self) -> None:
        assert self.server is not None
        assert self._shutdown_event is not None
        await self.server.start()
        self._is_running = True
        self.started_event.set()
        try:
            await self._shutdown_event.wait()
        finally:
            await self.server.stop()

    def wait_until_started(self, timeout: float = 3.0) -> bool:
        started = self.started_event.wait(timeout)
        return started and self._is_running and not self.last_error

    def stop(self) -> None:
        self._is_running = False
        if self.loop and self._shutdown_event:
            self.loop.call_soon_threadsafe(self._shutdown_event.set)
        self.join(timeout=2)
