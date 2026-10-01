"""Coordinated finite robot playback: a separate process owns each serial bus.

No simulator, vision, model inference or disk IO runs in a motor dispatch loop.
The supervisor grants one common monotonic epoch only after all devices are ready.
"""

import json
import multiprocessing
import time
from dataclasses import dataclass
from types import SimpleNamespace

from takeone.calibration import ArmMapping
from takeone.cart.runtime import CartRunner, Timing
from takeone.config import read_json
from takeone.motion.arm import ArmRunner
from takeone.motion.limits import ArmTiming, measured_limits, preflight
from takeone.motion.plan import ROLES, load_plan
from takeone.paths import CONFIGS

DEVICES = (*ROLES, "cart")
WAITING, READY, DONE, FAILED = 0, 1, 2, -1


@dataclass
class Coordination:
    booted: object
    epoch: object
    supervisor: object
    cancel: object
    heartbeat: dict
    state: dict

    def pulse(self, role):
        self.heartbeat[role].value = time.monotonic()

    def check(self, role, duration_s, timing):
        supervisor_stamp = self.supervisor.value
        now = time.monotonic()
        if self.cancel.is_set():
            raise InterruptedError("Coordinated run cancelled")
        if not 0 <= now - supervisor_stamp <= timing.supervisor_lease_s:
            raise RuntimeError("Supervisor lease expired")
        epoch = self.epoch.value
        if epoch < 0 or now < epoch:
            return
        for other in DEVICES:
            if other == role:
                continue
            state = self.state[other].value
            if state == FAILED:
                raise RuntimeError(f"{other} worker failed")
            if state == DONE and now >= epoch + duration_s:
                continue
            peer_stamp = self.heartbeat[other].value
            if not 0 <= time.monotonic() - peer_stamp <= timing.peer_lease_s:
                raise RuntimeError(f"{other} feedback/dispatch lease expired")


