from dataclasses import dataclass
import os


@dataclass
class Config(object):
    """Hold basic configuration for the MCP server."""

    calibre_library_path: str


def load_config() -> Config:
    """Load configuration from environment variables or defaults.

    For now, read CALIBRE_LIBRARY_PATH. Later add config files if needed.
    """
    root = os.environ.get("CALIBRE_LIBRARY_PATH")
    if not root:
        # Force explicit configuration for now.
        raise RuntimeError("Set CALIBRE_LIBRARY_PATH to your Calibre library root")
    return Config(calibre_library_path=root)
