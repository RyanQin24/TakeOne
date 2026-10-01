"""Physical Feetech hold entry point: python -m takeone.motion.hold.

The default bus opens the configured serial port through LeRobot's Feetech SDK.
Manual/observation modes write the captured goals before AND after torque enable.
Always attempts torque off before closing. No simulated bus is selected by the CLI.
"""

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.fixed_pose import activate_fixed_pose
from takeone.adapters.identity import identify_port
from takeone.clock import monotonic
from takeone.contracts import JOINTS
from takeone.motion.commission import specification


def make_hold_bus(device, raw):
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    class FeetechHoldBus(FeetechMotorsBus):
        def sync_write(self, data_name, values, *, normalize=False, num_retry=0):
            if normalize is not False or set(values) != set(JOINTS):
                raise PermissionError("Supported hold requires five explicit raw motor targets")
            if data_name == "Goal_Position":
                valid = all(
                    type(v) is int and raw[n]["range_min"] <= v <= raw[n]["range_max"]
                    for n, v in values.items()
                )
            elif data_name == "Torque_Enable":
                valid = all(type(v) is int and v in (0, 1) for v in values.values())
            else:
                valid = False
            if not valid:
                raise PermissionError("Hold permits only bounded raw goals and torque enable/disable")
            return super().sync_write(data_name, values, normalize=False, num_retry=num_retry)

        def write(self, data_name, motor, value, *, normalize=False, num_retry=0):
            valid = motor in JOINTS and normalize is False and type(value) is int
            if valid and data_name == "Goal_Position":
                valid = raw[motor]["range_min"] <= value <= raw[motor]["range_max"]
            elif valid and data_name == "Torque_Enable":
                valid = value in (0, 1)
            else:
                valid = False
            if not valid:
                raise PermissionError("Hold permits only bounded raw goals and torque enable/disable")
            result = super().write(data_name, motor, value, normalize=False, num_retry=num_retry)
            self.acknowledged_writes.append(
                dict(register=data_name, motor_id=self.motors[motor].id, value=value)
            )
            return result

    motors = {name: Motor(id_, "sts3215", MotorNormMode.DEGREES) for name, id_ in device["motor_ids"].items()}
    calibration = {name: MotorCalibration(**value) for name, value in raw.items()}
    bus = FeetechHoldBus(device["port"], motors, calibration=calibration)
    bus.acknowledged_writes = []
    return bus


