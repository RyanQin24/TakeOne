"""Own a tracking subprocess from the local UI; no camera or serial imports."""

import hashlib
import json
import os
import queue
import secrets
import subprocess
import threading
import time
from pathlib import Path

from takeone.config import read_json
from takeone.paths import CONFIGS, DATA, WORKSPACE

TOKEN_HEADER = "X-TakeOne-Tracking-Token"
LEASE_S = 5.0
STOP_GRACE_S = 3.0
SOURCES = {
    "cart": ("robocart_tracking.py", "9a743fd24036d5ea531d9db2f225443a518ffcfc8df409efd7e3387abc24dcba"),
    "arms": ("roboarm_tracking.py", "f467fe7f4479c06a5775731a7667d62a8c2f200c06874c8bdac8d0fbb8dae571"),
}
UART_HASH = "33db8afd69fa7024c545874c4c3f1aa5e1cadcf2334f9aeed9823e58e4832e92"


def settings():
    config = read_json(CONFIGS / "tracking.json")
    return (WORKSPACE / config["python"]).resolve(), (WORKSPACE / config["working_directory"]).resolve()


def source_path(mode):
    if mode not in SOURCES:
        raise ValueError("Choose Robocart tracking or Roboarm only")
    filename, expected = SOURCES[mode]
    source = WORKSPACE / "scripts/tracking" / filename
    for path, digest in ((source, expected), (source.with_name("motor_UART.py"), UART_HASH)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"The supplied tracking source changed: {path.name}")
    return source


