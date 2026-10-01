"""Boom intent is checked on achieved filmed samples, not labels or setup poses."""

import copy
import json
import unittest

from takeone.previs.capture import window
from takeone.previs.motion_review import review_motion


def shot(duration=4):
    return dict(shot_id="boom-test", start_ms=0, end_ms=duration * 1000)


def settings(template="boom_up", start=1.5, end=1.6, keys=None):
    return dict(
        template_id=template,
        height_start_m=start,
        height_end_m=end,
        rise_start=0,
        rise_end=1,
        channels={"camera_height_m": keys} if keys else {},
    )


def preview(heights=(1.5, 1.6), duration=4, setup=2):
    samples = [dict(time_s=0, camera=dict(pos=[0, 0, 0.7]), axle_m=[0, 0])]
    samples += [
        dict(time_s=setup + duration * i / (len(heights) - 1), camera=dict(pos=[0, 0, h]), axle_m=[0, 0])
        for i, h in enumerate(heights)
    ]
    return dict(
        frames=samples,
        orbit_start_s=setup,
        orbit_duration_s=duration,
        duration_s=setup + duration,
        summary={},
    )


def codes(report):
    return [issue["code"] for issue in report["issues"]]


class MotionReviewTests(unittest.TestCase):
    def test_zero_authored_boom_is_not_a_solver_failure(self):
        result = review_motion(shot(), settings(end=1.5), preview((1.5, 1.5)))
        self.assertEqual(codes(result), ["boom_authored_no_motion"])
        self.assertEqual(result["checks"][0]["expected_direction"], "up")
        self.assertEqual(result["status"], "needs_revision")

    def test_authored_rise_not_achieved_has_a_different_diagnostic(self):
        result = review_motion(shot(), settings(), preview((1.5, 1.5)))
        self.assertEqual(codes(result), ["boom_motion_not_realized"])
        self.assertAlmostEqual(result["checks"][0]["requested_delta_m"], 0.1)

    def test_correct_rise_and_fall(self):
        for template, start, end in (("boom_up", 1.5, 1.6), ("boom_down", 1.6, 1.5)):
            with self.subTest(template=template):
                report = review_motion(shot(), settings(template, start, end), preview((start, end)))
                self.assertEqual(report["status"], "reviewable")
                self.assertEqual(codes(report), [])

    def test_authored_direction_opposes_the_label(self):
        report = review_motion(shot(), settings(start=1.6, end=1.5), preview((1.6, 1.5)))
        self.assertEqual(codes(report), ["boom_authored_wrong_direction"])

    def test_achieved_direction_opposes_the_request(self):
        report = review_motion(shot(), settings(), preview((1.6, 1.5)))
        self.assertEqual(codes(report), ["boom_motion_wrong_direction"])

    def test_explicit_keys_override_preset_direction_without_renaming(self):
        keys = [dict(at=0, value=1.6, ease="linear"), dict(at=1, value=1.5, ease="linear")]
        s = settings(keys=keys)
        original = copy.deepcopy(s)
        result = review_motion(shot(), s, preview((1.6, 1.5)))
        self.assertEqual(result["intent_source"], "camera_height_keyframes")
        self.assertEqual(result["template_id"], "boom_up")
        self.assertEqual(result["status"], "reviewable")
        self.assertEqual(s, original)

    def test_explicit_keyed_hold_is_legal_but_actual_excursion_is_not(self):
        keys = [dict(at=0, value=1.5, ease="linear"), dict(at=1, value=1.5, ease="linear")]
        held = review_motion(shot(), settings(keys=keys), preview((1.5, 1.5, 1.5)))
        moved = review_motion(shot(), settings(keys=keys), preview((1.5, 1.6, 1.5)))
        self.assertEqual(codes(held), [])
        self.assertEqual(codes(moved), ["boom_hold_not_realized"])

    def test_legitimate_static_shot_is_not_a_boom(self):
        self.assertIsNone(review_motion(shot(), settings("static", end=1.5), preview((1.5, 1.5))))

    def test_setup_cannot_satisfy_the_rise(self):
        result = review_motion(shot(), settings(), preview((1.5, 1.5)))
        self.assertEqual(result["checks"][0]["achieved_delta_m"], 0)

    def test_missing_or_nonfinite_camera_evidence_never_passes(self):
        for mutation in ("missing", "nan", "one_sample", "unordered"):
            p = preview((1.5, 1.55, 1.6))
            if mutation == "missing":
                del p["frames"][-1]["camera"]
            elif mutation == "nan":
                p["frames"][-1]["camera"]["pos"][2] = float("nan")
            elif mutation == "one_sample":
                p["frames"] = p["frames"][-1:]
            else:
                p["frames"][2:4] = reversed(p["frames"][2:4])
            with self.subTest(mutation=mutation):
                report = review_motion(shot(), settings(), p)
                self.assertEqual(report["status"], "unverified")
                self.assertIn("boom_motion_evidence_missing", codes(report))
                json.dumps(report, allow_nan=False)

    def test_missing_timing_is_unverified(self):
        p = preview()
        del p["orbit_start_s"]
        self.assertEqual(review_motion(shot(), settings(), p)["status"], "unverified")

    def test_missing_window_end_is_unverified(self):
        p = preview()
        p["frames"][-1]["time_s"] -= 0.5
        self.assertEqual(review_motion(shot(), settings(), p)["status"], "unverified")

    def test_shared_capture_uses_full_take_key_times_not_renormalized_clip_time(self):
        keys = [
            dict(at=0, value=1.5, ease="linear"),
            dict(at=0.5, value=1.5, ease="linear"),
            dict(at=1, value=1.6, ease="linear"),
        ]
        full = preview((1.5, 1.5, 1.5, 1.55, 1.6), duration=8)
        first = window(full, 0, 4, True)
        second = window(full, 4, 4, False)
        a = review_motion(shot(), settings(keys=keys), first)
        b = review_motion(shot(), settings(keys=keys), second)
        self.assertEqual(a["checks"][0]["expected_direction"], "hold")
        self.assertEqual(b["checks"][0]["expected_direction"], "up")
        self.assertEqual(b["checks"][0]["source_range_s"], [4, 8])
        self.assertEqual(b["checks"][0]["time_range_s"], [0, 4])
        self.assertEqual(codes(a) + codes(b), [])

    def test_unused_source_tail_cannot_satisfy_an_edited_rise(self):
        full = preview((1.5, 1.5, 1.5, 1.55, 1.6), duration=8)
        result = review_motion(shot(4), settings(), full)
        self.assertEqual(codes(result), ["boom_motion_not_realized"])
        self.assertEqual(result["checks"][0]["source_range_s"], [0, 4])

    def test_keyed_hold_then_rise_has_separate_evidence(self):
        keys = [
            dict(at=0, value=1.5, ease="linear"),
            dict(at=0.5, value=1.5, ease="linear"),
            dict(at=1, value=1.6, ease="linear"),
        ]
        result = review_motion(shot(), settings(keys=keys), preview((1.5, 1.5, 1.5, 1.55, 1.6)))
        self.assertEqual([c["expected_direction"] for c in result["checks"]], ["hold", "up"])
        self.assertEqual(result["status"], "reviewable")

    def test_main_review_reports_missing_optical_geometry_without_invented_lens(self):
        from takeone.previs.shot_review import review

        p = preview()
        del p["frames"][-1]["camera"]
        report = review(shot(), settings(), {}, {}, p)
        self.assertEqual(report["status"], "needs_revision")
        self.assertEqual(report["motion"]["status"], "unverified")
        self.assertIsNone(report["lens_start"])
        self.assertIsNone(report["camera_height_range_m"])
        json.dumps(report, allow_nan=False)

    def test_nonfinite_source_timing_is_not_serialized_as_nan(self):
        p = preview()
        p["source_in_s"] = float("nan")
        report = review_motion(shot(), settings(), p)
        self.assertEqual(report["status"], "unverified")
        self.assertIsNone(report["source_in_s"])
        json.dumps(report, allow_nan=False)

    def test_processed_view_cannot_supply_missing_raw_motion(self):
        p = preview((1.5, 1.5))
        p["frames"][-1]["camera_view"] = dict(pos=[0, 0, 1.7])
        report = review_motion(shot(), settings(), p)
        self.assertEqual(codes(report), ["boom_motion_not_realized"])

    def test_review_does_not_mutate_inputs(self):
        s, p, sh = settings(), preview(), shot()
        before = copy.deepcopy((s, p, sh))
        report = review_motion(sh, s, p)
        self.assertEqual((s, p, sh), before)
        json.dumps(report, allow_nan=False)

    def test_source_schema_manifest_and_program_expose_the_diagnostic(self):
        from takeone.previs.sequence import build_program

        from tests.test_shot_design import manifest, story

        fixture = story()
        authored = fixture["document"]["scenes"][0]["shots"][0]
        authored["movement"]["template_id"] = "boom_up"
        authored["movement"]["parameters"] += [
            dict(name="height_start_m", value=1.55),
            dict(name="height_end_m", value=1.55),
        ]
        original = copy.deepcopy(fixture)
        compiled = build_program(manifest(fixture))
        segment = compiled["segments"][0]
        self.assertEqual(segment["template_id"], "boom_up")
        self.assertEqual(segment["assessment"], "needs_revision")
        self.assertIn("boom_authored_no_motion", codes(segment["shot_review"]["motion"]))
        self.assertIn(segment["shot_id"], compiled["needs_revision_shot_ids"])
        self.assertEqual(fixture, original)


if __name__ == "__main__":
    unittest.main()