def run_trial(
    bus,
    raw,
    duration_s,
    max_drift_deg,
    *,
    clock=monotonic,
    sleep=time.sleep,
    observe=False,
    emit=None,
    release_requested=None,
):
    """Supported state check or operator-held pose; injectable for fault tests."""
    manual = release_requested is not None
    if manual and (not callable(release_requested) or duration_s is not None):
        raise ValueError("Manual release requires a release callback and no timed duration")
    observe = observe or manual
    report = dict(
        completed=False,
        torque_enable_attempted=False,
        torque_on_confirmed=False,
        active_target_confirmed=False,
        torque_disabled_confirmed=False,
        stationary_observation=observe,
        physical_holding_capacity_verified=False,
        motion_target="Fresh current raw positions only",
        samples=[],
        max_drift_deg=0.0,
        duration_requested_s=duration_s,
        last_sample_elapsed_s=None,
        max_drift_limit_deg=max_drift_deg,
        hold_mode="until_enter" if manual else "timed",
        drift_policy="report_without_release" if manual else "abort_and_release",
        sample_count=0,
        samples_dropped=0,
        goal_writes_acknowledged=False,
        active_goal_writes_acknowledged=False,
    )
    duration_limit = 30.0 if observe else 2.0
    if not manual and (not math.isfinite(duration_s) or not 0.1 <= duration_s <= duration_limit):
        raise ValueError(f"Supported hold duration must be between 0.1 and {duration_limit:g} seconds")
    if not math.isfinite(max_drift_deg) or not 0.1 <= max_drift_deg <= 1.0:
        raise ValueError("Drift detection threshold must be between 0.1 and 1 degree")

    def read(register):
        start = clock()
        values = (
            {n: bus.read(register, n, normalize=False, num_retry=0) for n in JOINTS}
            if manual
            else bus.sync_read(register, normalize=False, num_retry=0)
        )
        if clock() - start > 0.05:
            raise RuntimeError(f"{register}: read exceeded the 50 ms inspection budget")
        if set(values) != set(JOINTS) or any(type(v) is not int for v in values.values()):
            raise ValueError(f"Incomplete {register} feedback")
        return values

    def positions():
        values = read("Present_Position")
        if any(not raw[n]["range_min"] <= v <= raw[n]["range_max"] for n, v in values.items()):
            raise ValueError("Current pose is outside the original encoder range")
        return values

    def event(phase, **values):
        if emit is not None:
            emit(dict(phase=phase, **values))

    def command(register, values):
        if manual:
            # These call the real SDK's acknowledged writeTxRx in the CLI.
            for name in JOINTS:
                bus.write(register, name, values[name], normalize=False, num_retry=0)
        else:
            bus.sync_write(register, values, normalize=False, num_retry=0)

    def observed_health(limits):
        state = {
            name: read(name)
            for name in (
                "Present_Voltage",
                "Present_Temperature",
                "Torque_Limit",
                "Status",
                "Present_Current",
                "Present_Load",
            )
        }
        # Preserve the snapshot even when it explains a refusal or fault.
        report["last_health_raw"] = state
        for name in JOINTS:
            voltage = state["Present_Voltage"][name]
            if not limits["Min_Voltage_Limit"][name] <= voltage <= limits["Max_Voltage_Limit"][name]:
                raise RuntimeError(f"{name}: voltage feedback {voltage / 10:g} V is outside firmware limits")
            if state["Present_Temperature"][name] >= limits["Max_Temperature_Limit"][name]:
                raise RuntimeError(f"{name}: temperature reached its firmware limit")
            if not 0 < state["Torque_Limit"][name] <= limits["Max_Torque_Limit"][name]:
                raise RuntimeError(f"{name}: active torque limit is zero or exceeds the stored maximum")
            if state["Status"][name] != 0:
                raise RuntimeError(f"{name}: servo status flags are {state['Status'][name]:#x}")
        return state

    try:
        if {n: asdict(c) for n, c in bus.read_calibration().items()} != raw:
            raise ValueError("Hardware calibration differs from the original")
        if any(read("Torque_Enable").values()):
            raise ValueError("This supported test requires all five motors initially torque-off")
        if any(read("Operating_Mode").values()):
            raise ValueError("Position mode is required; no implicit mode change")
        if any(v & 16 for v in read("Phase").values()):
            raise ValueError("Unsupported extended-angle mode")
        limits = None
        if observe:
            limits = {
                name: read(name)
                for name in (
                    "Min_Voltage_Limit",
                    "Max_Voltage_Limit",
                    "Max_Temperature_Limit",
                    "Max_Torque_Limit",
                    "P_Coefficient",
                )
            }
            report["firmware_limits_raw"] = limits
            for name in JOINTS:
                if not 0 < limits["Min_Voltage_Limit"][name] < limits["Max_Voltage_Limit"][name]:
                    raise ValueError(f"{name}: invalid firmware voltage limits")
                if any(
                    limits[key][name] <= 0
                    for key in ("Max_Temperature_Limit", "Max_Torque_Limit", "P_Coefficient")
                ):
                    raise ValueError(
                        f"{name}: holding requires nonzero temperature/torque limits and position gain"
                    )
            observed_health(limits)
        event("preparing", duration_s=duration_s, manual_release=manual)
        if manual and release_requested():
            raise RuntimeError("Operator ended the hold before torque enable")
        targets = positions()
        report["targets_raw"] = targets
        if manual:
            started = activate_fixed_pose(
                bus, targets, read, positions, max_drift_deg, report, clock=clock, cancelled=release_requested
            )
        else:
            seeded = clock()
            command("Goal_Position", targets)
            report["goal_writes_acknowledged"] = manual
            if read("Goal_Position") != targets:
                raise RuntimeError("Current-position goals were not confirmed; torque remains off")
            current = positions()
            if any(abs(current[n] - targets[n]) * 360 / 4095 > max_drift_deg for n in JOINTS):
                raise RuntimeError("Arm moved while goals were being prepared; torque remains off")
            if clock() - seeded > 0.1:
                raise RuntimeError("Prepared goals are stale; torque remains off")
            if manual and release_requested():
                raise RuntimeError("Operator ended the hold before torque enable")
            report["torque_enable_attempted"] = True
            started = clock()
            command("Torque_Enable", dict.fromkeys(JOINTS, 1))
            if observe:
                # A goal register readback while torque is off does not establish
                # execution of a position command while enabled. Issue the SAME
                # fixed targets once after enable, never follow a sagging position.
                if any(v != 1 for v in read("Torque_Enable").values()):
                    raise RuntimeError("Torque-enabled state was not confirmed")
                report["torque_on_confirmed"] = True
                if not manual:
                    # The timed observation retains its original drift guard.
                    if read("Goal_Position") != targets:
                        raise RuntimeError("Stored hold targets changed before active command")
                    current = positions()
                    if any(abs(current[n] - targets[n]) * 360 / 4095 > max_drift_deg for n in JOINTS):
                        raise RuntimeError("Arm moved beyond the drift limit before active command")
                if clock() - started > 0.1:
                    raise RuntimeError("Active target preparation exceeded 100 ms")
                # Manual hold reissues the captured values even if the controller
                # changed its goal register during the torque-enable transition.
                command("Goal_Position", targets)
                report["active_goal_writes_acknowledged"] = manual
                if read("Goal_Position") != targets:
                    raise RuntimeError("Active current-position targets were not confirmed")
                report["active_target_confirmed"] = True
        while True:
            torque = read("Torque_Enable")
            if any(v != 1 for v in torque.values()):
                raise RuntimeError("Torque-enabled state was not confirmed")
            report["torque_on_confirmed"] = True
            health = observed_health(limits) if observe else None
            if observe and read("Goal_Position") != targets:
                raise RuntimeError("Stored hold targets changed during the observation")
            current = positions()
            drift = {n: abs(current[n] - targets[n]) * 360 / 4095 for n in JOINTS}
            report["max_drift_deg"] = max(report["max_drift_deg"], max(drift.values()))
            elapsed = clock() - started
            report["last_sample_elapsed_s"] = elapsed
            sample = dict(elapsed_s=elapsed, positions_raw=current, drift_deg=drift)
            if observe:
                sample.update(torque_enable=torque, health_raw=health)
            report["samples"].append(sample)
            report["sample_count"] += 1
            if manual and len(report["samples"]) > 1200:
                del report["samples"][0]
                report["samples_dropped"] += 1
            if max(drift.values()) > max_drift_deg:
                worst = max(drift, key=drift.get)
                crossing = dict(
                    joint=worst, elapsed_s=elapsed, drift_deg=drift[worst], limit_deg=max_drift_deg
                )
                if manual:
                    report.setdefault("first_drift_warning", crossing)
                else:
                    report["drift_trip"] = crossing
                    raise RuntimeError(
                        f"Hold drift exceeded the declared detection threshold: {worst} "
                        f"drifted {drift[worst]:.3f} deg at {elapsed:.3f} s (limit {max_drift_deg:g} deg)"
                    )
            event(
                "holding",
                elapsed_s=elapsed,
                remaining_s=None if manual else max(0, duration_s - elapsed),
                max_drift_deg=max(drift.values()),
                drift_warning=manual and max(drift.values()) > max_drift_deg,
                health_raw=health,
            )
            if manual and release_requested():
                report["release_reason"] = "operator_enter"
                break
            if not manual and elapsed >= duration_s:
                report["release_reason"] = "duration_elapsed"
                break
            sleep(0.04 if manual else min(0.04, duration_s - elapsed))
        report["completed"] = True
    except (Exception, KeyboardInterrupt) as error:
        report.update(completed=False, error=f"{type(error).__name__}: {error}")
        report["release_reason"] = "operator_interrupt" if isinstance(error, KeyboardInterrupt) else "fault"
    finally:
        if report["torque_enable_attempted"]:
            # A broken console must not prevent release attempts.
            try:
                event("releasing")
            except (Exception, KeyboardInterrupt):
                pass
            failures = []
            # Attempt every motor even if a preceding write fails. Mechanical
            # support is required throughout; process/USB loss can prevent release.
            for name in JOINTS:
                try:
                    bus.write("Torque_Enable", name, 0, normalize=False, num_retry=0)
                except (Exception, KeyboardInterrupt) as error:
                    failures.append(f"{name}: {type(error).__name__}: {error}")
            try:
                report["torque_disabled_confirmed"] = all(v == 0 for v in read("Torque_Enable").values())
            except (Exception, KeyboardInterrupt) as error:
                failures.append(f"{type(error).__name__}: {error}")
            if failures:
                report["release_errors"] = failures
            if failures or not report["torque_disabled_confirmed"]:
                report.update(completed=False, manual_motor_power_cut_required=True)
            try:
                event("released", torque_disabled_confirmed=report["torque_disabled_confirmed"])
            except (Exception, KeyboardInterrupt):
                pass
    return report


