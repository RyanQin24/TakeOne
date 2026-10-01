"""ffprobe, normalised into the editor's own typed probe. No guessing, no defaults for
values the container actually declares."""

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from ..errors import AnalysisError
from ..state import MediaProbe


def executable(name="ffprobe"):
    found = shutil.which(name)
    if not found:
        raise AnalysisError(f"{name} was not found on PATH")
    return found


def probe(path, binary=None):
    media = Path(path)
    if not media.is_file():
        raise AnalysisError(f"Media file not found: {media}")
    argv = [
        binary or executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(media),
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AnalysisError("ffprobe failed", {"stderr": result.stderr.strip()[-1000:]})
    try:
        document = json.loads(result.stdout)
    except ValueError as error:
        raise AnalysisError(f"ffprobe returned unreadable JSON: {error}") from None
    streams = document.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise AnalysisError(f"{media.name} contains no video stream")
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    rate = Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    if rate <= 0:
        rate = Fraction(video.get("r_frame_rate") or "30/1")
    duration = _duration(video, document, media)
    rotation = _rotation(video)
    width, height = int(video["width"]), int(video["height"])
    if rotation in (90, 270):
        width, height = height, width
    return MediaProbe(
        duration_s=duration,
        width=width,
        height=height,
        fps_num=rate.numerator,
        fps_den=rate.denominator,
        has_audio=has_audio,
        video_codec=str(video.get("codec_name", "unknown")),
        rotation_deg=rotation,
        pixel_format=str(video.get("pix_fmt", "yuv420p")),
    )


def _duration(video, document, media):
    for candidate in (video.get("duration"), document.get("format", {}).get("duration")):
        try:
            value = float(candidate)
            if value > 0:
                return value
        except (TypeError, ValueError):
            continue
    raise AnalysisError(f"{media.name} declares no usable duration")


def _rotation(video):
    for entry in video.get("side_data_list", []) or []:
        if "rotation" in entry:
            try:
                return int(round(float(entry["rotation"]))) % 360
            except (TypeError, ValueError):
                continue
    tags = video.get("tags", {}) or {}
    try:
        return int(round(float(tags.get("rotate", 0)))) % 360
    except (TypeError, ValueError):
        return 0
