"""Repeatable host timing and drift witnesses; simulated transport only, no UART."""

import argparse
import json
import math
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.simulated import SimulatedCart
from takeone.cart.diagnostics import DriftTrial, analyze_trial
from takeone.cart.plan import prepare_cart
from takeone.cart.runtime import CartRunner, Timing, host_timing_priority
from takeone.paths import WORKSPACE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error("--runs must be between 1 and 10")
    if args.output.exists():
        parser.error("Output already exists; retain earlier timing evidence")
    plan, timing = prepare_cart({"duration": 4}), Timing.load()
    reports = []
    for _ in range(args.runs):
        runner = CartRunner(SimulatedCart(), timing)
        priority = None
        try:
            with host_timing_priority() as priority:
                runner.run(plan)
        except (OSError, RuntimeError, InterruptedError) as error:
            runner.fault = runner.fault or f"{type(error).__name__}: {error}"
        reports.append(runner.report() | {"host_timing_priority": priority})
    # Analytic synthetic witness: right speed 2% higher in reverse, not real data.
    left, right, duration, track = -0.1375, -0.1375 * 1.02, 4, 0.58
    witness = analyze_trial(
        DriftTrial(
            "synthetic-2-percent",
            -0.04,
            -0.04,
            duration,
            (left + right) * duration / 2,
            math.degrees((right - left) * duration / track),
            track,
            "Synthetic analytic witness; NOT a real cart measurement",
            "constant speeds; no slip",
        )
    )
    report = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip(),
        source_hashes=plan.to_dict()["provenance"],
        timing=asdict(timing),
        prediction=plan.to_dict()["prediction"],
        host_trials=reports,
        synthetic_drift_witness=witness,
        all_host_trials_passed=all(r["fault"] is None for r in reports),
        maximum_observed_host_gap_s=max(r["max_host_gap_s"] for r in reports),
        no_serial_ports_opened=True,
        hardware_straightness_verified=False,
        limitations="Host timing excludes USB/firmware queues, real braking and physical cart response",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("source_hashes", "host_trials", "prediction", "synthetic_drift_witness")
            }
            | {"output": str(args.output.resolve())},
            indent=2,
        )
    )
    return int(not report["all_host_trials_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
