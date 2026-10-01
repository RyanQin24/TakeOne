"""Play a reviewed simulator shot on the real robot: joint counts out, timed wheel commands out.

The simulator has already solved the trajectory. This module converts its joint
angles to encoder counts once, up front, then streams them. No inverse kinematics,
no model evaluation and no qualification record is consulted in a dispatch loop.

Packet loss is tolerated on purpose. Goal_Position streams over SYNC_WRITE, one
broadcast packet that expects no reply. A lost packet costs a single 40 ms
setpoint: the servo holds its last goal and the next packet resumes the
trajectory. Stopping a moving robot over a dropped datagram is the less safe
choice, so the loops log misses and keep going. The cart's own firmware watchdog
is the independent brake if the host stops talking altogether.
"""

import argparse
import bisect
import json
import math
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.identity import identify_port
from takeone.adapters.uart import MotorUART
from takeone.calibration import ArmMapping
from takeone.config import read_json
from takeone.contracts import JOINTS
from takeone.paths import CONFIGS, DATA

ROLES = ("phone", "light")
SETTLE_S = 0.5
STOP_WINDOW_S = 0.5
MISS_LIMIT = 40
# The cart brakes if its firmware hears nothing for 60 ms. The compiled schedule
# changes at 20 ms, but re-sending the active command every 5 ms means a missed
# host wake-up still lands far inside the watchdog instead of jolting the rig to
# a stop mid-move. Ten bytes at 115200 baud is under 1 ms of wire time, so this
# keepalive costs under 2% of the line and needs a dozen consecutive missed
# wake-ups before the firmware would brake.
CART_TICK_S = 0.005


class Joints:
    """Calibrated encoder conversion for one arm. Clamps to range; never refuses."""

    def __init__(self, role):
        mapping = ArmMapping.load(role, require_motion=False)
        raw = mapping.raw_calibration
        self.role = role
        self.calibration = raw
        self.ids = {n: raw[n]["id"] for n in JOINTS}
        self.low = {n: raw[n]["range_min"] for n in JOINTS}
        self.high = {n: raw[n]["range_max"] for n in JOINTS}
        self.mid = {n: (self.low[n] + self.high[n]) / 2 for n in JOINTS}
        self.sign = dict(zip(JOINTS, mapping.signs))
        self.offset = dict(zip(JOINTS, mapping.offsets_deg))
        self.clamped = {n: 0 for n in JOINTS}

    def counts(self, q_rad):
        """Same arithmetic as the installed LeRobot degree mode, bounded by calibration."""
        result = {}
        for name, q in zip(JOINTS, q_rad):
            degrees = math.degrees(q) * self.sign[name] + self.offset[name]
            value = int(degrees * 4095 / 360 + self.mid[name])
            bounded = max(self.low[name], min(self.high[name], value))
            if bounded != value:
                self.clamped[name] += 1
            result[name] = bounded
        return result

    def degrees_apart(self, a, b):
        return max(abs(a[n] - b[n]) for n in JOINTS) * 360 / 4095


def load_shot(path):
    """Read the reviewed export. Identity and structure only; nothing is recompiled."""
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("schema") != "takeone.robot-plan.v2":
        raise ValueError("Expected a takeone.robot-plan.v2 export")
    samples, schedule = document["samples"], document["cart_schedule"]
    if len(samples) < 2 or len(schedule) < 2:
        raise ValueError("Shot needs arm samples and a wheel schedule")
    if float(document["arm_period_s"]) <= 0 or float(document["duration_s"]) <= 0:
        raise ValueError("Shot needs a positive period and duration")
    if tuple(document["joint_order"]) != JOINTS or tuple(document["roles"]) != ROLES:
        raise ValueError("Unsupported joint order or arm roles")
    if tuple(schedule[-1]["commands"]) != (0, 0):
        raise ValueError("Wheel schedule must finish stopped")
    return document


def approach_frames(start, target, period_s, rate_deg_s):
    """Cosine ease from the measured pose to the shot's first pose.

    Every joint runs the same eased profile, so the arm starts and finishes at
    zero velocity and no joint leads the others. A cosine peaks at pi/2 times its
    average rate, so size the duration from that peak rather than the average.
    """
    span = max(abs(target[n] - start[n]) for n in JOINTS) * 360 / 4095
    if span < 0.1:
        return []
    duration = max(2.0, math.pi * span / (2 * rate_deg_s))
    # Ceil, not round: rounding the tick count down shortens the move and pushes
    # the peak rate back above the limit the caller asked for.
    ticks = max(2, math.ceil(duration / period_s))
    return [
        {
            n: round(start[n] + (target[n] - start[n]) * (1 - math.cos(math.pi * i / ticks)) / 2)
            for n in JOINTS
        }
        for i in range(1, ticks + 1)
    ]


