"""Script meaning survives schema, solved camera framing and rehearsal."""

import copy
import json
import math
import unittest
from pathlib import Path

import numpy as np
from takeone.director.cinematic import wire_settings
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, plan_schema, validate, validate_plan
from takeone.director.shot_design import FRAMINGS, defaults
from takeone.director.studio import rehearsal_manifest
from takeone.previs.channels import ramp, validate_channels
from takeone.previs.sequence import build_program
from takeone.previs.shot_review import lens_cue, projection
from takeone.previs.templates import compile_template, defaults_for, validate_settings


def story(framing="full"):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/director_arrival.json").read_text(encoding="utf-8")
    )
    doc = fixture["document"]
    scene = doc["scenes"][0]
    shot = scene["shots"][0]
    shot.update(
        start_ms=0,
        end_ms=6000,
        framing=framing,
        primitive="template",
        movement=dict(
            template_id="static",
            subject_motion="hold",
            parameters=[
                dict(name="radius_m", value=3),
                dict(name="focal_mm", value=80),
            ],
            cinematography=wire_settings(defaults_for("static")),
        ),
        camera_target=dict(kind="actor", target_id=shot["actor_id"]),
        capture=dict(take_id="", in_s=0),
    )
    shot["design"] = defaults(shot) | dict(lens_policy="fit_subject")
    scene["shots"] = [shot]
    scene["cast"] = []
    scene["objects"] = []
    doc["scenes"] = [scene]
    doc["marks"] = [next(m for m in doc["marks"] if m["mark_id"] == shot["mark_id"])]
    doc["marks"][0].update(position_m=[0, 0], facing_rad=0)
    fixture["brief"]["duration_ms"] = 6000
    return fixture


def manifest(fixture):
    doc = fixture["document"]
    return rehearsal_manifest(
        dict(
            session=dict(session_id="shot-test", revision=1, brief=fixture["brief"]),
            creative=dict(document=doc, context=fixture["context"], digest=digest(doc)),
        ),
        digest(doc),
    )


