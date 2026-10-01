"""Keyframe extraction, content-addressed on the media bytes and timestamps.

Extraction costs ~200-400 ms per take; the cache makes re-review instant and —
because a verdict is computed from these exact frames — deterministic across
runs. JPEG frames feed a vision model; small grayscale PGM frames feed the
local pixel statistics (PGM parses in pure Python).
"""

import hashlib
import shutil
import subprocess
from pathlib import Path

from takeone.paths import DATA

DIRECTORY = DATA / "review-cache" / "keyframes"
MAX_ENTRIES = 128
PGM_SCALE = "160:-2"  # small enough for pure-Python statistics, large enough to rank focus


def default_timestamps(duration_s, count=4):
    """Spread inside the take, avoiding the first and last frames' settle."""
    if not duration_s or duration_s <= 0:
        raise ValueError("Keyframes need a positive media duration")
    return [round(duration_s * (index + 1) / (count + 1), 3) for index in range(count)]


def _key(media_sha256, timestamps, kind):
    canonical = f"{media_sha256}:{','.join(f'{t:.3f}' for t in timestamps)}:{kind}"
    return hashlib.sha256(canonical.encode()).hexdigest()


def extract(media_path, media_sha256, timestamps, *, kind="jpeg", run=subprocess.run):
    """One file per timestamp, from cache when the same media was framed before."""
    if kind not in ("jpeg", "pgm"):
        raise ValueError("Keyframe kind must be jpeg or pgm")
    media_path = Path(media_path)
    folder = DIRECTORY / _key(media_sha256, timestamps, kind)
    suffix = ".jpg" if kind == "jpeg" else ".pgm"
    expected = [folder / f"{index:02d}{suffix}" for index in range(len(timestamps))]
    if all(path.is_file() for path in expected):
        for path in expected:
            path.touch()  # youngest-used survives eviction
        return expected
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for keyframe extraction")
    folder.mkdir(parents=True, exist_ok=True)
    for timestamp, path in zip(timestamps, expected):
        argv = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(media_path),
            "-frames:v",
            "1",
        ]
        if kind == "pgm":
            argv += ["-vf", f"scale={PGM_SCALE}", "-pix_fmt", "gray"]
        else:
            argv += ["-q:v", "3"]
        argv.append(str(path))
        result = run(argv, capture_output=True, timeout=30)
        if result.returncode or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Keyframe extraction failed at {timestamp:.3f}s")
    _evict()
    return expected


def _evict():
    if not DIRECTORY.is_dir():
        return
    entries = sorted(DIRECTORY.iterdir(), key=lambda p: p.stat().st_mtime)
    for folder in entries[: max(0, len(entries) - MAX_ENTRIES)]:
        shutil.rmtree(folder, ignore_errors=True)


def read_pgm(path):
    """A binary P5 PGM as (width, height, bytes). Pure Python on purpose."""
    data = Path(path).read_bytes()
    if not data.startswith(b"P5"):
        raise ValueError("Expected a binary PGM keyframe")
    fields = []
    index = 2
    while len(fields) < 3:
        while index < len(data) and data[index : index + 1].isspace():
            index += 1
        if data[index : index + 1] == b"#":
            while data[index : index + 1] not in (b"\n", b""):
                index += 1
            continue
        start = index
        while index < len(data) and not data[index : index + 1].isspace():
            index += 1
        fields.append(int(data[start:index]))
    width, height, maximum = fields
    if maximum > 255:
        raise ValueError("Expected 8-bit PGM keyframes")
    pixels = data[index + 1 : index + 1 + width * height]
    if len(pixels) != width * height:
        raise ValueError("PGM keyframe is truncated")
    return width, height, pixels
