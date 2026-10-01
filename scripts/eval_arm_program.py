"""Paid opt-in NLP -> vector program -> offline trajectory evaluation. No hardware dispatch."""

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import math
import os
from pathlib import Path

from takeone.planning.arm_program import compile_program, rehearsal_pose
from takeone.voice.arm_program import prepare_program
from takeone.voice.live_robot import BACKEND_INSTRUCTIONS, TOOLS

MODEL = "gpt-5.6-terra"


def step(t=(0, 0, 0), r=(0, 0, 0), frame="optical", duration=None):
    return dict(
        translation_m=list(t), rotation_rad=list(r), frame=frame, duration_s=duration, aim_target=None
    )


CASES = [
    (
        "Lower the camera two centimetres over two seconds.",
        "phone",
        [step((0, 0, -0.02), frame="world", duration=2)],
    ),
    ("Raise the light arm 10 mm.", "light", [step((0, 0, 0.01), frame="world")]),
    ("Pan the camera left 5 degrees.", "phone", [step(r=(0, -math.radians(5), 0))]),
    ("Pan the camera right 3 degrees.", "phone", [step(r=(0, math.radians(3), 0))]),
    ("Tilt the camera up 3 degrees.", "phone", [step(r=(math.radians(3), 0, 0))]),
    ("Tilt the camera down 4 degrees.", "phone", [step(r=(-math.radians(4), 0, 0))]),
    ("Roll the camera clockwise 4 degrees.", "phone", [step(r=(0, 0, math.radians(4)))]),
    ("Roll the camera counterclockwise 2 degrees.", "phone", [step(r=(0, 0, -math.radians(2)))]),
    ("Translate the camera forward one inch along its own optical axis.", "phone", [step((0, 0, 0.0254))]),
    (
        "Move the camera arm 2 cm forward relative to the chassis.",
        "phone",
        [step((-0.02, 0, 0), frame="chassis")],
    ),
    (
        "Move the camera diagonally in its own view: right 17 mm and up 9 mm at the same time.",
        "phone",
        [step((0.017, -0.009, 0))],
    ),
    (
        "Lower the camera 2 cm, then raise it 1 cm.",
        "phone",
        [step((0, 0, -0.02), frame="world"), step((0, 0, 0.01), frame="world")],
    ),
    (
        "Correction: do not lower it. Raise the camera 2 cm instead.",
        "phone",
        [step((0, 0, 0.02), frame="world")],
    ),
    ("Face the camera toward the person I selected in the live camera view.", "target", None),
    ("Move the camera left a little.", "ambiguous", None),
    ("Tilt the camera.", "ambiguous", None),
    ("Lower the camera a little.", "default", None),
    ("Don't move anything. Stop.", "stop", None),
    ("Explain what a camera tilt means; do not move anything.", "explain", None),
    ("Move the robot forward a little, not the camera arm.", "cart", None),
]


def evaluate(case):
    text, expected_role, expected = case
    connection = http.client.HTTPSConnection("api.openai.com", timeout=60)
    try:
        body = dict(
            model=MODEL,
            instructions=BACKEND_INSTRUCTIONS,
            input=text,
            tools=TOOLS,
            parallel_tool_calls=False,
            max_output_tokens=1800,
            store=False,
            reasoning={"effort": "low"},
        )
        connection.request(
            "POST",
            "/v1/responses",
            json.dumps(body),
            {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(262145)
        if response.status != 200 or len(raw) > 262144:
            raise ValueError(f"Provider HTTP {response.status}")
        provider = json.loads(raw)
        calls = [
            dict(name=o["name"], arguments=json.loads(o["arguments"]))
            for o in provider.get("output", [])
            if o.get("type") == "function_call"
        ]
        passed = provider.get("status") == "completed"
        rehearsal = None
        if expected_role in ("stop", "explain", "cart"):
            if expected_role == "explain":
                passed &= all(c["name"] == "stop_robot" for c in calls)
            else:
                passed &= len(calls) == 1 and calls[0]["name"] == (
                    "stop_robot" if expected_role == "stop" else "request_robot_move"
                )
        else:
            passed &= len(calls) == 1 and calls[0]["name"] == "prepare_arm_motion"
            if passed:
                arguments = calls[0]["arguments"]
                validated = prepare_program(arguments)
                actual = validated["program"]
                if expected_role == "ambiguous":
                    passed &= bool(actual["questions"])
                elif expected_role == "target":
                    passed &= any(s["aim_target"] for s in actual["segments"])
                    passed &= all(
                        not any(s["translation_m"]) and not any(s["rotation_rad"]) for s in actual["segments"]
                    )
                elif expected_role == "default":
                    passed &= bool(actual["assumptions"]) and actual["segments"][0]["translation_m"] == [
                        0,
                        0,
                        -0.02,
                    ]
                else:
                    passed &= (
                        actual["role"] == expected_role
                        and len(actual["segments"]) == len(expected)
                        and not actual["questions"]
                    )
                    for row, want in zip(actual["segments"], expected):
                        for key in ("translation_m", "rotation_rad"):
                            passed &= all(
                                math.isclose(a, b, abs_tol=1e-5) for a, b in zip(row[key], want[key])
                            )
                        passed &= (
                            row["frame"] == want["frame"]
                            and row["duration_s"] == want["duration_s"]
                            and row["aim_target"] is None
                        )
                if passed:
                    result = compile_program(arguments, rehearsal_pose(), pose_source="simulated")
                    rehearsal = {k: v for k, v in result.items() if k not in ("document", "frames")}
        return dict(
            text=text,
            passed=bool(passed),
            calls=calls,
            rehearsal=rehearsal,
            usage=provider.get("usage"),
            hardware_tools_dispatched=False,
        )
    except (ValueError, KeyError, OSError, http.client.HTTPException) as error:
        return dict(text=text, passed=False, error=str(error), hardware_tools_dispatched=False)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live or not os.environ.get("OPENAI_API_KEY"):
        parser.error("Requires --live and OPENAI_API_KEY; never actuates hardware")
    with args.output.open("x", encoding="utf-8") as output:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(evaluate, CASES))
        passed = sum(r["passed"] for r in results)
        report = dict(
            model=MODEL,
            instructions_sha256=hashlib.sha256(BACKEND_INSTRUCTIONS.encode()).hexdigest(),
            passed=passed,
            total=len(results),
            results=results,
            scope="Text NLP and simulated paths; no mic, camera, or hardware",
        )
        json.dump(report, output, indent=2)
    print(
        json.dumps(
            dict(
                passed=passed,
                total=len(results),
                output=str(args.output),
                failed=[r["text"] for r in results if not r["passed"]],
            )
        )
    )
    return int(passed != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
