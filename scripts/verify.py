"""Run relevant product, simulation and web checks from any working directory."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def web_commands():
    app = ROOT / "apps/rehearsal"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm:
        return [([npm, "test"], app), ([npm, "run", "check"], app)]
    if not shutil.which("node"):
        raise RuntimeError("Node.js is required for the browser checks; put node on PATH first")
    # These existing package scripts invoke only Node. Running their declared
    # commands also supports a Node runtime that does not bundle npm.
    scripts = json.loads((app / "package.json").read_text(encoding="utf-8"))["scripts"]
    shell = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c"] if os.name == "nt" else ["sh", "-c"]
    return [([*shell, scripts[name]], app) for name in ("test", "check")]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="write verification reports outside the default repository evidence directory",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    # Browser test reports contain Unicode; redirected Windows stdout may
    # otherwise default to cp1252 and abort an otherwise successful check.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    destination = args.output_dir.resolve() if args.output_dir is not None else ROOT / "data/verification"
    destination.mkdir(parents=True, exist_ok=True)
    browser_commands = web_commands()
    commands = [
        ([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], ROOT),
        (
            [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests/simulation"), "-v"],
            ROOT / "apps/rehearsal",
        ),
        *browser_commands,
    ]
    commands.append(
        (
            [
                sys.executable,
                str(ROOT / "scripts/check_integrity.py"),
                "--output-dir",
                str(destination),
            ],
            ROOT,
        )
    )
    for action in (["check"], ["format", "--check"]):
        commands.append(
            ([sys.executable, "-m", "ruff", *action, "packages/takeone", "tests", "scripts"], ROOT)
        )
    results = []
    for index, (command, cwd) in enumerate(commands):
        result = subprocess.run(command, cwd=cwd, capture_output=True)
        output = result.stdout + result.stderr
        (destination / f"check-{index}.txt").write_bytes(output)
        print(output.decode("utf-8", errors="replace"))
        results.append(
            dict(command=command, cwd=str(cwd), exit_code=result.returncode, log=f"check-{index}.txt")
        )
    (destination / "summary.json").write_text(
        json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(), checks=results), indent=2),
        encoding="utf-8",
    )
    return int(any(r["exit_code"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
