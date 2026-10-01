"""Read-only checks for a TAKE ONE saved rehearsal; no robot or API imports.

This is a narrow semantic regression checker, not a cinematic-quality scorer.
It does not change the source program or establish hardware qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def inspect_program(program: dict, epsilon_m: float = 0.001) -> dict:
    if not finite(epsilon_m) or epsilon_m <= 0:
        raise ValueError("Motion tolerance must be finite and positive.")
    if not isinstance(program, dict) or program.get("kind") != "takeone_rehearsal_program":
        raise ValueError("Expected a saved takeone_rehearsal_program object.")
    if program.get("schema_version") != 1 or not isinstance(program.get("segments"), list):
        raise ValueError("Expected schema version 1 and a segments array.")
    findings, shots = [], []
    for segment in program["segments"]:
        if not isinstance(segment, dict):
            raise ValueError("Every segment must be an object.")
        if segment.get("kind") != "shot":
            continue
        shot_id = segment.get("shot_id", "unnamed")
        template = segment.get("template_id", "unknown")
        summary = segment.get("summary") or {}
        review = segment.get("shot_review") or {}
        start = summary.get("camera_height_start_m")
        end = summary.get("camera_height_end_m")
        tracking = segment.get("tracking") or {}
        evidence = {
            "shot_id": shot_id, "template_id": template,
            "existing_assessment": segment.get("assessment"),
            "camera_height_start_m": start, "camera_height_end_m": end,
            "camera_height_range_m": review.get("camera_height_range_m"),
            "coverage_samples": review.get("coverage_samples_examined"),
            "source": review.get("source", "unspecified"),
        }
        shots.append(evidence)
        if template in ("boom_up", "boom_down"):
            direction = 1 if template == "boom_up" else -1
            if not finite(start) or not finite(end):
                findings.append({"shot_id": shot_id, "severity": "unverified",
                    "code": "missing_achieved_height", "evidence": evidence,
                    "message": "Cannot evaluate the boom label without achieved endpoint heights."})
            else:
                signed_change = direction * (end - start)
                if signed_change <= epsilon_m:
                    findings.append({"shot_id": shot_id, "severity": "contradiction",
                        "code": "boom_label_not_realized", "evidence": {
                            "template_id": template, "start_m": start, "end_m": end,
                            "signed_change_m": signed_change, "epsilon_m": epsilon_m,
                            "existing_assessment": segment.get("assessment")},
                        "message": "The solved endpoint heights do not realize the named boom direction. "
                                   "Review the authored motion and label; do not silently rewrite either."})
        following = tracking.get("cart") == "follow_actor" or tracking.get("phone") == "follow_head"
        if following and tracking.get("live_available") is not True:
            findings.append({"shot_id": shot_id, "severity": "unverified",
                "code": "live_follow_not_established", "evidence": {
                    "cart": tracking.get("cart"), "phone": tracking.get("phone"),
                    "live_state": tracking.get("live_state"),
                    "preview_source": tracking.get("preview_source")},
                "message": "A scripted follow preview is not evidence of an integrated live controller."})
        planned = segment.get("planned_filming_s")
        filmed = segment.get("filming_s")
        if finite(planned) and finite(filmed) and planned > filmed + 0.04:
            findings.append({"shot_id": shot_id, "severity": "contradiction",
                "code": "source_shorter_than_planned_edit", "evidence": {
                    "planned_s": planned, "filmed_s": filmed},
                "message": "The source duration is shorter than the planned filming window. "
                           "Review capture-window semantics; a held preview is not new footage."})
    return {
        "kind": "takeone_semantic_audit", "schema_version": 1,
        "document_digest": program.get("document_digest"),
        "title": program.get("title"), "shot_count": len(shots),
        "motion_epsilon_m": epsilon_m,
        "contradictions": sum(f["severity"] == "contradiction" for f in findings),
        "findings": findings, "shots": shots,
        "scope": "Read-only checks of existing serialized simulated evidence, not a new simulation.",
        "not_evaluated": ["Occlusion and distractors", "Acting and eyeline accuracy",
            "Narrative or aesthetic quality", "Focus, exposure and recorded sound",
            "Collision clearance and hardware qualification", "Live tracking performance"],
        "hardware_actions": False, "paid_model_requests": False,
    }


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is not permitted: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="New JSON file; existing files are never overwritten.")
    parser.add_argument("--motion-epsilon-m", type=float, default=0.001,
                        help="Numerical no-op tolerance, NOT a universal cinematic motion minimum.")
    args = parser.parse_args(argv)
    try:
        raw = args.program.read_bytes()
        program = json.loads(raw.decode("utf-8-sig"), parse_constant=reject_constant)
        report = inspect_program(program, args.motion_epsilon_m)
        report.update(input_path=str(args.program.resolve()),
                      input_sha256=hashlib.sha256(raw).hexdigest(),
                      created_utc=datetime.now(timezone.utc).isoformat())
        text = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(text)
        print(text, end="")
        return 1 if report["contradictions"] else 0
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
        print(f"Audit could not complete: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
