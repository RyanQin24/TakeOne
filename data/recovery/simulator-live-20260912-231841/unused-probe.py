"""Explicit small joint-space hardware trial; no IK, saved shot or simulated bus.

Both shoulder pans move 34 encoder counts out and back. Other goals stay fixed.
The cart sends 0.04 to both wheels for one second during the arm plateau.
This diagnoses real actuation; it does not qualify a cinematic trajectory.
"""

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone

from takeone.adapters.identity import identify_port
from takeone.adapters.lerobot_arm import openable_arm
from takeone.adapters.uart import MotorUART
from takeone.cart.plan import prepare_command_test
from takeone.cart.runtime import CartRunner, Timing, check_commissioning, host_timing_priority
from takeone.config import read_json
from takeone.contracts import JOINTS
from takeone.motion.limits import execution_mapping
from takeone.motion.service import console_commands
from takeone.paths import CONFIGS, DATA


def pan_offset(elapsed):
    if elapsed <= 0 or elapsed >= 5:
        return 0
    u = elapsed / 2 if elapsed < 2 else (5 - elapsed) / 2 if elapsed > 3 else 1
    return round(34 * u**3 * (10 - 15 * u + 6 * u * u))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-ready", action="store_true")
    args = parser.parse_args(argv)
    if not args.operator_ready or not sys.stdin.isatty():
        parser.error("Use --operator-ready in an interactive terminal; abort/release remain available")
    operator = console_commands()
    folder = DATA / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-small-motion")
    folder.mkdir(parents=True)
    devices = read_json(CONFIGS / "devices/windows.json")
    if devices["hardware_enabled"] is not True:
        raise ValueError("Windows hardware profile is disabled")
    arms, samples, states, initial, threads, errors = {}, {}, {}, {}, [], []
    stop, release = threading.Event(), threading.Event()
    cart = runner = None
    epoch = None
    emitted_hold = False
    report = dict(
        mode="real-small-joint-space-trial",
        cart_physical_travel_verified=False,
        requested_pan_counts=34,
        requested_cart_command=[0.04, 0.04],
        requested_cart_duration_s=1,
        cinematic_shot_executed=False,
        directory=str(folder),
    )

    def emit(value):
        print(json.dumps(value), flush=True)

    def save():
        result = report | dict(
            initial_raw=initial,
            errors=errors,
            states=states,
            arm_samples=samples,
            arm_lifecycle={r: a.lifecycle for r, a in arms.items()},
            release_requested=release.is_set(),
            cart=runner.report() if runner else None,
        )
        (folder / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    def arm_worker(role):
        arm = arms[role]
        next_tick = epoch
        try:
            while not release.is_set():
                now = time.perf_counter()
                if now < next_tick:
                    release.wait(min(0.01, next_tick - now))
                    continue
                if now - next_tick > 0.04:
                    raise RuntimeError(f"{role}: arm update missed its 40 ms deadline")
                started = now
                observation = arm.read()
                raw = observation.raw_positions
                goal = dict(arm.last_raw_goal)
                if any(abs(raw[n] - goal[n]) > 65 for n in JOINTS):
                    raise RuntimeError(f"{role}: tracking error exceeds 65 encoder counts")
                elapsed = now - epoch
                if not stop.is_set() and elapsed <= 5.08:
                    value = initial[role]["shoulder_pan"] + pan_offset(elapsed)
                    arm.bus.write("Goal_Position", "shoulder_pan", value, normalize=False, num_retry=0)
                    arm.last_raw_goal["shoulder_pan"] = value
                states[role] = "holding" if stop.is_set() or elapsed >= 5 else "moving"
                if len(samples[role]) < 1500:
                    samples[role].append(
                        dict(elapsed_s=elapsed, raw=raw, acknowledged_goal=dict(arm.last_raw_goal))
                    )
                if time.perf_counter() - started > 0.04:
                    raise RuntimeError(f"{role}: arm read/write exceeded 40 ms")
                next_tick += 0.04
        except BaseException as error:
            errors.append(str(error))
            stop.set()
            states[role] = "fault_hold"
            emit(dict(phase="device_error", role=role, error=str(error)))
        finally:
            release.wait()
            try:
                arm.release_supported()
                states[role] = "released"
            except BaseException as error:
                errors.append(f"{role} release: {error}")
            arm.disconnect()

    def cart_worker(plan):
        try:
            with host_timing_priority():
                runner.run(plan, start_epoch=lambda writer: epoch + 2)
            states["cart"] = "zero_sent"
        except BaseException as error:
            errors.append(str(error))
            stop.set()
            states["cart"] = "fault"
            emit(dict(phase="device_error", role="cart", error=str(error)))
        finally:
            cart.close()

    try:
        emit(dict(phase="opening_real_devices", directory=str(folder)))
        for role in ("phone", "light"):
            device = devices["arms"][role]
            identify_port(device["port"], device["usb_serial"])
            mapping = execution_mapping(role, "commissioning")
            arm = openable_arm(device, mapping, 0.025)
            arms[role] = arm
            observation = arm.read()
            initial[role] = dict(observation.raw_positions)
            target = initial[role]["shoulder_pan"] + 34
            if (
                not mapping.raw_calibration["shoulder_pan"]["range_min"]
                <= target
                <= mapping.raw_calibration["shoulder_pan"]["range_max"]
            ):
                raise ValueError(f"{role}: small pan target exceeds calibration")
            samples[role] = []
            states[role] = "connected"
            emit(dict(phase="real_start", role=role, raw=initial[role], target_pan_raw=target))
        timing = Timing.load()
        cart_plan = prepare_command_test(0.04, 1)
        check_commissioning(cart_plan)
        device = devices["cart"]
        identify_port(device["port"], device["usb_serial"])
        cart = MotorUART(
            device["port"], device["baudrate"], timing.write_timeout_s, write_timeout=timing.write_timeout_s
        )
        cart.connect()
        cart.stop()
        runner = CartRunner(cart, timing, cancelled=stop.is_set)
        for role, arm in arms.items():
            fresh = arm.read()
            if any(abs(fresh.raw_positions[n] - initial[role][n]) > 3 for n in JOINTS):
                raise ValueError(f"{role}: arm moved during preparation")
            initial[role] = dict(fresh.raw_positions)
            arm.activate(fresh, (0.035,) * 5)
        epoch = time.perf_counter() + 0.3
        for role in arms:
            thread = threading.Thread(target=arm_worker, args=(role,), daemon=True)
            thread.start()
            threads.append(thread)
        thread = threading.Thread(target=cart_worker, args=(cart_plan,), daemon=True)
        thread.start()
        threads.append(thread)
        emit(
            dict(
                phase="running", duration_s=5, command="abort stops travel; support both arms before release"
            )
        )
        last_progress = 0
        while not release.is_set():
            command = operator()
            if command in ("abort", "release", "detach"):
                stop.set()
                if command == "release":
                    release.set()
                elif command == "detach":
                    raise RuntimeError("Operator terminal disconnected; torque state retained")
            elapsed = time.perf_counter() - epoch
            holding = elapsed > 5.1 or stop.is_set()
            if holding and not emitted_hold:
                emitted_hold = True
                save()
                emit(
                    dict(
                        phase="holding",
                        states=states,
                        errors=errors,
                        instructions="Support BOTH arms, then type release.",
                    )
                )
            elif not holding and elapsed >= last_progress:
                emit(dict(phase="moving", elapsed_s=round(elapsed, 2), states=states))
                last_progress += 1
            time.sleep(0.01)
    except BaseException as error:
        stop.set()
        errors.append(str(error))
        emit(dict(phase="error", error=str(error)))
        if any(a.lifecycle.get("torque_enable_attempted") for a in arms.values()) and sys.stdin.isatty():
            emit(dict(phase="holding", instructions="Support BOTH arms, then type release."))
            while not release.is_set():
                if operator() == "release":
                    release.set()
                time.sleep(0.02)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=2)
        for role, arm in arms.items():
            if not threads and release.is_set() and arm.lifecycle.get("torque_enable_attempted"):
                try:
                    arm.release_supported()
                except Exception as error:
                    errors.append(str(error))
            if not threads:
                arm.disconnect()
        if cart and cart.connected:
            try:
                cart.stop()
            finally:
                cart.close()
        save()
    emit(dict(phase="finished", errors=errors, directory=str(folder)))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
