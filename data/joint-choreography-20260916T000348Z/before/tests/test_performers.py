"""Named attention survives schema, source timing and the canonical actor samples."""

import copy
import json
import math
import unittest

from takeone.director.creative import plan_schema, validate
from takeone.director.performers import PALETTE, validate_links
from takeone.previs.capture import window
from takeone.previs.performers import HEAD_RATIO, build_samples, sample_actors
from takeone.previs.sequence import build_program

from tests.test_shot_design import manifest, story


def look(kind, target_id="", point=None):
    return [
        dict(at=t, ease="linear", kind=kind, target_id=target_id, point_m=point or [0, 0, 0]) for t in (0, 1)
    ]


def track(actor_id, target_id, heading):
    return dict(
        actor_id=actor_id,
        body_heading_rad=[dict(at=t, value=heading, ease="linear") for t in (0, 1)],
        look_at=look("actor", target_id),
        gestures=[],
    )


def fixture():
    f = story("medium")
    doc, scene = f["document"], f["document"]["scenes"][0]
    shot = scene["shots"][0]
    lead = shot["actor_id"]
    doc["actors"] = [
        dict(actor_id=lead, name="Visitor", appearance=dict(PALETTE)),
        dict(actor_id="maker", name="Maker", appearance=PALETTE | dict(cloth="#17263c")),
    ]
    scene.update(
        space_id="workshop",
        cast=[dict(actor_id="maker", offset_m=[0, 1, 0], facing_rad=-math.pi / 2, motion="hold")],
    )
    shot["performers"] = [track(lead, "maker", math.pi / 2), track("maker", lead, -math.pi / 2)]
    shot["design"].update(composition="two_shot", featured_actor_ids=[lead, "maker"])
    return f


def frame(time=0):
    return dict(
        time_s=time,
        actor=dict(position_m=[0, 0, 0], heading_rad=0, phase_rad=0, gait_weight=0, walking=False),
        axle_m=[0, 0],
    )


def poses(f):
    scene = f["document"]["scenes"][0]
    return sample_actors(
        scene["shots"][0], scene, f["document"]["marks"][0], frame(), dict(subject_height_m=1.72), 0.5
    )


