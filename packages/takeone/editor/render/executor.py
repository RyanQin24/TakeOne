"""Running FFmpeg. Argument lists only, progress parsed, artifacts written atomically."""

import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..errors import RenderError


@dataclass(frozen=True, slots=True)
class RenderResult:
    schema_version: ClassVar[int] = 1
    output_path: str
    duration_s: float
    elapsed_s: float
    node_count: int
    command: tuple = field(default_factory=tuple)

    def wire(self):
        return {
            "output_path": self.output_path,
            "duration_s": self.duration_s,
            "elapsed_s": round(self.elapsed_s, 3),
            "node_count": self.node_count,
        }


class RenderExecutor:
    """One FFmpeg process at a time per executor; cancellation is cooperative and immediate."""

    def __init__(self, on_progress=None):
        self.on_progress = on_progress
        self._process = None
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()

    def run(self, plan):
        import time

        process = None
        destination = Path(plan.output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=str(destination.parent), prefix=".render-", suffix=destination.suffix or ".mp4"
        )
        os.close(handle)
        argv = list(plan.argv)
        argv[-1] = temporary
        argv = argv[:1] + ["-progress", "pipe:1", "-nostats"] + argv[1:]
        started = time.monotonic()
        try:
            with self._lock:
                self._cancelled = False
                self._process = subprocess.Popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
            process = self._process
            for line in process.stdout:
                if self.on_progress is None:
                    continue
                key, _, value = line.strip().partition("=")
                if key == "out_time_ms" and value.isdigit() and plan.duration_s > 0:
                    fraction = min(1.0, int(value) / 1_000_000.0 / plan.duration_s)
                    self.on_progress({"stage": "render", "progress": round(fraction, 4)})
            errors = process.stderr.read()
            code = process.wait()
            if self._cancelled:
                raise RenderError("Render cancelled", {"output": plan.output_path})
            if code != 0:
                raise RenderError(
                    f"FFmpeg exited with status {code}",
                    {"stderr": errors.strip()[-2000:], "argv": argv},
                )
            os.replace(temporary, destination)
            temporary = None
            return RenderResult(
                output_path=str(destination),
                duration_s=plan.duration_s,
                elapsed_s=time.monotonic() - started,
                node_count=len(plan.node_ids),
                command=tuple(plan.argv),
            )
        finally:
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            with self._lock:
                self._process = None
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
