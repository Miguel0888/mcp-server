import importlib.util
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_RUNNER = PROJECT_ROOT / 'calibre_plugin' / 'server_runner.py'

spec = importlib.util.spec_from_file_location('mcp_server_runner', PLUGIN_RUNNER)
server_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_runner)  # type: ignore[arg-type]
MCPServerThread = server_runner.MCPServerThread


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_server_thread_start_and_stop():
    with TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / 'metadata.db'
        metadata_path.touch()

        port = _free_port()
        server = MCPServerThread(host='127.0.0.1', port=port, library_path=tmpdir)
        server.start()
        assert server.wait_until_started(timeout=5), 'server did not start in time'

        server.stop()
        time.sleep(0.1)
        assert not server.is_running, 'server thread should be stopped'