def device_worker(role, plan, factory, limits, arm_timing, cart_timing, shared, folder):
    """Spawn entry point. Health timestamps publish only after successful device work."""
    device = runner = None
    failure = None

    def guard():
        shared.check(role, plan.duration_s, arm_timing)

    def pulse():
        shared.pulse(role)

    try:
        if not shared.booted.wait(arm_timing.startup_timeout_s):
            raise TimeoutError("Supervisor did not finish starting the workers")
        guard()
        device = factory.open(role, plan, arm_timing, cart_timing)
        if device.simulated is not factory.simulated:
            raise ValueError("Mixed physical and simulated devices are forbidden")
        if role == "cart":
            runner = CartRunner(
                device, cart_timing, cancelled=shared.cancel.is_set, guard=guard, heartbeat=pulse
            )

            def agree_epoch(writer):
                shared.state[role].value = READY
                while shared.epoch.value < 0:
                    due = writer.now() + cart_timing.period_s
                    writer.wait_until(due)
                    writer.send((0.0, 0.0), due, "ready_zero")
                return shared.epoch.value

            wheels = SimpleNamespace(
                times_s=plan.cart_times_s, duration_s=plan.duration_s, command_at=plan.command_at
            )
            runner.run(wheels, start_epoch=agree_epoch)
        else:
            runner = ArmRunner(device, role, plan, limits[role], arm_timing, guard=guard, heartbeat=pulse)
            while shared.epoch.value < 0 or time.monotonic() < shared.epoch.value - arm_timing.period_s:
                runner.ready()
                shared.state[role].value = READY
                runner.wait(time.monotonic() + arm_timing.period_s)
            runner.run(shared.epoch.value)
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)
        shared.state[role].value = FAILED
        shared.cancel.set()
        if role != "cart" and runner is not None:
            runner.fault = failure
            runner.hold_on_fault()
    finally:
        if device is not None:
            try:
                device.close() if role == "cart" else device.disconnect()
            except BaseException as error:
                failure = failure or "Close failed: " + str(error)
                shared.cancel.set()
        # Completion is published only after endpoints/zero window and disconnect.
        shared.state[role].value = FAILED if failure else DONE
        report = runner.report() if runner is not None else {}
        report.update(worker_error=failure, role=role)
        # Logs are written after leaving device control; no pipe can block dispatch.
        (folder / f"{role}.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


class RobotRunner:
    """One-shot coordinator. Live authorization/plan validation precedes construction.

    Windows is not a hard real-time OS. Deadline failures latch a fault. Arm
    processes never keep a failed session alive with background heartbeats.
    """

    def __init__(self, plan, factory, limits, timing=None, cart_timing=None):
        self.plan, self.factory, self.limits = plan, factory, limits
        self.timing, self.cart_timing = timing or ArmTiming.load(), cart_timing or Timing.load()
        self.used = False

    def run(self, folder):
        if self.used:
            raise RuntimeError("Robot runner is single-use; review before a new run")
        self.used = True
        load_plan(self.plan.to_dict())
        if not self.factory.simulated:
            blockers = preflight(self.plan, self.factory.devices["platform"])["blockers"]
            if blockers:
                raise ValueError("Physical execution blocked: " + "; ".join(blockers))
            profile = self.factory.devices["platform"]
            if self.factory.devices != read_json(CONFIGS / "devices" / f"{profile}.json"):
                raise ValueError("Execution device configuration changed after preflight")
            for role in ROLES:
                if self.factory.mappings[role] != ArmMapping.load(role) or self.limits[
                    role
                ] != measured_limits(role):
                    raise ValueError("Execution alignment/limits differ from verified files")
        for role in ROLES:
            mapping = None if self.factory.simulated else self.factory.mappings[role]
            self.limits[role].validate_plan(self.plan, role, self.timing, mapping)
        context = multiprocessing.get_context("spawn")
        # Each raw scalar has exactly one writer. Values are health signals, never
        # trajectories. No shared lock can let a blocked serial owner hold the cart.
        shared = Coordination(
            context.Event(),
            context.Value("d", -1, lock=False),
            context.Value("d", time.monotonic(), lock=False),
            context.Event(),
            {r: context.Value("d", 0, lock=False) for r in DEVICES},
            {r: context.Value("i", WAITING, lock=False) for r in DEVICES},
        )
        processes = {}
        error = None
        started = time.monotonic()
        try:
            for role in DEVICES:
                process = context.Process(
                    name=f"takeone-{role}",
                    target=device_worker,
                    args=(
                        role,
                        self.plan,
                        self.factory,
                        self.limits,
                        self.timing,
                        self.cart_timing,
                        shared,
                        folder,
                    ),
                )
                process.start()
                processes[role] = process
            shared.supervisor.value = time.monotonic()
            shared.booted.set()
            while True:
                now = time.monotonic()
                shared.supervisor.value = now
                if shared.cancel.is_set():
                    raise RuntimeError("A device worker rejected or faulted the run")
                if any(
                    p.exitcode is not None and shared.state[r].value != DONE for r, p in processes.items()
                ):
                    raise RuntimeError("A device worker exited before successful completion")
                if shared.epoch.value < 0:
                    if now - started > self.timing.startup_timeout_s:
                        raise TimeoutError("Robot readiness timed out")
                    if all(shared.state[r].value == READY for r in DEVICES):
                        if all(now - shared.heartbeat[r].value <= self.timing.peer_lease_s for r in DEVICES):
                            shared.epoch.value = now + self.timing.start_lead_s
                else:
                    for role in DEVICES:
                        if (
                            shared.state[role].value != DONE
                            and now - shared.heartbeat[role].value > self.timing.peer_lease_s
                        ):
                            raise RuntimeError(f"{role} worker stopped reporting fresh device work")
                    if now > shared.epoch.value + self.plan.duration_s + self.timing.settle_timeout_s + 1:
                        raise TimeoutError("Coordinated robot completion timed out")
                if all(shared.state[r].value == DONE for r in DEVICES):
                    break
                time.sleep(0.005)
        except BaseException as failure:
            error = type(failure).__name__ + ": " + str(failure)
            shared.cancel.set()
            shared.booted.set()
        finally:
            # Bound shutdown even when a USB SDK call never returns. Terminating a
            # process is not evidence of a physical arm stop; torque stays enabled.
            deadline = time.monotonic() + 1.0
            while any(p.is_alive() for p in processes.values()) and time.monotonic() < deadline:
                shared.supervisor.value = time.monotonic()
                time.sleep(0.005)
            terminated = []
            for role, process in processes.items():
                if process.is_alive():
                    process.terminate()
                    terminated.append(role)
                process.join(timeout=0.2)
                process.close()
        reports = {}
        for role in DEVICES:
            path = folder / f"{role}.json"
            if path.is_file():
                try:
                    reports[role] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    reports[role] = dict(worker_error="Completion report unreadable; physical state unknown")
            else:
                reports[role] = dict(worker_error="No completion report; physical state unknown")
            error = error or reports[role].get("worker_error")
        if terminated:
            error = error or "Unresponsive worker process terminated"
        return dict(
            plan_id=self.plan.plan_id,
            mode="simulated" if self.factory.simulated else "live",
            epoch_monotonic_s=shared.epoch.value if shared.epoch.value >= 0 else None,
            completed=error is None,
            error=error,
            terminated_workers=terminated,
            roles=reports,
            physical_cart_motion_verified=False,
            physical_stop_confirmed=False,
        )
