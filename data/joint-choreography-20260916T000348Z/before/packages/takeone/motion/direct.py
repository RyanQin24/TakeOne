"""Explicit playback of a direct raw-motor rehearsal on the configured robot."""

import argparse
import json
import math
import queue
import sys
import threading
import time
from pathlib import Path

from takeone.adapters.identity import identify_port
from takeone.adapters.lerobot_arm import openable_arm
from takeone.adapters.uart import MotorUART
from takeone.calibration import ArmMapping
from takeone.config import read_json
from takeone.contracts import JOINTS
from takeone.direct import ROLES, calibrated_positions
from takeone.paths import CONFIGS


def load_direct_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if plan.get("schema") != "take-one.direct-joint-rehearsal.v1" or not plan.get("directJointMode"):
        raise ValueError("Expected a direct raw-joint rehearsal export")
    frames = plan.get("frames")
    if not isinstance(frames, list) or len(frames) < 2:
        raise ValueError("Direct plan needs at least two frames")
    duration = plan.get("settings", {}).get("duration")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Direct plan duration is invalid")
    previous = -1.0
    for frame in frames:
        stamp = frame.get("time_s")
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp <= previous:
            raise ValueError("Direct frame times must be finite and strictly increasing")
        previous = stamp
        raw_by_role = frame.get("rawByRole")
        if not isinstance(raw_by_role, dict):
            raise ValueError("Direct frame is missing raw motor values")
        for role in ROLES:
            mapping, ranges, _ = calibrated_positions(role)
            raw = raw_by_role.get(role)
            if not isinstance(raw, dict) or set(raw) != set(JOINTS):
                raise ValueError(f"{role}: direct frame must contain all five raw motor values")
            mapping.from_raw(raw)
            if any(not ranges[name][0] <= raw[name] <= ranges[name][1] for name in JOINTS):
                raise ValueError(f"{role}: raw motor value is outside its calibration")
    if previous != duration:
        raise ValueError("Direct frames must end exactly at the declared duration")
    for role in ROLES:
        _, ranges, midpoints = calibrated_positions(role)
        expected = {
            "ranges": {name: list(bounds) for name, bounds in ranges.items()},
            "midpoints": midpoints,
        }
        if plan.get("calibration", {}).get(role) != expected:
            raise ValueError(f"{role}: export does not match the calibration currently installed")
        if frames[0]["rawByRole"][role] != midpoints or frames[-1]["rawByRole"][role] != midpoints:
            raise ValueError(f"{role}: direct plan must start and finish at calibrated midpoints")
    commands = plan.get("motorCommands")
    if not isinstance(commands, list) or len(commands) < 2 or commands[-1].get("wire") != "0.00,0.00\n":
        raise ValueError("Direct plan needs a finite cart schedule ending in zero")
    return plan


def _wait(epoch, offset, stopped):
    while not stopped.is_set():
        remaining = epoch + offset - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.002))


def _arm_worker(role, arm, mapping, frames, epoch, stopped, failures):
    try:
        previous = dict(frames[0]["rawByRole"][role])
        for frame in frames:
            _wait(epoch, frame["time_s"], stopped)
            if stopped.is_set():
                return
            raw = frame["rawByRole"][role]
            mapping.from_raw(raw)
            for name in JOINTS:
                if raw[name] != previous[name]:
                    arm.bus.write("Goal_Position", name, raw[name], normalize=False, num_retry=3)
                    arm.last_raw_goal[name] = raw[name]
            previous = dict(raw)
    except BaseException as error:
        failures.put((role, error))
        stopped.set()


def _cart_worker(cart, commands, epoch, stopped, failures):
    try:
        for item in commands:
            _wait(epoch, item["time"], stopped)
            if stopped.is_set():
                return
            left, right = (float(value) for value in item["wire"].strip().split(","))
            if cart.set_speed(left, right) != item["wire"]:
                raise RuntimeError("Cart transport returned a different wire packet")
    except BaseException as error:
        failures.put(("cart", error))
        stopped.set()


def _write_all_direct(arm, register, values):
    trace = arm.lifecycle.setdefault("direct_activation_writes", [])
    for name in JOINTS:
        event = {
            "register": register,
            "joint": name,
            "raw_value": values[name],
            "write_start_s": arm.clock(),
            "acknowledged": False,
        }
        trace.append(event)
        try:
            arm.bus.write(register, name, values[name], normalize=False, num_retry=5)
            event.update(write_end_s=arm.clock(), acknowledged=True)
        except BaseException as error:
            event.update(write_end_s=arm.clock(), error=str(error))
            raise


