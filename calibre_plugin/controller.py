#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@goyal.net>'
__docformat__ = 'restructuredtext en'

import os
import shlex
import subprocess
import threading

from calibre_plugins.mcp_server.config import prefs


class MCPServerController:
    def __init__(self, prefs=prefs, library_path=None):
        self.prefs = prefs
        self.library_path = library_path
        self._process = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.is_running:
                return False
            command = self._parse_command()
            if not command:
                raise RuntimeError('Startkommando fehlt')
            env = os.environ.copy()
            effective_path = self.library_path or env.get('CALIBRE_LIBRARY_PATH')
            if effective_path:
                env['CALIBRE_LIBRARY_PATH'] = effective_path
            kwargs = {
                'cwd': self.prefs['working_dir'] or None,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.STDOUT,
                'env': env,
            }
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            self._process = subprocess.Popen(command, **kwargs)
            return True

    def stop(self):
        with self._lock:
            if not self.is_running:
                return False
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            finally:
                self._process = None
            return True

    def toggle(self):
        if self.is_running:
            return self.stop()
        return self.start()

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def _parse_command(self):
        raw = self.prefs['command']
        if not raw:
            return []
        try:
            return shlex.split(raw, posix=os.name != 'nt')
        except ValueError:
            return raw.split()

    def set_library_path(self, library_path):
        self.library_path = library_path
