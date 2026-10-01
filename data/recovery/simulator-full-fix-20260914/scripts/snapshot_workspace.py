"""Read-only source snapshot, including nested Git history and untracked work."""

import hashlib
import json
import os
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}


def main():
    destination = ROOT / "archive/recovery" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, exist_ok=False)
    entries = []
    with zipfile.ZipFile(destination / "workspace.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for directory, children, names in os.walk(ROOT):
            children[:] = [
                name
                for name in children
                if name not in EXCLUDED and not (Path(directory) == ROOT and name == "archive")
            ]
            for name in names:
                source = Path(directory) / name
                if source.is_symlink():
                    raise RuntimeError(f"Symlink needs explicit recovery handling: {source}")
                # Active server logs are captured separately after the server stops.
                if source.name in {"server-out.log", "server-error.log"}:
                    continue
                data = source.read_bytes()
                relative = source.relative_to(ROOT).as_posix()
                archive.writestr(relative, data)
                entries.append(dict(path=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    with zipfile.ZipFile(destination / "workspace.zip") as archive:
        for entry in entries:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"], entry["path"]
    metadata = dict(
        schema=1,
        root=str(ROOT),
        verified=True,
        files=entries,
        excludes=sorted(EXCLUDED | {"archive", "active server logs"}),
    )
    (destination / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for filename, args in [
        ("lerobot-status.txt", ["status", "--porcelain=v1", "-uall"]),
        ("lerobot-head.txt", ["rev-parse", "HEAD"]),
        ("lerobot-diff.patch", ["diff", "--binary", "HEAD"]),
    ]:
        result = subprocess.run(["git", "-C", str(ROOT / "lerobot"), *args], capture_output=True, check=True)
        (destination / filename).write_bytes(result.stdout)
    print(
        json.dumps(
            dict(
                snapshot=str(destination), verified_files=len(entries), bytes=sum(e["bytes"] for e in entries)
            )
        )
    )


if __name__ == "__main__":
    main()
