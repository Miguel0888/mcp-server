from typing import List

from .plugin_base import ResearchPlugin
from .models import FulltextHit, Excerpt


class PluginRegistry(object):
    """Registry for research plugins that can post-process results."""

    def __init__(self, service):
        self._service = service
        self._plugins: List[ResearchPlugin] = []

    @property
    def service(self):
        """Return underlying LibraryResearchService instance."""
        return self._service

    def register_plugin(self, plugin: ResearchPlugin) -> None:
        """Register plugin instance."""
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: p.priority(), reverse=True)

    def apply_fulltext_plugins(self, hits: List[FulltextHit]) -> List[FulltextHit]:
        """Apply plugins to full-text hits."""
        result = hits
        for plugin in self._plugins:
            result = plugin.on_fulltext_results(result)
        return result

    def apply_excerpt_plugins(self, excerpt: Excerpt) -> Excerpt:
        """Apply plugins to excerpt."""
        result = excerpt
        for plugin in self._plugins:
            result = plugin.on_excerpt_created(result)
        return result
