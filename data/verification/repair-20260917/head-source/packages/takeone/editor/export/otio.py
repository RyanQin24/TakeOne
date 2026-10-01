"""OpenTimelineIO JSON, written directly.

OTIO's on-disk form is a small, stable, self-describing JSON schema. Writing it by hand
keeps the editor dependency-free and keeps the mapping from our timeline to theirs visible
and reviewable, which matters more than reusing a library for four object types. Effects,
looks and speed curves that OTIO has no native concept for are preserved under the
`takeone` metadata key rather than silently dropped.
"""

import json
from pathlib import Path

from ..errors import ValidationError


def _time(value_s, rate):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate), "value": round(value_s * rate, 6)}


def _range(start_s, duration_s, rate):
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _time(start_s, rate),
        "duration": _time(duration_s, rate),
    }


def _media_reference(media, rate):
    return {
        "OTIO_SCHEMA": "ExternalReference.1",
        "target_url": Path(media.path).as_uri(),
        "available_range": _range(0.0, media.probe.duration_s, rate),
        "metadata": {"takeone": {"media_id": media.media_id, "sha256": media.sha256}},
    }


def _clip(state, clip, rate):
    media = state.media_item(clip.media_id)
    return {
        "OTIO_SCHEMA": "Clip.1",
        "name": clip.label or clip.clip_id,
        "source_range": _range(clip.source_start_s, clip.source_span_s, rate),
        "media_reference": _media_reference(media, rate),
        "metadata": {
            "takeone": {
                "clip_id": clip.clip_id,
                "timeline_start_s": clip.timeline_start_s,
                "timeline_duration_s": clip.timeline_duration_s,
                "speed_curve": clip.speed_curve.wire() if clip.speed_curve else None,
                "interpolation": clip.interpolation,
                "color": clip.color.wire(),
                "effects": [item.wire() for item in clip.effects],
            }
        },
    }


def _gap(duration_s, rate):
    return {
        "OTIO_SCHEMA": "Gap.1",
        "name": "gap",
        "source_range": _range(0.0, duration_s, rate),
        "metadata": {},
    }


def document(state, name="TAKE ONE"):
    rate = state.render_settings.fps
    tracks = []
    for track in state.timeline.tracks:
        if track.kind not in ("video", "overlay"):
            continue
        children = []
        cursor = 0.0
        for clip in track.clips:
            if clip.timeline_start_s > cursor + 1e-6:
                children.append(_gap(clip.timeline_start_s - cursor, rate))
            children.append(_clip(state, clip, rate))
            cursor = clip.timeline_end_s
        tracks.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "name": track.track_id,
                "kind": "Video",
                "children": children,
                "metadata": {},
            }
        )
    if not tracks:
        raise ValidationError("There is no video track to export")
    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": name,
        "global_start_time": _time(0.0, rate),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": tracks,
            "metadata": {},
        },
        "metadata": {
            "takeone": {
                "project_id": state.project_id,
                "version": state.version,
                "transitions": [item.wire() for item in state.timeline.transitions],
                "markers": [item.wire() for item in state.timeline.markers],
                "audio": [item.wire() for item in state.audio],
                "note": "Effects, looks and speed curves live here; OTIO has no native form "
                "for them and dropping them silently would misrepresent the edit.",
            }
        },
    }


def export(state, destination, name="TAKE ONE"):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document(state, name), indent=2), encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}
