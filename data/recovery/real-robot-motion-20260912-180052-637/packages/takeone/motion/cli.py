"""Prepare, inspect, rehearse and explicitly execute a reviewed complete robot plan."""

import argparse
import json
from pathlib import Path

from .limits import preflight
from .plan import load_plan, prepare_shot
from .service import execute_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description="TakeOne synchronized cart and dual-arm motion")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Prepare a reviewed simulator export; no device IO")
    source = prepare.add_mutually_exclusive_group()
    source.add_argument("--shot", type=Path)
    source.add_argument("--settings", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    for name in ("preflight", "replay", "timing", "live"):
        action = sub.add_parser(name)
        action.add_argument("--plan", type=Path, required=True)
        action.add_argument("--profile", choices=("windows", "linux"), default="windows")
        if name == "live":
            action.add_argument("--confirm-plan", required=True)
            action.add_argument("--operator-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if args.shot:
                shot = json.loads(args.shot.read_text(encoding="utf-8-sig"))
            else:
                from takeone.planning.compiler import compile_shot

                settings = json.loads(args.settings.read_text(encoding="utf-8-sig")) if args.settings else {}
                shot = compile_shot(settings)
            plan = prepare_shot(shot)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
            result = preflight(plan) | {"output": str(args.output.resolve())}
        else:
            plan = load_plan(json.loads(args.plan.read_text(encoding="utf-8-sig")))
            if args.command == "preflight":
                result = preflight(plan, args.profile)
            else:
                result = execute_plan(
                    plan,
                    mode=args.command,
                    profile=args.profile,
                    confirm_plan=getattr(args, "confirm_plan", None),
                    operator_ready=getattr(args, "operator_ready", False),
                )
        print(json.dumps(result, indent=2))
        return int(result.get("completed") is False)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(json.dumps({"error": str(error), "completed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