def _activate_exported_midpoint(arm, targets):
    """Enable position mode directly on the exported raw midpoint goals."""
    _write_all_direct(arm, "Goal_Position", targets)
    if arm._read_all("Goal_Position") != targets:
        raise RuntimeError("Direct midpoint goals were not stored while torque was off")
    arm.lifecycle["torque_enable_attempted"] = True
    _write_all_direct(arm, "Torque_Enable", dict.fromkeys(JOINTS, 1))
    if any(value != 1 for value in arm._read_all("Torque_Enable").values()):
        raise RuntimeError("Direct midpoint torque enable was not confirmed")
    _write_all_direct(arm, "Goal_Position", targets)
    if arm._read_all("Goal_Position") != targets:
        raise RuntimeError("Active direct midpoint goals were not stored")
    arm.last_raw_goal = dict(targets)
    arm.active = True


def execute(plan, profile):
    if not sys.stdin.isatty():
        raise ValueError("Direct hardware motion requires an interactive terminal")
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    arm_timing = read_json(CONFIGS / "arm-execution.json")
    opened = {}
    cart = None
    stopped = threading.Event()
    failures = queue.SimpleQueue()
    try:
        for role in ROLES:
            device = devices["arms"][role]
            identify_port(device["port"], device["usb_serial"])
            mapping = ArmMapping.load(role, require_motion=False)
            arm = openable_arm(device, mapping, arm_timing["io_limit_s"])
            opened[role] = (arm, mapping)
            _activate_exported_midpoint(arm, plan["calibration"][role]["midpoints"])

        cart_device = devices["cart"]
        identify_port(cart_device["port"], cart_device["usb_serial"])
        cart = MotorUART(
            cart_device["port"],
            baudrate=cart_device["baudrate"],
            timeout=cart_device["timeout_s"],
            write_timeout=cart_device["timeout_s"],
        )
        cart.connect()
        cart.stop()
        print("Direct owners active. Starting exact raw sequence in 1 second. Ctrl+C stops the cart.")
        epoch = time.perf_counter() + 1.0
        arms_are_fixed = all(
            all(
                frame["rawByRole"][role] == plan["calibration"][role]["midpoints"] for frame in plan["frames"]
            )
            for role in ROLES
        )
        threads = []
        if not arms_are_fixed:
            threads.extend(
                threading.Thread(
                    target=_arm_worker,
                    args=(role, arm, mapping, plan["frames"], epoch, stopped, failures),
                    name=f"direct-{role}",
                )
                for role, (arm, mapping) in opened.items()
            )
        threads.append(
            threading.Thread(
                target=_cart_worker,
                args=(cart, plan["motorCommands"], epoch, stopped, failures),
                name="direct-cart",
            )
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if not failures.empty():
            role, error = failures.get()
            raise RuntimeError(f"{role}: {error}")
        print(
            "Direct sequence finished at calibrated midpoints. Support both arms, then press Enter to release."
        )
        input()
    except KeyboardInterrupt:
        stopped.set()
        print("Stopping direct sequence.")
    finally:
        stopped.set()
        if cart is not None:
            try:
                cart.stop()
            finally:
                cart.close()
        for arm, _ in opened.values():
            try:
                arm.release_supported()
            finally:
                arm.disconnect()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Play exact direct raw motor values; no IK or plan limits")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--profile", choices=("windows", "linux"), default="windows")
    parser.add_argument("--confirm-plan")
    parser.add_argument("--operator-ready", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    plan = load_direct_plan(args.plan)
    summary = {
        "plan_id": plan["planId"],
        "duration_s": plan["settings"]["duration"],
        "frames": len(plan["frames"]),
        "cart_wire": plan["motorCommands"][0]["wire"].strip(),
        "phone_midpoints": plan["calibration"]["phone"]["midpoints"],
        "light_midpoints": plan["calibration"]["light"]["midpoints"],
        "ik_solves": 0,
        "hardware_commands_sent": False,
    }
    if not args.execute:
        print(json.dumps(summary, indent=2))
        return 0
    if not args.operator_ready or args.confirm_plan != plan["planId"]:
        raise ValueError("Execution requires --operator-ready and the exact --confirm-plan ID")
    print(json.dumps(summary | {"hardware_commands_starting": True}, indent=2), flush=True)
    execute(plan, args.profile)
    print(json.dumps(summary | {"hardware_commands_sent": True, "completed": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