def build_timeline(shot, counts, starts, rate_deg_s):
    """One index-aligned count timeline per arm: approach, settle, shot, settle."""
    period = float(shot["arm_period_s"])
    settle = max(1, round(SETTLE_S / period))
    approaches = {r: approach_frames(starts[r], counts[r][0], period, rate_deg_s) for r in ROLES}
    lead = max(len(approaches[r]) for r in ROLES) + settle
    frames = {}
    for role in ROLES:
        pad = [counts[role][0]] * (lead - len(approaches[role]))
        frames[role] = approaches[role] + pad + list(counts[role]) + [counts[role][-1]] * settle
    return frames, lead * period, period


def _sleep_until(deadline, stop):
    """Absolute deadline wait that stays responsive to an operator stop.

    time.sleep is deliberate. On Windows it uses a high-resolution waitable
    timer, while threading.Event.wait falls back to the 15.6 ms scheduler tick:
    with Event.wait every 40 ms arm tick landed ~11 ms late and the cart's gap
    reached 57 ms against its 60 ms firmware watchdog.

    One long nap to just short of the deadline, then short ones. Capping every
    nap at 2 ms instead cost hundreds of extra GIL handoffs per second and left
    a whole thread a tick behind. A stop is noticed within one tick either way.
    """
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return not stop.is_set()
        if stop.is_set():
            return False
        time.sleep(remaining - 0.001 if remaining > 0.003 else min(remaining, 0.001))


@contextmanager
def fine_timers():
    """Hold 1 ms timer granularity, a short GIL slice and a raised host priority.

    The default 5 ms switch interval lets a compute-bound thread keep the GIL
    while a woken dispatch thread waits, which is enough to push the cart past
    its watchdog. Priority is best effort: losing it degrades timing margin, so
    it is reported rather than allowed to block a run. All three are restored
    on the way out.
    """
    from takeone.cart.runtime import host_timing_priority

    status = dict(timer_ms=None, switch_interval_s=0.001, priority=None)
    switch = sys.getswitchinterval()
    sys.setswitchinterval(0.001)
    winmm = None
    priority = host_timing_priority(enabled=True)
    try:
        if sys.platform == "win32":
            import ctypes

            winmm = ctypes.WinDLL("winmm")
            status["timer_ms"] = 1 if winmm.timeBeginPeriod(1) == 0 else None
        try:
            status["priority"] = priority.__enter__()
        except Exception as error:  # noqa: BLE001 - timing margin, never a blocker
            status["priority"] = dict(applied=False, error=str(error))
            priority = None
        yield status
    finally:
        if priority is not None:
            try:
                priority.__exit__(None, None, None)
            except Exception as error:  # noqa: BLE001
                status["priority_restore_error"] = str(error)
        if winmm is not None and status["timer_ms"]:
            winmm.timeEndPeriod(1)
        sys.setswitchinterval(switch)


class Arm:
    """Owns one servo bus: read present counts, stream goals, activate, release."""

    def __init__(self, role, device, joints, timeout_s=0.05):
        from lerobot.motors import Motor, MotorCalibration, MotorNormMode
        from lerobot.motors.feetech import FeetechMotorsBus

        if device["motor_ids"] != joints.ids:
            raise ValueError(f"{role}: configured motor IDs differ from the calibration")
        motors = {n: Motor(i, "sts3215", MotorNormMode.DEGREES) for n, i in joints.ids.items()}
        calibration = {n: MotorCalibration(**raw) for n, raw in joints.calibration.items()}
        self.role, self.joints = role, joints
        self.bus = FeetechMotorsBus(device["port"], motors, calibration=calibration)
        self.timeout_ms = int(timeout_s * 1000)
        self.active = False

    def open(self):
        # The handshake pings every expected ID and checks its model number; read-only.
        self.bus.connect()
        self.bus.set_timeout(self.timeout_ms)
        return self.present()

    def present(self):
        return {n: int(self.bus.read("Present_Position", n, normalize=False, num_retry=2)) for n in JOINTS}

    def goal(self, counts):
        """One TX-only broadcast for all five motors. No reply is expected or waited for."""
        self.bus.sync_write("Goal_Position", dict(counts), normalize=False)

    def activate(self, counts):
        """Goal, enable, same goal: torque comes up on the pose the arm is already in."""
        self.goal(counts)
        for name in JOINTS:
            self.bus.write("Torque_Enable", name, 1, normalize=False, num_retry=2)
        self.goal(counts)
        self.active = True

    def release(self):
        errors = []
        for name in JOINTS:
            try:
                self.bus.write("Torque_Enable", name, 0, normalize=False, num_retry=2)
            except Exception as error:  # noqa: BLE001 - try every motor, report the rest
                errors.append(f"{name}: {error}")
        self.active = False
        return errors

    def close(self):
        if self.bus.is_connected:
            self.bus.disconnect(disable_torque=False)


