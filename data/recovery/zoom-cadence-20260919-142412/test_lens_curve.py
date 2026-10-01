"""What the lens does across a move, for every movement that asks it to move.

Four presets in the library carry a lens curve — `zoom_in`, `zoom_out`,
`dolly_zoom_in`, `dolly_zoom_out` — and every other preset holds one focal
length. Three things about that were wrong and are pinned here:

- A Dolly Zoom's closing focal length is derived from the distance ratio, not
  the settings. `screen_geometry` read `focal_mm` at both ends, so it reported a
  Dolly Zoom travelling from one shot size to another, which is precisely what
  the move exists not to do.
- The lens range was defined twice with different ceilings: the motion pre-pass
  stopped at 200 mm, the channel that overwrites it at 360 mm.
- A move can ask for a focal length the rig does not have. It was filmed at the
  limit with no record that the request had been changed, so a Dolly Zoom could
  silently stop holding subject size while still reporting itself as one.

The pre-roll contract is pinned too: the arm-setup frames before the move hold
the opening focal length, so the lens is already where the shot starts rather
than travelling into position on the first filmed frame.
"""

import unittest

import mujoco  # noqa: F401  (compile_template needs the simulation extra)
import numpy as np
from scipy.spatial.transform import Rotation
from takeone.previs.camera import MAX_FOCAL_MM, MIN_FOCAL_MM
from takeone.previs.program import focal_length
from takeone.previs.templates import BY_ID, PRESETS, compile_template, defaults_for, screen_geometry

FRAME_HEIGHT_MM = 36 / (16 / 9)
ZOOMING = ("zoom_in", "zoom_out", "dolly_zoom_in", "dolly_zoom_out")


def image_heights(preview):
    """Metres of world filling the frame height, from the achieved pose."""
    start = preview["orbit_start_s"]
    heights = []
    for frame in preview["frames"]:
        if frame["time_s"] < start - 1e-8:
            continue
        forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
        target = frame.get("camera_target_m", frame["face"])
        depth = float(forward @ (np.asarray(target) - frame["camera"]["pos"]))
        heights.append(max(0.0, depth) * FRAME_HEIGHT_MM / frame["focal_mm"])
    return heights


class LensCurveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {tid: compile_template(defaults_for(tid)) for tid in ZOOMING}

    def parts(self, tid):
        preview = self.results[tid]["preview"]
        start = preview["orbit_start_s"]
        pre = [f for f in preview["frames"] if f["time_s"] < start - 1e-8]
        filming = [f for f in preview["frames"] if f["time_s"] >= start - 1e-8]
        return preview, pre, filming

    # ── which movements move the lens ───────────────────────────────────────

    def test_exactly_the_four_lens_presets_resolve_to_a_moving_zoom_mode(self):
        moving = {p["id"] for p in PRESETS if p["aim"] in ("zoom", "dolly_zoom")}
        self.assertEqual(moving, set(ZOOMING))
        for tid in ZOOMING:
            preview, _, _ = self.parts(tid)
            expected = "preset_ramp" if BY_ID[tid]["aim"] == "zoom" else "dolly"
            self.assertEqual(preview["camera_output"]["zoom"], expected)

    # ── pre-zoom: the lens is parked before the move starts ─────────────────

    def test_setup_frames_hold_the_opening_focal_length(self):
        for tid in ZOOMING:
            with self.subTest(id=tid):
                _, pre, filming = self.parts(tid)
                self.assertTrue(pre, "every move has calibrated arm setup before it films")
                opening = filming[0]["focal_mm"]
                self.assertEqual({round(f["focal_mm"], 9) for f in pre}, {round(opening, 9)})
                self.assertAlmostEqual(opening, defaults_for(tid)["focal_mm"], places=6)

    def test_cues_start_at_zero_carry_the_opening_focal_and_cover_the_clock(self):
        for tid in ZOOMING:
            with self.subTest(id=tid):
                plan = self.results[tid]["plan"]
                cues = plan["camera_cues"]
                times = [cue["time_s"] for cue in cues]
                self.assertEqual(times[0], 0)
                self.assertAlmostEqual(times[-1], plan["duration_s"], places=6)
                self.assertTrue(all(b > a for a, b in zip(times, times[1:])))
                self.assertAlmostEqual(cues[0]["focal_mm"], defaults_for(tid)["focal_mm"], places=6)

    # ── the ramp ────────────────────────────────────────────────────────────

    def test_a_zoom_travels_the_authored_interval_and_stays_inside_it(self):
        for tid, opening, closing in (("zoom_in", 24.0, 70.0), ("zoom_out", 70.0, 24.0)):
            with self.subTest(id=tid):
                _, _, filming = self.parts(tid)
                focals = [f["focal_mm"] for f in filming]
                self.assertAlmostEqual(focals[0], opening, places=6)
                self.assertAlmostEqual(focals[-1], closing, places=6)
                self.assertGreaterEqual(min(focals), min(opening, closing) - 1e-6)
                self.assertLessEqual(max(focals), max(opening, closing) + 1e-6)
                direction = 1 if closing > opening else -1
                self.assertTrue(
                    all((b - a) * direction >= -1e-9 for a, b in zip(focals, focals[1:])),
                    "a zoom never reverses inside the shot",
                )

    # ── the dolly zoom ──────────────────────────────────────────────────────

    def test_a_dolly_zoom_holds_subject_size_and_moves_the_lens_the_right_way(self):
        # Approaching widens the lens; retreating tightens it.
        for tid, widens in (("dolly_zoom_in", True), ("dolly_zoom_out", False)):
            with self.subTest(id=tid):
                preview, _, filming = self.parts(tid)
                focals = [f["focal_mm"] for f in filming]
                self.assertNotAlmostEqual(focals[0], focals[-1], places=2)
                self.assertEqual(focals[-1] < focals[0], widens)
                heights = image_heights(preview)
                self.assertLess(max(heights) / min(heights) - 1, 0.01)
                self.assertLess(preview["summary"]["framing_drift_percent"], 0.01)
                self.assertFalse(preview["summary"]["lens_clamped"])

    def test_advisory_geometry_describes_the_same_shot_the_compiler_makes(self):
        """`screen_geometry` used to read `focal_mm` at both ends of a Dolly
        Zoom, reporting a 38-60% change in shot size for a move whose whole
        purpose is holding it.

        It estimates from the cart's ground radius rather than the solved
        optical depth, so its magnitudes stay approximate on purpose — it is the
        cheap pre-check, not the compiler. What it may not do is disagree about
        whether the shot size changes at all, or which way the lens travels.
        """
        for tid in ZOOMING:
            with self.subTest(id=tid):
                preview, _, _ = self.parts(tid)
                geometry = screen_geometry(defaults_for(tid))
                advisory = geometry["frame_height_m"]
                real = image_heights(preview)
                holds_size = BY_ID[tid]["aim"] == "dolly_zoom"
                self.assertEqual(abs(real[-1] / real[0] - 1) < 0.01, holds_size)
                self.assertEqual(abs(advisory[1] / advisory[0] - 1) < 0.01, holds_size)
                opening, closing = geometry["focal_mm"]
                compiled_ratio = preview["summary"]["focal_end_mm"] / preview["summary"]["focal_start_mm"]
                self.assertEqual(closing > opening, compiled_ratio > 1, "lens travels the same way")

    # ── the rig's lens range ────────────────────────────────────────────────

    def test_the_motion_pre_pass_and_the_lens_channel_share_one_range(self):
        program = {"aim": "dolly_zoom"}
        self.assertEqual(focal_length(program, 0.5, 1e6, 1.0, 50.0), MAX_FOCAL_MM)
        self.assertEqual(focal_length(program, 0.5, 1e-6, 1.0, 50.0), MIN_FOCAL_MM)

    def test_a_move_the_lens_cannot_reach_says_so_instead_of_filming_it_quietly(self):
        beyond = defaults_for("dolly_zoom_out") | dict(
            radius_m=0.8, distance_m=10.0, focal_mm=120.0, speed_m_s=0.35
        )
        preview = compile_template(beyond)["preview"]
        summary = preview["summary"]
        self.assertTrue(summary["lens_clamped"])
        self.assertGreater(summary["requested_focal_mm"][1], MAX_FOCAL_MM)
        self.assertEqual(summary["lens_range_mm"], [MIN_FOCAL_MM, MAX_FOCAL_MM])
        self.assertLessEqual(max(f["focal_mm"] for f in preview["frames"]), MAX_FOCAL_MM)
        # Clamped, it is no longer holding subject size, and the drift says so.
        self.assertGreater(summary["framing_drift_percent"], 1.0)
        self.assertTrue(any("outside the" in note for note in preview["notes"]))

    def test_a_reachable_move_reports_its_request_unclamped(self):
        for tid in ZOOMING:
            with self.subTest(id=tid):
                summary = self.results[tid]["preview"]["summary"]
                self.assertFalse(summary["lens_clamped"])
                low, high = summary["requested_focal_mm"]
                self.assertGreaterEqual(low, MIN_FOCAL_MM)
                self.assertLessEqual(high, MAX_FOCAL_MM)


if __name__ == "__main__":
    unittest.main()
