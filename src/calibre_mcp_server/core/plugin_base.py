from abc import ABCMeta, abstractmethod
from typing import List

from .models import FulltextHit, Excerpt


class ResearchPlugin(object):
    """Base interface for research plugins."""

    __metaclass__ = ABCMeta

    @abstractmethod
    def id(self) -> str:
        """Return unique plugin identifier."""
        raise NotImplementedError()

    @abstractmethod
    def priority(self) -> int:
        """Return plugin priority. Higher values are applied first."""
        raise NotImplementedError()

    def on_fulltext_results(self, hits: List[FulltextHit]) -> List[FulltextHit]:
        """Optionally post-process full-text hits."""
        return hits

    def on_excerpt_created(self, excerpt: Excerpt) -> Excerpt:
        """Optionally post-process excerpt text."""
        return excerpt
