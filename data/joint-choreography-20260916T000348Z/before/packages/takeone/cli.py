"""Offline operator commands. Deliberately no live execution command."""

import argparse
import json
import subprocess
import sys

from .calibration import hardware_blockers
from .config import file_hash, provenance, read_json, rig_config
from .paths import APP, CALIBRATION, CONFIGS, WORKSPACE


def diagnose(profile):
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    registry = read_json(CALIBRATION / "registry.json")
    snapshot = CALIBRATION / registry["snapshot"]
    integrity = file_hash(snapshot) == registry["snapshot_sha256"]
    result = dict(
        schema_version=1,
        mode="offline-diagnostics",
        workspace=str(WORKSPACE),
        serial_ports_opened=False,
        hardware_commands_sent=False,
        calibration_snapshot_integrity=integrity,
        hardware_ready=False,
        blockers=hardware_blockers(profile),
        devices=devices,
        rig=rig_config(),
        provenance=provenance(),
    )
    if not integrity:
        result["blockers"].append("Calibration evidence integrity failure")
    print(json.dumps(result, indent=2))
    return 0 if integrity else 1


def dry_run():
    from .motion.plan import prepare_shot
    from .motion.service import check_plan
    from .planning.compiler import compile_shot

    result = check_plan(prepare_shot(compile_shot()))
    print(json.dumps(result, indent=2))
    return int(not result["plan_valid"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="TakeOne offline tools; no motors are actuated")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("diagnose")
    doctor.add_argument("--profile", choices=["windows", "linux"], default="windows")
    sub.add_parser("dry-run")
    server = sub.add_parser("simulator")
    server.add_argument("--port", type=int, default=8766)
    server.add_argument("--voice-live-enabled", action="store_true")
    server.add_argument("--voice-live-timeout-seconds", type=int, default=10)
    server.add_argument("--voice-live-max-duration-seconds", type=int)
    args = parser.parse_args(argv)
    if args.command == "diagnose":
        return diagnose(args.profile)
    if args.command == "dry-run":
        return dry_run()
    command = [
        sys.executable,
        str(APP / "server.py"),
        "--port",
        str(args.port),
        "--voice-live-timeout-seconds",
        str(args.voice_live_timeout_seconds),
    ]
    if args.voice_live_max_duration_seconds is not None:
        command.extend(["--voice-live-max-duration-seconds", str(args.voice_live_max_duration_seconds)])
    if args.voice_live_enabled:
        command.append("--voice-live-enabled")
    return subprocess.call(command, cwd=APP)


if __name__ == "__main__":
    raise SystemExit(main())
