import sys
import asyncio
import threading
from pathlib import Path
from typing import Optional
import pkgutil


def _bootstrap_site_packages() -> None:
    """Ensure that bundled site-packages are importable in dev and ZIP mode."""
    plugin_file = Path(__file__).resolve()
    plugin_dir = plugin_file.parent

    # 1) Dev/entpacktes Plugin: <plugin_dir>/site-packages als echter Ordner
    site_dir = plugin_dir / "site-packages"
    if site_dir.is_dir():
        site_str = str(site_dir)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)
        return

    # 2) ZIP-Plugin: __file__ zeigt auf ...mcp_server_recherche.zip/...
    #    Hier hilft entweder der Loader (archive) oder ein String-Split auf ".zip".
    zip_path = None

    loader = pkgutil.get_loader(__name__)
    archive = getattr(loader, "archive", None)
    if archive and archive.lower().endswith(".zip"):
        zip_path = archive
    else:
        file_str = str(plugin_file)
        if ".zip" in file_str:
            zip_path = file_str.split(".zip", 1)[0] + ".zip"

    if zip_path:
        zip_site = zip_path + "/site-packages"
        if zip_site not in sys.path:
            # Do not check os.path.exists here – this is a logical ZIP-subdir path
            sys.path.insert(0, zip_site)


_bootstrap_site_packages()


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
            missing = exc.name or "unbekannt"
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
