"""Reproducible offline + browser audit for TakeOne cinematic choreography.

Compiles canonical presets/motifs without hardware I/O, writes concrete movement
metrics, and optionally delegates deterministic visual capture to the Node CDP
helper. A successful run is evidence about simulation only, never hardware.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
from pathlib import Path

from takeone.director.cinematic_motifs import MOTIFS, resolve
from takeone.previs.templates import PRESETS, compile_template, defaults_for
from takeone.previs.travel_review import review_travel


def _run(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        return f"unavailable: {error}"


def _distance(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:])) if len(points) > 1 else 0.0


def _review(settings, preview):
    actor_id = "lead" if settings["subject_motion"] != "none" else ""
    shot = {
        "start_ms": 0,
        "end_ms": round(preview["orbit_duration_s"] * 1000),
        "actor_id": actor_id,
    }
    return review_travel(shot, settings, preview)


def _row(label, settings, preview, family="", motif_id=None):
    review = _review(settings, preview)
    metrics = review.get("metrics") or {}
    frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
    return {
        "id": label,
        "motif_id": motif_id,
        "family": family,
        "template_id": settings["template_id"],
        "subject_motion": settings["subject_motion"],
        "setup_s": preview["orbit_start_s"],
        "filming_s": preview["orbit_duration_s"],
        "frames": len(frames),
        "cart_path_m": metrics.get("cart", {}).get("path_m"),
        "actor_path_m": metrics.get("actor", {}).get("path_m"),
        "optical_path_m": metrics.get("optical", {}).get("path_m"),
        "phone_relative_excursion_m": metrics.get("arm_relative", {}).get("excursion_m"),
        "phone_rotation_excursion_rad": metrics.get("arm_rotation_excursion_rad"),
        "light_relative_excursion_m": metrics.get("light_relative", {}).get("excursion_m"),
        "light_rotation_excursion_rad": metrics.get("light_rotation_excursion_rad"),
        "longest_actor_cart_phone_overlap_s": metrics.get("longest_simultaneous_s"),
        "coordination_phases": review.get("coordination_phases", []),
        "max_aim_error_deg": preview["summary"].get("max_aim_error_deg"),
        "plan_id": preview.get("plan_id"),
        "visual_times_s": [
            preview["orbit_start_s"] + fraction * preview["orbit_duration_s"]
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--debug-port", type=int, default=None)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    templates = []
    for preset in PRESETS:
        settings = defaults_for(preset["id"])
        preview = compile_template(settings)["preview"]
        templates.append(_row(preset["id"], settings, preview, preset["family"]))
        print("template", preset["id"], flush=True)

    motifs = []
    for motif_id, metadata in MOTIFS.items():
        duration = sum(metadata["duration_s"]) / 2
        resolved = resolve(motif_id, duration)
        preview = compile_template(resolved["settings"])["preview"]
        motifs.append(_row(motif_id, resolved["settings"], preview, "Cinematic motifs", motif_id))
        print("motif", motif_id, flush=True)

    (output / "movement-metrics.json").write_text(json.dumps(templates, indent=2), encoding="utf-8")
    (output / "motif-metrics.json").write_text(json.dumps(motifs, indent=2), encoding="utf-8")
    requests = [
        {
            "id": row["id"],
            "family": row["family"],
            "template_id": row["template_id"],
            "times_s": row["visual_times_s"],
        }
        for row in templates
    ]
    (output / "visual-requests.json").write_text(json.dumps(requests, indent=2), encoding="utf-8")
    manifest = {
        "source": "TakeOne deterministic simulator; no hardware I/O",
        "python": platform.python_version(),
        "node": _run("node", "--version"),
        "git_head": _run("git", "rev-parse", "HEAD"),
        "git_status": _run("git", "status", "--short"),
        "template_count": len(templates),
        "motif_count": len(motifs),
        "base_url": args.base_url,
        "visual_capture_requested": args.debug_port is not None,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.debug_port is not None:
        helper = Path(__file__).with_name("cinematic_visual_audit.mjs")
        subprocess.run(
            [
                "node",
                str(helper),
                "--requests",
                str(output / "visual-requests.json"),
                "--output",
                str(output),
                "--base-url",
                args.base_url,
                "--debug-port",
                str(args.debug_port),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
