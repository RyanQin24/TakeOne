"""What of the phone's footage has actually reached this computer.

The recorder is deliberately honest that it has never seen a frame: a phone take
ends with `media_location: phone_internal_storage` and `media_verified: false`,
because Blackmagic REST hands out transport control, not footage. Nothing here
changes that record.

This is the separate, additive fact: a clip with this take's name now exists on
this disk, it is this many bytes, and this is its digest. It is written beside
the takes rather than into them, so the recorder's own evidence stays exactly
what the device said.

Matching prefers the actual filename and size read back from the device after
Stop. Older takes retain requested-name matching as a compatibility fallback;
unmatched files are listed without guessing. No renaming, transcoding or deletion.
"""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from takeone.paths import DATA

CLIP_SUFFIXES = (".mov", ".mp4", ".m4v", ".braw")
MAX_FILES = 2000
# Hashing is bounded so a folder of 4K originals cannot stall the request.
HASH_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
READ_CHUNK = 1024 * 1024


def inbox_root(root=None):
    return Path(root) if root else DATA / "phone-sync"


def clip_name(plan_id):
    """The exact name PhoneTake gives the clip it starts."""
    return "TakeOne-" + str(plan_id)[:12]


def _digest(path):
    hasher = hashlib.sha256()
    read = 0
    with path.open("rb") as stream:
        while read < HASH_LIMIT_BYTES:
            chunk = stream.read(READ_CHUNK)
            if not chunk:
                break
            read += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), read


@lru_cache(maxsize=MAX_FILES)
def _cached_digest(path, size, modified_ns):
    return _digest(path)


def scan(root=None):
    """Every clip-shaped file in the inbox, with the facts this computer can check."""
    folder = inbox_root(root)
    if not folder.is_dir():
        return []
    files = []
    for path in sorted(folder.rglob("*")):
        if len(files) >= MAX_FILES:
            break
        if not path.is_file() or path.suffix.lower() not in CLIP_SUFFIXES:
            continue
        try:
            stat = path.stat()
            sha256, hashed = _cached_digest(path, stat.st_size, stat.st_mtime_ns)
        except OSError:
            continue
        files.append(
            {
                "name": path.name,
                "relative_path": str(path.relative_to(folder)).replace(os.sep, "/"),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "sha256": sha256,
                "hashed_bytes": hashed,
                "fully_hashed": hashed >= stat.st_size,
                "source": "local_file_read",
            }
        )
    return files


def reconcile(takes, root=None):
    """Join the takes this runtime recorded to the files that have arrived.

    A take is `synced` only when a file carrying its clip name is on this disk.
    Everything else stays `on_phone`, which is the truthful state for footage
    this computer has never been given.
    """
    files = scan(root)
    by_name = {}
    for entry in files:
        by_name.setdefault(entry["name"], entry)
    results, claimed = [], set()
    for take in takes:
        if take.get("source") != "phone":
            continue
        evidence = take.get("device_reported") or {}
        actual = evidence.get("clip") or {}
        expected = actual.get("filePath") or clip_name(take.get("plan_id") or take["take_id"])
        matches = [
            entry
            for entry in files
            if (
                entry["name"] == expected and entry["size_bytes"] == actual.get("fileSize")
                if actual.get("filePath")
                else expected in entry["name"]
            )
        ]
        match = matches[0] if len(matches) == 1 else None
        if match:
            claimed.add(match["relative_path"])
        results.append(
            {
                "take_id": take["take_id"],
                "plan_id": take.get("plan_id"),
                "state": take.get("state"),
                "clip_name": expected,
                "clip_identified": bool(actual.get("filePath")),
                "synced": match is not None,
                "media": match,
                # The bytes are here; nobody has judged the picture.
                "media_reviewed": False,
                "transfer_error": evidence.get("transfer_error"),
            }
        )
    unmatched = [entry for entry in files if entry["relative_path"] not in claimed]
    return {
        "schema_version": 1,
        "inbox": str(inbox_root(root)),
        "takes": results,
        "unmatched": unmatched,
        "file_count": len(files),
        "synced_count": sum(1 for result in results if result["synced"]),
        "source": "local_file_read",
        "media_verified": False,
    }


def write_manifest(report, root=None):
    """Append-only record of what had arrived, beside the inbox, never inside a take."""
    folder = inbox_root(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "sync-manifest.json"
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    pending.replace(path)
    return path