class ShotDesignTests(unittest.TestCase):
    def test_named_body_shots_include_the_actual_knee_and_thigh_landmarks(self):
        # The standing proxy's hip is at 0.78 m and its thigh is 0.36 m.
        for size, landmark_m in (("medium_full", 0.42), ("cowboy", 0.60)):
            with self.subTest(size=size):
                settings = manifest(story(size))["shots"][0]["settings"]
                preview = compile_template(settings)["preview"]
                for frame in preview["frames"]:
                    if frame["time_s"] < preview["orbit_start_s"]:
                        continue
                    point = np.asarray(frame["actor"]["position_m"]) + [0, 0, landmark_m]
                    screen, depth = projection(frame, [point])
                    self.assertGreater(depth[0], 0)
                    self.assertLessEqual(abs(screen[0][1]), 0.94)

    def test_reveal_checks_the_ending_without_misreporting_the_intentional_opening(self):
        f = story("full")
        shot = f["document"]["scenes"][0]["shots"][0]
        shot["design"].update(lens_policy="authored", visibility="by_end")
        shot["movement"]["cinematography"]["camera"] = dict(
            horizon="auto",
            zoom="keyframes",
            keyframes=[dict(at=0, focal_mm=120, ease="smooth"), dict(at=1, focal_mm=13, ease="smooth")],
        )
        ending = build_program(manifest(f))["segments"][0]["shot_review"]
        self.assertEqual(ending["coverage_samples_examined"], 1)
        self.assertFalse(any(i["code"] == "promised_region_cropped" for i in ending["issues"]))
        shot["design"]["visibility"] = "throughout"
        full = build_program(manifest(f))["segments"][0]["shot_review"]
        self.assertTrue(any(i["code"] == "promised_region_cropped" for i in full["issues"]))

    def test_nine_sizes_fit_and_survive_to_actor_card_and_review(self):
        for size in FRAMINGS:
            with self.subTest(size=size):
                f = story(size)
                m = manifest(f)
                json.dumps(m, allow_nan=False)
                shot = m["shots"][0]
                self.assertEqual(shot["shot_card"]["shot_size"], size)
                self.assertTrue(shot["framing_adjustment"]["applied"])
                program = build_program(m)
                segment = program["segments"][0]
                self.assertGreater(segment["shot_review"]["samples_examined"], 20)
                crop = [i for i in segment["shot_review"]["issues"] if i["code"] == "promised_region_cropped"]
                self.assertEqual(crop, [])
                self.assertGreaterEqual(segment["settings"]["focal_mm"], 13)
                self.assertLessEqual(segment["settings"]["focal_mm"], 360)

    def test_authored_tight_lens_reports_cropped_feet_with_times(self):
        f = story()
        f["document"]["scenes"][0]["shots"][0]["design"]["lens_policy"] = "authored"
        m = manifest(f)
        self.assertEqual(m["shots"][0]["settings"]["focal_mm"], 80)
        report = build_program(m)["segments"][0]["shot_review"]
        issue = next(i for i in report["issues"] if i["code"] == "promised_region_cropped")
        self.assertGreater(issue["evidence"]["affected_samples"], 0)
        self.assertGreater(issue["time_range_s"][1], 0)
        self.assertEqual(report["source"], "simulated_geometry")

    def test_actor_path_and_look_feed_real_solver_and_preserve_cart(self):
        s = defaults_for("boom_up") | dict(
            duration_s=12, height_start_m=1.5, height_end_m=1.5, scene=dict(actor_facing="fixed")
        )
        base = compile_template(s)["preview"]
        s["channels"] = dict(
            actor_position_m=ramp([0, 0, 0], [0, 0.4, 0], 0.2, 0.7),
            actor_heading_rad=ramp(0, 0.4),
            gaze_pitch_rad=ramp(0, 0.3),
        )
        moved = compile_template(s)["preview"]
        np.testing.assert_allclose(moved["frames"][-1]["actor"]["position_m"][:2], [0, 0.4])
        self.assertAlmostEqual(moved["frames"][-1]["actor"]["heading_rad"], 0.4)
        self.assertAlmostEqual(moved["frames"][-1]["actor"]["gaze_pitch_rad"], 0.3)
        np.testing.assert_allclose(moved["frames"][-1]["face"][:2], [0, 0.4])
        self.assertNotEqual(
            base["frames"][-1]["raw_by_role"]["phone"], moved["frames"][-1]["raw_by_role"]["phone"]
        )
        np.testing.assert_allclose(base["frames"][-1]["axle_m"], moved["frames"][-1]["axle_m"])

    def test_blocking_cannot_teleport_float_or_animate_an_absent_actor(self):
        for keys in (
            ramp([0, 0, 1], [0, 0, 1]),
            [dict(at=0, value=[0, 0, 0], ease="hold"), dict(at=1, value=[1, 0, 0], ease="smooth")],
        ):
            with self.assertRaises(ValueError):
                validate_channels(dict(actor_position_m=keys))
        with self.assertRaisesRegex(ValueError, "product-only"):
            validate_settings(defaults_for("product_orbit") | dict(channels=dict(gaze_yaw_rad=ramp(0, 0.2))))

    def test_two_shot_requires_staged_people_and_checks_both(self):
        f = story("medium")
        doc = f["document"]
        shot = doc["scenes"][0]["shots"][0]
        main = shot["actor_id"]
        other = next(a["actor_id"] for a in doc["actors"] if a["actor_id"] != main)
        shot["design"].update(
            composition="two_shot", featured_actor_ids=[main, other], lens_policy="authored"
        )
        with self.assertRaisesRegex(ValueError, "staged"):
            manifest(f)
        doc["scenes"][0]["cast"] = [
            dict(actor_id=other, offset_m=[0, 2, 0], facing_rad=math.pi, motion="hold")
        ]
        report = build_program(manifest(f))["segments"][0]["shot_review"]
        self.assertEqual(report["status"], "needs_revision")

    def test_bad_performance_times_are_rejected_without_mutation(self):
        for start, end in [(4, 3), (0, 7), (float("nan"), 1)]:
            f = story()
            f["document"]["scenes"][0]["shots"][0]["design"]["beats"][0].update(start_s=start, end_s=end)
            with self.assertRaises(ValueError):
                manifest(f)

    def test_manual_capabilities_are_reported_without_invented_footage_review(self):
        f = story()
        f["document"]["scenes"][0]["shots"][0]["design"].update(
            angle="aerial", focus=dict(mode="rack", target="Face to the sign.")
        )
        report = build_program(manifest(f))["segments"][0]["shot_review"]
        self.assertTrue({"equipment_required", "focus_manual"} <= {i["code"] for i in report["issues"]})
        self.assertIn("Facial performance and recorded sound", report["unchecked"])
        self.assertFalse(lens_cue(48)["physical_lens"])
        self.assertTrue(lens_cue(100)["physical_lens"])
        self.assertEqual(lens_cue(75)["control"], "manual_phone_app")

    def test_old_saved_data_and_old_channel_keys_stay_valid(self):
        f = story()
        doc = f["document"]
        del doc["scenes"][0]["shots"][0]["design"]
        channels = doc["scenes"][0]["shots"][0]["movement"]["cinematography"]["channels"]
        for key in ("actor_position_m", "actor_heading_rad", "gaze_yaw_rad", "gaze_pitch_rad"):
            channels.pop(key)
        before = copy.deepcopy(doc)
        validate_plan(doc, ProductionBrief.parse(f["brief"]), f["context"])
        self.assertEqual(doc, before)
        self.assertEqual(manifest(f)["shots"][0]["settings"]["focal_mm"], 80)

    def test_provider_schema_has_no_optional_keys_in_strict_mode(self):
        def check(schema):
            if schema["type"] == "object":
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                for value in schema["properties"].values():
                    check(value)
            if schema["type"] == "array":
                check(schema["items"])

        check(plan_schema())
        f = story()
        with self.assertRaises(ValueError):
            validate(f["document"], plan_schema())  # A new provider must supply visual_style.


if __name__ == "__main__":
    unittest.main()
