"""Content-addressed previews on disk, so a restart does not re-solve a whole script.

The key is the shot settings plus the existing provenance snapshot, which already
hashes every source file, config and calibration the compiler reads. Any change to
any of them misses the cache; nothing stale can ever be served.
"""

import json
import os
import tempfile

from takeone.config import provenance
from takeone.motion.plan import digest
from takeone.paths import DATA

DIRECTORY = DATA / "previs-cache"
# Sized for the pre-warm grid (28 templates × a handful of durations) plus live
# misses during a session, so warming never evicts what a conversation just used.
MAX_ENTRIES = 512


def key_for(settings):
    return digest({"settings": settings, "provenance": provenance()})


def compile_preview(settings):
    """The preview for these settings, from disk when it is already solved."""
    from .templates import compile_template, validate_settings

    # Normalise first, so two spellings of the same shot share one cache entry.
    settings = validate_settings(settings)
    key = key_for(settings)
    path = DIRECTORY / f"{key}.json"
    try:
        if path.is_file():
            os.utime(path)  # Youngest-used stays; eviction below is by access time.
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    preview = compile_template(settings)["preview"]
    store(path, preview)
    return preview


def store(path, preview):
    try:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=DIRECTORY, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(preview, file, separators=(",", ":"))
        os.replace(temporary, path)
        evict()
    except OSError:
        pass  # A cache that cannot be written is a slower compile, never a failed one.


def evict():
    entries = sorted(DIRECTORY.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in entries[: max(0, len(entries) - MAX_ENTRIES)]:
        path.unlink(missing_ok=True)


def clear():
    if DIRECTORY.is_dir():
        for path in DIRECTORY.glob("*.json"):
            path.unlink(missing_ok=True)