def supported_hold(
    role,
    profile,
    *,
    operator_ready,
    payload_supported,
    duration_s=2.0,
    max_drift_deg=1.0,
    observe=False,
    cart_parked=False,
    emit=None,
    bus_factory=make_hold_bus,
    identity_check=identify_port,
    release_requested=None,
):
    manual = release_requested is not None
    observe = observe or manual
    result = dict(
        role=role,
        profile=profile,
        completed=False,
        serial_port_opened=False,
        qualification_modified=False,
        live_execution_allowed=False,
    )
    if operator_ready is not True or payload_supported is not True:
        raise ValueError(
            "Physical hold requires --operator-ready and --payload-supported throughout the test"
        )
    if observe and cart_parked is not True:
        raise ValueError("Stationary observation requires --cart-parked with cart motor power off")
    duration_limit = 30.0 if observe else 2.0
    if manual and (not callable(release_requested) or duration_s is not None):
        raise ValueError("Manual release requires a release callback and no timed duration")
    if not manual and (not math.isfinite(duration_s) or not 0.1 <= duration_s <= duration_limit):
        raise ValueError(f"Duration must be between 0.1 and {duration_limit:g} seconds")
    if not math.isfinite(max_drift_deg) or not 0.1 <= max_drift_deg <= 1:
        raise ValueError("Drift threshold must be between 0.1 and 1 degree")
    device, raw, original_hash = specification(role, profile)
    result.update(
        identity=identity_check(device["port"], device["usb_serial"]),
        calibration_sha256=original_hash,
        entry_point=str(Path(__file__).resolve()),
        motor_ids=device["motor_ids"],
    )
    bus = bus_factory(device, raw)
    result["bus_class"] = f"{type(bus).__module__}.{type(bus).__qualname__}"
    if bus.is_connected:
        raise ValueError("Supported hold requires exclusive ownership of a closed arm bus")
    try:
        bus.connect()
        result["serial_port_opened"] = True
        bus.port_handler.ser.write_timeout = 0.05
        bus.set_timeout(50)
        result["baudrate"] = bus.port_handler.ser.baudrate
        if emit is not None:
            emit(
                dict(
                    phase="connected",
                    port=result["identity"]["port"],
                    motor_ids=list(device["motor_ids"].values()),
                    baudrate=result["baudrate"],
                )
            )
        result.update(
            run_trial(
                bus,
                raw,
                duration_s,
                max_drift_deg,
                observe=observe,
                emit=emit,
                release_requested=release_requested,
            )
        )
    except (Exception, KeyboardInterrupt) as error:
        result.update(completed=False, error=f"{type(error).__name__}: {error}")
    finally:
        if hasattr(bus, "acknowledged_writes"):
            result["acknowledged_motor_writes"] = bus.acknowledged_writes.copy()
        if bus.is_connected:
            result["serial_port_opened"] = True
            try:
                bus.disconnect(disable_torque=False)
            except Exception as error:
                result.update(completed=False, close_error=str(error))
    return result