def launch_worker(mode, arms_enabled, folder):
    python, cwd = settings()
    cwd.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(python),
            "-B",
            "-u",
            "-m",
            "takeone.motion.tracking_worker",
            "--mode",
            mode,
            *(["--arms"] if arms_enabled else []),
        ],
        cwd=cwd,
        env=dict(
            os.environ,
            TAKEONE_ROOT=str(WORKSPACE),
            PYTHONPATH=str(WORKSPACE / "packages"),
            PYTHONIOENCODING="utf-8",
            PYTHONUNBUFFERED="1",
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


class TrackingService:
    def __init__(
        self, *, launcher=launch_worker, folder=None, runtime=None, lease_s=LEASE_S, stop_grace_s=STOP_GRACE_S
    ):
        self.token = secrets.token_urlsafe(32)
        self.launcher = launcher
        self.folder = Path(folder) if folder else DATA / "runs"
        self.runtime = Path(runtime) if runtime else settings()[0]
        self.lease_s, self.stop_grace_s = lease_s, stop_grace_s
        self.lock = threading.RLock()
        self.state = dict(active=False, phase="idle", error=None)
        self.process = self.reader = self.monitor = self.writer = None
        self.requests = {}
        self.closed = False

    def status(self):
        with self.lock:
            return dict(self.state, token=self.token, runtime_available=self.runtime.is_file())

    def authorize(self, token):
        if not isinstance(token, str) or not secrets.compare_digest(token, self.token):
            raise PermissionError("Reload the simulator before controlling tracking")

    def start(self, mode, arms_enabled, request_id):
        if mode not in SOURCES or type(arms_enabled) is not bool:
            raise ValueError("A valid tracking mode and boolean arm selection are required")
        if mode == "arms" and not arms_enabled:
            raise ValueError("Roboarm-only mode requires arm tracking")
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 100:
            raise ValueError("A unique tracking request is required")
        with self.lock:
            if self.closed:
                raise ValueError("The tracking service is closing")
            if request_id in self.requests:
                previous_mode, previous_arms, previous_run = self.requests[request_id]
                if (previous_mode, previous_arms) != (mode, arms_enabled):
                    raise ValueError("Tracking request reused with different settings")
                if previous_run != self.state.get("run_id"):
                    raise ValueError("A later tracking run replaced this request")
                return self.status()
            if self.state["active"]:
                raise ValueError("Stop the active tracking script first")
            if not self.runtime.is_file():
                raise ValueError("Tracking Python is missing; check configs/tracking.json")
            if read_json(CONFIGS / "devices/windows.json").get("hardware_enabled") is not True:
                raise ValueError("The Windows robot device profile is disabled")
            source_path(mode)
            run_id = secrets.token_hex(12)
            folder = self.folder / ("tracking-" + run_id)
            folder.mkdir(parents=True)
            self.state = dict(
                active=False,
                phase="starting",
                run_id=run_id,
                mode=mode,
                arms_enabled=arms_enabled,
                directory=str(folder),
                error=None,
                started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                source_sha256=SOURCES[mode][1],
                cleanup_completed=False,
            )
            self._save(folder)
            try:
                self.process = self.launcher(mode, arms_enabled, folder)
            except (OSError, ValueError) as error:
                self.state.update(phase="failed", error=str(error))
                self._save(folder)
                raise
            self.requests[request_id] = (mode, arms_enabled, run_id)
            self.state["active"] = True
            self.last_seen = time.monotonic()
            self.stop_at = None
            self.terminal = None
            self.control_queue = queue.Queue(maxsize=1)
            self.writer = threading.Thread(target=self._write, args=(self.process,), daemon=True)
            self.reader = threading.Thread(target=self._read, args=(self.process, folder), daemon=True)
            self.monitor = threading.Thread(target=self._watch, args=(self.process, folder), daemon=True)
            self.reader.start()
            self.writer.start()
            self.monitor.start()
            return self.status()

    def _save(self, folder):
        (folder / "run.json").write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _read(self, process, folder):
        try:
            with (folder / "worker.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict) or event.get("source") != "tracking_worker":
                        continue
                    with self.lock:
                        if event.get("terminal"):
                            self.terminal = event
                        elif self.stop_at is None and event.get("phase"):
                            self.state["phase"] = event["phase"]
        except (OSError, ValueError) as error:
            with self.lock:
                self._stop(f"Tracking log/control failed: {error}")
        finally:
            process.stdout.close()

    def _stop(self, reason):
        if self.stop_at is not None:
            return
        self.stop_at = time.monotonic()
        self.state.update(phase="stopping", stop_reason=reason)
        self._queue("stop")

    def _queue(self, command):
        # A hung child may stop reading its pipe. The monitor never performs a
        # blocking pipe write, so Stop can still reach the termination deadline.
        try:
            self.control_queue.get_nowait()
        except queue.Empty:
            pass
        self.control_queue.put_nowait(command)

    def _write(self, process):
        while True:
            command = self.control_queue.get()
            if command is None:
                return
            try:
                process.stdin.write(json.dumps({"command": command}) + "\n")
                process.stdin.flush()
            except (OSError, ValueError):
                with self.lock:
                    self._stop("Tracking control channel closed")
                return

    def _watch(self, process, folder):
        forced = False
        while process.poll() is None:
            with self.lock:
                now = time.monotonic()
                if now - self.last_seen > self.lease_s:
                    self._stop("Browser connection lost")
                if self.stop_at is not None and now - self.stop_at > self.stop_grace_s:
                    try:
                        process.kill()
                        forced = True
                    except OSError as error:
                        self.state["error"] = f"Could not terminate tracking: {error}"
            time.sleep(0.05)
        code = process.wait()
        self.reader.join(timeout=1)
        with self.lock:
            self._queue(None)
        self.writer.join(timeout=1)
        try:
            process.stdin.close()
        except (OSError, ValueError):
            pass
        with self.lock:
            terminal = self.terminal or {}
            self.state.update(
                active=False,
                exit_code=code,
                forced=forced,
                phase="terminated" if forced else terminal.get("phase", "failed"),
                cleanup_completed=bool(terminal.get("cleanup_completed")) and not forced,
                error=(
                    "Script forcibly terminated; hardware stop is unconfirmed."
                    if forced
                    else terminal.get("error")
                    or (None if terminal else f"Tracking exited ({code}); see worker.log.")
                ),
            )
            self._save(folder)

    def command(self, command, run_id):
        with self.lock:
            if run_id != self.state.get("run_id"):
                raise ValueError("This tracking run is no longer current")
            if command not in ("stop", "heartbeat"):
                raise ValueError("Unknown tracking command")
            if self.state["active"]:
                if command == "stop":
                    self._stop("Stopped from the simulator")
                elif self.stop_at is None:
                    if time.monotonic() - self.last_seen > self.lease_s:
                        self._stop("Browser connection lost")
                    else:
                        self.last_seen = time.monotonic()
                        self._queue("heartbeat")
            return self.status()

    def close(self):
        with self.lock:
            self.closed = True
            if self.state["active"]:
                self._stop("Simulator closed")
        if self.monitor:
            self.monitor.join(timeout=self.stop_grace_s + 2)
