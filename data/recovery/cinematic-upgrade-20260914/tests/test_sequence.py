"""Multi-shot rehearsal: placement, contiguous timing, repositions and advisory notes."""

import math
import unittest

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.motion.studio_plan import ARM_PERIOD, ROLES
from takeone.previs.reposition import compile_reposition, plan
from takeone.previs.sequence import build_program, stage_for
from takeone.previs.start_pose import initial_counts
from takeone.previs.templates import defaults_for, route_filming_time_s, screen_geometry
from takeone.simulation.drive import HEADING_OFFSET

A = dict(mark_id="A", description="", position_m=[0.0, 0.0], facing_rad=0.0)
B = dict(mark_id="B", description="", position_m=[3.0, 1.5], facing_rad=math.pi / 2)


def shot(index, template, mark, start_ms, end_ms, framing="medium", **overrides):
    return dict(
        shot_id=f"s{index}",
        start_ms=start_ms,
        end_ms=end_ms,
        actor_id="a1",
        mark_id=mark,
        action="",
        framing=framing,
        camera_intent="",
        light_intent="",
        dialogue="",
        name=template,
        error=None,
        defaulted_parameters=[],
        settings=defaults_for(template) | overrides,
    )


def manifest(shots, marks=(A, B)):
    return dict(
        kind="takeone_director_rehearsal",
        schema_version=1,
        title="Test",
        session_id="s",
        document_digest="d",
        manifest_digest="m",
        marks=[dict(m) for m in marks],
        shots=shots,
    )


class SequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = build_program(
            manifest(
                [
                    shot(1, "static", "A", 0, 4000, duration_s=4.0),
                    shot(2, "push_in", "B", 4000, 9000, distance_m=1.2, speed_m_s=0.3),
                    shot(3, "arc_left", "A", 9000, 15000, radius_m=1.5, sweep_rad=math.radians(80)),
                ]
            )
        )

    def test_every_segment_is_contiguous_on_one_clock(self):
        segments = self.program["segments"]
        self.assertEqual([s["kind"] for s in segments], ["shot", "reposition", "shot", "reposition", "shot"])
        for before, after in zip(segments, segments[1:]):
            self.assertAlmostEqual(before["t0_s"] + before["duration_s"], after["t0_s"], places=9)
        last = segments[-1]
        self.assertAlmostEqual(last["t0_s"] + last["duration_s"], self.program["duration_s"], places=9)

    def test_recompiling_the_same_script_is_identical(self):
        again = build_program(
            manifest(
                [
                    shot(1, "static", "A", 0, 4000, duration_s=4.0),
                    shot(2, "push_in", "B", 4000, 9000, distance_m=1.2, speed_m_s=0.3),
                    shot(3, "arc_left", "A", 9000, 15000, radius_m=1.5, sweep_rad=math.radians(80)),
                ]
            )
        )
        self.assertEqual(again["program_digest"], self.program["program_digest"])

    def test_a_shot_is_placed_on_its_mark_facing_the_scripted_direction(self):
        from takeone.previs.templates import compile_template

        preview = compile_template(defaults_for("static") | dict(duration_s=4.0))["preview"]
        stage = stage_for(B, preview)
        self.assertEqual(stage["origin_m"], [3.0, 1.5])
        opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8)
        staged = math.atan2(opening["camera"]["pos"][1], opening["camera"]["pos"][0])
        self.assertAlmostEqual(staged + stage["heading_rad"], B["facing_rad"], places=9)

    def test_marks_without_coordinates_rehearse_exactly_as_before(self):
        plain = [dict(mark_id="A", description=""), dict(mark_id="B", description="")]
        program = build_program(manifest([shot(1, "static", "A", 0, 4000, duration_s=4.0)], marks=plain))
        self.assertEqual(program["segments"][0]["stage"], dict(origin_m=[0.0, 0.0], heading_rad=0.0))

    def test_a_shot_the_translator_could_not_settle_does_not_stop_the_rest(self):
        broken = shot(1, "static", "A", 0, 4000, duration_s=4.0)
        broken["settings"] = None
        broken["error"] = "Choose an exact movement template for this shot before rehearsal."
        program = build_program(manifest([broken, shot(2, "static", "B", 4000, 8000, duration_s=4.0)]))
        self.assertEqual(program["segments"][0]["kind"], "unavailable")
        self.assertEqual(program["segments"][1]["kind"], "shot")
        self.assertGreater(program["duration_s"], 0)

    def test_notes_are_advisory_and_never_remove_a_shot(self):
        program = build_program(manifest([shot(1, "orbit_360", "A", 0, 5000, framing="close_up")]))
        segment = program["segments"][0]
        self.assertEqual(segment["kind"], "shot")
        self.assertIsNone(segment["error"])
        self.assertTrue(any("longer than" in note for note in segment["advice"]))
        self.assertTrue(any("closest to" in note for note in segment["advice"]))


