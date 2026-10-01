"""Install a visual-proof film using reusable cinematic motifs. No hardware I/O.

This is authored verification data, not a generation rule. Exact movement settings
come from cinematic_motifs.resolve and remain editable by Director/Shot Studio.
"""

import argparse
from pathlib import Path

from moving_camera_showcase import install, shot_from_settings, staged_object
from takeone.director.cinematic_motifs import resolve
from takeone.director.performers import PALETTE
from takeone.previs.templates import compile_template


def project():
    specs = [
        ("doorway_arrival", 8.0, "exterior_day", "Actor clears the doorway before the robot joins the walk."),
        (
            "actor_stop_camera_continue",
            8.0,
            "exterior_dusk",
            "Actor stops first; camera continues into a changed relationship.",
        ),
        (
            "pass_by_pan_back",
            8.0,
            "exterior_night",
            "Base passes while the phone keeps attention on the performer.",
        ),
        (
            "foreground_reveal_push",
            7.0,
            "interior_warm",
            "Foreground clears, then the camera makes a compact emphasis move.",
        ),
        (
            "product_parallax_light",
            7.0,
            "interior_cool",
            "Product stays fixed while parallax and independent light movement reveal form.",
        ),
    ]
    scenes, marks, clock = [], [], 0.0
    for index, (motif_id, duration, atmosphere, purpose) in enumerate(specs):
        resolved = resolve(motif_id, duration)
        settings = resolved["settings"]
        actual_duration = compile_template(settings)["preview"]["orbit_duration_s"]
        shot_id = f"motif-{index + 1}"
        shot = shot_from_settings(
            shot_id,
            settings,
            actual_duration,
            clock,
            purpose,
            framing="close_up" if settings["subject_motion"] == "none" else "medium",
        )
        scene_id = f"motif-scene-{index + 1}"
        mark_id = f"motif-mark-{index + 1}"
        shot["mark_id"] = mark_id
        shot["light_intent"] = (
            f"Motif role: {resolved['light_role']}. BR60 brightness/CCT remain manual; position and aim are simulated."
        )
        shot["design"]["continuity"] = (
            "Visual-proof take. The set stays fixed while actor, cart, phone and light follow the compiled program."
        )
        shot["motion_requirements"]["priority"] = "preferred"
        shot["motion_requirements"]["light_role"] = resolved["light_role"]
        shot["motion_requirements"].update(cart_travel_m=0.35, camera_travel_m=0.30)
        if settings["subject_motion"] == "walk":
            shot["motion_requirements"].update(
                actor_travel_m=0.45, arm_translation_m=0.03, simultaneous_s=0.8
            )
        if motif_id == "product_parallax_light":
            shot["motion_requirements"].update(light_translation_m=0.08)
        if motif_id == "product_parallax_light":
            objects = [
                staged_object("workpiece", "product", [0, 0, 1.4], [0.18, 0.18, 0.35]),
                staged_object("plinth", "plinth", [0, 0, 0.625], [0.65, 0.65, 1.25]),
                staged_object("practical", "practical_light", [1.35, 0.75, 0.9], [0.4, 0.4, 1.8]),
                staged_object("background", "screen", [0, 2.2, 1.1], [1.5, 0.15, 2.2]),
            ]
        else:
            objects = [
                staged_object("door", "doorway", [-0.8, 1.1, 1.4], [1.5, 0.18, 2.8], "ENTRY"),
                staged_object("bench", "table", [1.3, 1.0, 0.45], [1.5, 0.7, 0.9]),
                staged_object("workpiece", "product", [1.3, 1.0, 1.10], [0.18, 0.18, 0.35]),
                staged_object("practical", "practical_light", [2.0, 1.4, 0.9], [0.4, 0.4, 1.8]),
            ]
            if motif_id == "foreground_reveal_push":
                objects.append(staged_object("foreground", "screen", [-0.25, -0.7, 1.05], [0.45, 0.12, 2.1]))
        scenes.append(
            dict(
                scene_id=scene_id,
                space_id=scene_id,
                title=resolved["name"],
                location="Authored visual-proof set; not a measured venue",
                atmosphere=atmosphere,
                location_notes="Keep the displayed route, actor lane and foreground screen clear. Coordinates are simulation staging only.",
                objects=objects,
                cast=[],
                shots=[shot],
            )
        )
        marks.append(
            dict(
                mark_id=mark_id,
                scene_id=scene_id,
                description="Motif opening mark",
                position_m=[0, 0],
                facing_rad=0,
            )
        )
        clock += actual_duration
    title = "Cinematic motif visual proof"
    purpose = "Visually inspect adaptive motif choreography, staggered motion, foreground depth and day/night/light behavior."
    style = dict(
        visual_rules="Movement follows story beats; stillness is intentional and set depth remains fixed.",
        palette="Neutral set with a rust performer and teal product.",
        lighting="Atmosphere profile plus robot-light pose; BR60 brightness and CCT are manual setup.",
        wardrobe="Visitor remains in rust across actor shots.",
        sound="Simulation has no recorded production sound.",
        continuity_locks=[
            "Set objects do not move to fake parallax.",
            "Hardware is not actuated by this showcase.",
        ],
    )
    return dict(
        brief=dict(title=title, objective=purpose, duration_ms=round(clock * 1000), aspect_ratio="16:9"),
        context=dict(
            skill_id="cinematic", audience="TakeOne engineering review", tone="cinematic proof", facts=[]
        ),
        document=dict(
            title=title,
            logline=purpose,
            audience="TakeOne engineering review",
            tone="cinematic proof",
            actors=[dict(actor_id="visitor", name="Visitor", appearance=PALETTE | dict(cloth="#b95f3e"))],
            marks=marks,
            questions=[],
            visual_style=style,
            scenes=scenes,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--output", type=Path, default=Path("data/cinematic-choreography-audit-20260917/motif-showcase")
    )
    args = parser.parse_args()
    sample = project()
    if args.install:
        install(sample, args.output, f"http://127.0.0.1:{args.port}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(__import__("json").dumps(sample, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
