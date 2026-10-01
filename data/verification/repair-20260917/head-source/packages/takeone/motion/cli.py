"""Prepare, inspect, rehearse and explicitly execute a reviewed complete robot plan."""

import argparse
import json
import time
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
    prepare.add_argument(
        "--transition-seconds", type=float, default=0.0, help="Explicit new approach/departure revision"
    )
    prepare.add_argument(
        "--initial-pose", type=Path, help="JSON array of ten measured model angles for the reviewed approach"
    )
    prepare.add_argument("--criteria", type=Path, help="Predeclared acceptance thresholds and methods")
    for name in ("preflight", "check", "replay", "timing", "templates", "live"):
        action = sub.add_parser(name)
        action.add_argument("--plan", type=Path, required=True)
        action.add_argument("--profile", choices=("windows", "linux"), default="windows")
        if name in ("preflight", "live"):
            action.add_argument(
                "--qualified", action="store_true", help="Require measured production qualification"
            )
        if name == "live":
            action.add_argument("--confirm-plan", required=True)
            action.add_argument("--operator-ready", action="store_true")
            action.add_argument(
                "--plan-start", action="store_true", help="Require arms already at the plan start"
            )
        if name == "templates":
            action.add_argument("--output-directory", type=Path, required=True)
    assessment = sub.add_parser(
        "assess", help="Compare actual traces and independent observations; no device IO"
    )
    assessment.add_argument("--run", type=Path, required=True)
    assessment.add_argument("--observations", type=Path, required=True)
    assessment.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    print(json.dumps(dict(phase="starting", command=args.command)), flush=True)
    try:
        if args.command == "assess":
            from .measurements import assess_run

            result = assess_run(args.run, args.observations)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
        elif args.command == "prepare":
            print(
                json.dumps(dict(phase="planning", message="Solving IK once; live reuses this result")),
                flush=True,
            )
            if args.shot:
                shot = json.loads(args.shot.read_text(encoding="utf-8-sig"))
            else:
                from takeone.planning.compiler import compile_shot

                settings = json.loads(args.settings.read_text(encoding="utf-8-sig")) if args.settings else {}
                shot = compile_shot(settings)
            plan = prepare_shot(
                shot,
                transition_s=args.transition_seconds,
                initial_rad=json.loads(args.initial_pose.read_text(encoding="utf-8-sig"))
                if args.initial_pose
                else None,
                criteria=json.loads(args.criteria.read_text(encoding="utf-8-sig")) if args.criteria else None,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(plan.to_dict(), stream, indent=2, allow_nan=False)
            from .checked import record_check

            receipt = record_check(plan, "canonical_preparation")
            result = preflight(plan, execution_mode="commissioning") | {
                "output": str(args.output.resolve()),
                "checked_receipt": receipt,
            }
        else:
            plan = load_plan(json.loads(args.plan.read_text(encoding="utf-8-sig")))
            if args.command == "templates":
                from .measurements import templates

                args.output_directory.mkdir(parents=True, exist_ok=False)
                for name, document in templates(plan).items():
                    (args.output_directory / f"{name}.json").write_text(
                        json.dumps(document, indent=2), encoding="utf-8"
                    )
                result = dict(
                    output_directory=str(args.output_directory.resolve()),
                    values="Missing measurements remain null",
                )
            elif args.command == "preflight":
                result = preflight(
                    plan, args.profile, execution_mode="qualified" if args.qualified else "commissioning"
                )
            else:
                result = execute_plan(
                    plan,
                    mode=args.command,
                    profile=args.profile,
                    confirm_plan=getattr(args, "confirm_plan", None),
                    operator_ready=getattr(args, "operator_ready", False),
                    execution_mode="qualified" if getattr(args, "qualified", False) else "commissioning",
                    from_current=not getattr(args, "plan_start", False),
                )
        result["elapsed_s"] = round(time.perf_counter() - started, 3)
        print(json.dumps(result, indent=2))
        return int(result.get("completed") is False)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "error": str(error),
                    "completed": False,
                    "elapsed_s": round(time.perf_counter() - started, 3),
                }
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