class RepositionTests(unittest.TestCase):
    def test_a_pure_turn_moves_the_cart_nowhere(self):
        move = compile_reposition(
            dict(
                from_axle_m=[1.0, 2.0, 0.0],
                to_axle_m=[1.0, 2.0, 1.2],
                from_raw={r: initial_counts(ArmMapping.load(r, require_motion=False)) for r in ROLES},
            )
        )
        for frame in move["frames"]:
            self.assertAlmostEqual(frame["axle_m"][0], 1.0, places=9)
            self.assertAlmostEqual(frame["axle_m"][1], 2.0, places=9)

    def test_travel_only_ever_follows_the_heading_the_cart_is_already_facing(self):
        move = compile_reposition(
            dict(
                from_axle_m=[0.0, 0.0, 0.0],
                to_axle_m=[2.0, 1.0, math.pi / 2],
                from_raw={r: initial_counts(ArmMapping.load(r, require_motion=False)) for r in ROLES},
            )
        )
        moved = 0
        for before, after in zip(move["frames"], move["frames"][1:]):
            dx = after["axle_m"][0] - before["axle_m"][0]
            dy = after["axle_m"][1] - before["axle_m"][1]
            if math.hypot(dx, dy) < 1e-9:
                continue
            moved += 1
            # A strafe would point the displacement away from both the heading it
            # started the step with and the one it ended with.
            offsets = [
                abs(math.remainder(math.atan2(dy, dx) - (frame["q"][2] + HEADING_OFFSET), math.tau))
                for frame in (before, after)
            ]
            self.assertLess(min(offsets), 1e-6, f"lateral translation of {math.hypot(dx, dy):.4f} m")
        self.assertGreater(moved, 5, "the cart should actually have driven")

    def test_both_arms_finish_at_their_calibrated_midpoints(self):
        mappings = {r: ArmMapping.load(r, require_motion=False) for r in ROLES}
        start = {r: {n: v + 120 for n, v in initial_counts(m).items()} for r, m in mappings.items()}
        move = compile_reposition(
            dict(from_axle_m=[0.0, 0.0, 0.0], to_axle_m=[0.5, 0.0, 0.0], from_raw=start)
        )
        for role, mapping in mappings.items():
            self.assertEqual(move["frames"][-1]["raw_by_role"][role], initial_counts(mapping))
        self.assertEqual(move["frames"][0]["raw_by_role"], start)
        self.assertAlmostEqual(
            round(move["duration_s"] / ARM_PERIOD) * ARM_PERIOD, move["duration_s"], places=9
        )

    def test_standing_still_needs_no_cart_route(self):
        self.assertIsNone(plan([1.0, 2.0, 0.3], [1.0, 2.0, 0.3]))
        self.assertIsNotNone(plan([1.0, 2.0, 0.3], [1.0, 2.0, 1.3]))

    def test_the_move_never_claims_measured_travel(self):
        move = compile_reposition(
            dict(
                from_axle_m=[0.0, 0.0, 0.0],
                to_axle_m=[1.0, 0.0, 0.0],
                from_raw={r: initial_counts(ArmMapping.load(r, require_motion=False)) for r in ROLES},
            )
        )
        self.assertFalse(move["summary"]["physical_path_verified"])
        self.assertTrue(any("kinematic estimate" in note for note in move["notes"]))
        self.assertEqual(set(move["frames"][0]["raw_by_role"]), set(ROLES))
        self.assertEqual(set(move["frames"][0]["raw_by_role"]["phone"]), set(JOINTS))


class GeometryTests(unittest.TestCase):
    def test_route_time_follows_the_documented_arithmetic(self):
        orbit = defaults_for("orbit_360") | dict(radius_m=2.5, speed_m_s=0.17)
        self.assertAlmostEqual(route_filming_time_s(orbit), 2.5 * math.tau / 0.17, places=6)
        push = defaults_for("push_in") | dict(distance_m=1.5, speed_m_s=0.35)
        self.assertAlmostEqual(route_filming_time_s(push), 1.5 / 0.35, places=6)
        self.assertEqual(route_filming_time_s(defaults_for("static") | dict(duration_s=7.0)), 7.0)

    def test_frame_height_matches_the_published_table(self):
        for radius, focal, expected in [(2.5, 24.0, 2.11), (2.5, 48.0, 1.05), (1.5, 13.0, 2.34)]:
            geometry = screen_geometry(defaults_for("static") | dict(radius_m=radius, focal_mm=focal))
            self.assertAlmostEqual(geometry["frame_height_m"][0], expected, places=2)

    def test_a_push_in_reads_as_both_bands_it_travels_through(self):
        geometry = screen_geometry(defaults_for("push_in"))
        self.assertEqual(geometry["implied"], ["wide", "medium"])


if __name__ == "__main__":
    unittest.main()