def stream_arms(arms, frames, period_s, epoch, stop, records):
    """Drive both arms from one thread: one setpoint each, per tick.

    Sharing a thread keeps the two arms in exact lockstep and halves the GIL
    handoffs a dispatch tick needs. Each sync_write is a ~20 byte packet on its
    own port, so both fit in well under a millisecond of the 40 ms budget.
    Late ticks skip forward; they never burst a backlog at the servos.

    Nothing is read here. A Present_Position sweep is ten serial round trips, and
    a Windows USB-serial latency timer can turn that into a stall far longer than
    one tick. Actual positions are sampled at the phase boundaries instead, where
    the arms are stationary and a slow reply costs nothing.
    """
    index = 0
    total = len(next(iter(frames.values())))
    consecutive = {role: 0 for role in arms}
    while index < total:
        if not _sleep_until(epoch + index * period_s, stop):
            break
        late = time.perf_counter() - (epoch + index * period_s)
        due = index + int(late / period_s)
        if due > index:
            # A position servo follows the newest goal, so superseded setpoints are
            # dropped rather than replayed behind the rest of the robot.
            for record in records.values():
                record["late_skips"] += due - index
            index = min(due, total - 1)
        for record in records.values():
            record["max_late_s"] = round(max(record["max_late_s"], late), 4)
        for role, arm in arms.items():
            record = records[role]
            try:
                arm.goal(frames[role][index])
                record["sent"] += 1
                # Recorded on the send, not after the loop: a stop can land while
                # the loop is waiting, and the operator needs the goal the arm is
                # actually frozen on, not the one it was about to receive.
                record["final_goal"] = frames[role][index]
                consecutive[role] = 0
            except Exception as error:  # noqa: BLE001 - a lost datagram is not a robot fault
                record["misses"] += 1
                consecutive[role] += 1
                if len(record["errors"]) < 20:
                    record["errors"].append(dict(index=index, error=str(error)))
                if consecutive[role] > MISS_LIMIT:
                    record["fault"] = f"{role}: {consecutive[role]} goal packets failed in a row"
                    stop.set()
        if stop.is_set():
            break
        index += 1


def drive_cart(cart, times, commands, lead_s, duration_s, period_s, epoch, stop, record):
    """Re-send the active wheel command every tick so the firmware watchdog never trips."""
    index = 0
    previous = None
    consecutive = 0
    try:
        while True:
            elapsed = index * period_s
            if elapsed >= lead_s + duration_s:
                break
            if not _sleep_until(epoch + elapsed, stop):
                break
            # Select from the shared clock after waking. Never replay overdue
            # wheel packets in a burst while the arms have already skipped ahead.
            elapsed = max(elapsed, time.perf_counter() - epoch)
            if elapsed >= lead_s + duration_s:
                break
            shot_t = elapsed - lead_s
            pair = (0.0, 0.0) if shot_t < 0 else commands[bisect.bisect_right(times, shot_t) - 1]
            try:
                now = time.perf_counter()
                cart.set_speed(*pair)
                # The gap between consecutive packets is what the firmware watchdog
                # actually measures, so record the worst one this run saw.
                if previous is not None:
                    record["max_gap_s"] = round(max(record["max_gap_s"], now - previous), 4)
                previous = now
                consecutive = 0
                record["sent"] += 1
                if pair != (0.0, 0.0):
                    record["moving_writes"] += 1
            except Exception as error:  # noqa: BLE001 - the watchdog brakes if this persists
                record["misses"] += 1
                consecutive += 1
                if len(record["errors"]) < 20:
                    record["errors"].append(dict(t_s=round(elapsed, 3), error=str(error)))
                if consecutive >= 3:
                    record["fault"] = "Cart transport failed three consecutive writes"
                    stop.set()
                    break
            index = max(index + 1, math.floor((time.perf_counter() - epoch) / period_s) + 1)
    finally:
        # Hold an explicit stop for several watchdog intervals, whatever happened above.
        end = time.perf_counter() + STOP_WINDOW_S
        while time.perf_counter() < end:
            try:
                cart.set_speed(0.0, 0.0)
                record["stop_writes"] += 1
            except Exception as error:  # noqa: BLE001
                if len(record["errors"]) < 20:
                    record["errors"].append(dict(phase="stop", error=str(error)))
            time.sleep(period_s)


