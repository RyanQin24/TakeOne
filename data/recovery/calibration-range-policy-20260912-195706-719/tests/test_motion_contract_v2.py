"""Independent polynomial/encoder arithmetic and explicitly injected fault checks."""

import math
import unittest

import mujoco
import numpy as np
from scipy.interpolate import CubicSpline
from takeone.calibration import ArmMapping
from takeone.motion.measurements import criteria_blockers, pose_error
from takeone.planning.curve import JointCurve, dispatch_times, quintic

from tests import test_robot_motion
from tests.test_contracts import SerialDouble, mapping


class CurveContractTests(unittest.TestCase):
    def test_plan_identity_survives_real_javascript_json_roundtrip(self):
        import json
        import subprocess

        from takeone.motion.plan import digest

        document = {"positions": [0.0, -0.0, 1.0, 0.04, 1e-7, 1.2345678901234567], "passed": False}
        result = subprocess.run(
            [
                "node",
                "-e",
                "process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8'))))",
            ],
            input=json.dumps(document),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(digest(document), digest(json.loads(result.stdout)))
        self.assertNotEqual(digest({"flag": True}), digest({"flag": 1}))
        with self.assertRaisesRegex(ValueError, "exact browser JSON"):
            digest({"value": 2**53 + 1})

    def test_geometry_speed_bound_covers_independently_differenced_fk(self):
        from takeone.config import read_json
        from takeone.paths import CONFIGS
        from takeone.planning.envelope import EnvelopeScreen
        from takeone.planning.settings import parameters
        from takeone.simulation import drive
        from takeone.simulation.robot import load_model, pose_frame

        settings = parameters({"duration": 2})
        model = load_model()
        data = mujoco.MjData(model)
        zeros = (0,) * 10
        curve = JointCurve((0, 2), (quintic(zeros, zeros, zeros, (0.1,) * 10, zeros, zeros, 2),))
        trace = drive.simulate(settings)
        screen = EnvelopeScreen(model, curve, trace, read_json(CONFIGS / "scene.json"), settings)
        for t in (0.3, 0.8, 1.4):
            samples = []
            for stamp in (t, t + 1e-5):
                base = drive.sample(trace, stamp)
                pose_frame(model, data, (*base["cart"], *curve.at(stamp)), stamp, base)
                samples.append(data.geom_xpos[screen.geom_ids].copy())
            observed = np.linalg.norm(samples[1] - samples[0], axis=1) / 1e-5
            self.assertTrue(np.all(observed <= screen.velocity + 1e-8))

    def test_scipy_reference_matches_runtime_at_knots_midpoints_dispatch_and_endpoint(self):
        knots = np.linspace(0, 2, 9)
        values = np.array([[math.sin(t + j) / 5 for j in range(10)] for t in knots])
        spline = CubicSpline(knots, values)
        curve = JointCurve(
            tuple(knots),
            tuple(
                tuple(tuple(spline.c[3 - p, i]) if p < 4 else (0,) * 10 for p in range(6))
                for i in range(len(knots) - 1)
            ),
        )
        times = sorted(set([*knots, *((knots[:-1] + knots[1:]) / 2), *dispatch_times(2, 0.04)]))
        for derivative in range(4):
            np.testing.assert_allclose(
                [curve.at(t, derivative) for t in times], spline(times, derivative), rtol=0, atol=1e-12
            )
        revised = curve.with_transitions(1.3)
        self.assertTrue(revised.rest_boundaries())
        for derivative in range(4):
            # Piecewise jerk may jump at a join; q, v and a must not.
            for t in times[:-1] if derivative == 3 else times:
                np.testing.assert_allclose(
                    revised.at(t + 1.3, derivative), curve.at(t, derivative), rtol=0, atol=1e-11
                )
        self.assertAlmostEqual(revised.duration_s, 4.6)

    def test_known_stationary_root_is_included_in_analytic_extrema(self):
        # q=t-t^2, its maximum lies at .5, not at either endpoint.
        curve = JointCurve((0, 1), (((0,) * 10, (1,) * 10, (-1,) * 10, (0,) * 10, (0,) * 10, (0,) * 10),))
        self.assertEqual(curve.extrema(), ((0.0,) * 10, (0.25,) * 10))
        self.assertEqual(curve.extrema(1), ((-1.0,) * 10, (1.0,) * 10))
        self.assertFalse(curve.rest_boundaries())

    def test_no_unbounded_sampling_or_changed_dispatch_period(self):
        with self.assertRaises(ValueError):
            dispatch_times(120, 1e-10)

    def test_recovered_originals_support_nominal_arithmetic_without_motion_qualification(self):
        for role in ("phone", "light"):
            calibration = ArmMapping.load(role, require_motion=False)
            raw = calibration.to_raw((0,) * 5)
            q = calibration.from_raw(raw)
            self.assertLessEqual(max(abs(v) for v in q), math.radians(360 / 4095))
            self.assertEqual(calibration.raw_calibration["wrist_roll"]["id"], 6 if role == "phone" else 5)

    def test_signed_degree_conversion_round_trip_with_integer_truncation(self):
        calibration = mapping()
        for q in np.linspace(-0.9, 0.9, 101):
            values = (float(q),) * 5
            raw = calibration.to_raw(values)
            observed = calibration.from_raw(raw)
            self.assertLess(
                max(abs(a - b) for a, b in zip(values, observed)), math.radians(360 / 4095) + 1e-12
            )

    def test_quantization_cannot_cross_a_measured_operating_boundary(self):
        from dataclasses import replace

        calibration = replace(mapping(), signs=(1,) * 5, offsets_deg=(0,) * 5, safe_ranges_rad=((0, 1),) * 5)
        # Midpoint 2047.5 truncates to 2047: q=0 would encode outside [0, 1].
        with self.assertRaisesRegex(ValueError, "quantization leaves measured safe range"):
            calibration.to_raw((0,) * 5)

    def test_encoded_command_jerk_is_checked_separately_from_smooth_curve(self):
        from dataclasses import replace
        from types import SimpleNamespace

        from support.devices import software_limits
        from takeone.motion.limits import ArmTiming

        curve = JointCurve(
            (0, 1), (quintic((0,) * 10, (0,) * 10, (0,) * 10, (0.01,) * 10, (0,) * 10, (0,) * 10, 1),)
        )
        plan = SimpleNamespace(
            curve=curve,
            duration_s=1,
            phone=[curve.at(0)[:5], curve.at(1)[:5]],
            arm_at=lambda role, t: curve.at(t)[:5],
            dispatch_times=lambda period: dispatch_times(1, period),
        )
        limits = replace(software_limits(), jerk_rad_s3=(1,) * 5)
        limits.validate_plan(plan, "phone", ArmTiming.load())
        with self.assertRaisesRegex(ValueError, "encoded trajectory exceeds measured jerk"):
            limits.validate_plan(plan, "phone", ArmTiming.load(), mapping())

    def test_endpoint_measurement_uses_distance_and_wrapped_heading(self):
        distance, heading = pose_error((0.03, 0.04, -math.pi + 0.01), (0, 0, math.pi - 0.01))
        self.assertAlmostEqual(distance, 0.05)
        self.assertAlmostEqual(heading, 0.02)
        self.assertTrue(criteria_blockers(dict(schema="takeone.acceptance-criteria.v1", declared_at=None)))

    def test_real_uart_boundary_rejects_clip_or_round_before_any_write(self):
        from takeone.adapters.uart import MotorUART

        serial = SerialDouble()
        adapter = MotorUART("INJECTED", serial_factory=lambda: serial)
        adapter.connect()
        for command in (0.151, 0.044, math.nan):
            with self.assertRaises(ValueError):
                adapter.set_speed(command, 0.04)
        self.assertEqual(serial.sent, [])


class WholeCycleFaultTests(unittest.TestCase):
    def setUp(self):
        fixture = test_robot_motion.ArmControlTests()
        fixture.setUp()
        self.clock, self.arm, self.runner = fixture.clock, fixture.arm, fixture.runner

    def test_injected_read_plus_write_overrun_faults_even_when_individual_calls_fit(self):
        read, write = self.arm.read, self.arm.command

        def slow_read():
            self.clock.sleep(0.006)
            return read()

        def slow_write(q):
            self.clock.sleep(0.020)
            return write(q)

        self.arm.read, self.arm.command = slow_read, slow_write
        with self.assertRaisesRegex(RuntimeError, "complete read/write cycle"):
            self.runner.run(100.2)

    def test_retained_target_does_not_follow_injected_sag(self):
        self.runner.ready()
        original = self.runner.last_goal
        self.clock.sleep(0.04)
        self.arm.q = (0.01, 0, 0, 0, 0)
        self.runner.monitor_hold()
        self.assertEqual(self.runner.last_goal, original)
        self.assertFalse(any(e["phase"] == "command" for e in self.runner.events))
