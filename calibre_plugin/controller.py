#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

import os
import shlex
import subprocess
import threading

from calibre_plugins.mcp_server.config import prefs


class MCPServerController(object):
    """Control lifecycle of external MCP WebSocket server process."""

    def __init__(self, library_path=None, prefs_obj=prefs):
        # Store preferences and optional library path override
        self.prefs = prefs_obj
        self.library_path = library_path
        self._process = None
        self._lock = threading.Lock()

    @property
    def is_running(self):
        """Return True if server process is alive."""
        return self._process is not None and self._process.poll() is None

    def start(self):
        """Start MCP server if not already running."""
        with self._lock:
            if self.is_running:
                return False

            command = self._parse_command()
            if not command:
                raise RuntimeError('Startkommando fehlt (Plugin-Einstellungen prüfen).')

            # Build environment
            env = os.environ.copy()

            # Calibre library path: prefer explicit setting, fall back to GUI library
            library_path = self.prefs.get('library_path') or self.library_path
            if library_path:
                env['CALIBRE_LIBRARY_PATH'] = library_path

            # Optional API key for server
            api_key = self.prefs.get('api_key')
            if api_key:
                env['MCP_SERVER_API_KEY'] = api_key

            kwargs = {
                'cwd': self.prefs.get('working_dir') or None,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.STDOUT,
                'env': env,
            }

            if os.name == 'nt':
                # Detach new process group on Windows
                kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

            self._process = subprocess.Popen(command, **kwargs)
            return True

    def stop(self):
        """Terminate MCP server process if running."""
        with self._lock:
            if not self.is_running:
                return False

            try:
                self._process.terminate()
            except OSError:
                # Ignore terminate errors
                pass
            finally:
                self._process = None
            return True

    def toggle(self):
        """Toggle MCP server running state."""
        if self.is_running:
            return self.stop()
        return self.start()

    def _parse_command(self):
        """Parse configured command string into argument list."""
        raw = self.prefs.get('command') or ''
        if not raw:
            return []

        try:
            return shlex.split(raw, posix=os.name != 'nt')
        except ValueError:
            # Fallback for weird quoting
            return raw.split()