def summarise(counts, joints, starts=None):
    rows = {}
    for role in ROLES:
        rows[role] = {}
        for name in JOINTS:
            values = [c[name] for c in counts[role]]
            steps = [abs(b - a) for a, b in zip(values, values[1:])]
            entry = dict(
                calibration=[joints[role].low[name], joints[role].high[name]],
                plan_min=min(values),
                plan_max=max(values),
                max_step_counts=max(steps, default=0),
                clamped_samples=joints[role].clamped[name],
            )
            if starts:
                entry["now"] = starts[role][name]
                entry["approach_deg"] = round(abs(values[0] - starts[role][name]) * 360 / 4095, 1)
            rows[role][name] = entry
    return rows


def run(shot, profile, rate_deg_s, folder, *, stop_event=None, emit=lambda event: None, interactive=True):
    """Hold 1 ms timer granularity for the whole session, including port setup."""
    with fine_timers() as timers:
        return _play(
            shot,
            profile,
            rate_deg_s,
            folder,
            timers,
            stop_event=stop_event,
            emit=emit,
            interactive=interactive,
        )


def _play(
    shot, profile, rate_deg_s, folder, timers, *, stop_event=None, emit=lambda event: None, interactive=True
):
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    cart_device = devices["cart"]
    cart_runtime = read_json(CONFIGS / "cart-runtime.json")
    cart_period = min(CART_TICK_S, cart_runtime["watchdog_s"] / 4)
    polarity = cart_runtime.get("wire_polarity", 1)
    joints = {r: Joints(r) for r in ROLES}
    counts = {r: [joints[r].counts(s["arms"][r]) for s in shot["samples"]] for r in ROLES}
    for role in ROLES:
        identify_port(devices["arms"][role]["port"], devices["arms"][role]["usb_serial"])
    identify_port(cart_device["port"], cart_device["usb_serial"])

    arms, cart, starts = {}, None, {}
    report = dict(
        shot=shot["plan_id"],
        duration_s=shot["duration_s"],
        started_utc=datetime.now(timezone.utc).isoformat(),
        completed=False,
        arms={},
        cart=dict(sent=0, misses=0, moving_writes=0, stop_writes=0, max_gap_s=0.0, errors=[]),
    )
    stop = stop_event if stop_event is not None else threading.Event()
    threads = []

    def check_stop():
        if stop.is_set():
            raise InterruptedError("Playback stopped by the operator or browser connection")

    try:
        check_stop()
        for role in ROLES:
            check_stop()
            arms[role] = Arm(role, devices["arms"][role], joints[role])
            starts[role] = arms[role].open()
            if set(starts[role]) != set(JOINTS) or any(
                not joints[role].low[n] <= starts[role][n] <= joints[role].high[n] for n in JOINTS
            ):
                raise ValueError(f"{role}: measured starting position is outside its calibration")
            print(json.dumps(dict(phase="start_encoders", role=role, counts=starts[role])), flush=True)

        frames, lead_s, period = build_timeline(shot, counts, starts, rate_deg_s)
        report["approach_s"] = round(lead_s, 2)
        report["encoder_plan"] = summarise(counts, joints, starts)
        print(
            json.dumps(
                dict(
                    phase="ready",
                    approach_s=round(lead_s, 2),
                    shot_s=shot["duration_s"],
                    total_s=round(lead_s + shot["duration_s"] + SETTLE_S, 2),
                    ticks=len(frames["phone"]),
                    approach_deg={
                        r: round(joints[r].degrees_apart(starts[r], counts[r][0]), 1) for r in ROLES
                    },
                )
            ),
            flush=True,
        )
        cart = MotorUART(
            cart_device["port"],
            baudrate=cart_device["baudrate"],
            timeout=cart_device["timeout_s"],
            write_timeout=cart_runtime["write_timeout_s"],
            polarity=polarity,
        )
        report["wire_polarity"] = polarity
        cart.connect()
        cart.stop()
        for role in ROLES:
            check_stop()
            arms[role].activate(starts[role])
        print(
            "Torque on at the measured pose. Moving in 2 s. Ctrl+C stops the cart and freezes the arms.",
            flush=True,
        )
        emit(dict(phase="countdown", approach_s=lead_s, duration_s=shot["duration_s"]))
        if not _sleep_until(time.perf_counter() + 2.0, stop):
            check_stop()

        epoch = time.perf_counter() + 0.1
        report["host_tuning"] = timers
        for role in ROLES:
            report["arms"][role] = dict(
                sent=0, misses=0, late_skips=0, max_late_s=0.0, final_goal=None, errors=[], fault=None
            )
        threads = [
            threading.Thread(
                target=stream_arms,
                args=(arms, frames, period, epoch, stop, report["arms"]),
                name="arms",
            )
        ]
        threads.append(
            threading.Thread(
                target=drive_cart,
                args=(
                    cart,
                    [float(s["time_s"]) for s in shot["cart_schedule"]],
                    [tuple(float(v) for v in s["commands"]) for s in shot["cart_schedule"]],
                    lead_s,
                    float(shot["duration_s"]),
                    cart_period,
                    epoch,
                    stop,
                    report["cart"],
                ),
                name="cart",
            )
        )
        for thread in threads:
            thread.start()
        try:
            while any(t.is_alive() for t in threads):
                elapsed = max(0.0, time.perf_counter() - epoch)
                emit(
                    dict(
                        phase="stopping"
                        if stop.is_set()
                        else "positioning"
                        if elapsed < lead_s
                        else "running",
                        elapsed_s=max(0.0, min(float(shot["duration_s"]), elapsed - lead_s)),
                        approach_s=lead_s,
                        duration_s=shot["duration_s"],
                    )
                )
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nStopping: cart to zero, arms freeze at their last goal.", flush=True)
            stop.set()
            report["operator_stop"] = True
        for thread in threads:
            thread.join()
        # Both arms are stationary now, so a slow reply costs nothing here.
        for role, arm in arms.items():
            record = report["arms"][role]
            try:
                actual = arm.present()
                record["final_actual"] = actual
                if record["final_goal"] is not None:
                    record["final_error_deg"] = round(
                        joints[role].degrees_apart(record["final_goal"], actual), 2
                    )
            except Exception as error:  # noqa: BLE001 - the log, not the run, depends on this
                record["final_actual_error"] = str(error)
        report["completed"] = (
            not stop.is_set()
            and not report["cart"].get("fault")
            and not any(report["arms"][r]["fault"] for r in ROLES)
        )
        print(json.dumps(dict(phase="motion_finished", completed=report["completed"])), flush=True)
    except (KeyboardInterrupt, InterruptedError):
        # Ctrl+C before the threads start, during port setup or the countdown.
        stop.set()
        report["operator_stop"] = True
        print("\nStopped before the shot finished.", flush=True)
    finally:
        stop.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join()
        if cart is not None:
            try:
                cart.stop()
            except Exception as error:  # noqa: BLE001 - still close all owners and preserve arm torque
                report["stop_error"] = str(error)
                report["completed"] = False
            finally:
                cart.close()
        if any(a.active for a in arms.values()):
            answer = "hold"
            if interactive:
                print(
                    "\nSupport BOTH arms now, then press Enter to release torque"
                    " (type hold then Enter to leave torque on).",
                    flush=True,
                )
                try:
                    answer = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    # A lost operator channel never confirms a supported release.
                    answer = "hold"
            if answer == "hold":
                report["release"] = "torque left enabled; release with Run-Robot.ps1 -Release"
            else:
                errors = [e for a in arms.values() for e in a.release()]
                report["release"] = "errors: " + "; ".join(errors) if errors else "torque off on all motors"
            print(report["release"], flush=True)
        for arm in arms.values():
            arm.close()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["directory"] = str(folder)
    return report


