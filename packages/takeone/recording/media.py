"""Bounded creation and validation of unmistakably synthetic MP4 fixtures."""

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from uuid import UUID


class MediaWriteError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SyntheticMediaWriter:
    def __init__(self, *, ffmpeg=None, ffprobe=None, timeout_seconds=15):
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 60
        ):
            raise ValueError("Media timeout must be finite and from 0 to 60 seconds")
        self.ffmpeg = Path(ffmpeg) if ffmpeg is not None else Path(shutil.which("ffmpeg") or "ffmpeg")
        self.ffprobe = Path(ffprobe) if ffprobe is not None else Path(shutil.which("ffprobe") or "ffprobe")
        self.timeout_seconds = float(timeout_seconds)

    def _run(self, argv, *, code, tool):
        try:
            result = subprocess.run(
                [str(item) for item in argv],
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise MediaWriteError(
                "media_tool_unavailable", f"Required {tool} executable is unavailable."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise MediaWriteError("media_tool_timeout", f"Bounded {tool} process timed out.") from error
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[-180:]
            raise MediaWriteError(code, f"{tool} rejected the synthetic media. {detail}".strip())
        return result

    def write(self, take_id, media_root, duration_ms, scenario):
        try:
            canonical_take_id = str(UUID(take_id)) if isinstance(take_id, str) else None
        except ValueError:
            canonical_take_id = None
        if canonical_take_id != take_id:
            raise ValueError("Synthetic media take ID must be a canonical UUID")
        if type(duration_ms) is not int or not 250 <= duration_ms <= 10_000:
            raise ValueError("Synthetic duration must be an integer from 250 to 10000 ms")
        if scenario == "save_failure":
            raise MediaWriteError("save_failure", "Injected synthetic storage failure.")

        media_root = Path(media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        take_directory = media_root / take_id
        try:
            take_directory.mkdir()
        except FileExistsError as error:
            raise MediaWriteError("refused_overwrite", "The take media directory already exists.") from error
        partial = take_directory / "synthetic.partial.mp4"
        published = take_directory / "synthetic.mp4"
        seconds = f"{duration_ms / 1000:.3f}"
        self._run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-n",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=320x180:rate=24",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000",
                "-t",
                seconds,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-profile:v",
                "baseline",
                "-level:v",
                "3.0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                partial,
            ],
            code="media_generation_failed",
            tool="ffmpeg",
        )
        if scenario == "corrupt_media":
            partial.write_bytes(b"incomplete synthetic transfer")

        try:
            probed = self._run(
                [
                    self.ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,size:stream=index,codec_name,codec_type,width,height,sample_rate,channels",
                    "-of",
                    "json",
                    partial,
                ],
                code="corrupt_media",
                tool="ffprobe",
            )
            probe = json.loads(probed.stdout)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise MediaWriteError("corrupt_media", "ffprobe returned invalid media metadata.") from error
        self._run(
            [
                self.ffmpeg,
                "-v",
                "error",
                "-nostdin",
                "-xerror",
                "-err_detect",
                "explode",
                "-i",
                partial,
                "-f",
                "null",
                "-",
            ],
            code="corrupt_media",
            tool="ffmpeg decode",
        )
        try:
            duration = float(probe["format"]["duration"])
            streams = probe["streams"]
        except (KeyError, TypeError, ValueError) as error:
            raise MediaWriteError("corrupt_media", "Required stream metadata is missing.") from error
        if not math.isfinite(duration) or abs(duration * 1000 - duration_ms) > 150:
            raise MediaWriteError(
                "duration_mismatch", "Synthetic media duration does not match its timeline."
            )
        if {stream.get("codec_type") for stream in streams} != {"video", "audio"}:
            raise MediaWriteError(
                "stream_mismatch", "Synthetic media must contain one video and one audio stream."
            )
        size = partial.stat().st_size
        if size <= 0:
            raise MediaWriteError("corrupt_media", "Synthetic media is empty.")
        digest = hashlib.sha256(partial.read_bytes()).hexdigest()
        if published.exists():
            raise MediaWriteError("refused_overwrite", "A published take already exists.")
        partial.rename(published)
        return {
            "relative_path": published.relative_to(media_root).as_posix(),
            "sha256": digest,
            "size_bytes": size,
            "duration_ms": round(duration * 1000),
            "requested_timeline_ms": duration_ms,
            "streams": streams,
            "probe": {"format": probe["format"], "streams": streams},
            "provenance": {
                "source": "synthetic_ffmpeg",
                "video_source": "testsrc2",
                "audio_source": "sine",
                "timeline_source": "requested_synthetic_timeline",
                "requested_duration_ms": duration_ms,
            },
        }
