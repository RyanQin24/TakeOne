"""Intent versus result for one recorded take → (score, signals, reason).

The shape deliberately matches the editor's probe scoring: a 0..1 score, a
signals dict, and a human reason under 240 characters. The verdict ladder
degrades and never breaks: a vision analyst when configured, local pixel
statistics wherever ffmpeg lives, and probe-only metadata scoring as the floor.

Verdicts are cached content-addressed — media bytes, plan, timestamps and
prompt version — so re-review is instant and bumping PROMPT_VERSION recomputes
every take, which is exactly what changing the question should do.
"""

import json
import os
import tempfile
import time

from takeone.paths import DATA

from . import keyframes
from .vlm import AnalysisUnavailable, LocalFrameAnalyst

PROMPT_VERSION = 1
DIRECTORY = DATA / "review-cache" / "verdicts"
MAX_ENTRIES = 512
REASON_MAX_CHARS = 240


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _cache_key(media_sha256, plan_id, timestamps, model):
    import hashlib

    canonical = json.dumps(
        {
            "media_sha256": media_sha256,
            "plan_id": plan_id,
            "timestamps": [round(t, 3) for t in timestamps],
            "prompt_version": PROMPT_VERSION,
            "model": model,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _cached(key):
    path = DIRECTORY / f"{key}.json"
    try:
        if path.is_file():
            os.utime(path)
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def _store(key, verdict):
    try:
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=DIRECTORY, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(verdict, file, separators=(",", ":"))
        os.replace(temporary, DIRECTORY / f"{key}.json")
        entries = sorted(DIRECTORY.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for path in entries[: max(0, len(entries) - MAX_ENTRIES)]:
            path.unlink(missing_ok=True)
    except OSError:
        pass  # a cache that cannot be written is a slower review, never a failed one


def probe_verdict(media):
    """The floor: score from the metadata the recorder verified with ffprobe."""
    duration_s = media["duration_ms"] / 1000
    requested_s = media.get("requested_timeline_ms", media["duration_ms"]) / 1000
    fidelity = _clamp(1 - abs(duration_s - requested_s) / max(requested_s, 0.001))
    video = next((s for s in media.get("streams", []) if s.get("codec_type") == "video"), {})
    megapixels = (video.get("width", 0) * video.get("height", 0)) / 1_000_000
    resolution = _clamp(megapixels / 2.0)
    score = _clamp(0.6 * fidelity + 0.4 * resolution)
    signals = {
        "duration_fidelity": round(fidelity, 4),
        "resolution": round(resolution, 4),
        "source": "probe_only",
    }
    reason = (
        f"Probe-only: {video.get('width', '?')}×{video.get('height', '?')} · "
        f"{duration_s:.1f}s of {requested_s:.1f}s requested. Frames were not analysed."
    )
    return score, signals, reason[:REASON_MAX_CHARS]


def _frame_verdict(analysis, media):
    signals = dict(analysis["signals"])
    duration_s = media["duration_ms"] / 1000
    requested_s = media.get("requested_timeline_ms", media["duration_ms"]) / 1000
    fidelity = _clamp(1 - abs(duration_s - requested_s) / max(requested_s, 0.001))
    signals["duration_fidelity"] = round(fidelity, 4)
    if "in_frame" in signals:  # a vision analyst saw the subject questions
        score = _clamp(
            0.4 * signals["in_frame"]
            + 0.25 * signals["focus"]
            + 0.15 * signals["exposure"]
            + 0.2 * fidelity
            - (0.25 if signals.get("left_frame") else 0.0)
        )
    else:
        score = _clamp(0.5 * signals["focus"] + 0.3 * signals["exposure"] + 0.2 * fidelity)
    reason = analysis["reason"][:REASON_MAX_CHARS]
    return score, signals, reason


def review_take(take, media_path, *, analyst=None, clock=time.monotonic_ns):
    """One verdict dict for a ready take. Raises ValueError for unreviewable takes."""
    media = take.get("media")
    if take.get("state") != "ready" or not media:
        raise ValueError("Only a ready take with validated media can be reviewed")
    timestamps = keyframes.default_timestamps(media["duration_ms"] / 1000)
    primary = analyst if analyst is not None else LocalFrameAnalyst()
    key = _cache_key(media["sha256"], take.get("plan_id"), timestamps, primary.model)
    cached = _cached(key)
    if cached is not None:
        return cached
    try:
        analysis = primary.analyze(media_path, media["sha256"], timestamps)
        score, signals, reason = _frame_verdict(analysis, media)
        model = analysis["model"]
    except (AnalysisUnavailable, RuntimeError, OSError):
        if analyst is not None:
            # The configured analyst failed; the local one still answers pixels.
            try:
                analysis = LocalFrameAnalyst().analyze(media_path, media["sha256"], timestamps)
                score, signals, reason = _frame_verdict(analysis, media)
                model = analysis["model"]
            except (RuntimeError, OSError, ValueError):
                score, signals, reason = probe_verdict(media)
                model = "probe-only"
        else:
            score, signals, reason = probe_verdict(media)
            model = "probe-only"
    verdict = {
        "take_id": take["take_id"],
        "plan_id": take.get("plan_id"),
        "prompt_version": PROMPT_VERSION,
        "score": round(score, 4),
        "signals": signals,
        "reason": reason,
        "model": model,
        "created_ns": str(clock()),
        "keyframe_timestamps": timestamps,
    }
    _store(key, verdict)
    return verdict
