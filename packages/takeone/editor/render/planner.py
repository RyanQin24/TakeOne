"""What needs rendering, and in what order. The planner decides; the compiler translates."""

from dataclasses import dataclass
from typing import ClassVar

from .cache import ArtifactCache


@dataclass(frozen=True, slots=True)
class RenderWork:
    schema_version: ClassVar[int] = 1
    output_id: str
    cached_path: str | None
    nodes: tuple
    cache_report: dict

    @property
    def needs_render(self):
        return self.cached_path is None

    def wire(self):
        return {
            "output_id": self.output_id,
            "cached_path": self.cached_path,
            "node_count": len(self.nodes),
            "cache": self.cache_report,
        }


class RenderPlanner:
    def __init__(self, cache: ArtifactCache):
        self.cache = cache

    def plan(self, graph):
        """The output artifact is what the caller wants; everything else is provenance."""
        output_node = graph.by_id(graph.output_id)
        entry = self.cache.get(output_node.node_id)
        return RenderWork(
            output_id=output_node.node_id,
            cached_path=entry.path if entry else None,
            nodes=graph.ancestors(graph.output_id),
            cache_report=self.cache.report(graph),
        )
