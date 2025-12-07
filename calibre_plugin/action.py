import os
import subprocess

from calibre.gui2.actions import InterfaceAction
from qt.core import QIcon


class McpInterfaceAction(InterfaceAction):
    """Add a toolbar / menu action to start and stop the MCP server.

    The action simply spawns the calibre_mcp_server.main module as an
    external Python process. It passes the path of the currently open
    Calibre library via CALIBRE_LIBRARY_PATH so the server knows which
    metadata.db to use.
    """

    name = "Calibre MCP Server"

    # (Text, Icon, Tooltip, Shortcut)
    action_spec = (
        "MCP Server",
        None,
        "Start or stop the MCP research server for this library",
        None,
    )

    def genesis(self):
        """Initialize action and wire up click handler."""
        self._process = None

        # Try to load a plugin icon if available. Ignore errors to keep
        # the plugin robust when no icon resource is shipped.
        try:
            from calibre.gui2 import I

            icon = QIcon(I("plugins/mcp_server.png"))
            self.qaction.setIcon(icon)
        except Exception:
            pass

        self.qaction.triggered.connect(self.toggle_server)

    def toggle_server(self):
        """Start server if not running, otherwise stop it."""
        if self._process is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        """Spawn the MCP server as an external process.

        This implementation assumes that the Python environment where
        Calibre runs has the calibre_mcp_server package and its
        dependencies installed (for example via `pip install -e .`).
        """
        library_path = self.gui.current_db.library_path

        env = os.environ.copy()
        env["CALIBRE_LIBRARY_PATH"] = library_path

        # Use system Python. Adjust this if a specific interpreter is
        # required on the target machine.
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

    def shutting_down(self):
        """Ensure the server is stopped when Calibre exits."""
        self.stop_server()
