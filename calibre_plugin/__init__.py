# __init__.py
import os
import subprocess

from calibre.customize import InterfaceActionBase
from calibre.gui2 import I
from qt.core import QIcon


class CalibreMcpServerPlugin(InterfaceActionBase):
    name = "Calibre MCP Server"
    description = "Start/stop MCP research server for the current Calibre library."
    supported_platforms = ["windows", "osx", "linux"]
    author = "Miguel"
    version = (0, 0, 2)
    minimum_calibre_version = (6, 0, 0)

    def genesis(self):
        """Create toolbar/menu action and wire up click handler."""
        # Try to load an icon from the plugin resources, but do not fail if absent.
        icon = None
        try:
            icon = QIcon(I("plugins/mcp_server.png"))
        except Exception:
            icon = None

        self._process = None

        # (Text, Icon, Tooltip, Shortcut)
        self.qaction = self.create_action(
            spec=("MCP Server", icon, "Start/stop MCP research server", None),
            callback=self.toggle_server,
        )

    def toggle_server(self, *args):
        """Start server if not running, otherwise stop it."""
        if self._process is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        """Spawn the MCP server as an external process."""
        library_path = self.gui.current_db.library_path
        env = os.environ.copy()
        env["CALIBRE_LIBRARY_PATH"] = library_path

        # NOTE: Use the python that has calibre_mcp_server installiert
        cmd = ["python", "-m", "calibre_mcp_server.main"]

        try:
            self._process = subprocess.Popen(cmd, env=env)
            self.gui.status_bar.showMessage(
                "MCP server started for library: %s" % library_path, 5000
            )
        except Exception as exc:
            self.gui.status_bar.showMessage(
                "Failed to start MCP server: %s" % exc, 8000
            )
            self._process = None

    def stop_server(self):
        """Terminate the external MCP server process."""
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self.gui.status_bar.showMessage("MCP server stopped", 5000)

    def shutdown(self):
        """Ensure the server is stopped when Calibre exits."""
        self.stop_server()
