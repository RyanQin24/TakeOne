"""Render reproducible SVG evidence for the mobile-IK correction."""

import html
import json
from pathlib import Path

import numpy as np
from takeone.planning.targets import ARMS, actor_target, tracking_programs
from takeone.simulation import drive

ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "data" / "real-robot-review-geometry-calibration-final.json"
AFTER = ROOT / "data" / "real-robot-review-mobile-ik-final-20260912.json"
OUTPUT = ROOT / "docs" / "images" / "tool-path-errors-before-after.svg"


def old_series(document, arm):
    settings = document["settings"]
    program = tracking_programs(settings, drive.DIRECTION_SIGN)[arm.role]
    transition = document["revision"]["transition_s"]
    requested, achieved = [], []
    for frame in document["execution_preview"]["frames"]:
        elapsed = frame["time_s"] - transition
        if not 0 <= elapsed <= settings["duration"]:
            continue
        phase = elapsed / settings["duration"]
        target = program.at(phase, np.asarray(frame["q"][:3]), actor_target(settings, phase))
        requested.append(target.position_m[:2])
        achieved.append(frame["camera" if arm.role.value == "phone" else "light"]["pos"][:2])
    return np.asarray(requested), np.asarray(achieved)


def new_series(document, arm):
    settings = document["settings"]
    transition = document["revision"]["transition_s"]
    target_samples = document["requested_world_targets"][arm.role.value]["samples"]
    frames = document["execution_preview"]["frames"]
    requested, achieved = [], []
    target_phases = np.asarray([item["phase"] for item in target_samples])
    target_xy = np.asarray([item["position_m"][:2] for item in target_samples])
    for frame in frames:
        elapsed = frame["time_s"] - transition
        if not 0 <= elapsed <= settings["duration"]:
            continue
        phase = elapsed / settings["duration"]
        requested.append([np.interp(phase, target_phases, target_xy[:, axis]) for axis in (0, 1)])
        achieved.append(frame["camera" if arm.role.value == "phone" else "light"]["pos"][:2])
    return np.asarray(requested), np.asarray(achieved)


def panel(x, title, requested, achieved):
    left, top, width, height = x, 105, 270, 510
    points = np.vstack([requested, achieved])
    center = (points.min(axis=0) + points.max(axis=0)) / 2
    span = np.maximum(points.max(axis=0) - points.min(axis=0), [0.12, 0.12])
    scale = min((width - 46) / span[0], (height - 100) / span[1])

    def project(values):
        px = left + width / 2 + (values[:, 0] - center[0]) * scale
        py = top + height / 2 - (values[:, 1] - center[1]) * scale
        return np.c_[px, py]

    wanted, actual = project(requested), project(achieved)
    errors = np.linalg.norm(achieved - requested, axis=1)
    worst = int(np.argmax(errors))
    rms = float(np.sqrt(np.mean(np.square(errors))))

    def polyline(values):
        stride = max(1, len(values) // 80)
        selected = values[::stride]
        if not np.array_equal(selected[-1], values[-1]):
            selected = np.vstack([selected, values[-1]])
        return " ".join(f"{a:.2f},{b:.2f}" for a, b in selected)

    return f"""
    <g>
      <rect x="{left}" y="{top}" width="{width}" height="{height}" rx="12" fill="#111827" stroke="#334155"/>
      <text x="{left + 16}" y="{top + 28}" class="panel-title">{html.escape(title)}</text>
      <line x1="{left + 24}" y1="{top + height - 35}" x2="{left + 76}" y2="{top + height - 35}" class="axis"/>
      <line x1="{left + 24}" y1="{top + height - 35}" x2="{left + 24}" y2="{top + height - 87}" class="axis"/>
      <text x="{left + 79}" y="{top + height - 30}" class="axis-label">world +X</text>
      <text x="{left + 5}" y="{top + height - 91}" class="axis-label">+Y</text>
      <polyline points="{polyline(wanted)}" class="requested"/>
      <polyline points="{polyline(actual)}" class="achieved"/>
      <line x1="{wanted[worst, 0]:.2f}" y1="{wanted[worst, 1]:.2f}" x2="{actual[worst, 0]:.2f}" y2="{actual[worst, 1]:.2f}" class="error"/>
      <circle cx="{wanted[worst, 0]:.2f}" cy="{wanted[worst, 1]:.2f}" r="4" fill="#38bdf8"/>
      <circle cx="{actual[worst, 0]:.2f}" cy="{actual[worst, 1]:.2f}" r="4" fill="#fb7185"/>
      <text x="{left + 16}" y="{top + height - 62}" class="metric">XY max {100 * errors[worst]:.3f} cm · RMS {100 * rms:.3f} cm</text>
    </g>"""


def main():
    before = json.loads(BEFORE.read_text(encoding="utf-8-sig"))
    after = json.loads(AFTER.read_text(encoding="utf-8-sig"))
    columns = []
    for arm, label in zip(ARMS, ("Phone", "Light")):
        columns.append((label + " · before", *old_series(before, arm)))
        columns.append((label + " · corrected", *new_series(after, arm)))
    panels = "".join(
        panel(25 + index * 290, title, wanted, actual)
        for index, (title, wanted, actual) in enumerate(columns)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
    <style>
      text {{ font-family: Inter, Segoe UI, sans-serif; fill: #e5e7eb; }}
      .title {{ font-size: 25px; font-weight: 700; }} .subtitle {{ font-size: 14px; fill: #94a3b8; }}
      .panel-title {{ font-size: 17px; font-weight: 650; }} .metric {{ font-size: 13px; fill: #cbd5e1; }}
      .axis {{ stroke: #64748b; stroke-width: 1.5; }} .axis-label {{ font-size: 11px; fill: #94a3b8; }}
      .requested {{ fill: none; stroke: #38bdf8; stroke-width: 3; }}
      .achieved {{ fill: none; stroke: #fb7185; stroke-width: 2.2; }}
      .error {{ stroke: #fbbf24; stroke-width: 4; stroke-dasharray: 7 5; }}
    </style>
    <rect width="1200" height="680" fill="#070b14"/>
    <text x="25" y="38" class="title">Requested and achieved optical-center paths · world XY top view</text>
    <text x="25" y="65" class="subtitle">Blue: frozen requested path · pink: FK result · yellow: largest XY error vector. Each panel uses equal X/Y scale.</text>
    {panels}
    </svg>"""
    OUTPUT.write_text(svg, encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
