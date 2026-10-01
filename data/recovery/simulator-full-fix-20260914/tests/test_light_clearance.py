"""The light arm lights the actor without standing in the phone's shot.

Five joints against four constraints leaves a family of solutions. Before the
clearance term the solver picked arbitrarily, and for a truck it chose a pose that
reached straight across the lens axis.
"""

import math
import unittest

import numpy as np

from takeone.previs.compiler import FIXTURE_RADIUS_M, WIDEST_CONE, AimingSolver
from takeone.previs.templates import compile_template, defaults_for
from takeone.simulation.robot import load_model

SHOTS = {
    "truck_left": dict(radius_m=2.5, distance_m=1.5, bearing_rad=math.pi),
    "hero_orbit": dict(radius_m=2.5),
    "push_in": dict(radius_m=1.6, distance_m=1.2),
    "orbit_360": dict(radius_m=2.5),
    "static": dict(radius_m=2.0, duration_s=6.0),
    "arc_left": dict(radius_m=1.8, sweep_rad=math.radians(90)),
}


def preview_for(name, focal_mm=35.0):
    settings = defaults_for(name) | dict(
        speed_m_s=0.17, height_start_m=1.59, height_end_m=1.59, focal_mm=focal_mm
    ) | SHOTS[name]
    return settings, compile_template(settings)["preview"]


def clearance(frame, focal_mm):
    """Metres the light sits outside the lens cone. Negative means it is in shot."""
    camera = np.array(frame["camera"]["pos"])
    axis = np.array(frame["face"]) - camera
    axis = axis / np.linalg.norm(axis)
    reach = np.array(frame["light"]["pos"]) - camera
    along = float(reach @ axis)
    off = float(np.linalg.norm(reach - along * axis))
    return off - ((18.0 / focal_mm) * max(0.0, along) + FIXTURE_RADIUS_M)


class ClearanceTests(unittest.TestCase):
    def test_the_light_stays_out_of_frame_for_every_move(self):
        for name in SHOTS:
            settings, preview = preview_for(name)
            filming = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
            worst = min(clearance(f, settings["focal_mm"]) for f in filming)
            with self.subTest(template=name):
                self.assertGreater(worst, 0.0, f"{name}: light is {-worst:.3f} m inside the frame")

    def test_the_truck_that_exposed_this_is_clear_by_a_real_margin(self):
        settings, preview = preview_for("truck_left")
        filming = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
        worst = min(clearance(f, settings["focal_mm"]) for f in filming)
        # It used to be 0.326 m inside the 35 mm cone, and 0.016 m off a 2.5 m sight line.
        self.assertGreater(worst, 0.10)
        closest = min(
            float(np.linalg.norm(np.array(f["light"]["pos"]) - np.array(f["camera"]["pos"])))
            for f in filming
        )
        self.assertGreater(closest, 0.15, "the light should not be sitting on the lens either")

    def test_clearance_does_not_cost_aim_or_height(self):
        for name in SHOTS:
            settings, preview = preview_for(name)
            with self.subTest(template=name):
                self.assertLess(preview["summary"]["max_aim_error_deg"], 3.0)
                self.assertAlmostEqual(preview["summary"]["camera_height_m"], 1.59, delta=0.03)

    def test_a_wider_lens_needs_more_room_than_a_longer_one(self):
        settings, preview = preview_for("push_in")
        frame = preview["frames"][-1]
        self.assertLess(clearance(frame, 13.0), clearance(frame, 200.0))

    def test_the_solver_reports_the_optical_point_of_the_pose_it_is_given(self):
        model = load_model()
        solver = AimingSolver(model)
        q = np.r_[np.zeros(3), (solver.lower + solver.upper) / 2]
        origin = solver.optical(q, "phone")
        q[0] += 1.0
        moved = solver.optical(q, "phone")
        self.assertAlmostEqual(float(moved[0] - origin[0]), 1.0, places=6)
        self.assertAlmostEqual(float(moved[1] - origin[1]), 0.0, places=6)
        self.assertFalse(np.allclose(solver.optical(q, "light"), moved))

    def test_the_widest_cone_constant_matches_the_phone_profile(self):
        from takeone.previs.camera import MIN_FOCAL_MM

        self.assertAlmostEqual(WIDEST_CONE, 18.0 / MIN_FOCAL_MM, places=9)


if __name__ == "__main__":
    unittest.main()
