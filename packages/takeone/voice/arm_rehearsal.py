"""Session-local rehearsal context. Only an explicit operator route captures encoders."""

import json
import os
import secrets
import subprocess
import threading
import time

from takeone.motion.studio import runtime_python, worker_environment
from takeone.paths import DATA, WORKSPACE
from takeone.planning.arm_program import compile_program, rehearsal_pose
from takeone.voice.arm_program import prepare_program


def read_snapshot():
    folder = DATA / "arm-snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (secrets.token_hex(12) + ".json")
    try:
        result = subprocess.run(
            [str(runtime_python()), "-m", "takeone.motion.arm_snapshot", "--output", str(path)],
            cwd=WORKSPACE,
            env=worker_environment(),
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Read-only inspection timed out; no motion or simulated fallback") from error
    path.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError(
            "Read-only arm inspection failed. Check power, ownership and the saved inspection log; no simulated fallback."
        )
    return json.loads(path.read_text(encoding="utf-8"))


class ArmRehearsal:
    def __init__(self, *, snapshot_reader=read_snapshot, clock=time.monotonic):
        self.reader, self.clock = snapshot_reader, clock
        self.lock = threading.RLock()
        self.contexts = {}

    def set_pose(self, owner, source):
        if source not in ("simulated", "measured_snapshot"):
            raise ValueError("Choose simulated or measured_snapshot")
        with self.lock:
            self.contexts = {k: v for k, v in self.contexts.items() if self.clock() - v["captured_s"] <= 120}
            self.contexts.pop(owner, None)
            if len(self.contexts) >= 16:
                raise ValueError("Too many rehearsal sessions")
            snapshot = self.reader() if source == "measured_snapshot" else None
            qpos = snapshot["qpos"] if snapshot else rehearsal_pose()
            self.contexts[owner] = dict(qpos=qpos, source=source, captured_s=self.clock(), latest=None)
            return dict(
                ok=True,
                pose_source=source,
                qpos=qpos,
                hardware_commands_sent=False,
                message="Starting pose selected for offline rehearsal only. No physical movement; no camera opened.",
            )

    def prepare(self, owner, request):
        with self.lock:
            context = self.contexts.get(owner)
            if context:
                context["latest"] = None  # A correction always revokes the old preview.
            prepared = prepare_program(request)
            if prepared["program"]["questions"]:
                return prepared
            if context is None:
                return prepared | dict(
                    code="arm_pose_required",
                    message="Choose a simulated start or click Read arm encoders on the page. No movement was sent.",
                )
            if self.clock() - context["captured_s"] > 120:
                raise ValueError("Rehearsal pose expired; explicitly capture/select another start")
            result = compile_program(request, context["qpos"], pose_source=context["source"])
            context["latest"] = result
            # Keep large curves/provenance and frames local, not in the model context.
            return {k: v for k, v in result.items() if k not in ("document", "frames")}

    def review(self, owner):
        with self.lock:
            context = self.contexts.get(owner)
            if not context or not context["latest"]:
                return dict(ok=True, review=None)
            return dict(ok=True, review=context["latest"])

    def close(self, owner):
        with self.lock:
            self.contexts.pop(owner, None)
