"""Create a labelled local cinematic draft and record non-actuating HTTP preview evidence.

Run from any directory with TakeOne's .venv Python. No AI provider or robot endpoint
is invoked. Existing productions are preserved. --install creates one new draft.
"""

import argparse
import copy
import json
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from takeone.director.cinematic import wire_settings
from takeone.previs.channels import ramp
from takeone.previs.templates import defaults_for

ROOT = Path(__file__).resolve().parents[1]


def request(path, body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8766" + path, raw, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def envelope():
    runtime = request("/api/director/runtime")
    return dict(
        schema_version=1,
        operation_id=str(uuid4()),
        runtime_epoch=runtime["runtime_epoch"],
        expires_monotonic_ns=str(int(runtime["now_monotonic_ns"]) + int(runtime["command_ttl_ns"])),
    )


def project():
    title = "Cinematic upgrade · product study and short cuts"
    brief = dict(
        title=title,
        objective="Authored software demonstration: a product light study, three short edit beats from one take, organic orbit, negative space, foreground reveal and detail pass.",
        duration_ms=30000,
        aspect_ratio="16:9",
    )
    context = dict(
        skill_id="product", audience="Director workflow review", tone="Measured product study", facts=[]
    )
    objects = [
        dict(
            object_id="bottle",
            asset_id="product",
            label="Product study proxy",
            position_m=[0, 0, 1.4],
            size_m=[0.16, 0.16, 0.3],
            yaw_rad=0,
        ),
        dict(
            object_id="plinth",
            asset_id="plinth",
            label="Display plinth",
            position_m=[0, 0, 0.625],
            size_m=[0.6, 0.6, 1.25],
            yaw_rad=0,
        ),
    ]
    scenes, marks = [], []
    base = defaults_for("product_highlight") | dict(duration_s=4)
    choices = [
        (0, 800, "product_highlight", 0, 0, base),
        (800, 1600, "product_highlight", 0, 0.8, base),
        (1600, 2400, "product_highlight", 0, 1.6, base),
        (
            2400,
            10000,
            "product_orbit",
            1,
            None,
            defaults_for("product_orbit")
            | dict(
                texture=dict(enabled=True, amplitude_rad=0.01, frequency_hz=0.2),
                channels=dict(
                    camera_height_m=ramp(1.5, 1.59, 0.05, 0.3), light_height_m=ramp(1.6, 1.5, 0.6, 0.95)
                ),
            ),
        ),
        (10000, 16000, "product_drift", 1, None, defaults_for("product_drift")),
        (16000, 23000, "product_reveal", 2, None, defaults_for("product_reveal")),
        (23000, 30000, "product_macro", 2, None, defaults_for("product_macro")),
    ]
    for i in range(3):
        scene_id = f"studio-{i + 1}"
        scenes.append(
            dict(
                scene_id=scene_id,
                title=[
                    "One light study · three short cuts",
                    "Shape and negative space",
                    "Foreground and detail",
                ][i],
                location="Assumed tabletop studio",
                space_id=scene_id,
                atmosphere="studio",
                location_notes="Find a clear level studio floor. Place a small product on a stable plinth near lens height with a neutral background. Leave at least the full displayed cart route clear. This is an authored demonstration, not a surveyed set.",
                objects=copy.deepcopy(objects),
                cast=[],
                shots=[],
            )
        )
        marks.append(
            dict(
                mark_id=f"M{i}",
                description="Product centre on the plinth",
                scene_id=scene_id,
                position_m=[0, 0],
                facing_rad=0,
            )
        )
    # The opening sightline, rather than the cart path, passes through this screen.
    scenes[2]["objects"].append(
        dict(
            object_id="screen",
            asset_id="wall",
            label="Foreground screen",
            position_m=[0.86, -0.66, 1.4],
            size_m=[0.35, 0.35, 0.7],
            yaw_rad=0,
        )
    )
    for i, (start, end, template, scene_index, source_in, s) in enumerate(choices):
        parameters = [dict(name="duration_s", value=4)] if source_in is not None else []
        scenes[scene_index]["shots"].append(
            dict(
                shot_id=f"beat-{i + 1}",
                start_ms=start,
                end_ms=end,
                actor_id="",
                mark_id=f"M{scene_index}",
                action="Keep the product still. Let the selected camera or light gesture carry this beat.",
                framing="close_up",
                primitive="template",
                camera_intent="Study the object's silhouette and surface; review the full take as well as the short edit.",
                light_intent="Move the light arm on its own timeline. Brightness and colour are manual.",
                edit_intent="Use source motion at its captured speed; trim excess footage.",
                lines=[],
                selected_line=0,
                movement=dict(
                    template_id=template,
                    subject_motion="none",
                    parameters=parameters,
                    cinematography=wire_settings(s),
                ),
                transition="reposition" if i == 6 else "cut",
                camera_target=dict(kind="object", target_id="bottle"),
                tracking=dict(
                    cart="planned",
                    phone="planned",
                    on_loss="stop_and_hold",
                    reason="Static product; no person following.",
                ),
                audio_intent="No spoken line. Add an appropriate music or room-sound bed in the edit.",
                capture=dict(take_id="light-study" if source_in is not None else "", in_s=source_in or 0),
            )
        )
    return dict(
        brief=brief,
        context=context,
        document=dict(
            title=title,
            logline=brief["objective"],
            audience=context["audience"],
            tone=context["tone"],
            actors=[],
            marks=marks,
            questions=[],
            scenes=scenes,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--previews", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "data/cinematic-upgrade-20260914"
    destination.mkdir(parents=True, exist_ok=True)
    sample = project()
    (destination / "demonstration-project.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    if args.install:
        result = request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))
        session = result["session"]
        scope = dict(
            session_id=session["session_id"],
            expected_revision=session["revision"],
            cancellation_generation=session["cancellation_generation"],
            take_id=session["take_id"],
            plan_id=None,
        )
        request(
            "/api/director/creative",
            envelope()
            | dict(
                scope=scope, action="start_script", payload={k: sample[k] for k in ("document", "context")}
            ),
        )
        detail = request("/api/director/sessions/" + session["session_id"])
        ref = session["session_id"] + "/" + detail["creative"]["digest"]
        manifest = request("/api/director/studio/" + ref)
        program = request("/api/previs/sequence", manifest)
        (destination / "demonstration-installed.json").write_text(
            json.dumps(dict(reference=ref, detail=detail, program=program), indent=2), encoding="utf-8"
        )
        print("DEMONSTRATION http://127.0.0.1:8766/?script=" + ref, flush=True)
    if args.previews:
        results = []
        for template in (
            "spiral",
            "s_curve",
            "arc_push",
            "pass_by",
            "three_beat",
            "product_highlight",
            "product_macro",
            "product_orbit",
            "product_reveal",
            "product_drift",
        ):
            start = time.perf_counter()
            preview = request("/api/previs/templates", defaults_for(template))
            row = dict(
                template_id=template,
                seconds=time.perf_counter() - start,
                frames=len(preview["frames"]),
                summary=preview["summary"],
                plan_id=preview["plan_id"],
            )
            results.append(row)
            print(template, round(row["seconds"], 3), flush=True)
        (destination / "http-preview-evidence.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
