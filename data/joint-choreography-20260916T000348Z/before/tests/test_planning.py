"""Motion intent, failure contracts and reproducible integration behavior."""

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from takeone.calibration import ArmMapping
from takeone.config import read_json
from takeone.paths import APP, CONFIGS
from takeone.planning.compiler import compile_shot
from takeone.planning.kinematics import ArmSolver, pointing_basis
from takeone.planning.settings import ShotSettings, parameters
from takeone.planning.targets import (
    ARMS,
    ArmRole,
    FixedWorldTarget,
    ToolTarget,
    tracking_programs,
)
from takeone.planning.trajectory import solve_trajectory
from takeone.planning.validation import evaluate_plan
from takeone.simulation import drive
from takeone.simulation.robot import load_model


class MotionIntentTests(unittest.TestCase):
    def test_settings_are_immutable_and_reject_unknown_or_invalid_values(self):
        raw = {"armTravel": 0.1}
        settings = ShotSettings.from_request(raw)
        raw["armTravel"] = 0.2
        self.assertEqual(settings.values["armTravel"], 0.1)
        with self.assertRaises(TypeError):
            settings.values["armTravel"] = 0.3
        with self.assertRaises(FrozenInstanceError):
            settings.values = {}
        for request in [
            {"lightTravel": -0.01},
            {"lightLift": float("nan")},
            {"duration": True},
            {"mode": "guess"},
            [],
        ]:
            with self.assertRaises(ValueError):
                ShotSettings.from_request(request)

    def test_camera_and_light_have_independent_sweep_lift(self):
        settings = parameters({"armTravel": 0.2, "armLift": 0.04, "lightTravel": 0.08, "lightLift": 0.01})
        programs = tracking_programs(settings)
        camera, light = programs[ArmRole.PHONE], programs[ArmRole.LIGHT]
        np.testing.assert_allclose(camera.offset(0), [-0.1, 0, 0])
        np.testing.assert_allclose(camera.offset(0.5), [0, 0, 0.04], atol=1e-14)
        np.testing.assert_allclose(camera.offset(1), [0.1, 0, 0], atol=1e-14)
        np.testing.assert_allclose(light.offset(0), [-0.04, 0, 0])
        np.testing.assert_allclose(light.offset(0.5), [0, 0, 0.01], atol=1e-14)

    def test_world_target_rotates_translation_with_cart_and_keeps_subject_aim(self):
        programs = tracking_programs(parameters({"armTravel": 0.0, "armLift": 0.0}))
        subject = np.array([4.0, 5.0, 1.6])
        target = programs[ArmRole.PHONE].at(0.5, np.array([1.0, 2.0, np.pi / 2]), subject)
        np.testing.assert_allclose(target.position_m, [1.0 - 0.38, 2.0 + 0.02, 1.5], atol=1e-12)
        np.testing.assert_allclose(target.look_at_m, subject)

    def test_fixed_world_target_has_no_cart_or_tracking_fallback(self):
        target = ToolTarget((1.0, 2.0, 1.5), (0.0, 0.0, 1.6))
        strategy = FixedWorldTarget(target)
        self.assertIs(strategy.at(0, np.zeros(3), np.zeros(3)), target)
        self.assertIs(strategy.at(1, np.ones(3) * 10, np.ones(3) * 10), target)
        with self.assertRaises(ValueError):
            ToolTarget((0, 0, 0), (0, 0, 0))

    def test_undefined_aim_and_invalid_phase_are_explicit_errors(self):
        with self.assertRaises(ValueError):
            pointing_basis(np.zeros(3), np.zeros(3))
        direction, right = pointing_basis(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        np.testing.assert_allclose(direction, [0.0, 0.0, 1.0])
        self.assertAlmostEqual(float(direction @ right), 0.0)
        self.assertAlmostEqual(float(np.linalg.norm(right)), 1.0)
        program = tracking_programs(parameters({}))[ArmRole.PHONE]
        for phase in [-0.1, 1.1, float("nan")]:
            with self.assertRaises(ValueError):
                program.offset(phase)

    def test_missing_strategy_or_bad_seed_is_not_substituted(self):
        settings = parameters({})
        model = load_model()
        motion = drive.simulate(settings)
        with self.assertRaises(ValueError):
            solve_trajectory(model, settings, motion, {})
        solver = ArmSolver(model)
        seed = np.zeros(13)
        seed[3] = 100.0
        with self.assertRaisesRegex(ValueError, "seed"):
            solver.solve(seed, ARMS[0], ToolTarget((0.0, 0.0, 1.5), (1.0, 1.0, 1.6)))

    def test_unconverged_solver_is_reported_with_its_best_bounded_candidate(self):
        model = load_model()
        solver = ArmSolver(model)
        seed = np.zeros(13)
        result = SimpleNamespace(x=np.array([0.1, 0.2, 0.3, 0.4, 0.5]), success=False, nfev=120)
        with patch("takeone.planning.kinematics.least_squares", return_value=result):
            solved = solver.solve(seed, ARMS[0], ToolTarget((0.0, 0.0, 1.5), (1.0, 1.0, 1.6)))
        self.assertFalse(solved.converged)
        self.assertGreaterEqual(solved.evaluations, 4 * result.nfev)
        self.assertTrue(np.isfinite(solved.joints_rad).all())
        self.assertTrue(np.all(np.asarray(solved.joints_rad) >= solver.lower[ARMS[0].qpos_slice]))
        self.assertTrue(np.all(np.asarray(solved.joints_rad) <= solver.upper[ARMS[0].qpos_slice]))
        np.testing.assert_array_equal(seed, np.zeros(13))

    def test_application_has_no_compatibility_shims(self):
        for filename in ["engine.py", "drive.py", "bootstrap.py", "build_rehearsal_model.py"]:
            self.assertFalse((APP / filename).exists())
        for filename in ["server.py", "export_models.mjs", "audit_model.py", "verify_drive.py"]:
            source = (APP / filename).read_text(encoding="utf-8")
            self.assertNotIn("from engine import", source)
            self.assertNotIn("import bootstrap", source)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = parameters({})
        cls.model = load_model()
        cls.motion = drive.simulate(cls.settings)
        cls.programs = tracking_programs(cls.settings)
        cls.trajectory = solve_trajectory(cls.model, cls.settings, cls.motion, cls.programs)
        cls.mappings = {role: ArmMapping.load(role.value, require_motion=False) for role in cls.programs}
        cls.dispatch_period_s = read_json(CONFIGS / "arm-execution.json")["period_s"]

    def test_dense_frame_aim_validation_finds_between_keyframe_error(self):
        q = self.trajectory.q.copy()
        try:
            self.trajectory.q[1, 3] += 0.2  # index 1 is not an IK keyframe (stride 4).
            evaluation = evaluate_plan(
                self.model,
                self.settings,
                self.trajectory,
                self.programs,
                drive.summary(self.motion),
                mappings=self.mappings,
                dispatch_period_s=self.dispatch_period_s,
            )
            self.assertFalse(next(c["passed"] for c in evaluation.checks if c["name"] == "Aim at actor"))
        finally:
            self.trajectory.q[:] = q

    def test_light_motion_change_preserves_phone_intent_and_cart_reference(self):
        modified = parameters({"lightTravel": 0.0, "lightLift": 0.0})
        modified_programs = tracking_programs(modified)
        for phase in np.linspace(0.0, 1.0, 9):
            np.testing.assert_allclose(
                modified_programs[ArmRole.PHONE].offset(phase),
                self.programs[ArmRole.PHONE].offset(phase),
            )
        self.assertGreater(
            float(
                np.max(
                    abs(
                        modified_programs[ArmRole.LIGHT].offset(0.0)
                        - self.programs[ArmRole.LIGHT].offset(0.0)
                    )
                )
            ),
            0.01,
        )
        modified_motion = drive.simulate(modified)
        np.testing.assert_allclose(
            [record["axle"] for record in modified_motion["records"]],
            [record["axle"] for record in self.motion["records"]],
        )

    def test_plan_has_explicit_motion_outline_and_successful_solves(self):
        shot = compile_shot()
        self.assertEqual(shot["solver"]["solves"], 2 * shot["coordination"]["arm_constraint_samples"])
        self.assertEqual(shot["solver"]["failed"], 0)
        self.assertEqual([entry["role"] for entry in shot["motionOutline"]], ["phone", "light"])
        self.assertEqual(shot["settings"]["lightTravel"], 0.12)
        self.assertTrue(shot["planValid"])
        self.assertTrue(shot["shotFidelityPassed"])
        self.assertTrue(shot["playable"])
        self.assertFalse(shot["hardwareReady"])
        self.assertIn("packages/takeone/planning/targets.py", shot["provenance"])
