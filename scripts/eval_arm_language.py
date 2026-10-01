"""Historical v1 semantic evaluation. Use eval_arm_program.py for the active vector tool.

Opt-in real-model requests. NEVER dispatches a returned robot tool.
"""

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from takeone.voice.arm_intent import ARM_INSTRUCTIONS, ARM_TOOL, prepare_arm_intent
from takeone.voice.arm_program import PROGRAM_INSTRUCTIONS
from takeone.voice.live_robot import BACKEND_INSTRUCTIONS, TOOLS

BACKEND_INSTRUCTIONS = BACKEND_INSTRUCTIONS.replace(PROGRAM_INSTRUCTIONS, ARM_INSTRUCTIONS)
TOOLS = [ARM_TOOL if tool["name"] == "prepare_arm_motion" else tool for tool in TOOLS]

MODEL = "gpt-5.6-terra"
CASES = [
    ("Lower the camera arm a little.", "phone", [("lower", None, "world")]),
    ("Raise the camera 2 centimetres.", "phone", [("raise", 0.02, "world")]),
    ("Lower the light arm 10 mm.", "light", [("lower", 0.01, "world")]),
    ("Pan the camera left five degrees.", "phone", [("pan_left", math.radians(5), "tool")]),
    ("Pan the camera right a little.", "phone", [("pan_right", None, "tool")]),
    ("Tilt the camera up 3 degrees.", "phone", [("tilt_up", math.radians(3), "tool")]),
    ("Tilt the camera down 5 degrees.", "phone", [("tilt_down", math.radians(5), "tool")]),
    ("Roll the camera clockwise 4 degrees.", "phone", [("roll_right", math.radians(4), "tool")]),
    ("Roll the camera counterclockwise 4 degrees.", "phone", [("roll_left", math.radians(4), "tool")]),
    ("Move the camera arm left 2 cm relative to the chassis.", "phone", [("left", 0.02, "chassis")]),
    ("Move the light arm right 1 cm relative to the chassis.", "light", [("right", 0.01, "chassis")]),
    ("Move the camera forward 2 cm along its optical direction.", "phone", [("forward", 0.02, "tool")]),
    ("Move the camera backward one inch in its own frame.", "phone", [("backward", 0.0254, "tool")]),
    (
        "Lower the camera arm a little, tilt it, and face toward us.",
        "phone",
        [("lower", None, "world"), ("tilt_unspecified", None, "tool"), ("face_target", None, None)],
    ),
    ("Move the camera left a little.", "phone", [("left", None, "unspecified")]),
    (
        "Face the camera toward the person I selected in the live view.",
        "phone",
        [("face_target", None, None)],
    ),
    ("Don't move anything. Stop.", "stop", []),
    ("Explain what tilting a camera means. Do not move it.", "explain", []),
    ("Correction: not lower. Raise the camera 2 cm instead.", "phone", [("raise", 0.02, "world")]),
    ("Move the robot forward a little, not the camera arm.", "cart", []),
]


def evaluate(case):
    text, role, expected = case
    body = dict(
        model=MODEL,
        instructions=BACKEND_INSTRUCTIONS,
        input=text,
        tools=TOOLS,
        parallel_tool_calls=False,
        max_output_tokens=1200,
        store=False,
        reasoning={"effort": "low"},
    )
    connection = http.client.HTTPSConnection("api.openai.com", timeout=60)
    try:
        connection.request(
            "POST",
            "/v1/responses",
            json.dumps(body),
            {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(262145)
        if response.status != 200 or len(raw) > 262144:
            return dict(
                text=text, passed=False, error=f"Provider HTTP {response.status}; response body omitted"
            )
        result = json.loads(raw)
        calls = [
            dict(name=o["name"], arguments=json.loads(o["arguments"]))
            for o in result.get("output", [])
            if o.get("type") == "function_call"
        ]
        passed = result.get("status") == "completed"
        validation = None
        if role == "stop":
            passed &= len(calls) == 1 and calls[0]["name"] == "stop_robot"
        elif role == "explain":
            passed &= not calls or all(c["name"] == "stop_robot" for c in calls)
        elif role == "cart":
            passed &= len(calls) == 1 and calls[0] == dict(
                name="request_robot_move", arguments=dict(direction="forward", distance_m=None)
            )
        else:
            passed &= len(calls) == 1 and calls[0]["name"] == "prepare_arm_adjustment"
            if passed:
                arguments = calls[0]["arguments"]
                validation = prepare_arm_intent(
                    arguments
                )  # Pure validation only. No robot client is constructed.
                actual = arguments["operations"]
                passed &= arguments["role"] == role and len(actual) == len(expected)
                for operation, (action, amount, frame) in zip(actual, expected):
                    passed &= operation["action"] == action
                    passed &= (
                        operation["amount"] is None
                        if amount is None
                        else type(operation["amount"]) in (int, float)
                        and math.isclose(operation["amount"], amount, abs_tol=1e-5)
                    )
                    if frame is not None:
                        passed &= operation["frame"] == frame
                    if action == "face_target":
                        passed &= isinstance(operation["target"], str) and bool(operation["target"].strip())
        return dict(
            text=text,
            passed=bool(passed),
            calls=calls,
            local_result=validation,
            usage=result.get("usage"),
            hardware_tools_dispatched=False,
        )
    except (ValueError, KeyError, OSError, http.client.HTTPException) as error:
        return dict(text=text, passed=False, error=type(error).__name__, hardware_tools_dispatched=False)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Authorize paid OpenAI text requests; no microphone/camera/hardware",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("Real model evaluation requires --live; unit tests are offline")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required")
    # Reserve the output before making paid requests; never overwrite previous evidence.
    with args.output.open("x", encoding="utf-8") as output:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(evaluate, CASES))
        passed = sum(r["passed"] for r in results)
        report = dict(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=MODEL,
            instructions_sha256=hashlib.sha256(BACKEND_INSTRUCTIONS.encode()).hexdigest(),
            passed=passed,
            total=len(results),
            results=results,
            scope="text-to-tool semantics only, no audio, no hardware",
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
