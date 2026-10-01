"""Independent analytic, numerical and geometry regression checks."""

import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scipy.integrate import solve_ivp
from scipy.spatial.transform import Rotation
from takeone.planning.settings import DEFAULTS, LEGACY_SETTINGS, parameters
from takeone.simulation import drive
from takeone.simulation.robot import load_model


class DriveTests(unittest.TestCase):
    def test_uart_matches_supplied_controller(self):
        self.assertEqual(drive.uart_pair(0.7, -0.2), "0.15,-0.15\n")
        self.assertEqual(drive.uart_pair(0.039, 0.034), "0.04,0.03\n")
        for left, right in [(0, 0), (-0.041, 0.057), (0.145, -0.145), (0.155, -0.155)]:
            expected = f"{max(-0.15, min(0.15, left)):.2f},{max(-0.15, min(0.15, right)):.2f}\n"
            self.assertEqual(drive.uart_pair(left, right), expected)
        for invalid in [True, None, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                drive.uart_pair(invalid, 0)

    def test_speed_measurement_and_wheel_rotation(self):
        response = drive.CartResponse.load(0.1375)
        speed = response.speeds_for((0.04, 0.04))[0]
        self.assertAlmostEqual(speed * 4, 0.55)
        turns = 0.55 / (2 * math.pi * drive.WHEEL_RADIUS)
        self.assertAlmostEqual(turns, 0.921422, places=5)
        self.assertAlmostEqual(speed / drive.WHEEL_RADIUS * 60 / (2 * math.pi), 13.82133, places=4)
        self.assertEqual(response.speeds_for((0.03, -0.03)), (0, 0))

    def test_straight_reverse_stop_and_spin(self):
        np.testing.assert_allclose(drive.integrate([0, 0, 0], 0.55, 0.55, 0.58), [0.55, 0, 0], atol=1e-12)
        np.testing.assert_allclose(drive.integrate([0, 0, 0], -0.55, -0.55, 0.58), [-0.55, 0, 0], atol=1e-12)
        np.testing.assert_allclose(drive.integrate([1, 2, 0.3], 0, 0, 0.58), [1, 2, 0.3], atol=1e-12)
        pivot = drive.integrate([0, 0, 0], -0.1, 0.1, 0.58)
        np.testing.assert_allclose(pivot[:2], 0, atol=1e-12)
        self.assertAlmostEqual(pivot[2], 0.2 / 0.58)

    def test_exact_arc_against_independent_ode_solver(self):
        rng = np.random.default_rng(20260912)
        for _ in range(50):
            left, right = rng.uniform(-0.5, 0.5, 2)
            track = float(rng.uniform(0.52, 0.9))
            duration = float(rng.uniform(0.01, 5))
            initial = rng.uniform(-2, 2, 3)
            v = (left + right) / 2
            omega = (right - left) / track
            numerical = solve_ivp(
                lambda t, q: [v * math.cos(q[2]), v * math.sin(q[2]), omega],
                [0, duration],
                initial,
                rtol=1e-11,
                atol=1e-12,
            ).y[:, -1]
            np.testing.assert_allclose(
                drive.integrate(initial, left * duration, right * duration, track), numerical, atol=1e-9
            )

    def test_actual_wheel_centers_roll_without_sideways_slip(self):
        # Differentiate positions of EACH powered wheel, not the offset cart center.
        b = 0.58
        axle = np.array([0.2, -0.8, 0.63])
        left = 0.1375
        right = 0.20625
        h = 1e-6
        a = drive.integrate(axle, left * h, right * h, b)
        for sign, speed in [(1, left), (-1, right)]:

            def wheel(q):
                return q[:2] + Rotation.from_euler("z", q[2]).as_matrix()[:2, :2] @ np.array(
                    [0, sign * b / 2]
                )

            velocity = (wheel(a) - wheel(axle)) / h
            local = Rotation.from_euler("z", axle[2]).as_matrix()[:2, :2].T @ velocity
            self.assertAlmostEqual(local[0], speed, places=6)
            self.assertLess(abs(local[1]), 1e-7)
        cart_velocity = (drive.cart_from_axle(a)[:2] - drive.cart_from_axle(axle)[:2]) / h
        local = Rotation.from_euler("z", axle[2]).as_matrix()[:2, :2].T @ cart_velocity
        self.assertAlmostEqual(local[1], -0.27 * (right - left) / b, places=6)

    def test_lower_only_rotation_and_measured_wheels(self):
        m = load_model()
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        old = json.loads((Path(__file__).parents[1] / "fixtures/upper_before_rotation.json").read_text())
        measured_height_delta = np.array([0.0, 0.0, 0.03])
        for name, expected in old["bodies"].items():
            i = m.body(name).id
            np.testing.assert_allclose(
                d.xpos[i], np.array(expected["pos"]) + measured_height_delta, atol=1e-12
            )
            np.testing.assert_allclose(d.xquat[i], expected["quat"], atol=1e-12)
        for name, expected in old["geoms"].items():
            i = m.geom(name).id
            structure_delta = {
                "upright_front": 0.015,
                "upright_rear": 0.015,
                "mast_cable_front": 0.014,
                "mast_cable_rear": 0.014,
            }.get(name, 0.03)
            np.testing.assert_allclose(
                d.geom_xpos[i], np.array(expected["pos"]) + [0, 0, structure_delta], atol=1e-12
            )
            np.testing.assert_allclose(d.geom_xmat[i], expected["mat"], atol=1e-12)
        np.testing.assert_allclose(
            d.xmat[m.body("lower_cart").id].reshape(3, 3) @ np.array([0, 1, 0]), [1, 0, 0], atol=1e-12
        )
        for side, x, y in [("left", 0.29, -0.29), ("right", -0.29, 0.29)]:
            g = m.geom(f"drive_tire_{x}").id
            np.testing.assert_allclose(m.geom_size[g][:2], [0.095, 0.03], atol=1e-12)
            np.testing.assert_allclose(d.geom_xpos[g], [-0.27, y, 0.095], atol=1e-12)
            np.testing.assert_allclose(d.xpos[m.body("drive_" + side).id], d.geom_xpos[g], atol=1e-12)
            axis = d.geom_xmat[g].reshape(3, 3)[:, 2]
            self.assertAlmostEqual(abs(axis[1]), 1)
            self.assertAlmostEqual(d.geom_xpos[g, 2] - m.geom_size[g, 0], 0)

    def test_powered_front_and_passive_rear_caster_geometry(self):
        m = load_model()
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        for side, x in [("left", 0.29), ("right", -0.29)]:
            wheel = m.geom(f"caster_tire_{x}").id
            pivot = m.body("caster_" + side).id
            # Cart -X is forward: rear pivots have positive X, with wheels trailing farther back.
            self.assertAlmostEqual(d.xpos[pivot, 0], 0.32)
            self.assertAlmostEqual(d.geom_xpos[wheel, 0], 0.345)
            self.assertAlmostEqual(d.geom_xpos[wheel, 2] - m.geom_size[wheel, 0], 0)
            self.assertEqual(m.body_jntnum[pivot], 0, "casters have no powered DOF")
            self.assertLess(d.geom_xpos[m.geom(f"drive_tire_{x}").id, 0], 0)
        self.assertEqual(m.nu, 10, "only the existing two five-joint arms have actuators")

    def test_straight_dolly_center_is_an_explicit_shot_setting(self):
        for center in [-0.3, 0.0, 0.4]:
            settings = parameters({"dollyOffset": center})
            midpoint = drive.cart_from_axle(drive.reference(settings, settings["duration"] / 2)[0])
            np.testing.assert_allclose(midpoint, [-1.6, center, -math.pi / 2], atol=1e-12)
            start = drive.cart_from_axle(drive.reference(settings, 0)[0])
            end = drive.cart_from_axle(drive.reference(settings, settings["duration"])[0])
            self.assertAlmostEqual(end[1] - start[1], drive.DIRECTION_SIGN * 0.1375 * settings["duration"])

    def test_both_global_directions_apply_to_prediction_wire_and_powered_front(self):
        for sign in (-1, 1):
            with self.subTest(sign=sign), patch.object(drive, "DIRECTION_SIGN", sign):
                trace = drive.simulate(DEFAULTS)
                report = drive.summary(trace)
                self.assertEqual(report["commandDirection"], "forward" if sign == 1 else "reverse")
                self.assertEqual(report["commandSign"], sign)
                wire = drive.uart_pair(sign * 0.04, sign * 0.04)
                self.assertTrue(all(r["wire"] == wire for r in trace["records"]))
                start = drive.reference(DEFAULTS, 0)[0]
                end = drive.reference(DEFAULTS, DEFAULTS["duration"])[0]
                toward_powered_front = np.array([math.cos(start[2]), math.sin(start[2])])
                self.assertGreater(sign * float((end[:2] - start[:2]) @ toward_powered_front), 0)

    def test_rendered_wheel_rotation_cancels_contact_velocity(self):
        m = load_model()
        before, after = mujoco.MjData(m), mujoco.MjData(m)
        h = 1e-6
        for left, right in [(0.1375, 0.1375), (0.1375, 0.20625), (-0.1375, -0.1375), (-0.1375, 0.1375)]:
            # Drive heading pi corresponds to an unchanged upper-cart yaw of zero.
            axle = np.array([-0.27, 0.0, math.pi])
            before.qpos[:3] = drive.cart_from_axle(axle)
            after.qpos[:3] = drive.cart_from_axle(drive.integrate(axle, left * h, right * h, 0.58))
            mujoco.mj_forward(m, before)
            mujoco.mj_forward(m, after)
            frame = drive.sample(drive.simulate(DEFAULTS), 1)
            for side, speed in [("left", left), ("right", right)]:
                body = m.body("drive_" + side).id
                velocity = (after.xpos[body] - before.xpos[body]) / h
                local_axis = np.array([frame["wheelAxisSign"], 0, 0])
                world_axis = before.xmat[body].reshape(3, 3) @ local_axis
                rotation_velocity = np.cross(world_axis * speed / 0.095, [0, 0, -0.095])
                np.testing.assert_allclose(velocity + rotation_velocity, 0, atol=1e-7)
            if left == right and left > 0:
                self.assertLess(after.qpos[0], before.qpos[0], "positive commands move toward powered front")

    def test_casters_align_with_their_pivot_velocity(self):
        # Analytic velocity at each rear swivel pivot, including reversing and an in-place turn.
        for left, right in [(0.1375, 0.1375), (0.1375, 0.20625), (-0.1375, -0.1375), (-0.1375, 0.1375)]:
            trace = drive.simulate(DEFAULTS)
            for record in trace["records"]:
                record["speeds"] = record["target"] = np.array([left, right])
            frame = drive.sample(trace, 1)
            linear, omega = (left + right) / 2, (right - left) / 0.58
            for index, dy in enumerate([0.2262, -0.2262]):
                velocity = np.array([linear - omega * dy, omega * -0.59])
                direction = np.array(
                    [math.cos(frame["casterYaw"][index]), math.sin(frame["casterYaw"][index])]
                )
                np.testing.assert_allclose(direction, velocity / np.linalg.norm(velocity), atol=1e-12)

    def test_quantized_commands_expose_old_path_failure(self):
        trace = drive.simulate({**DEFAULTS, **LEGACY_SETTINGS})
        report = drive.summary(trace)
        self.assertFalse(report["reproducesRequestedPath"])
        self.assertAlmostEqual(report["wheelTravel"][1], 0)
        self.assertGreater(report["maxPathError"], 0.7)
        self.assertLess(report["maxPathError"], 0.73)

    def test_known_command_pair_reconstructs_steady_arc(self):
        b = 0.58
        vl = 0.1375
        vr = 0.20625
        angle = math.radians(35)
        # Independent circle geometry from the two wheel speeds.
        radius = b * (vl + vr) / (2 * (vr - vl))
        duration = b * angle / (vr - vl)
        trace = drive.simulate(
            {**DEFAULTS, "radius": radius, "duration": duration, "driveProfile": "constant"}
        )
        report = drive.summary(trace)
        self.assertTrue(report["reproducesRequestedPath"])
        self.assertLess(report["maxPathError"], 1e-10)
        wire = drive.uart_pair(drive.DIRECTION_SIGN * 0.06, drive.DIRECTION_SIGN * 0.04)
        self.assertTrue(all(r["wire"] == wire for r in trace["records"]))
        self.assertAlmostEqual(report["baseTurnDegrees"], drive.FORWARD_SIGN * drive.DIRECTION_SIGN * 35)

    def test_assumed_response_and_braking_are_not_instantaneous(self):
        velocity, distance = drive.response(0, 0.1375, 4, 0.4)
        self.assertLess(distance, 0.55)
        self.assertAlmostEqual(distance, 0.1375 * (4 - 0.4 * (1 - math.exp(-10))))
        velocity, distance = drive.response(0.1375, 0, 20, 0.4)
        self.assertAlmostEqual(distance, 0.055)
        self.assertLess(velocity, 1e-20)

    def test_track_width_is_shared_by_geometry_and_odometry(self):
        m = load_model(track_width=0.7)
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        self.assertAlmostEqual(
            np.linalg.norm(d.xpos[m.body("drive_left").id] - d.xpos[m.body("drive_right").id]), 0.7
        )
        for invalid in [
            {"trackWidth": 0},
            {"responseTime": -1},
            {"brakeTime": float("nan")},
            {"driveProfile": []},
        ]:
            with self.assertRaises(ValueError):
                parameters(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
