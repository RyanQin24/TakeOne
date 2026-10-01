"""One-shot, operator-confirmed cart commissioning service. No hardware IO in this process."""

import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path

from takeone.cart.nudge_plan import prepare_nudge, validate_nudge
from takeone.motion.studio import runtime_python, worker_environment
from takeone.paths import DATA, WORKSPACE


def launch_nudge(path, plan_id):
    return subprocess.Popen(
        [
            str(runtime_python()),
            "-u",
            "-m",
            "takeone.cart.nudge_worker",
            "--plan",
            str(path),
            "--confirm-plan",
            plan_id,
            "--operator-ready",
            "--execute",
        ],
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


class NudgeService:
    def __init__(self, check_idle, *, launcher=launch_nudge, clock=time.monotonic, folder=None, runtime=None):
        self.check_idle = check_idle
        self.launcher, self.clock = launcher, clock
        self.folder = Path(folder) if folder else DATA / "runs"
        self.runtime = Path(runtime) if runtime else runtime_python()
        self.lock = threading.RLock()
        self.pending = {}
        self.accepted = {}
        self.process = None
        self.owner = None
        self.state = dict(
            active=False, phase="idle", physical_motion_verified=False, physical_stop_confirmed=False
        )

    def status(self, owner):
        with self.lock:
            proposal = self.pending.get(owner)
            if proposal and proposal["expires_at"] <= self.clock():
                self.pending.pop(owner, None)
                proposal = None
            return dict(
                self.state,
                runtime_available=self.runtime.is_file(),
                owned=self.owner == owner,
                pending=self._review(proposal) if proposal else None,
                mode="operator_confirmed_cart_commissioning",
                automatic_motion_enabled=False,
            )

    def prepare(self, owner, direction, distance_m=None):
        if not owner:
            raise PermissionError("An active local session is required")
        with self.lock:
            # A changed/unsupported request invalidates the old review too.
            self.pending.pop(owner, None)
            if self.state["active"]:
                raise ValueError("Wait for the current cart test to end")
            if distance_m is not None:
                raise ValueError(
                    "Distance is not calibrated. Only an explicitly reviewed 0.5-second test is available"
                )
            self.check_idle()
            plan = prepare_nudge(direction)
            self.pending = {k: v for k, v in self.pending.items() if v["expires_at"] > self.clock()}
            if len(self.pending) >= 16:
                raise ValueError("Too many pending reviews")
            proposal = dict(
                review_id=secrets.token_urlsafe(24), plan=plan.to_dict(), expires_at=self.clock() + 90
            )
            self.pending[owner] = proposal
            return dict(
                ok=True,
                code="operator_review_required",
                review=self._review(proposal),
                hardware_commands_sent=False,
                message="A cart-only 0.5-second timed test is ready for review, not execution. "
                "Read the exact test card, support both arms, clear the area and have a physical abort ready. "
                "Only the operator's Run this exact test button can send motion. No distance is guaranteed.",
            )

    def _review(self, proposal):
        plan = proposal["plan"]
        return dict(
            review_id=proposal["review_id"],
            plan_id=plan["plan_id"],
            expires_in_s=max(0, round(proposal["expires_at"] - self.clock())),
            direction=plan["direction"],
            duration_s=plan["duration_s"],
            command_magnitude=plan["command_magnitude"],
            logical_commands=plan["logical_commands"],
            transmitted_wire=plan["transmitted_wire"].strip(),
            wire_polarity=plan["wire_polarity"],
            cart_port=plan["device"]["port"],
            usb_serial=plan["device"]["usb_serial"],
            predicted_distance_m=None,
            arms_commanded=False,
            physical_motion_verified=False,
        )

    def start(self, owner, review_id, plan_id, request_id, operator_ready):
        with self.lock:
            if not owner or operator_ready is not True:
                raise PermissionError(
                    "The present operator must confirm supported arms, clear area, identity and physical abort"
                )
            if not isinstance(request_id, str) or not 16 <= len(request_id) <= 100:
                raise ValueError("A unique execution request is required")
            key = (owner, request_id)
            if key in self.accepted:
                if self.accepted[key] != (review_id, plan_id):
                    raise ValueError("Execution request reused for a different review")
                return self.status(owner)
            if self.state["active"]:
                raise ValueError("A cart test is already active")
            proposal = self.pending.get(owner)
            if not proposal or proposal["review_id"] != review_id or proposal["plan"]["plan_id"] != plan_id:
                raise ValueError("Review is no longer current; prepare again")
            if proposal["expires_at"] <= self.clock():
                self.pending.pop(owner, None)
                raise ValueError("Review expired; prepare and review again")
            self.check_idle()
            plan = validate_nudge(proposal["plan"])
            if not self.runtime.is_file():
                raise ValueError("Robot runtime is not installed")
            if len(self.accepted) >= 128:
                raise ValueError("Execution limit reached; restart the test server")
            # Consume approval BEFORE launch; neither launch failures nor HTTP retries can replay it.
            self.pending.pop(owner)
            self.accepted[key] = (review_id, plan_id)
            run_id = secrets.token_hex(12)
            directory = self.folder / ("voice-cart-" + run_id)
            directory.mkdir(parents=True)
            path = directory / "plan.json"
            path.write_text(json.dumps(plan.to_dict(), allow_nan=False, indent=2), encoding="utf-8")
            (directory / "approval.json").write_text(
                json.dumps(
                    dict(
                        review_id=review_id,
                        plan_id=plan_id,
                        request_id=request_id,
                        operator_ready=True,
                        source="local_operator_button",
                        approved_at_unix_s=time.time(),
                    )
                ),
                encoding="utf-8",
            )
            self.owner = owner
            self.state = dict(
                active=False,
                phase="launching",
                run_id=run_id,
                plan_id=plan_id,
                directory=str(directory),
                physical_motion_verified=False,
                physical_stop_confirmed=False,
            )
            try:
                self.process = self.launcher(path, plan_id)
            except Exception as error:
                self.state.update(phase="failed", error=str(error))
                raise
            self.state.update(active=True)
            threading.Thread(target=self._read, args=(self.process, directory), daemon=True).start()
            return self.status(owner)

    def _read(self, process, directory):
        terminal = None
        try:
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict) or event.get("source") != "nudge_worker":
                        continue
                    with self.lock:
                        self.state.update(
                            {
                                k: event[k]
                                for k in ("phase", "error", "writes_completed", "fault")
                                if k in event
                            }
                        )
                    if event.get("terminal"):
                        terminal = event
                code = process.wait()
                with self.lock:
                    self.state.update(
                        active=False,
                        phase=terminal["phase"] if terminal and code == 0 else "failed",
                        error=(terminal or {}).get("error")
                        or (
                            None if terminal and code == 0 else f"Worker exited ({code}); inspect worker.log"
                        ),
                    )
        except (OSError, ValueError) as error:
            # Do not declare the process idle while it may still be running.
            with self.lock:
                self.state.update(phase="uncertain", error=str(error))
                self._send("stop")
            process.wait()
            with self.lock:
                self.state.update(active=False)
        finally:
            process.stdout.close()
            with self.lock:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()

    def _send(self, command):
        if self.state["active"] and self.process:
            try:
                self.process.stdin.write(json.dumps(dict(command=command)) + "\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.state.update(phase="uncertain", error="Control pipe unavailable; physical state unknown")

    def heartbeat(self, owner, run_id):
        with self.lock:
            if self.owner != owner or self.state.get("run_id") != run_id:
                raise PermissionError("This browser does not own the cart test")
            self._send("execute" if self.state["phase"] == "ready_for_execute" else "heartbeat")
            return self.status(owner)

    def stop(self, owner):
        with self.lock:
            self.pending.pop(owner, None)
            if self.owner == owner and self.state["active"]:
                self._send("stop")
                self.state["phase"] = "stopping"
            return self.status(owner)

    def cancel_review(self, owner):
        """Changing to an arm request cannot leave an unrelated cart approval available."""
        with self.lock:
            self.pending.pop(owner, None)

    def close(self):
        with self.lock:
            self.pending.clear()
            self._send("stop")
            if self.process and self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
