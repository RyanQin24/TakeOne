"""Proxy media, thumbnails and waveforms.

Editing never changes the original. Preview picture uses the silent proxy, while preview
audio and every master render reopen the original media.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..errors import RenderError
from .ffmpeg import executable


@dataclass(frozen=True, slots=True)
class ProxySet:
    proxy_path: str
    thumbnail_path: str
    waveform_path: str | None = None

    def wire(self):
        return {
            "proxy_path": self.proxy_path,
            "thumbnail_path": self.thumbnail_path,
            "waveform_path": self.waveform_path,
        }


class ProxyManager:
    def __init__(self, root, long_edge=960, crf=26, binary=None):
        self.root = Path(root)
        self.long_edge = int(long_edge)
        self.crf = int(crf)
        self.binary = binary
        self.root.mkdir(parents=True, exist_ok=True)

    def _run(self, argv):
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RenderError(
                "Proxy generation failed", {"stderr": result.stderr.strip()[-1500:], "argv": argv}
            )

    def build(self, media_id, source, probe, force=False):
        source = Path(source)
        directory = self.root / media_id
        directory.mkdir(parents=True, exist_ok=True)
        proxy = directory / "proxy.mp4"
        thumbnail = directory / "thumb.jpg"
        binary = self.binary or executable()
        scale = f"scale={self.long_edge}:-2" if probe.width >= probe.height else f"scale=-2:{self.long_edge}"
        if force or not proxy.exists():
            self._run(
                [
                    binary,
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    f"{scale},setsar=1,format=yuv420p",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    str(self.crf),
                    "-g",
                    "12",
                    "-keyint_min",
                    "12",
                    "-movflags",
                    "+faststart",
                    "-an",
                    str(proxy),
                ]
            )
        if force or not thumbnail.exists():
            at = min(max(0.1, probe.duration_s * 0.25), max(0.1, probe.duration_s - 0.05))
            self._run(
                [
                    binary,
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{at:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"{scale}",
                    "-q:v",
                    "4",
                    str(thumbnail),
                ]
            )
        waveform = None
        if probe.has_audio:
            waveform = directory / "waveform.png"
            if force or not waveform.exists():
                self._run(
                    [
                        binary,
                        "-hide_banner",
                        "-nostdin",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(source),
                        "-filter_complex",
                        "showwavespic=s=1200x160:colors=0x9AA1A8|0x9AA1A8:split_channels=0",
                        "-frames:v",
                        "1",
                        str(waveform),
                    ]
                )
            waveform = str(waveform)
        return ProxySet(str(proxy), str(thumbnail), waveform)
