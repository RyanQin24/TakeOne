"""A small regenerable store for scouted worlds. JSON files, no schema migration.

Worlds are cheap to rebuild from a candidate and an anchor, so this is a cache,
not evidence: losing it costs one re-scout. It lives beside the other
regenerable caches under ``data/`` and is deliberately bounded.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from takeone.paths import DATA

CACHE = DATA / "location-scout-cache"
MAX_WORLDS = 40
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def valid_id(value):
    if not isinstance(value, str) or not SAFE_ID.match(value):
        raise ValueError("Invalid world identifier")
    return value


class WorldStore:
    def __init__(self, root=None):
        self.root = Path(root or CACHE)
        self._lock = threading.Lock()
        self._memory = {}

    def _path(self, world_id):
        return self.root / f"{valid_id(world_id)}.json"

    def put(self, world_id, record):
        valid_id(world_id)
        with self._lock:
            self._memory[world_id] = record
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                self._path(world_id).write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
                stored = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime)
                for stale in stored[:-MAX_WORLDS]:
                    stale.unlink(missing_ok=True)
            except OSError:
                # The cache is best effort. An unwritable data directory must
                # never fail a scout that already succeeded in memory.
                pass
        return record

    def get(self, world_id):
        valid_id(world_id)
        with self._lock:
            if world_id in self._memory:
                return self._memory[world_id]
            try:
                record = json.loads(self._path(world_id).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            self._memory[world_id] = record
            return record

    def list_ids(self):
        with self._lock:
            ids = set(self._memory)
        try:
            ids |= {path.stem for path in self.root.glob("*.json")}
        except OSError:
            pass
        return sorted(ids)
