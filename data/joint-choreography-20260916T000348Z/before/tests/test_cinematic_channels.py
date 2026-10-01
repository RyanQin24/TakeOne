"""Cinematic contracts checked against real compilation; no device IO."""

import hashlib
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from takeone.director.cinematic import wire_settings
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, plan_schema, validate, validate_plan
from takeone.director.studio import rehearsal_manifest
from takeone.motion.plan import encoded
from takeone.previs.capture import window
from takeone.previs.channels import channel, ramp, validate_channels
from takeone.previs.compound import points
from takeone.previs.diagnostics import reach
from takeone.previs.path import compile_path
from takeone.previs.policy import motion_policy
from takeone.previs.program import aim_offsets
from takeone.previs.sequence import build_program
from takeone.previs.templates import compile_template, defaults_for


class CinematicChannelTests(unittest.TestCase):
    def test_all_28_pre_upgrade_settings_keep_exact_frames_samples_and_commands(self):
        baseline = json.loads((Path(__file__).parent / "fixtures/legacy-movement-frames.json").read_text())
        for old in baseline["templates"]:
            with self.subTest(template=old["template_id"]):
                result = compile_template(old["settings"])
                frames = [
                    {k: f[k] for k in baseline["frame_keys"] if k in f} for f in result["preview"]["frames"]
                ]
                for label, data in (
                    ("frame", frames),
                    ("samples", result["plan"]["samples"]),
                    ("cart", result["plan"]["cart_schedule"]),
                ):
                    self.assertEqual(hashlib.sha256(encoded(data)).hexdigest(), old[label + "_sha256"])

    def test_pan_tilt_roll_and_texture_are_summed_on_a_moving_arc(self):
        program = defaults_for("arc_left") | dict(aim="pan", sign=1)
        base = np.array(aim_offsets(program, 0.4, 20))
        program["channels"] = dict(
            pan_rad=ramp(0.02, 0.02), tilt_rad=ramp(0.03, 0.03), roll_rad=ramp(0.04, 0.04)
        )
        np.testing.assert_allclose(aim_offsets(program, 0.4, 20), base + [0.02, 0.03, 0.04])
        settings = defaults_for("arc_left") | dict(
            texture=dict(enabled=True, amplitude_rad=0.01, frequency_hz=0.2)
        )
        result = compile_template(settings)
        frames = result["preview"]["frames"]
        self.assertGreater(max(abs(f["requested_aim_rad"][2]) for f in frames), 0.002)
        self.assertGreater(result["preview"]["summary"]["distance_m"], 3)
        self.assertEqual(result["preview"]["camera_output"]["horizon"], "phone")

    def test_independent_camera_light_lens_and_target_timing(self):
        # The height change needs nine seconds within the unchanged arm rate.
        s = defaults_for("static") | dict(duration_s=30)
        s["channels"] = dict(
            camera_height_m=ramp(1.5, 1.6, 0, 0.3),
            camera_target_m=ramp([0, 0, 1.55], [0, 0.25, 1.55]),
            light_height_m=ramp(1.5, 1.65, 0.7, 1),
            light_target_m=ramp([0, -0.2, 1.5], [0, 0.2, 1.5]),
        )
        s["camera"] = dict(
            horizon="auto",
            zoom="keyframes",
            keyframes=[
                dict(at=0, focal_mm=35, ease="hold"),
                dict(at=0.5, focal_mm=35, ease="smooth"),
                dict(at=1, focal_mm=70, ease="smooth"),
            ],
        )
        self.assertEqual(channel(s, "camera_height_m", 0.5), 1.6)
        self.assertEqual(channel(s, "light_height_m", 0.5), 1.5)
        p = compile_template(s)["preview"]
        self.assertEqual(p["frames"][-1]["focal_mm"], 70)
        self.assertEqual(p["frames"][-1]["light_target_m"], [0, 0.2, 1.5])
        self.assertEqual(p["frames"][-1]["camera_target_m"], [0, 0.25, 1.55])
        self.assertLess(p["summary"]["max_aim_error_deg"], 3)
        self.assertAlmostEqual(p["frames"][-1]["requested_camera_height_m"], 1.6)

    def test_compound_sweep_keeps_requested_angle_past_ninety_degrees(self):
        angle = math.radians(135)
        for route in ("arc_push", "three_beat"):
            route_points = points(route, [1, 0], 2.5, 1.5, angle)
            np.testing.assert_allclose(route_points[48], [4 * math.cos(angle), 4 * math.sin(angle)])
        preview = compile_template(defaults_for("arc_push") | dict(sweep_rad=angle))["preview"]
        self.assertLess(preview["summary"]["endpoint_error_m"], 0.05)
        self.assertLess(preview["summary"]["max_aim_error_deg"], 3)

    def test_product_light_stays_on_object_when_camera_target_drifts(self):
        preview = compile_template(defaults_for("product_drift"))["preview"]
        self.assertEqual(preview["frames"][-1]["camera_target_m"], [0, 0.6, 1.4])
        self.assertTrue(all(frame["light_target_m"] == [0, 0, 1.4] for frame in preview["frames"]))

    def test_fast_height_keys_report_achieved_aim_instead_of_raising_arm_rate(self):
        s = defaults_for("static") | dict(channels=dict(camera_height_m=ramp(1.5, 1.6, 0, 0.3)))
        preview = compile_template(s)["preview"]
        diagnostic = next(d for d in reach("fast-height", preview["summary"]) if d.code == "aim_reach")
        self.assertGreater(diagnostic.observed, 3)
        self.assertEqual(diagnostic.observed, preview["summary"]["max_aim_error_deg"])

    def test_policy_cannot_change_the_motion_plan_clock(self):
        from takeone.config import read_json
        from takeone.paths import CONFIGS

        config = read_json(CONFIGS / "arm-execution.json")
        config["period_s"] = config["previs_policy"]["arm_period_s"] = 0.02
        config["previs_policy"]["arm_counts_per_tick"] = 5
        with patch("takeone.previs.policy.read_json", return_value=config):
            with self.assertRaisesRegex(ValueError, "motion-plan"):
                motion_policy()

    def test_drawn_route_can_carry_aim_and_light_channels(self):
        p = compile_path(
            dict(
                points_m=[[2.5, -0.5], [2.5, 0.5]],
                channels=dict(roll_rad=ramp(0, 0.05), light_height_m=ramp(1.5, 1.6)),
            )
        )["preview"]
        self.assertAlmostEqual(p["frames"][-1]["requested_aim_rad"][2], 0.05)
        self.assertEqual(p["camera_output"]["horizon"], "phone")

    def test_profile_preserves_command_grid_slew_holds_and_arm_step(self):
        s = defaults_for("pass_by") | dict(distance_m=1.5, speed_m_s=0.3)
        s["channels"] = {"pace_m_s": ramp(0.2, 0.3)}
        result = compile_template(s)
        plan = result["plan"]
        setup = plan["orbit_start_s"]
        rows = [r for r in plan["cart_schedule"] if r["time_s"] >= setup - 1e-8]
        self.assertTrue(all(r["commands"] == [0, 0] for r in rows if r["time_s"] < setup + 0.6 - 1e-8))
        self.assertTrue(all(r["commands"] == [0, 0] for r in rows if r["time_s"] > plan["duration_s"] - 1))
        for a, b in zip(rows, rows[1:]):
            for x, y in zip(a["commands"], b["commands"]):
                self.assertTrue(abs(x - y) <= 0.010001 or (min(x, y) == 0 and max(x, y) <= 0.040001))
        samples = [s for s in plan["samples"] if s["time_s"] >= setup - 1e-8]
        for a, b in zip(samples, samples[1:]):
            for role in ("phone", "light"):
                for joint in a["raw_by_role"][role]:
                    self.assertLessEqual(
                        abs(b["raw_by_role"][role][joint] - a["raw_by_role"][role][joint]), 11
                    )
        self.assertEqual(motion_policy().cart_pace_max_m_s, 0.35)
        self.assertEqual(motion_policy().arm_counts_per_tick, 11)

    def test_invalid_channel_time_units_and_unknown_names_are_rejected(self):
        for value in (
            {"surprise": ramp(0, 1)},
            {"pace_m_s": ramp(0.14, 0.36)},
            {"pan_rad": ramp(0, math.nan)},
            {
                "camera_height_m": [
                    dict(at=0.1, value=1.5, ease="smooth"),
                    dict(at=1, value=1.6, ease="smooth"),
                ]
            },
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_channels(value)

    def test_shared_take_amortizes_setup_without_truncating_unused_source(self):
        s = defaults_for("static") | dict(duration_s=4.0)
        shots = [
            dict(
                shot_id=f"s{i}",
                mark_id="A",
                start_ms=i * 800,
                end_ms=(i + 1) * 800,
                settings=s,
                capture=dict(take_id="one", in_s=i * 0.8),
                transition="cut",
            )
            for i in range(3)
        ]
        manifest = dict(
            title="Three quick cuts",
            session_id="test",
            document_digest="test",
            manifest_digest="test",
            shots=shots,
            marks=[],
        )
        program = build_program(manifest)
        segments = program["segments"]
        self.assertEqual(len(segments), 3)
        self.assertEqual([s["setup_s"] for s in segments[1:]], [0, 0])
        full = compile_template(s)["preview"]
        self.assertAlmostEqual(program["duration_s"], full["duration_s"])
        self.assertEqual(program["edit_duration_s"], 2.4)
        a = window(full, 0, 0.8, True)
        b = window(full, 0.8, 0.8, False)
        self.assertEqual(a["frames"][-1]["raw_by_role"], b["frames"][0]["raw_by_role"])
        shots[1]["capture"]["in_s"] = 1.0
        with self.assertRaisesRegex(ValueError, "adjoining"):
            build_program(manifest)

    def test_product_script_with_zero_actors_roundtrips_to_a_visible_object_target(self):
        project = json.loads((Path(__file__).parent / "fixtures/director_arrival.json").read_text())
        doc = project["document"]
        doc["actors"] = []
        doc["scenes"] = doc["scenes"][:1]
        doc["marks"] = doc["marks"][:1]
        scene = doc["scenes"][0]
        scene["cast"] = []
        scene["objects"] = [
            dict(
                object_id="bottle",
                asset_id="product",
                label="Bottle",
                position_m=[0, 0, 1.4],
                size_m=[0.16, 0.16, 0.3],
                yaw_rad=0,
            )
        ]
        shot = scene["shots"][0]
        shot.update(
            actor_id="",
            end_ms=8000,
            camera_target=dict(kind="object", target_id="bottle"),
            tracking=dict(cart="planned", phone="planned", on_loss="stop_and_hold", reason="Static product."),
            capture=dict(take_id="", in_s=0),
        )
        s = defaults_for("product_highlight")
        shot["movement"] = dict(
            template_id="product_highlight",
            subject_motion="none",
            parameters=[],
            cinematography=wire_settings(s),
        )
        # This product draft extends an older saved fixture; new provider
        # proposals additionally carry visual_style and shot-design fields.
        validate(doc, plan_schema(require_movement=False))
        validate_plan(doc, ProductionBrief.parse(project["brief"]), project["context"])
        detail = dict(
            creative=dict(document=doc, context=project["context"], digest=digest(doc)),
            session=dict(brief=project["brief"], session_id="test", revision=1),
        )
        manifest = rehearsal_manifest(detail, digest(doc))
        preview = compile_template(manifest["shots"][0]["settings"])["preview"]
        self.assertEqual(preview["settings"]["subject_motion"], "none")
        self.assertEqual(preview["frames"][-1]["camera_target_m"], [0, 0, 1.4])
        self.assertEqual(preview["set_scene"]["objects"][0]["asset_id"], "product")
        self.assertEqual(manifest["shots"][0]["tracking"]["requested_controllers"], [])