def console_observer(role):
    """Visible state/countdown; do not imply that register confirmation measures force."""
    last_print = -1.0

    def emit(event):
        nonlocal last_print
        phase = event["phase"]
        if phase == "connected":
            print(
                f"{role}: SERIAL OPEN {event['port']} at {event['baudrate']} baud | "
                f"motor IDs {event['motor_ids']}",
                flush=True,
            )
        elif phase == "preparing":
            print(
                f"{role}: preparing fresh current-position targets. Keep mechanical support/catch in place.",
                flush=True,
            )
        elif phase == "holding" and event["elapsed_s"] - last_print >= 0.5:
            last_print = event["elapsed_s"]
            remaining = event["remaining_s"]
            state = event["health_raw"]
            voltages = list(state["Present_Voltage"].values())
            if remaining is None:
                release = "holding until ENTER; support before release"
                warning = " | DRIFT WARNING; TORQUE REMAINS ON" if event["drift_warning"] else ""
            else:
                release = f"{remaining:5.1f}s until automatic release"
                warning = " | RELEASE SOON: SUPPORT THE ARM NOW" if remaining <= 5 else ""
            print(
                f"{role}: TORQUE ON 5/5 | {release} | "
                f"drift {event['max_drift_deg']:.3f} deg | "
                f"{min(voltages) / 10:.1f}-{max(voltages) / 10:.1f} V | servo status clear{warning}",
                flush=True,
            )
        elif phase == "releasing":
            print(f"{role}: RELEASING TORQUE NOW. Keep the arm supported.", flush=True)
        elif phase == "released":
            message = (
                "TORQUE OFF CONFIRMED"
                if event["torque_disabled_confirmed"]
                else "TORQUE OFF UNCONFIRMED - CUT ARM MOTOR POWER"
            )
            print(f"{role}: {message}", flush=True)

    return emit


