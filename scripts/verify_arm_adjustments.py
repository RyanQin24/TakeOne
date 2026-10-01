"""Offline model-space sweep: attainable endpoints and explicit failures, no devices."""

import argparse
import json
from pathlib import Path

import numpy as np
from takeone.planning.arm_adjustment import preview_adjustment
from takeone.planning.kinematics import ArmSolver
from takeone.simulation.robot import load_model
from takeone.voice.arm_intent import ROTATIONS, TRANSLATIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    solver = ArmSolver(load_model())
    rows = []
    with args.output.open("x", encoding="utf-8") as output:
        for fraction in (0.4, 0.5, 0.6):
            q = np.r_[[0.0, 0.0, 0.0], solver.lower[3:] + fraction * (solver.upper[3:] - solver.lower[3:])]
            for role in ("phone", "light"):
                for action in (*TRANSLATIONS, *ROTATIONS):
                    frame = "world" if action in ("lower", "raise") else "tool"
                    request = dict(
                        role=role, operations=[dict(action=action, amount=None, frame=frame, target=None)]
                    )
                    try:
                        result = preview_adjustment(request, q)
                        row = dict(fraction=fraction, role=role, action=action, result=result)
                    except ValueError as error:
                        row = dict(fraction=fraction, role=role, action=action, rejected=str(error))
                    rows.append(row)
        counts = dict(
            total=len(rows),
            feasible=sum(r.get("result", {}).get("endpoint_feasible", False) for r in rows),
            rejected=sum("rejected" in r for r in rows),
        )
        counts["infeasible"] = counts["total"] - counts["feasible"] - counts["rejected"]
        json.dump(
            dict(scope="synthetic model poses only; no hardware qualification", counts=counts, rows=rows),
            output,
            indent=2,
        )
    print(json.dumps(counts | {"output": str(args.output)}))


if __name__ == "__main__":
    main()
