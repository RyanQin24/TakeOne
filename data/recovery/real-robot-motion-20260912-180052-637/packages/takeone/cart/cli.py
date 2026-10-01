"""Explicit cart-only plan/replay/timing/commission commands; never called by the web app."""

import argparse
import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.identity import identify_port
from takeone.adapters.simulated import SimulatedCart, VirtualClock
from takeone.clock import monotonic
from takeone.config import read_json
from takeone.paths import CONFIGS, DATA

from .plan import cart_from_shot, load_cart_plan, prepare_cart, prepare_command_test
from .runtime import CartRunner, Timing, check_commissioning, host_timing_priority


def execute(args, plan):
    timing = Timing.load()
    if args.command == "live-test":
        if not args.execute or not args.operator_ready:
            raise ValueError(
                "Live test requires --execute and --operator-ready; read docs/cart-live-testing.md"
            )
        envelope = check_commissioning(plan)
        identity = identify_port(args.port, args.usb_serial)
        from takeone.adapters.uart import MotorUART

        transport = MotorUART(args.port, timeout=timing.write_timeout_s, write_timeout=timing.write_timeout_s)
    else:
        envelope, identity, transport = None, None, SimulatedCart()
    virtual = VirtualClock()
    is_virtual = args.command == "replay"
    runner = CartRunner(
        transport,
        timing,
        virtual.now if is_virtual else monotonic,
        virtual.sleep if is_virtual else time.sleep,
    )
    folder = (
        DATA
        / "runs"
        / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-cart-" + uuid.uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    (folder / "plan.json").write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    error = None
    priority = {"requested": not is_virtual, "applied": False, "platform": None}
    try:
        with host_timing_priority(enabled=not is_virtual) as priority:
            if args.command == "live-test":
                transport.connect()
            runner.run(plan)
    except (Exception, KeyboardInterrupt) as failure:
        error = type(failure).__name__ + ": " + str(failure)
    finally:
        try:
            transport.close()
        except Exception as failure:
            error = error or "Close failed: " + str(failure)
        result = runner.report() | dict(
            mode=args.command,
            error=error,
            simulated_transport=transport.simulated,
            virtual_clock=is_virtual,
            plan_id=plan.plan_id,
            timing=asdict(timing),
            host_timing_priority=priority,
            identity=identity,
            commissioning_envelope=envelope,
            operator_ready_attested=bool(getattr(args, "operator_ready", False)),
            watchdog_evidence=read_json(CONFIGS / "cart-runtime.json")["watchdog_source"],
            nonzero_commands_attempted=sum(
                e.get("requested_wire") not in (None, "0.00,0.00\n") for e in runner.events
            ),
            hardware_qualified=False,
        )
        (folder / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "events"} | {"run_directory": str(folder)}, indent=2
        )
    )
    return int(error is not None or runner.fault is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cart-only commissioning; no arm imports or actuator commands"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    source = prepare.add_mutually_exclusive_group()
    source.add_argument("--shot", type=Path, help="Current simulator exported JSON")
    source.add_argument("--settings", type=Path, help="Shot settings object (no schema wrapper)")
    source.add_argument(
        "--command",
        dest="command_magnitude",
        type=float,
        help="Explicit equal wheel-command experiment; magnitude, not watts or a speed calibration",
    )
    prepare.add_argument("--duration", type=float, help="Override duration only when preparing from settings")
    prepare.add_argument("--output", type=Path, required=True)
    for name in ("replay", "timing", "live-test"):
        p = commands.add_parser(name)
        p.add_argument("--plan", type=Path, required=True)
        if name == "live-test":
            p.add_argument("--port", required=True)
            p.add_argument("--usb-serial", required=True)
            p.add_argument("--execute", action="store_true")
            p.add_argument(
                "--operator-ready",
                action="store_true",
                help="Attest identity, supported arms, clear test area and physical abort procedure",
            )
    commands.add_parser("ports", help="List USB serial identities without opening ports")
    analyze = commands.add_parser("analyze-drift", help="Analyze measured axle drift; never opens a port")
    analyze.add_argument("--measurements", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "analyze-drift":
        from .diagnostics import analyze_measurements

        report = analyze_measurements(args.measurements)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2, allow_nan=False)
        print(json.dumps({"report": str(args.output.resolve()), "trials": len(report["trials"])}))
        return 0
    if args.command == "ports":
        from serial.tools import list_ports

        print(
            json.dumps(
                [
                    dict(port=p.device, usb_serial=p.serial_number, description=p.description)
                    for p in list_ports.comports()
                ],
                indent=2,
            )
        )
        return 0
    if args.command == "prepare":
        if args.command_magnitude is not None:
            plan = prepare_command_test(
                args.command_magnitude,
                2.0 if args.duration is None else args.duration,
            )
        elif args.shot:
            if args.duration is not None:
                raise ValueError("An imported shot's timing cannot be overridden; recompile in the simulator")
            plan = cart_from_shot(json.loads(args.shot.read_text(encoding="utf-8-sig")))
        else:
            settings = (
                {} if args.settings is None else json.loads(args.settings.read_text(encoding="utf-8-sig"))
            )
            if args.duration is not None:
                settings["duration"] = args.duration
            plan = prepare_cart(settings)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(plan.to_dict(), stream, indent=2)
        print(
            json.dumps(
                dict(
                    plan=str(args.output.resolve()),
                    plan_id=plan.plan_id,
                    duration_s=plan.duration_s,
                    prediction=plan.to_dict()["prediction"],
                ),
                indent=2,
            )
        )
        return 0
    plan = load_cart_plan(json.loads(args.plan.read_text(encoding="utf-8-sig")))
    return execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