def console_release_request():
    """Wait for operator input without blocking feedback checks; CLI use only."""
    if sys.platform == "win32":
        import msvcrt

        def requested():
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\r", "\n"):
                    return True
                if key == "\x03":
                    raise KeyboardInterrupt
            return False
    else:
        import select

        def requested():
            if not select.select([sys.stdin], [], [], 0)[0]:
                return False
            if not sys.stdin.readline():
                raise RuntimeError("Operator terminal input closed; releasing supported arm")
            return True

    return requested


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PHYSICAL supported hold check; fresh goals, torque on, torque off"
    )
    parser.add_argument("--role", choices=("phone", "light"), required=True)
    parser.add_argument("--profile", choices=("windows", "linux"), default="windows")
    parser.add_argument("--operator-ready", action="store_true")
    parser.add_argument("--payload-supported", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--observe",
        action="store_true",
        help="Stationary visible hold with health monitoring; up to 30 seconds",
    )
    mode.add_argument(
        "--until-enter",
        action="store_true",
        help="Hold until ENTER/Ctrl+C; drift is reported without automatic release",
    )
    parser.add_argument(
        "--cart-parked", action="store_true", help="Attest cart is parked with its motor power off"
    )
    parser.add_argument("--duration", type=float, help="Default: 2 seconds, or 20 seconds with --observe")
    parser.add_argument("--max-drift-deg", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.operator_ready or not args.payload_supported:
            raise ValueError("Readiness and payload support must be confirmed before any hardware access")
        if (args.observe or args.until_enter) and not args.cart_parked:
            raise ValueError("Stationary hold requires --cart-parked with cart motor power off")
        if args.until_enter and (args.duration is not None or not sys.stdin.isatty()):
            raise ValueError("--until-enter requires an interactive terminal and no --duration")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            result = supported_hold(
                args.role,
                args.profile,
                operator_ready=args.operator_ready,
                payload_supported=args.payload_supported,
                duration_s=None
                if args.until_enter
                else (args.duration if args.duration is not None else (20.0 if args.observe else 2.0)),
                max_drift_deg=args.max_drift_deg,
                observe=args.observe,
                cart_parked=args.cart_parked,
                emit=console_observer(args.role) if (args.observe or args.until_enter) else None,
                release_requested=console_release_request() if args.until_enter else None,
            )
            result.update(
                schema="takeone.supported-hold.v1",
                captured_utc=datetime.now(timezone.utc).isoformat(),
                scope="Stationary supported/caught hold; no joint travel requested, shot positioning or combined qualification",
                output=str(args.output.resolve()),
            )
            destination.write(json.dumps(result, indent=2, allow_nan=False))
        summary_keys = (
            "role",
            "hold_mode",
            "identity",
            "bus_class",
            "entry_point",
            "completed",
            "torque_on_confirmed",
            "goal_writes_acknowledged",
            "active_goal_writes_acknowledged",
            "active_target_confirmed",
            "last_sample_elapsed_s",
            "max_drift_deg",
            "drift_trip",
            "first_drift_warning",
            "release_reason",
            "torque_disabled_confirmed",
            "physical_holding_capacity_verified",
            "error",
            "release_errors",
            "manual_motor_power_cut_required",
            "close_error",
            "output",
        )
        display = (
            {k: result[k] for k in summary_keys if k in result}
            if (args.observe or args.until_enter)
            else result
        )
        print(json.dumps(display, indent=2, allow_nan=False))
        return int(not result["completed"])
    except (ValueError, OSError) as error:
        print(json.dumps(dict(completed=False, error=str(error))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
