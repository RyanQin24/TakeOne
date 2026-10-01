"""Loopback UI owner for explicitly started robot takes. Never imports a serial driver."""

import json
import os
import secrets
import subprocess
import threading
from pathlib import Path

from takeone.config import read_json
from takeone.motion.studio_plan import prepare, validate
from takeone.paths import CONFIGS, DATA, WORKSPACE

TOKEN_HEADER = "X-TakeOne-Robot-Token"


def runtime_python():
    return WORKSPACE / ".runtime/robot/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def worker_environment():
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(WORKSPACE / "packages"), str(WORKSPACE / "lerobot/src")]),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
    )


def launch_worker(plan_path, folder):
    return subprocess.Popen(
        [str(runtime_python()), "-u", "-m", "takeone.motion.studio_worker", "--plan", str(plan_path)],
        cwd=WORKSPACE,
        env=worker_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


class RobotPlayback:
    def __init__(self, *, launcher=launch_worker, folder=None, runtime=None, phone=None):
        self.token = secrets.token_urlsafe(32)
        self.launcher = launcher
        self.folder = Path(folder) if folder else DATA / "runs"
        self.runtime = Path(runtime) if runtime else runtime_python()
        self.phone = phone
        self.lock = threading.RLock()
        self.plans = {}
        self.requests = {}
        self.process = None
        self.reader = None
        self.state = dict(active=False, phase="idle", elapsed_s=0.0)

    def status(self):
        with self.lock:
            devices = read_json(CONFIGS / "devices/windows.json")
            return dict(
                self.state,
                token=self.token,
                runtime_available=self.runtime.is_file(),
                devices={
                    "cart": devices["cart"]["port"],
                    **{r: d["port"] for r, d in devices["arms"].items()},
                },
                phone=self.phone.readiness()
                if self.phone is not None
                else dict(enabled=False, ready=False, reason="Phone capture is not attached."),
                physical_path_verified=False,
            )

    def authorize(self, token):
        if not isinstance(token, str) or not secrets.compare_digest(self.token, token):
            raise PermissionError("Reload the simulator before controlling the robot.")

    def prepare(self, settings, shot=None):
        with self.lock:
            if self.state["active"]:
                raise ValueError("Stop the current robot take before preparing another.")
        if shot is None:
            plan = prepare(settings)
        else:
            from takeone.motion.record_shot import prepare_shot

            plan = prepare_shot(settings, shot)
        with self.lock:
            if self.state["active"]:
                raise ValueError("A robot take started while this orbit was preparing.")
            if len(self.plans) >= 8:
                self.plans.pop(next(iter(self.plans)))
            self.plans[plan["plan_id"]] = plan
        return dict(
            plan_id=plan["plan_id"],
            settings=plan["settings"],
            summary=plan["summary"],
            raw_goals=plan["raw_goals"],
            record_shot=plan.get("record_shot"),
            ports_opened=False,
        )

    def start(self, plan_id, request_id):
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 100:
            raise ValueError("A unique playback request is required")
        with self.lock:
            if request_id in self.requests:
                if self.requests[request_id] != plan_id:
                    raise ValueError("Playback request was reused for a different orbit")
                return self.status()
            if self.state["active"]:
                raise ValueError("A robot take is already active")
            if read_json(CONFIGS / "devices/windows.json").get("hardware_enabled") is not True:
                raise ValueError("The Windows robot device profile is disabled")
            if plan_id not in self.plans:
                raise ValueError("Prepare the current orbit before running it")
            if not self.runtime.is_file():
                raise ValueError("Robot runtime is missing. Run scripts/setup_robot_runtime.py first.")
            plan = validate(self.plans[plan_id])
            run_id = secrets.token_hex(12)
            folder = self.folder / ("studio-" + run_id)
            folder.mkdir(parents=True)
            path = folder / "plan.json"
            path.write_text(json.dumps(plan, allow_nan=False), encoding="utf-8")
            phone_reserved = False
            try:
                phone_config = self.phone.reserve(plan) if self.phone is not None else None
                phone_reserved = phone_config is not None
                if plan.get("record_shot") and not phone_reserved:
                    raise ValueError("Enable and configure iPhone capture before filming this shot.")
                if phone_config is not None:
                    (folder / "phone-capture-config.json").write_text(
                        json.dumps(phone_config, allow_nan=False), encoding="utf-8"
                    )
                process = self.launcher(path, folder)
            except BaseException:
                if phone_reserved:
                    self.phone.release(folder, launched=False)
                raise
            self.process = process
            self.requests[request_id] = plan_id
            self.state = dict(
                active=True,
                phase="connecting",
                run_id=run_id,
                plan_id=plan_id,
                settings=plan["settings"],
                elapsed_s=0.0,
                duration_s=plan["duration_s"],
                orbit_start_s=plan["orbit_start_s"],
                orbit_duration_s=plan["orbit_duration_s"],
                directory=str(folder),
                phone_capture_required=phone_reserved,
                record_shot=plan.get("record_shot"),
                recording_confirmed=False if phone_reserved else None,
                error=None,
            )
            self.reader = threading.Thread(
                target=self._read, args=(process, folder, phone_reserved), daemon=True
            )
            self.reader.start()
            return self.status()

    def _read(self, process, folder, phone_reserved=False):
        terminal = None
        try:
            with (folder / "worker.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict) or event.get("source") != "studio_worker":
                        continue
                    with self.lock:
                        self.state.update(
                            {
                                k: event[k]
                                for k in (
                                    "phase",
                                    "elapsed_s",
                                    "approach_s",
                                    "error",
                                    "recording_confirmed",
                                )
                                if k in event and (k != "elapsed_s" or event[k] is not None)
                            }
                        )
                    if event.get("terminal"):
                        terminal = event
            code = process.wait()
            with self.lock:
                self.state.update(
                    active=False,
                    phase=terminal["phase"] if terminal else "failed",
                    error=terminal.get("error")
                    if terminal
                    else f"Robot worker exited ({code}); see worker.log.",
                )
        except (OSError, ValueError) as error:
            with self.lock:
                self.state.update(active=False, phase="failed", error=str(error))
        finally:
            if phone_reserved:
                self.phone.release(folder, launched=True)
                phone_status = self.phone.status()
                with self.lock:
                    self.state["phone_capture"] = phone_status["last_result"]
                    self.state["phone_capture_uncertain"] = phone_status["uncertain"]
            process.stdout.close()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()

    def command(self, command, run_id):
        if command not in ("heartbeat", "stop"):
            raise ValueError("Unknown robot command")
        with self.lock:
            if run_id != self.state.get("run_id"):
                raise ValueError("This robot take is no longer current")
            if self.state["active"]:
                try:
                    self.process.stdin.write(json.dumps({"command": command}) + "\n")
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    self.state["error"] = (
                        "Robot control channel closed; the worker will stop on connection loss."
                    )
                if command == "stop":
                    self.state["phase"] = "stopping"
            return self.status()

    def close(self):
        with self.lock:
            if self.state["active"]:
                self.command("stop", self.state["run_id"])
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