class PerformerTests(unittest.TestCase):
    def test_schema_accepts_authored_identity_and_attention(self):
        f = fixture()
        validate(f["document"], plan_schema(require_movement=False))
        validate_links(f["document"])
        self.assertEqual(json.loads(json.dumps(f))["document"], f["document"])

    def test_old_document_remains_unchanged(self):
        f = story()
        before = copy.deepcopy(f)
        manifest(f)
        self.assertEqual(f, before)

    def test_mutual_attention_uses_other_actor_not_the_lead_gaze(self):
        f = fixture()
        result = poses(f)
        lead = f["document"]["scenes"][0]["shots"][0]["actor_id"]
        self.assertAlmostEqual(result[lead]["heading_rad"], math.pi / 2)
        self.assertAlmostEqual(result["maker"]["heading_rad"], -math.pi / 2)
        for actor in result.values():
            self.assertAlmostEqual(actor["gaze_yaw_rad"], 0)
            self.assertAlmostEqual(actor["attention_error_rad"], 0)

    def test_world_target_is_translated_by_nonzero_scene_mark(self):
        f = fixture()
        shot = f["document"]["scenes"][0]["shots"][0]
        lead = shot["actor_id"]
        f["document"]["marks"][0]["position_m"] = [2, -3]
        shot["performers"][0]["look_at"] = look("point", point=[2, -2, HEAD_RATIO * 1.72])
        result = poses(f)[lead]
        self.assertEqual(result["look_target_m"][:2], [0, 1])
        self.assertAlmostEqual(result["gaze_yaw_rad"], 0)

    def test_behind_body_target_reports_head_limit_instead_of_rotating_body(self):
        f = fixture()
        t = f["document"]["scenes"][0]["shots"][0]["performers"][0]
        for key in t["body_heading_rad"]:
            key["value"] = -math.pi / 2
        result = poses(f)[t["actor_id"]]
        self.assertAlmostEqual(result["heading_rad"], -math.pi / 2)
        self.assertGreater(result["attention_error_rad"], 1)

    def test_invalid_color_and_unknown_look_target_are_refused(self):
        f = fixture()
        f["document"]["actors"][0]["appearance"]["cloth"] = "orange"
        with self.assertRaisesRegex(ValueError, "RRGGBB"):
            validate_links(f["document"])
        f = fixture()
        f["document"]["scenes"][0]["shots"][0]["performers"][0]["look_at"] = look("actor", "ghost")
        with self.assertRaisesRegex(ValueError, "staged"):
            validate_links(f["document"])

    def test_self_attention_is_refused(self):
        f = fixture()
        t = f["document"]["scenes"][0]["shots"][0]["performers"][0]
        t["look_at"] = look("actor", t["actor_id"])
        with self.assertRaisesRegex(ValueError, "another actor"):
            validate_links(f["document"])

    def test_bad_key_order_is_refused(self):
        f = fixture()
        t = f["document"]["scenes"][0]["shots"][0]["performers"][0]
        t["look_at"][1]["at"] = 0
        with self.assertRaises(ValueError):
            validate_links(f["document"])

    def test_reach_samples_hand_location_without_moving_the_object(self):
        f = fixture()
        t = f["document"]["scenes"][0]["shots"][0]["performers"][0]
        for k in t["body_heading_rad"]:
            k["value"] = 0
        t["gestures"] = [
            dict(
                at=at,
                ease="linear",
                name="reach",
                weight=1,
                kind="point",
                target_id="",
                point_m=[0.35, -0.2, 1.2],
            )
            for at in (0, 1)
        ]
        before = copy.deepcopy(f)
        result = poses(f)[t["actor_id"]]
        self.assertLess(result["reach_error_m"], 1e-5)
        self.assertEqual(f, before)

    def test_capture_window_keeps_full_take_attention_time(self):
        f = fixture()
        scene = f["document"]["scenes"][0]
        shot = scene["shots"][0]
        t = shot["performers"][0]
        t["body_heading_rad"] = [
            dict(at=0, value=0, ease="linear"),
            dict(at=1, value=math.pi / 2, ease="linear"),
        ]
        full = dict(
            frames=[frame(t) for t in (0, 2, 4, 6, 8, 10)],
            orbit_start_s=2,
            orbit_duration_s=8,
            duration_s=10,
            summary={},
        )
        clip = window(full, 4, 4, False)
        samples = build_samples(shot, dict(subject_height_m=1.72), scene, f["document"]["marks"][0], clip)
        self.assertAlmostEqual(samples[0]["actors"][t["actor_id"]]["heading_rad"], math.pi / 4)
        self.assertAlmostEqual(samples[-1]["actors"][t["actor_id"]]["heading_rad"], math.pi / 2)

    def test_manifest_and_compiled_samples_preserve_identity(self):
        f = fixture()
        m = manifest(f)
        self.assertEqual(m["actors"][1]["appearance"]["cloth"], "#17263c")
        self.assertEqual(m["shots"][0]["performers"], f["document"]["scenes"][0]["shots"][0]["performers"])
        program = build_program(m)
        samples = program["segments"][0]["performance_samples"]
        self.assertGreater(len(samples), 2)
        self.assertIn("maker", samples[-1]["actors"])
        json.dumps(program, allow_nan=False)

    def test_unachieved_mutual_eyeline_reaches_the_production_review(self):
        f = fixture()
        track = f["document"]["scenes"][0]["shots"][0]["performers"][0]
        for key in track["body_heading_rad"]:
            key["value"] = -math.pi / 2
        program = build_program(manifest(f))
        issues = program["segments"][0]["shot_review"]["issues"]
        self.assertIn("attention_target_outside_head_range", {issue["code"] for issue in issues})
