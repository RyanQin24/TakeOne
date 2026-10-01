"""Shared test scaffolding. No media, no FFmpeg, no network: these tests are hermetic."""

import os
import sys
import uuid
from pathlib import Path

# Compile tests require an absolute path. `/media/...` is relative on Windows.
_MEDIA_ROOT = "C:/media" if os.name == "nt" else "/media"

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages"))

from takeone.editor import reducer, state  # noqa: E402
from takeone.editor.operations import EditOperation, OperationType, Target  # noqa: E402

PROBE = {
    "duration_s": 10.0,
    "width": 1920,
    "height": 1080,
    "fps_num": 30,
    "fps_den": 1,
    "has_audio": True,
    "audio_start_s": 0.0,
    "audio_duration_s": 10.0,
    "video_codec": "h264",
}


def op(op_type, op_target, **parameters):
    return EditOperation(
        operation_id=str(uuid.uuid4()),
        type=op_type,
        target=op_target,
        parameters=parameters,
    )


def media_op(media_id="m1", name="Shot", duration_s=10.0, fps_num=30, fps_den=1, width=1920, height=1080):
    return op(
        OperationType.IMPORT_MEDIA,
        Target.project(),
        media_id=media_id,
        name=name,
        path=f"{_MEDIA_ROOT}/{media_id}.mp4",
        sha256=("%064x" % abs(hash(media_id)))[:64],
        probe={
            **PROBE,
            "duration_s": duration_s,
            "audio_duration_s": duration_s,
            "fps_num": fps_num,
            "fps_den": fps_den,
            "width": width,
            "height": height,
        },
    )


def project_with_clips(spans=((0.0, 0.0, 2.0),), media_ids=None, project_id="p1"):
    """Build a project with one video track and the given `(timeline, in, out)` clips."""
    current = state.empty(project_id)
    media_ids = media_ids or ["m1"] * len(spans)
    for media_id in dict.fromkeys(media_ids):
        current, _ = reducer.apply(current, media_op(media_id))
    current, _ = reducer.apply(
        current, op(OperationType.ADD_TRACK, Target.project(), track_id="V1", kind="video")
    )
    for index, ((timeline_start, source_start, source_end), media_id) in enumerate(zip(spans, media_ids)):
        current, _ = reducer.apply(
            current,
            op(
                OperationType.ADD_CLIP,
                Target("track", track_id="V1"),
                clip_id=f"c{index + 1}",
                media_id=media_id,
                timeline_start_s=timeline_start,
                source_start_s=source_start,
                source_end_s=source_end,
            ),
        )
    return current
