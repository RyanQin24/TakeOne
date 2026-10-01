"""Artifacts keyed by node identity. A cache entry is never invalidated, only superseded.

Because a node's id is the hash of its meaning, an artifact rendered for that id stays
correct forever. Changing a colour parameter produces different ids for that node and
everything downstream, and leaves every unaffected artifact usable. This is where the
editor's responsiveness comes from, and it is a consequence of the graph design rather
than a separate optimisation.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..errors import RenderError


@dataclass(frozen=True, slots=True)
class CacheEntry:
    node_id: str
    path: str
    bytes: int
    duration_s: float

    def wire(self):
        return {
            "node_id": self.node_id,
            "path": self.path,
            "bytes": self.bytes,
            "duration_s": self.duration_s,
        }


class ArtifactCache:
    def __init__(self, root, suffix=".mp4"):
        self.root = Path(root)
        self.suffix = suffix
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, node_id):
        if not node_id or "/" in node_id or "\\" in node_id or ".." in node_id:
            raise RenderError(f"Refusing a cache path for an unsafe id '{node_id}'")
        return self.root / f"{node_id}{self.suffix}"

    def get(self, node_id):
        path = self.path_for(node_id)
        sidecar = path.with_suffix(path.suffix + ".json")
        if not path.exists() or not sidecar.exists():
            return None
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return CacheEntry(node_id, str(path), path.stat().st_size, float(meta.get("duration_s", 0.0)))

    def put(self, node_id, duration_s):
        path = self.path_for(node_id)
        if not path.exists():
            raise RenderError(f"Cannot record a cache entry for a missing artifact: {path}")
        sidecar = path.with_suffix(path.suffix + ".json")
        sidecar.write_text(
            json.dumps({"node_id": node_id, "duration_s": duration_s}, separators=(",", ":")),
            encoding="utf-8",
        )
        return CacheEntry(node_id, str(path), path.stat().st_size, duration_s)

    def report(self, graph):
        """How much of this graph is already rendered. Honest progress needs this."""
        total = len(graph.nodes)
        hits = sum(1 for item in graph.nodes if self.get(item.node_id) is not None)
        return {"nodes": total, "cached": hits, "missing": total - hits}
