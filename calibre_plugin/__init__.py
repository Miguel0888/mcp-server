#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Miguel Iglesias'
__docformat__ = 'restructuredtext en'

# The class that all Interface Action plugin wrappers must inherit from
from calibre.customize import InterfaceActionBase

import sys
from pathlib import Path
import zipfile
import pkgutil
import tempfile
import os
import logging
import importlib


# ---------------------------------------------------------------------------
# Bootstrap sys.path so that:
# - the plugin package itself (calibre_plugins.mcp_server_recherche)
# - the bundled MCP server package (calibre_mcp_server)
# - und ALLE Dependencies aus site-packages/
# importierbar sind – sowohl im ZIP-Plugin als auch im Dev-Ordner.
# ---------------------------------------------------------------------------

def _bootstrap_module_paths():
    plugin_dir = Path(__file__).resolve().parent
    parent = plugin_dir.parent

    # 1) Plugin-Ordner selber
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))

    # 2) Optional: ./src für Dev-Modus
    src_dir = parent / "src"
    if src_dir.is_dir():
        src_str = str(src_dir)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


def _bootstrap_site_packages():
    """
    Stelle sicher, dass der Inhalt von site-packages importierbar ist.

    - Im Dev-Modus: <plugin_dir>/site-packages als echter Ordner.
    - Im ZIP-Plugin: site-packages/ aus dem ZIP in einen Temp-Ordner entpacken
      und diesen Ordner auf sys.path legen.
    """
    plugin_dir = Path(__file__).resolve().parent
    # Fall 1: entpacktes Plugin mit realem site-packages-Ordner
    site_dir = plugin_dir / "site-packages"
    if site_dir.is_dir():
        site_str = str(site_dir)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)
        return

    # Fall 2: Plugin als ZIP – __file__ zeigt auf .../plugin.zip/__init__.py
    loader = pkgutil.get_loader(__name__)
    archive_path = getattr(loader, "archive", None)
    if not archive_path or not archive_path.lower().endswith(".zip"):
        # Kein ZIP-Plugin, nichts weiter zu tun
        return

    try:
        with zipfile.ZipFile(archive_path) as zf:
            # Alle Einträge unterhalb von site-packages/
            members = [n for n in zf.namelist() if n.startswith("site-packages/")]
            if not members:
                return

            tmp_root = Path(tempfile.mkdtemp(prefix="mcp_site_"))

            # Struktur unterhalb von site-packages/ erhalten
            for name in members:
                rel = name[len("site-packages/"):]
                if not rel:
                    continue
                target = tmp_root / rel
                if name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())

            tmp_str = str(tmp_root)
            if tmp_str not in sys.path:
                sys.path.insert(0, tmp_str)
    except Exception:
        # Im Fehlerfall nicht crashen – dann greifen ggf. globale Installationen
        # von websockets/fastmcp, falls vorhanden.
        return


_bootstrap_module_paths()
_bootstrap_site_packages()

site_packages_dir = PLUGIN_DIR / 'site-packages'
if site_packages_dir.exists():
    sys.path.insert(0, str(site_packages_dir))
loader = pkgutil.get_loader(__name__)
archive_path = getattr(loader, 'archive', None)
if archive_path:
    zip_site_packages = f"{archive_path}/site-packages"
    if zip_site_packages not in sys.path:
        sys.path.insert(0, zip_site_packages)

log = logging.getLogger(__name__)


def _log_dependency_visibility():
    targets = [str(site_packages_dir), archive_path or '(no archive)']
    log.info("MCP plugin sys.path entries relevant to site-packages: %s", targets)
    log.debug("First 8 sys.path entries: %s", sys.path[:8])
    for mod_name in ("websockets", "fastmcp"):
        try:
            module = importlib.import_module(mod_name)
            location = getattr(module, "__file__", "<built-in>")
            log.info("Module %s resolved from %s", mod_name, location)
        except ModuleNotFoundError as exc:
            log.warning("Module %s not importable: %s", mod_name, exc)


_log_dependency_visibility()


class MCPServerRecherchePlugin(InterfaceActionBase):
    '''
    This class is a simple wrapper that provides information about the actual
    plugin class. The actual interface plugin class is called MCPServerRechercheAction
    and is defined in the ui.py file, as specified in the actual_plugin field
    below.

    The reason for having two classes is that it allows the command line
    calibre utilities to run without needing to load the GUI libraries.
    '''
    name = 'MCP Server Recherche'
    description = 'Frontend fuer MCP-basierte Recherche in Calibre'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Miguel Iglesias'
    version = (0, 1, 0)
    minimum_calibre_version = (6, 0, 0)

    #: This field defines the GUI plugin class that contains all the code
    #: that actually does something. Its format is module_path:class_name
    #: The specified class must be defined in the specified module.
    actual_plugin = 'calibre_plugins.mcp_server_recherche.ui:MCPServerRechercheAction'

    def is_customizable(self):
        '''
        This method must return True to enable customization via
        Preferences->Plugins
        '''
        return True

    def config_widget(self):
        '''
        Implement this method and :meth:`save_settings` in your plugin to
        use a custom configuration dialog.

        This method, if implemented, must return a QWidget. The widget can have
        an optional method validate() that takes no arguments and is called
        immediately after the user clicks OK. Changes are applied if and only
        if the method returns True.

        If for some reason you cannot perform the configuration at this time,
        return a tuple of two strings (message, details), these will be
        displayed as a warning dialog to the user and the process will be
        aborted.
        '''
        from calibre_plugins.mcp_server_recherche.config import (
            MCPServerRechercheConfigWidget,
        )
        return MCPServerRechercheConfigWidget()

    def save_settings(self, config_widget):
        '''
        Save the settings specified by the user with config_widget.

        :param config_widget: The widget returned by :meth:`config_widget`.
        '''
        config_widget.save_settings()

        # Apply the changes
        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