def probe(profile, shot=None, rate_deg_s=25.0):
    """Read the real robot without moving it.

    Opens every port, reads each servo's live encoder, supply voltage, temperature
    and torque state, and opens the cart port to send a stop. No torque is enabled
    and no motion goal is written. With a shot, also reports how far each arm would
    have to travel to reach its first pose.
    """
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    result = dict(arms={}, cart={}, motion_commands_sent=False, torque_enabled=False)
    joints = {role: Joints(role) for role in ROLES}
    starts = {}
    for role in ROLES:
        device = devices["arms"][role]
        result["arms"][role] = entry = dict(
            port=device["port"], usb=identify_port(device["port"], device["usb_serial"])
        )
        arm = Arm(role, device, joints[role])
        try:
            starts[role] = arm.open()
            entry["encoders"] = starts[role]
            for register in ("Present_Voltage", "Present_Temperature", "Torque_Enable", "Present_Load"):
                entry[register] = {
                    name: int(arm.bus.read(register, name, normalize=False, num_retry=2)) for name in JOINTS
                }
            # The STS3215 reports tenths of a volt.
            volts = [v / 10 for v in entry["Present_Voltage"].values()]
            entry["supply_v"] = dict(low=min(volts), high=max(volts))
            entry["holding_torque"] = any(entry["Torque_Enable"].values())
            entry["at_calibration_edge"] = [
                name
                for name in JOINTS
                if starts[role][name] in (joints[role].low[name], joints[role].high[name])
            ]
        finally:
            arm.close()
    cart_device = devices["cart"]
    result["cart"] = dict(
        port=cart_device["port"], usb=identify_port(cart_device["port"], cart_device["usb_serial"])
    )
    transport = MotorUART(
        cart_device["port"],
        baudrate=cart_device["baudrate"],
        timeout=cart_device["timeout_s"],
        write_timeout=cart_device["timeout_s"],
        polarity=read_json(CONFIGS / "cart-runtime.json").get("wire_polarity", 1),
    )
    transport.connect()
    try:
        result["cart"]["stop_packet"] = transport.stop().strip()
    finally:
        transport.close()
    if shot is not None:
        counts = {r: [joints[r].counts(s["arms"][r]) for s in shot["samples"]] for r in ROLES}
        frames, lead_s, _ = build_timeline(shot, counts, starts, rate_deg_s)
        result["approach"] = dict(
            seconds=round(lead_s, 2),
            total_seconds=round(lead_s + float(shot["duration_s"]) + SETTLE_S, 2),
            per_arm={
                role: {
                    name: dict(
                        now=starts[role][name],
                        first=counts[role][0][name],
                        travel_deg=round(abs(counts[role][0][name] - starts[role][name]) * 360 / 4095, 1),
                    )
                    for name in JOINTS
                }
                for role in ROLES
            },
        )
        result["encoder_plan"] = summarise(counts, joints, starts)
    return result


