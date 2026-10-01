"""The native project file: state plus the operation log that produced it.

A `.takeone.json` is replayable. Loading it reconstructs the project by folding the log,
and the stored state is checked against that fold rather than trusted, so a hand-edited or
truncated file is caught at load time instead of producing a subtly wrong film.
"""

import json
from pathlib import Path

from ..contracts import encode
from ..project import now_utc

EXTENSION = ".takeone.json"
FORMAT_VERSION = 1


def document(service, project_id):
    # The service owns edits: keep snapshot and complete journal paired under its lock.
    with service.locked_project(project_id) as state:
        snapshot = service.repository.snapshot(project_id)
        history = service.repository.iter_operations(project_id)
        return {
            "format": "takeone-editor-project",
            "format_version": FORMAT_VERSION,
            "exported_utc": now_utc(),
            "project_id": project_id,
            "title": snapshot["title"],
            "created_utc": snapshot["created_utc"],
            "updated_utc": snapshot["updated_utc"],
            "state": state.wire(),
            "operations": [entry["operation"] for entry in history],
            "artifacts": service.repository.artifacts(project_id),
        }


def export(service, project_id, destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document(service, project_id), indent=2), encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(service, project_id):
    from ..ids import digest as sha

    return sha(json.loads(encode(document(service, project_id))))
