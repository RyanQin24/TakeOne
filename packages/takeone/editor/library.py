"""Per-project media folders. Each film owns a local directory of original clips.

The reducer never sees a file. This module only decides *where* a take lives on disk
and which operations will register it and place it on the timeline. Upload HTTP
framing stays in the adapter.
"""

import re
import shutil
import uuid
from pathlib import Path

from .errors import ValidationError
from .ids import file_digest
from .operations import EditOperation, OperationType, Target

ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg"}
UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_STEM = 60


def project_dir(workspace, project_id):
    return Path(workspace).resolve() / "library" / project_id


def media_dir(workspace, project_id):
    return project_dir(workspace, project_id) / "media"


def ensure_project_library(workspace, project_id):
    """Create the film's local folder. Safe to call more than once."""
    folder = media_dir(workspace, project_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_filename(name):
    """A stored name is a stem plus a known video suffix. Paths and spaces do not survive."""
    # Uploads may carry Windows paths to a POSIX server and vice versa, so strip
    # directories under both conventions instead of trusting Path's host rules.
    base = re.split(r"[\\/]", str(name or ""))[-1]
    suffix = Path(base).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError(
            f"Unsupported media type '{suffix or '(none)'}'; use {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )
    stem = UNSAFE_NAME.sub("-", Path(base).stem).strip(".-") or "clip"
    return f"{stem[:MAX_STEM]}{suffix}"


def unique_destination(directory, filename):
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for index in range(2, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValidationError("Too many files already use this name in the project folder")


def store_file(directory, filename, source_path):
    """Copy an uploaded take into the project folder. Never writes outside `directory`."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    safe = safe_filename(filename)
    for _ in range(1000):
        destination = unique_destination(directory, safe).resolve()
        if destination != directory and not destination.is_relative_to(directory):
            raise ValidationError("Refusing to store media outside the project folder")
        try:
            with destination.open("xb") as target, Path(source_path).open("rb") as source:
                shutil.copyfileobj(source, target)
            return destination
        except FileExistsError:
            continue
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    raise ValidationError("Too many files already use this name in the project folder")


def find_media_by_digest(state, digest):
    for item in state.media.values():
        if item.sha256 == digest:
            return item
    return None


def video_track(state):
    for track in state.timeline.tracks:
        if track.kind == "video":
            return track
    return None


def ensure_track_operation():
    return EditOperation(
        operation_id=str(uuid.uuid4()),
        type=OperationType.ADD_TRACK,
        target=Target.project(),
        parameters={"track_id": "V1", "kind": "video"},
        public_explanation="Opened the picture track.",
        metadata={"source": "ingest"},
    )


def place_clip_operation(state, media_id, name=None, source_start_s=0.0, source_end_s=None, explanation=None):
    """Append the media as the next shot on the first video track.

    The start is ceiled onto the project frame grid so a 24 fps take never overlaps the
    previous 60 fps take after both in/out points snap to their own media grids.
    """
    item = state.media_item(media_id)
    track = video_track(state)
    if track is None:
        raise ValidationError("The film has no video track to place a clip on")
    start = state.quantize_ceil(track.duration_s)
    source_end = item.probe.duration_s if source_end_s is None else source_end_s
    label = (name or item.name)[:80]
    return EditOperation(
        operation_id=str(uuid.uuid4()),
        type=OperationType.ADD_CLIP,
        target=Target("track", track_id=track.track_id),
        parameters={
            "clip_id": f"c-{uuid.uuid4().hex[:10]}",
            "media_id": media_id,
            "timeline_start_s": start,
            "source_start_s": source_start_s,
            "source_end_s": source_end,
            "label": label,
        },
        public_explanation=explanation or f"Placed {label} on the timeline.",
        metadata={"source": "ingest"},
    )


def digest_of(path):
    return file_digest(path)