def release_only(profile):
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    results = {}
    for role in ROLES:
        arm = Arm(role, devices["arms"][role], Joints(role))
        try:
            arm.open()
            errors = arm.release()
            results[role] = "; ".join(errors) if errors else "torque off"
        finally:
            arm.close()
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Play a reviewed simulator shot on the real robot")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--profile", choices=("windows", "linux"), default="windows")
    parser.add_argument("--go", action="store_true", help="Open the serial ports and move the robot")
    parser.add_argument("--release", action="store_true", help="Only turn torque off on both arms")
    parser.add_argument(
        "--probe", action="store_true", help="Read the real robot without enabling torque or moving"
    )
    parser.add_argument("--approach-deg-s", type=float, default=25.0)
    args = parser.parse_args(argv)

    if args.release:
        print(json.dumps(release_only(args.profile), indent=2))
        return 0
    if args.probe:
        shot = load_shot(args.plan) if args.plan else None
        print(json.dumps(probe(args.profile, shot, args.approach_deg_s), indent=2))
        return 0
    if not args.plan:
        parser.error("--plan is required")
    shot = load_shot(args.plan)
    if not args.go:
        joints = {r: Joints(r) for r in ROLES}
        counts = {r: [joints[r].counts(s["arms"][r]) for s in shot["samples"]] for r in ROLES}
        print(
            json.dumps(
                dict(
                    shot=shot["plan_id"],
                    duration_s=shot["duration_s"],
                    arm_period_s=shot["arm_period_s"],
                    arm_setpoints=len(shot["samples"]),
                    wheel_commands=len(shot["cart_schedule"]),
                    encoder_plan=summarise(counts, joints),
                    ports_opened=False,
                    hint="Add --go to open the serial ports and move the robot",
                ),
                indent=2,
            )
        )
        return 0
    if not sys.stdin.isatty():
        raise ValueError("Moving the robot needs an interactive terminal for stop and release")
    folder = DATA / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-play")
    report = run(shot, args.profile, args.approach_deg_s, folder)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("shot", "completed", "approach_s", "duration_s", "release", "directory")
                if k in report
            },
            indent=2,
        )
    )
    return 0 if report.get("completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
